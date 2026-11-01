"""Pick the prompting technique from the intake answers.

Rules from the spec's "Choosing the technique" table. Techniques combine when
several signals fire; zero-shot is used only when nothing else applies, so the
prompt carries no technique it does not need.
"""

from __future__ import annotations

from typing import List

from optimizer import vocab
from optimizer.models import MATERIAL_INPUTS, IntakeAnswers

ZERO_SHOT = "zero-shot"
FEW_SHOT = "few-shot"
STEP_BY_STEP = "step-by-step"
ROLE = "role"
SYSTEM_RULES = "system-style rules"
CREATIVE = "creative"
GROUNDING = "grounding"

DESCRIPTIONS = {
    ZERO_SHOT: "Clear instruction, format and length only.",
    FEW_SHOT: "Your own examples, marked as examples, set the style.",
    STEP_BY_STEP: "The model reasons before answering and checks itself.",
    ROLE: "One line says who answers and for whom.",
    SYSTEM_RULES: "Your standing rules go before the task.",
    CREATIVE: "Open constraints; several options to choose from.",
    GROUNDING: "Answer only from your material; say when it isn't there.",
}


def _contains(text: str, needles: List[str]) -> bool:
    low = f" {text.lower()} "
    return any(n in low for n in needles)


def choose_techniques(answers: IntakeAnswers, output_type: str, inputs: List[str],
                      sub_tasks: List[str]) -> List[str]:
    text = " ".join([answers.draft, answers.notes, answers.scope])
    chosen: List[str] = []

    if _contains(text, vocab.STANDING_RULE_WORDS):
        chosen.append(SYSTEM_RULES)
    if answers.audience or _contains(answers.draft, ["as a ", "act as", "you are a", "pretend you"]):
        chosen.append(ROLE)
    if "examples" in inputs or _contains(text, vocab.STYLE_EXAMPLE_WORDS):
        chosen.append(FEW_SHOT)
    if set(inputs) & MATERIAL_INPUTS:
        chosen.append(GROUNDING)
    if output_type == "analysis_decision" or _contains(text, vocab.REASONING_WORDS):
        chosen.append(STEP_BY_STEP)
    if output_type in ("story_creative", "ideas_list"):
        chosen.append(CREATIVE)

    return chosen or [ZERO_SHOT]
