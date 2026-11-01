"""Demo benchmark: tokens to reach an acceptable answer, with and without the tool.

For each task in bench/tasks.json, two conversations run on the same model:

  A. Without the tool: send the raw prompt. While the reply fails the user's
     acceptance criteria, send a follow-up (up to --max-turns turns in total).
  B. With the tool: build the optimized prompt from the intake answers, send
     it, then the same follow-up loop.

Every token the provider reports is counted, including the re-sent chat
history on each turn and hidden thinking tokens. Run B also counts the tool's
own overhead in the host: the tool definitions the host sends to the model on
every turn, plus the start_intake call and its result. Both runs get the same
follow-up wording for the same failure, so neither side is judged loosely.

Usage:
  export GEMINI_API_KEY=...            # from Google AI Studio
  python -m bench.run_benchmark --provider gemini --model gemini-2.5-flash
  python -m bench.run_benchmark --provider fake   # dry run; numbers are NOT real

Output goes to bench/results/<timestamp>/: turns.csv, summary.csv, summary.md,
transcripts.json, and two charts (see bench/report.py).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from llm import get_provider
from optimizer import Contract, IntakeAnswers, build_prompt, check_output

HERE = Path(__file__).resolve().parent


@dataclass
class Turn:
    n: int
    sent: str
    reply: str
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    passed: bool
    failures: List[str]

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens + self.thinking_tokens


@dataclass
class Run:
    task: str
    arm: str                  # "without_tool" | "with_tool"
    turns: List[Turn] = field(default_factory=list)
    overhead_tokens: int = 0  # tool definitions + intake call (with_tool only)
    passed: bool = False

    @property
    def model_tokens(self) -> int:
        return sum(t.total for t in self.turns)

    @property
    def total_tokens(self) -> int:
        return self.model_tokens + self.overhead_tokens


def follow_up_for(result, custom: Dict[str, str]) -> str:
    """One message fixing every failure; task-specific wording where given."""
    fixes = []
    for item in result.items:
        if not item["passed"]:
            text = custom.get(item["check"]) or item.get("fix") or ""
            if text and text not in fixes:
                fixes.append(text)
    return " ".join(fixes) + " Keep everything else the same."


def converse(provider, first_message: str, acceptance: Contract, custom: Dict[str, str],
             max_turns: int, delay: float, run: Run) -> None:
    chat = provider.chat()
    message = first_message
    for n in range(1, max_turns + 1):
        reply = chat.send(message)
        result = check_output(acceptance, reply.text)
        failures = [i["check"] for i in result.items if not i["passed"]]
        run.turns.append(Turn(n, message, reply.text, reply.usage.input_tokens, reply.usage.output_tokens,
                              reply.usage.thinking_tokens, result.passed, failures))
        if result.passed:
            run.passed = True
            return
        message = follow_up_for(result, custom)
        time.sleep(delay)


async def tool_overhead_texts(enabled: List[str]) -> Dict[str, str]:
    """The tool definitions and start_intake round trip, exactly as the server produces them."""
    os.environ.setdefault("AUTH_MODE", "none")
    from mcp import Client
    from server.app import create_server
    from server.config import Settings

    server = create_server(Settings(auth_mode="none", gemini_api_key=""))
    async with Client(server) as client:
        tools = await client.list_tools()
        defs = json.dumps([{"name": t.name, "description": t.description, "parameters": t.input_schema}
                           for t in tools.tools if t.name in enabled])
    return {"tool_definitions": defs}


async def intake_texts(draft: str) -> Dict[str, str]:
    from mcp import Client
    from server.app import create_server
    from server.config import Settings

    server = create_server(Settings(auth_mode="none", gemini_api_key=""))
    async with Client(server) as client:
        res = await client.call_tool("start_intake", {"draft": draft})
    return {"call": json.dumps({"name": "start_intake", "args": {"draft": draft}}),
            "result": res.content[0].text}


def load_tasks(only: Optional[List[str]]) -> List[dict]:
    data = json.loads((HERE / "tasks.json").read_text(encoding="utf-8"))
    tasks = []
    for t in data["tasks"]:
        if only and t["id"] not in only:
            continue
        material = t.get("material", "")
        t["raw_prompt"] = t["raw_prompt"].replace("{material}", material)
        t["intake"] = {k: (v.replace("{material}", material) if isinstance(v, str) else v)
                       for k, v in t["intake"].items()}
        tasks.append(t)
    return tasks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", default="gemini", choices=["gemini", "fake"])
    ap.add_argument("--model", default=None, help="e.g. gemini-2.5-flash (default: GEMINI_MODEL or gemini-2.5-flash)")
    ap.add_argument("--tasks", nargs="*", help="task ids to run (default: all)")
    ap.add_argument("--repeats", type=int, default=1, help="runs per task and arm; averages reduce noise")
    ap.add_argument("--max-turns", type=int, default=4)
    ap.add_argument("--delay", type=float, default=4.0, help="seconds between calls (free-tier rate limits)")
    ap.add_argument("--thinking-budget", type=int, default=None,
                    help="Gemini thinking token budget; leave unset for the model default")
    ap.add_argument("--enabled-tools", default="start_intake,build_prompt",
                    help="tools enabled as actions in the host; their definitions are counted on every turn")
    ap.add_argument("--no-turn-overhead", action="store_true",
                    help="do not count tool definitions on every with-tool turn (counted by default)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    kwargs = {"model": args.model}
    if args.provider == "gemini":
        kwargs["thinking_budget"] = args.thinking_budget
    provider = get_provider(args.provider, **kwargs)
    if args.provider == "fake":
        args.delay = 0.0
        print("DRY RUN with the fake provider: the numbers below are NOT measurements.")

    out = Path(args.out or HERE / "results" / datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)

    overhead_texts = asyncio.run(tool_overhead_texts(args.enabled_tools.split(",")))
    defs_tokens = provider.count_tokens(overhead_texts["tool_definitions"])
    runs: List[Run] = []

    for task in load_tasks(args.tasks):
        acceptance = Contract.from_string(task["acceptance"])
        custom = task.get("followups", {})
        answers = IntakeAnswers(draft=task["raw_prompt"], target_model="gemini", **task["intake"])
        built = build_prompt(answers, provider.count_tokens)
        intake = asyncio.run(intake_texts(task["raw_prompt"]))
        # The intake turn: the model reads the raw prompt, calls start_intake and reads its result.
        intake_tokens = (provider.count_tokens(task["raw_prompt"]) + provider.count_tokens(intake["call"])
                         + provider.count_tokens(intake["result"]))

        for rep in range(args.repeats):
            a = Run(task["id"], "without_tool")
            converse(provider, task["raw_prompt"], acceptance, custom, args.max_turns, args.delay, a)
            runs.append(a)
            time.sleep(args.delay)

            b = Run(task["id"], "with_tool")
            converse(provider, built.prompt, acceptance, custom, args.max_turns, args.delay, b)
            # Overhead in the host: definitions ride along on the intake turn and every answer turn.
            per_turn = 0 if args.no_turn_overhead else defs_tokens
            b.overhead_tokens = intake_tokens + per_turn * (len(b.turns) + 1)
            runs.append(b)
            print(f"{task['id']:>8} rep {rep + 1}: without {a.total_tokens:>6} tok, {len(a.turns)} turns, "
                  f"{'pass' if a.passed else 'FAIL'} | with {b.total_tokens:>6} tok "
                  f"(overhead {b.overhead_tokens}), {len(b.turns)} turns, {'pass' if b.passed else 'FAIL'}")
            time.sleep(args.delay)

    write_outputs(out, runs, provider.model, args)
    from bench.report import make_report
    make_report(out, dry_run=args.provider == "fake")
    print(f"\nResults in {out}")


def write_outputs(out: Path, runs: List[Run], model: str, args) -> None:
    with open(out / "turns.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["task", "arm", "turn", "input_tokens", "output_tokens", "thinking_tokens", "turn_total",
                    "passed", "failures"])
        for r in runs:
            for t in r.turns:
                w.writerow([r.task, r.arm, t.n, t.input_tokens, t.output_tokens, t.thinking_tokens, t.total,
                            t.passed, "; ".join(t.failures)])
    with open(out / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["task", "arm", "turns", "passed", "model_tokens", "overhead_tokens", "total_tokens"])
        for r in runs:
            w.writerow([r.task, r.arm, len(r.turns), r.passed, r.model_tokens, r.overhead_tokens, r.total_tokens])
    meta = {"model": model, "provider": args.provider, "max_turns": args.max_turns, "repeats": args.repeats,
            "thinking_budget": args.thinking_budget, "dry_run": args.provider == "fake",
            "run_at": datetime.now().isoformat(timespec="seconds")}
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    transcripts = [{"task": r.task, "arm": r.arm, "turns": [{"sent": t.sent, "reply": t.reply,
                                                              "failures": t.failures} for t in r.turns]}
                   for r in runs]
    (out / "transcripts.json").write_text(json.dumps(transcripts, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
