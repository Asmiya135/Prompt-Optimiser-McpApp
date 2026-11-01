"""Model-agnostic prompt optimizer core.

Nothing in this package calls a model or knows about MCP. Every decision is a
deterministic rule, so the same inputs always give the same prompt. That keeps
the optimizer itself at zero token cost.
"""

from optimizer.models import (
    INPUT_TYPES,
    OUTPUT_TYPES,
    Analysis,
    BuiltPrompt,
    Check,
    CheckResult,
    Contract,
    IntakeAnswers,
)
from optimizer.rules import analyze, prefill_from_draft
from optimizer.builder import build_prompt
from optimizer.checker import check_output
from optimizer.context import context_health, make_handoff

__all__ = [
    "INPUT_TYPES",
    "OUTPUT_TYPES",
    "Analysis",
    "BuiltPrompt",
    "Check",
    "CheckResult",
    "Contract",
    "IntakeAnswers",
    "analyze",
    "prefill_from_draft",
    "build_prompt",
    "check_output",
    "context_health",
    "make_handoff",
]
