"""Data shapes shared by the rules, builder, checker, server and benchmark."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# Question 1: what output do you expect? (key -> label shown in the form)
OUTPUT_TYPES: Dict[str, str] = {
    "explanation": "Explanation",
    "summary": "Summary",
    "code": "Code",
    "comparison_table": "Comparison table",
    "ideas_list": "List of ideas",
    "written_piece": "Written piece (email, essay, post)",
    "step_plan": "Step-by-step plan",
    "analysis_decision": "Analysis or decision",
    "story_creative": "Story or creative",
    "other": "Other (describe)",
}

# Question 2: what input do you have? (multi-select)
INPUT_TYPES: Dict[str, str] = {
    "nothing": "Nothing yet, just a question",
    "text": "Text to paste",
    "file": "File (PDF, doc, sheet)",
    "code": "Code",
    "data": "Data or numbers",
    "examples": "Examples of what I want",
    "links": "Links",
    "other": "Other (describe)",
}

# Inputs that mean "answer from my material", which triggers grounding.
MATERIAL_INPUTS = {"text", "file", "code", "data", "links"}


@dataclass
class IntakeAnswers:
    """Everything the user tells us: the draft plus the three questions."""

    draft: str
    output_type: str = ""          # key of OUTPUT_TYPES, "" if not chosen
    output_other: str = ""         # free text when output_type == "other"
    inputs: List[str] = field(default_factory=list)  # keys of INPUT_TYPES
    input_other: str = ""
    material: str = ""             # pasted text, code, data or examples
    # Question 3: constraints. Empty means "not given".
    length: str = ""               # e.g. "300 words", "under 100 words", "5 bullet points"
    tone: str = ""
    audience: str = ""
    must_include: str = ""         # comma-separated
    avoid: str = ""                # comma-separated
    scope: str = ""                # deadline, scope or "focus on X"
    notes: str = ""                # anything else the user wants to say
    no_constraints: bool = False
    target_model: str = "gemini"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntakeAnswers":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in known and v is not None}
        if isinstance(clean.get("inputs"), str):
            clean["inputs"] = [s.strip() for s in clean["inputs"].split(",") if s.strip()]
        return cls(**clean)


@dataclass
class Check:
    """One rule from the brief, applied to the request."""

    rule: str        # e.g. "Be specific"
    passed: bool
    action: str      # "ok" | "ask" | "fixed" | "default" | "split" | "flag"
    message: str


@dataclass
class Analysis:
    task_type: str
    prefill: Dict[str, Any]
    checks: List[Check]
    questions: List[str]             # at most 3, only for missing essentials
    techniques: List[str]
    risk_flags: List[str]
    sub_tasks: List[str]
    typo_fixes: List[List[str]]      # [[wrong, right], ...]
    conflicts: List[str]
    assumptions: List[str]           # defaults we used instead of guessing silently
    ready: bool                      # True = draft already passes, form can be skipped

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Contract:
    """What a good answer must look like. Checked after the model replies."""

    output_type: str = ""
    format: str = ""                 # "table" | "bullets" | "numbered" | "code" | "" (any)
    min_words: Optional[int] = None
    max_words: Optional[int] = None
    items: Optional[int] = None      # number of list items or table rows asked for
    items_max: bool = False          # True: "at most N"; False: "exactly N"
    must_include: List[str] = field(default_factory=list)
    avoid: List[str] = field(default_factory=list)
    parts: int = 1                   # number of sub-tasks the answer must cover
    unsure_rule: bool = False        # prompt asked the model to say when it is unsure

    def to_string(self) -> str:
        """Compact, single-line form the model can pass back to check_output."""
        bits = ["po1"]
        if self.output_type:
            bits.append(f"type={self.output_type}")
        if self.format:
            bits.append(f"fmt={self.format}")
        if self.min_words is not None or self.max_words is not None:
            lo = "" if self.min_words is None else str(self.min_words)
            hi = "" if self.max_words is None else str(self.max_words)
            bits.append(f"words={lo}-{hi}")
        if self.items is not None:
            bits.append(f"items={'<' if self.items_max else ''}{self.items}")
        if self.must_include:
            bits.append("inc=" + "|".join(self.must_include))
        if self.avoid:
            bits.append("avoid=" + "|".join(self.avoid))
        if self.parts > 1:
            bits.append(f"parts={self.parts}")
        if self.unsure_rule:
            bits.append("unsure=1")
        return ";".join(bits)

    @classmethod
    def from_string(cls, text: str) -> "Contract":
        c = cls()
        for chunk in text.strip().split(";"):
            if "=" not in chunk:
                continue
            key, _, value = chunk.partition("=")
            key, value = key.strip(), value.strip()
            if key == "type":
                c.output_type = value
            elif key == "fmt":
                c.format = value
            elif key == "words":
                lo, _, hi = value.partition("-")
                c.min_words = int(lo) if lo.strip().isdigit() else None
                c.max_words = int(hi) if hi.strip().isdigit() else None
            elif key == "items" and value.lstrip("<").isdigit():
                c.items_max = value.startswith("<")
                c.items = int(value.lstrip("<"))
            elif key == "inc":
                c.must_include = [v for v in value.split("|") if v]
            elif key == "avoid":
                c.avoid = [v for v in value.split("|") if v]
            elif key == "parts" and value.isdigit():
                c.parts = int(value)
            elif key == "unsure":
                c.unsure_rule = value == "1"
        return c


@dataclass
class BuiltPrompt:
    prompt: str                      # what gets sent as the user message
    system: str                      # standing rules; empty if none (API runs can send it separately)
    contract: Contract
    techniques: List[str]
    assumptions: List[str]
    warnings: List[str]
    tokens_before: int
    tokens_after: int
    token_method: str                # "estimate" or "gemini count_tokens"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["contract"] = self.contract.to_string()
        return d


@dataclass
class CheckResult:
    passed: bool
    items: List[Dict[str, Any]]      # [{"check", "passed", "detail", "fix"}]
    follow_up: str                   # one targeted follow-up, "" if everything passed

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
