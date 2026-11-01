"""The brief's rules and common mistakes, as deterministic checks.

analyze() never calls a model. It reads the draft and the intake answers and
reports: what is missing, which technique fits, what is risky, and what it
assumed. A failed check either asks the user or applies a visible default;
it never fills a gap with a silent guess.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from optimizer import vocab
from optimizer.models import MATERIAL_INPUTS, OUTPUT_TYPES, Analysis, Check, IntakeAnswers
from optimizer.techniques import choose_techniques

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'+#.-]*")
_URL = re.compile(r"https?://\S+")


# ---------------------------------------------------------------- helpers

def words(text: str) -> List[str]:
    return _WORD.findall(text or "")


def _has_any(text: str, needles: List[str]) -> bool:
    low = f" {text.lower()} "
    return any(n in low for n in needles)


def parse_length(text: str) -> Dict[str, Optional[int]]:
    """Turn '300 words', 'under 100 words', '5 bullet points' into numbers.

    Returns {"min_words", "max_words", "items", "items_max"}; items_max=1 means
    "at most N items" rather than exactly N.
    """
    out: Dict[str, Optional[int]] = {"min_words": None, "max_words": None, "items": None, "items_max": 0}
    if not text:
        return out
    low = text.lower()
    m = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)\s*words?", low)
    if m:
        out["min_words"], out["max_words"] = int(m.group(1)), int(m.group(2))
        return out
    m = re.search(r"(under|less than|fewer than|at most|max(?:imum)?|no more than|up to|within)\s*(\d+)\s*words?", low)
    if m:
        out["max_words"] = int(m.group(2))
        return out
    m = re.search(r"(at least|minimum|min|over|more than)\s*(\d+)\s*words?", low)
    if m:
        out["min_words"] = int(m.group(2))
        return out
    m = re.search(r"(\d+)\s*words?", low)
    if m:  # "about 300 words" -> 80%..120%
        n = int(m.group(1))
        out["min_words"], out["max_words"] = int(n * 0.8), int(n * 1.2)
        return out
    m = re.search(r"(?:one|1)\s+sentence", low)
    if m:
        out["max_words"] = 40
        return out
    m = re.search(r"(at most|max(?:imum)?|up to|no more than|under|fewer than)?\s*(\d+)\s*"
                  r"(bullet|bullets|points|ideas|items|names|steps|rows|examples|options|tips|questions|"
                  r"headlines|reasons)", low)
    if m:
        out["items"] = int(m.group(2))
        out["items_max"] = 1 if m.group(1) else 0
    return out


def fix_typos(text: str) -> Tuple[str, List[List[str]]]:
    """Fix only words in the curated typo list, preserving everything else."""
    fixes: List[List[str]] = []

    def repl(m: "re.Match[str]") -> str:
        word = m.group(0)
        right = vocab.COMMON_TYPOS.get(word.lower())
        if right is None:
            return word
        fixes.append([word, right])
        return right

    fixed = re.sub(r"(?<![\w/])[A-Za-z/]+(?![\w/])", repl, text)
    return fixed, fixes


def split_sub_tasks(text: str) -> List[str]:
    """Return separate asks if the draft contains more than one, else []."""
    numbered = re.findall(r"(?:^|\n)\s*(?:\d+[.)]|[-*•])\s+(.+)", text)
    if len(numbered) >= 2 and sum(1 for n in numbered if _starts_with_task_verb(n)) >= 2:
        return [n.strip() for n in numbered]
    # Split into clauses on sentence ends and joiners, then keep clauses led by a task verb.
    clauses = re.split(r"[?.!;\n]+|\band also\b|\balso\b|\band then\b|\bthen\b|,\s*and\b|\band\b(?=\s+(?:"
                       + "|".join(vocab.TASK_VERBS) + r")\b)", text, flags=re.I)
    tasks = [c.strip(" ,") for c in clauses if c and _starts_with_task_verb(c.strip(" ,"))]
    return tasks if len(tasks) >= 2 else []


def _first_word(text: str) -> Optional[str]:
    w = words(text.lower())
    skip = {"please", "pls", "can", "could", "you", "also", "and", "then", "now", "i", "want", "to", "need"}
    for token in w:
        if token not in skip:
            return token
    return None


def _starts_with_task_verb(text: str) -> bool:
    return (_first_word(text) or "") in vocab.TASK_VERBS


def guess_output_type(draft: str) -> str:
    low = f" {draft.lower()} "
    for key, keys in vocab.OUTPUT_KEYWORDS:
        if any(k in low for k in keys):
            return key
    return ""


def guess_inputs(draft: str) -> List[str]:
    found = [key for key, keys in vocab.INPUT_KEYWORDS.items() if _has_any(draft, keys)]
    if _URL.search(draft):
        found.append("links")
    return found


def guess_tone(draft: str) -> str:
    low = draft.lower()
    for t in vocab.TONES:
        if re.search(rf"\b{re.escape(t)}\b", low):
            return t
    return ""


def guess_audience(draft: str) -> str:
    low = draft.lower()
    m = re.search(r"\b(?:i am|i'm|im)\s+(?:a|an)\s+([a-z0-9 \-]{2,40}?)(?:[.,;!?]|$| and )", low)
    if m:
        return m.group(1).strip()
    m = re.search(r"\bfor\s+(?:a|an|my|our|the)?\s*([a-z0-9 \-]{2,40}?)(?:[.,;!?]|$| in | with | who | that )", low)
    if m and _has_any(m.group(1), vocab.AUDIENCE_NOUNS):
        return m.group(1).strip()
    m = re.search(r"\b(class \d+|grade \d+|\d+[- ]year[- ]old)\b", low)
    if m:
        return m.group(1)
    return ""


def guess_length(draft: str) -> str:
    low = draft.lower()
    m = re.search(r"((?:under|less than|at most|max(?:imum)?|no more than|up to|about|around|at least)?\s*"
                  r"\d+\s*(?:-\s*\d+\s*)?(?:words?|bullet points?|bullets|points|ideas|items|names|steps|rows|"
                  r"lines|sentences|paragraphs|examples|options|tips|headlines))", low)
    if m:
        return m.group(1).strip()
    m = re.search(r"\b(one sentence|a sentence|one paragraph|a paragraph|brief|short)\b", low)
    return m.group(1) if m else ""


def risk_flags(text: str) -> List[str]:
    return [name for name, pats in vocab.RISK_PATTERNS.items() if _has_any(text, pats)]


def is_vague(draft: str) -> Tuple[bool, str]:
    toks = [w.lower() for w in words(draft)]
    content = [t for t in toks if t not in vocab.GENERIC_WORDS and not t.isdigit()]
    if len(toks) == 0:
        return True, "The request is empty."
    vague_phrase = next((p for p in vocab.VAGUE_PHRASES if p in draft.lower()), "")
    if len(content) < 2:
        return True, "The request has no clear subject; say exactly what it is about."
    if vague_phrase and len(content) < 4:
        return True, f"'{vague_phrase}' is vague; name the subject, scope or quantity."
    return False, ""


# ---------------------------------------------------------------- public API

def prefill_from_draft(draft: str) -> Dict[str, Any]:
    """Best guesses for the form, read from the user's own words."""
    return {
        "output_type": guess_output_type(draft),
        "inputs": guess_inputs(draft),
        "length": guess_length(draft),
        "tone": guess_tone(draft),
        "audience": guess_audience(draft),
    }


def analyze(answers: IntakeAnswers) -> Analysis:
    draft = answers.draft or ""
    prefill = prefill_from_draft(draft)
    checks: List[Check] = []
    questions: List[str] = []
    assumptions: List[str] = []
    conflicts: List[str] = []

    # Fill unanswered fields from the draft. The user's explicit answers always win.
    output_type = answers.output_type or prefill["output_type"]
    inputs = answers.inputs or prefill["inputs"]
    length = answers.length or prefill["length"]
    tone = answers.tone or prefill["tone"]
    audience = answers.audience or prefill["audience"]

    # Rule: be clear, avoid typos.
    fixed_draft, typo_fixes = fix_typos(draft)
    if typo_fixes:
        shown = ", ".join(f"'{a}' -> '{b}'" for a, b in typo_fixes[:5])
        checks.append(Check("Be clear; avoid typos", False, "fixed", f"Fixed: {shown}."))
    else:
        checks.append(Check("Be clear; avoid typos", True, "ok", "No common typos found."))

    # Rule: be specific.
    vague, why = is_vague(fixed_draft)
    has_detail = bool(answers.notes or answers.scope or answers.material or answers.must_include)
    if vague and not has_detail:
        checks.append(Check("Be specific", False, "ask", why))
        questions.append("What exactly is it about? Name the subject, scope or quantity.")
    else:
        checks.append(Check("Be specific", True, "ok", "The request names a clear subject."))

    # Rule: specify the output format.
    if not output_type:
        checks.append(Check("Specify the output format", False, "ask", "No output type chosen or found in the draft."))
        questions.append("What output do you expect (explanation, summary, code, table, list, written piece...)?")
    else:
        checks.append(Check("Specify the output format", True, "ok",
                            f"Output: {OUTPUT_TYPES.get(output_type, output_type)}."))
    if answers.output_type and prefill["output_type"] and answers.output_type != prefill["output_type"]:
        conflicts.append(
            f"Your draft sounds like '{OUTPUT_TYPES[prefill['output_type']]}' but you picked "
            f"'{OUTPUT_TYPES.get(answers.output_type, answers.output_type)}'. Which is right?"
        )

    # Rule: set the context.
    if audience:
        checks.append(Check("Set the context", True, "ok", f"Audience: {audience}."))
    elif answers.notes:
        checks.append(Check("Set the context", True, "ok", "Background given in notes."))
    else:
        checks.append(Check("Set the context", False, "default",
                            "No audience given; using 'a general reader'. Change it if that's wrong."))
        assumptions.append("Audience: a general reader.")

    # Rule: use constraints.
    if answers.no_constraints:
        checks.append(Check("Use constraints", True, "ok", "You said there are no constraints."))
    elif length or tone:
        checks.append(Check("Use constraints", True, "ok", "Length or tone given."))
    else:
        default = vocab.DEFAULT_LENGTH.get(output_type or "other", "")
        checks.append(Check("Use constraints", False, "default",
                            f"No length given; using '{default}'. Change it if that's wrong."))
        if default:
            assumptions.append(f"Length: {default}.")

    # Rule: one thing per prompt.
    sub_tasks = split_sub_tasks(fixed_draft)
    if sub_tasks:
        checks.append(Check("One thing per prompt", False, "split",
                            f"Found {len(sub_tasks)} separate asks; they will be numbered so none is missed."))
    else:
        checks.append(Check("One thing per prompt", True, "ok", "One ask."))

    # Rule: don't expect perfect answers.
    flags = risk_flags(" ".join([fixed_draft, answers.notes, answers.scope]))
    if flags:
        checks.append(Check("Don't expect perfect answers", False, "flag",
                            "Asks for " + ", ".join(flags) + ". The prompt will tell the model to say when it "
                            "is unsure; check these facts yourself."))
    else:
        checks.append(Check("Don't expect perfect answers", True, "ok", "No high-risk facts requested."))

    # Grounding needs the material itself.
    if set(inputs) & MATERIAL_INPUTS and not answers.material and "```" not in draft and not _URL.search(draft):
        if "file" in inputs:
            checks.append(Check("Give the material", False, "ask",
                                "You have a file; attach it in the chat or paste the relevant part."))
        else:
            questions.append("Paste the text, code or data you want the answer to use.")

    techniques = choose_techniques(answers, output_type, inputs, sub_tasks)
    essentials_missing = any(c.action == "ask" for c in checks)
    ready = (not essentials_missing) and bool(output_type) and not typo_fixes and not conflicts \
        and bool(length or answers.no_constraints)

    return Analysis(
        task_type=output_type,
        prefill={**prefill, "output_type": output_type, "inputs": inputs, "length": length,
                 "tone": tone, "audience": audience},
        checks=checks,
        questions=questions[:3],
        techniques=techniques,
        risk_flags=flags,
        sub_tasks=sub_tasks,
        typo_fixes=typo_fixes,
        conflicts=conflicts,
        assumptions=assumptions,
        ready=ready,
    )
