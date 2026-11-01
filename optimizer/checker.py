"""Check a reply against its output contract, without calling a model.

Every check here is mechanical (word counts, list items, table rows, required
words). It cannot judge whether the content is true or good; that needs a
human or a model judge. When something fails, it writes ONE follow-up
message that fixes every failure at once, instead of a full retry.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from optimizer.models import CheckResult, Contract

_FENCE = re.compile(r"```.*?```", re.S)
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_BULLET = re.compile(r"^\s{0,3}[-*•]\s+\S")
_NUMBERED = re.compile(r"^\s{0,3}\d+[.)]\s+\S")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+\S")


def _prose(text: str) -> str:
    return _FENCE.sub(" ", text)


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’-]*", text))


def _table_rows(text: str) -> int:
    lines = text.splitlines()
    rows = [l for l in lines if _TABLE_ROW.match(l)]
    seps = [l for l in rows if _TABLE_SEP.match(l)]
    if not seps:
        return 0
    return max(0, len(rows) - len(seps) - 1)  # minus separator(s) and header


def _list_items(text: str) -> Dict[str, int]:
    lines = _prose(text).splitlines()
    return {
        "bullets": sum(1 for l in lines if _BULLET.match(l)),
        "numbered": sum(1 for l in lines if _NUMBERED.match(l)),
        "headings": sum(1 for l in lines if _HEADING.match(l)),
    }


def check_output(contract: Contract, reply: str) -> CheckResult:
    items: List[Dict[str, Any]] = []
    fixes: List[str] = []
    prose = _prose(reply) if contract.format == "code" else reply
    n_words = word_count(prose)
    lists = _list_items(reply)
    rows = _table_rows(reply)

    def add(name: str, ok: bool, detail: str, fix: str = "") -> None:
        items.append({"check": name, "passed": ok, "detail": detail, "fix": "" if ok else fix})
        if not ok and fix:
            fixes.append(fix)

    # Length.
    if contract.max_words is not None:
        ok = n_words <= contract.max_words
        add("Length (max)", ok, f"{n_words} words; limit {contract.max_words}.",
            f"Shorten it to at most {contract.max_words} words.")
    if contract.min_words is not None:
        ok = n_words >= contract.min_words
        add("Length (min)", ok, f"{n_words} words; minimum {contract.min_words}.",
            f"Expand it to at least {contract.min_words} words.")

    # Format.
    if contract.format == "table":
        add("Format: table", rows > 0, f"{rows} table rows found.", "Put the answer in a Markdown table.")
    elif contract.format == "code":
        has = "```" in reply
        add("Format: code block", has, "Code block found." if has else "No code block found.",
            "Put the code in a single fenced code block.")
    elif contract.format in ("bullets", "numbered"):
        n = lists["bullets"] + lists["numbered"]
        add(f"Format: {contract.format} list", n > 0, f"{n} list items found.",
            "Format the answer as a list, one point per line.")

    # Item count.
    if contract.items is not None:
        found = rows if contract.format == "table" else (lists["bullets"] + lists["numbered"])
        if contract.items_max:
            ok = 0 < found <= contract.items
            add("Item count (max)", ok, f"{found} items; at most {contract.items}.",
                f"Keep it to at most {contract.items} items.")
        else:
            ok = found == contract.items
            add("Item count", ok, f"{found} items; asked for {contract.items}.",
                f"Give exactly {contract.items} items.")

    # Required and banned content.
    low = reply.lower()
    missing = [m for m in contract.must_include if m.lower() not in low]
    if contract.must_include:
        add("Must include", not missing,
            "All required points present." if not missing else "Missing: " + ", ".join(missing) + ".",
            "Also cover: " + ", ".join(missing) + "." if missing else "")
    present = [a for a in contract.avoid if a.lower() in low]
    if contract.avoid:
        add("Avoid", not present,
            "Nothing banned found." if not present else "Found: " + ", ".join(present) + ".",
            "Remove: " + ", ".join(present) + "." if present else "")

    # Every sub-task answered (approximate: counts numbered items or headings).
    if contract.parts > 1:
        sections = max(lists["numbered"], lists["headings"])
        ok = sections >= contract.parts
        add("All parts answered (approx.)", ok, f"{sections} numbered parts or headings; expected {contract.parts}.",
            f"Answer all {contract.parts} numbered parts of the request.")

    passed = all(i["passed"] for i in items)
    follow_up = "" if passed else " ".join(fixes) + " Keep everything else the same."
    return CheckResult(passed=passed, items=items, follow_up=follow_up)
