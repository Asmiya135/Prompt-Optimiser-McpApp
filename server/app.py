"""The MCP server: tools, the intake widget (MCP App), auth, and the HTTP app.

Run locally:   AUTH_MODE=none python -m server.app
On Cloud Run:  the Dockerfile runs the same command; PORT is set by Cloud Run.

Design rules:
- Stateless: no session or answer is stored on the server, so Cloud Run can
  scale to zero between requests and any instance can serve any call.
- Every tool returns plain text too, so hosts that cannot show the form
  still get the same questions as numbered text.
- All tools are read-only (they change nothing), so Gemini Enterprise can run
  them without a confirmation prompt.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import anyio
import uvicorn
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp.server.apps import Apps, client_supports_apps
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from optimizer import (
    INPUT_TYPES,
    OUTPUT_TYPES,
    Contract,
    IntakeAnswers,
    analyze,
    build_prompt as build,
    check_output as check,
    context_health as health,
    make_handoff as handoff,
)
from optimizer import techniques as T
from optimizer.tokens import TokenCounter
from server.config import Settings

log = logging.getLogger("prompt-optimizer")

WIDGET_URI = "ui://prompt-optimizer/intake.html"
WIDGET_DIR = Path(__file__).parent / "widget"
VENDOR_JS = WIDGET_DIR / "vendor" / "ext-apps-app-with-deps.js"
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

INSTRUCTIONS = (
    "Prompt optimizer. When the user starts a NEW piece of work (writing, code, an explanation, a summary, "
    "a comparison, ideas, a plan or an analysis), call start_intake ONCE with their message as `draft` before "
    "answering. Do not call it again for small follow-ups on the same task. If the user submits the form, the "
    "optimized prompt arrives as their next message: answer that message directly. If no form is visible to "
    "the user, ask the numbered questions from start_intake in chat, then call build_prompt with the answers "
    "and answer the optimized prompt it returns."
)


# ---------------------------------------------------------------- widget

def load_widget_html() -> str:
    """intake.html with the MCP Apps SDK and the option lists inlined (one self-contained file)."""
    html = (WIDGET_DIR / "intake.html").read_text(encoding="utf-8")
    bundle = VENDOR_JS.read_text(encoding="utf-8").replace("</script", "<\\/script")
    options = json.dumps({"output_types": OUTPUT_TYPES, "input_types": INPUT_TYPES})
    return html.replace("/*__EXT_APPS_BUNDLE__*/", bundle).replace("/*__OPTIONS__*/null", options)


# ---------------------------------------------------------------- helpers

def _text(text: str, structured: Optional[Dict[str, Any]] = None, is_error: bool = False) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)],
                          structured_content=structured, is_error=is_error)


def _questions_text(draft: str, prefill: Dict[str, Any], questions: List[str], conflicts: List[str]) -> str:
    guess_out = OUTPUT_TYPES.get(prefill.get("output_type") or "", "not sure")
    guess_in = ", ".join(INPUT_TYPES[i] for i in prefill.get("inputs") or []) or "not sure"
    lines = [
        "Ask these 3 questions in one message:",
        f"1. What output do you expect? Options: {', '.join(OUTPUT_TYPES.values())}. (My guess: {guess_out})",
        f"2. What input do you have? Pick any: {', '.join(INPUT_TYPES.values())}. (My guess: {guess_in})",
        "3. Any constraints? Length, tone, audience, must include or avoid, scope. Or say 'no constraints'.",
    ]
    extra = [q for q in questions if not q.startswith("What output")]  # question 1 already covers it
    if extra:
        lines.append("Also ask: " + " ".join(extra))
    if conflicts:
        lines.append("Clarify: " + " ".join(conflicts))
    lines.append("Then call build_prompt with their answers and answer the optimized prompt it returns.")
    return "\n".join(lines)


# ---------------------------------------------------------------- server

def create_server(settings: Settings, counter: Optional[TokenCounter] = None) -> MCPServer:
    apps = Apps()

    @apps.tool(
        resource_uri=WIDGET_URI,
        name="start_intake",
        title="Optimize my prompt",
        description="Call once at the start of a new task, before answering. Shows the user a 3-question "
                    "form prefilled from their message. draft = the user's message, copied exactly.",
        annotations=READ_ONLY,
    )
    def start_intake(draft: str, ctx: Context) -> CallToolResult:
        a = analyze(IntakeAnswers(draft=draft, target_model=settings.target_model))
        structured = {
            "draft": draft,
            "prefill": a.prefill,
            "checks": [c.__dict__ for c in a.checks],
            "questions": a.questions,
            "conflicts": a.conflicts,
            "assumptions": a.assumptions,
            "risk_flags": a.risk_flags,
            "ready": a.ready,
            "target_model": settings.target_model,
        }
        questions = _questions_text(draft, a.prefill, a.questions, a.conflicts)
        if client_supports_apps(ctx) or settings.assume_ui:
            text = ("The intake form is now shown to the user. Do not answer yet; wait for their next message, "
                    "which will be the optimized prompt. Only if they say they cannot see a form:\n" + questions)
        else:
            text = questions
        if a.ready:
            text += "\nNote: the draft already covers the essentials; the user may skip the form."
        return _text(text, structured)

    apps.add_html_resource(
        WIDGET_URI,
        load_widget_html(),
        name="intake-form",
        title="Prompt intake form",
        description="Three questions plus the draft prompt.",
        prefers_border=True,
    )

    mcp = MCPServer(
        "prompt-optimizer",
        title="Prompt Optimizer",
        instructions=INSTRUCTIONS,
        version="0.1.0",
        extensions=[apps],
        **_auth_kwargs(settings),
    )

    @mcp.tool(
        name="build_prompt",
        title="Build the optimized prompt",
        description="Build the optimized prompt from the draft and intake answers, then answer it. "
                    "output_type: " + "|".join(OUTPUT_TYPES) + ". inputs: list of " + "|".join(INPUT_TYPES) + ".",
        annotations=READ_ONLY,
    )
    async def build_prompt(
        draft: str,
        output_type: str = "",
        output_other: str = "",
        inputs: Optional[List[str]] = None,
        input_other: str = "",
        material: str = "",
        length: str = "",
        tone: str = "",
        audience: str = "",
        must_include: str = "",
        avoid: str = "",
        scope: str = "",
        notes: str = "",
        no_constraints: bool = False,
        target_model: str = "",
    ) -> CallToolResult:
        if output_type and output_type not in OUTPUT_TYPES:
            return _text(f"Unknown output_type {output_type!r}. Use one of: {', '.join(OUTPUT_TYPES)}.",
                         is_error=True)
        answers = IntakeAnswers(
            draft=draft, output_type=output_type, output_other=output_other,
            inputs=[i for i in (inputs or []) if i in INPUT_TYPES], input_other=input_other,
            material=material, length=length, tone=tone, audience=audience, must_include=must_include,
            avoid=avoid, scope=scope, notes=notes, no_constraints=no_constraints,
            target_model=target_model or settings.target_model,
        )
        built = await anyio.to_thread.run_sync(lambda: build(answers, counter))
        structured = built.to_dict()
        structured["technique_notes"] = {t: T.DESCRIPTIONS.get(t, "") for t in built.techniques}
        text = (
            "Optimized prompt. Answer it now as if the user had sent it; do not repeat it back.\n\n"
            f"{built.prompt}\n\n"
            f"(Output contract for check_output: {built.contract.to_string()})"
        )
        return _text(text, structured)

    @mcp.tool(
        name="check_output",
        title="Check an answer against its contract",
        description="Only when the user asks: check a reply against the contract string from build_prompt. "
                    "Returns pass/fail per item and one follow-up that fixes all failures.",
        annotations=READ_ONLY,
    )
    def check_output(contract: str, reply: str) -> CallToolResult:
        result = check(Contract.from_string(contract), reply)
        lines = [("PASS" if i["passed"] else "FAIL") + f" {i['check']}: {i['detail']}" for i in result.items]
        if result.follow_up:
            lines.append(f"Suggested follow-up: {result.follow_up}")
        return _text("\n".join(lines) or "Nothing to check.", result.to_dict())

    @mcp.tool(
        name="context_health",
        title="Check the conversation's health",
        description="Rate how polluted this chat is. Pass short lines, not the transcript: turns so far, "
                    "one line per user correction, one per unresolved contradiction.",
        annotations=READ_ONLY,
    )
    def context_health(turn_count: int, corrections: Optional[List[str]] = None,
                       contradictions: Optional[List[str]] = None) -> CallToolResult:
        r = health(turn_count, corrections or [], contradictions or [])
        text = f"Health: {r['level']}. " + " ".join(r["reasons"]) + f" {r['recommendation']}"
        return _text(text.strip(), r)

    @mcp.tool(
        name="make_handoff",
        title="Make a clean-restart handoff",
        description="Write a handoff prompt for a fresh chat. Include only facts and decisions the user "
                    "confirmed, never corrected or disputed ones.",
        annotations=READ_ONLY,
    )
    def make_handoff(open_task: str, confirmed_facts: Optional[List[str]] = None,
                     decisions: Optional[List[str]] = None,
                     constraints: Optional[List[str]] = None) -> CallToolResult:
        prompt = handoff(open_task, confirmed_facts or [], decisions or [], constraints or [])
        return _text("Copy this into a new chat:\n\n" + prompt, {"handoff_prompt": prompt})

    @mcp.resource("playbook://techniques", name="techniques", mime_type="text/markdown",
                  description="Which prompting technique the optimizer picks, and when.")
    def techniques_playbook() -> str:
        rows = "\n".join(f"- **{k}**: {v}" for k, v in T.DESCRIPTIONS.items())
        return "# Techniques\n\n" + rows

    @mcp.resource("playbook://models/{name}", mime_type="text/markdown",
                  description="Prompt layout used for a model family (gemini, claude, generic).")
    def model_playbook(name: str) -> str:
        notes = {
            "gemini": "Short labelled sections (Task, Context, Material, Output, Constraints); material between "
                      "<<< and >>> markers. Check Google's Gemini prompt design guide for current advice.",
            "claude": "XML tags per section (<task>, <context>, <material>, <output_format>). Check Anthropic's "
                      "prompt engineering docs for current advice.",
        }
        return f"# {name}\n\n" + notes.get(name.lower(), "Plain labelled sections.")

    @mcp.prompt(name="optimize", title="Optimize my next request",
                description="Start the intake form for a request.")
    def optimize(draft: str) -> str:
        return f"Call start_intake with this draft, then follow its instructions:\n\n{draft}"

    _slim_schemas(mcp)

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(_: Request) -> Response:
        return JSONResponse({"status": "ok"})

    return mcp


def _slim(node: Any) -> Any:
    """Drop schema keys the model does not need. Hosts send every enabled tool's
    definition to the model on every turn, so each saved token is saved per turn."""
    if isinstance(node, dict):
        return {k: _slim(v) for k, v in node.items()
                if k != "title" and not (k == "default" and v in ("", None, False))}
    if isinstance(node, list):
        return [_slim(v) for v in node]
    return node


def _slim_schemas(mcp: MCPServer) -> None:
    # Uses the SDK's tool manager (internal API in mcp 2.3.0; pinned in requirements.txt).
    # If a future SDK changes it, the schemas are simply left as they are.
    try:
        for tool in mcp._tool_manager.list_tools():  # noqa: SLF001
            tool.parameters = _slim(tool.parameters)
    except AttributeError:
        log.warning("Could not slim tool schemas; leaving them unchanged.")


def _auth_kwargs(settings: Settings) -> Dict[str, Any]:
    if settings.auth_mode == "none":
        return {}
    from server.auth import GoogleAccessTokenVerifier

    verifier = GoogleAccessTokenVerifier(settings.oauth_client_id, settings.allowed_email_domains,
                                         settings.allowed_emails)
    auth = AuthSettings(
        issuer_url="https://accounts.google.com",
        resource_server_url=(settings.public_url + "/mcp") if settings.public_url else None,
        required_scopes=None,
    )
    return {"auth": auth, "token_verifier": verifier}


def _token_counter(settings: Settings) -> Optional[TokenCounter]:
    if not settings.gemini_api_key:
        return None
    from llm.gemini import GeminiProvider

    provider = GeminiProvider(model=settings.gemini_model, api_key=settings.gemini_api_key, max_retries=0)
    return provider.count_tokens


def create_app(settings: Optional[Settings] = None):
    settings = settings or Settings()
    settings.validate()
    mcp = create_server(settings, _token_counter(settings))
    # Stateless + plain JSON responses: no session to keep, so Cloud Run can scale to zero.
    return mcp.streamable_http_app(stateless_http=True, json_response=True, host="0.0.0.0")


def main() -> None:
    settings = Settings()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(settings), host="0.0.0.0", port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
