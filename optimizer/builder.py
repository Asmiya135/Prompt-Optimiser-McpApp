"""Turn the intake answers into the leanest prompt that covers every rule.

Each section is added only when a rule or technique needs it. The prompt ends
with the requirements the checker later verifies (the output contract).
"""

from __future__ import annotations

import re
from typing import List, Optional

from optimizer import techniques as T
from optimizer import vocab
from optimizer.adapters import get_adapter
from optimizer.models import MATERIAL_INPUTS, BuiltPrompt, Contract, IntakeAnswers
from optimizer.rules import analyze, fix_typos, parse_length
from optimizer.tokens import TokenCounter, count

UNSURE_LINE = ("If you are not sure of a fact, figure, quote or recent event, say \"I'm not sure\" "
               "instead of guessing. Do not invent sources.")
GROUNDING_LINE = "Use only the material. If it does not contain the answer, say so."
LEAN_LINE = "Answer directly, with no introduction and no closing summary."
REASONING_LINE = "Work it out carefully before answering; show only the key steps, then the answer."


def _split_list(text: str) -> List[str]:
    return [t.strip() for t in re.split(r"[,;\n]", text or "") if t.strip()]


def _standing_rules(text: str) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+|\n", text or "")
    return [s.strip() for s in sentences
            if any(w in s.lower() for w in vocab.STANDING_RULE_WORDS) and s.strip()]


def build_prompt(answers: IntakeAnswers, counter: Optional[TokenCounter] = None) -> BuiltPrompt:
    analysis = analyze(answers)
    adapter = get_adapter(answers.target_model)
    output_type = analysis.task_type or "other"
    inputs = analysis.prefill.get("inputs") or []
    audience = analysis.prefill.get("audience") or ""
    length = analysis.prefill.get("length") or ""
    tone = analysis.prefill.get("tone") or ""
    techs = analysis.techniques
    warnings: List[str] = []
    assumptions = list(analysis.assumptions)

    task_text, _ = fix_typos(answers.draft.strip())

    # System-style rules: pulled out of the draft and notes and placed first.
    rules = _standing_rules(task_text + "\n" + answers.notes) if T.SYSTEM_RULES in techs else []
    if rules:
        for r in rules:
            task_text = task_text.replace(r, "").strip()

    # One thing per prompt: number the asks so none is skipped.
    if analysis.sub_tasks:
        numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(analysis.sub_tasks, 1))
        task_text = f"Do each of these, numbered to match:\n{numbered}"
    if output_type == "other" and answers.output_other:
        task_text += f"\nWanted output: {answers.output_other.strip()}"

    lines_task: List[str] = []
    if T.ROLE in techs:
        role = vocab.ROLE_FOR_TYPE.get(output_type, vocab.ROLE_FOR_TYPE["other"])
        lines_task.append(f"You are {role}" + (f", writing for: {audience}." if audience else "."))
    if rules:
        lines_task.append("Rules: " + " ".join(rules))
    lines_task.append(task_text)

    # Context.
    ctx: List[str] = []
    if audience and T.ROLE not in techs:
        ctx.append(f"Audience: {audience}.")
    if answers.notes:
        notes = answers.notes
        for r in rules:
            notes = notes.replace(r, "")
        if notes.strip():
            ctx.append(notes.strip())
    if answers.scope:
        ctx.append(f"Scope: {answers.scope.strip()}")
    if answers.input_other:
        ctx.append(f"I also have: {answers.input_other.strip()}")

    # Material and examples (grounding / few-shot).
    material, examples = "", ""
    if answers.material.strip():
        only_examples = "examples" in inputs and not (set(inputs) & MATERIAL_INPUTS)
        if only_examples:
            examples = answers.material.strip()
        else:
            material = answers.material.strip()
            if "examples" in inputs:
                warnings.append("Your material and examples are in one box, so they are sent together.")

    # Output format, length and tone.
    out: List[str] = []
    fmt = vocab.FORMAT_INSTRUCTION.get(output_type, "")
    if fmt:
        out.append(fmt)
    eff_length = length or ("" if answers.no_constraints else vocab.DEFAULT_LENGTH.get(output_type, ""))
    if eff_length:
        out.append(f"Length: {eff_length}.")
    if tone:
        out.append(f"Tone: {tone}.")
    if output_type not in ("code", "story_creative", "written_piece"):
        out.append(LEAN_LINE)

    # Constraints.
    must = _split_list(answers.must_include)
    avoid = _split_list(answers.avoid)
    cons: List[str] = []
    if must:
        cons.append("Must include: " + ", ".join(must) + ".")
    if avoid:
        cons.append("Avoid: " + ", ".join(avoid) + ".")
    if T.GROUNDING in techs and (material or "file" in inputs or "links" in inputs):
        cons.append(GROUNDING_LINE)
    if analysis.risk_flags:
        cons.append(UNSURE_LINE)

    reasoning = REASONING_LINE if T.STEP_BY_STEP in techs else ""

    sections = [
        ("task", "\n".join(lines_task)),
        ("context", "\n".join(ctx)),
        ("material", material),
        ("examples", examples),
        ("output", "\n".join(out) if len(out) > 1 else (out[0] if out else "")),
        ("constraints", "\n".join(cons)),
        ("reasoning", reasoning),
    ]
    prompt = adapter.render(sections)

    # Output contract: what check_output verifies later.
    parsed = parse_length(eff_length)
    contract = Contract(
        output_type=output_type,
        format=vocab.FORMAT_FOR_TYPE.get(output_type, ""),
        min_words=parsed["min_words"],
        max_words=parsed["max_words"],
        items=parsed["items"],
        items_max=bool(parsed.get("items_max")),
        must_include=must,
        avoid=avoid,
        parts=max(1, len(analysis.sub_tasks)),
        unsure_rule=bool(analysis.risk_flags),
    )

    before, method = count(answers.draft, counter)
    after, _ = count(prompt, counter)
    if analysis.conflicts:
        warnings.extend(analysis.conflicts)
    # Judge the draft on its own (not the form answers): could it have been sent as it was?
    if analyze(IntakeAnswers(draft=answers.draft, target_model=answers.target_model)).ready:
        warnings.append("Your draft already covers the essentials. Sending it as it is may cost fewer tokens.")

    return BuiltPrompt(
        prompt=prompt,
        system=" ".join(rules),
        contract=contract,
        techniques=techs,
        assumptions=assumptions,
        warnings=warnings,
        tokens_before=before,
        tokens_after=after,
        token_method=method,
    )
