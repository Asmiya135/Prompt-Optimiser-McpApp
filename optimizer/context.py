"""Conversation hygiene: a health check and a clean-restart handoff.

The server cannot read the host's chat history, so these take a short summary
the model (or user) passes in, not the full transcript. Passing the whole
transcript back as a tool argument would cost more tokens than it saves.
"""

from __future__ import annotations

from typing import Any, Dict, List

LONG_THREAD_TURNS = 20      # rough threshold; long threads tend to drift
MANY_CORRECTIONS = 2


def context_health(turn_count: int, corrections: List[str], contradictions: List[str]) -> Dict[str, Any]:
    reasons: List[str] = []
    score = 0
    if turn_count >= LONG_THREAD_TURNS:
        score += 1
        reasons.append(f"Long thread ({turn_count} turns): early mistakes are still in the context.")
    if len(corrections) >= MANY_CORRECTIONS:
        score += 2
        reasons.append(f"{len(corrections)} corrections so far: wrong claims may still influence answers.")
    elif corrections:
        score += 1
        reasons.append("One correction so far.")
    if contradictions:
        score += 2
        reasons.append(f"{len(contradictions)} unresolved contradiction(s): " + "; ".join(contradictions[:3]))

    if score >= 3:
        level, advice = "restart", "Start a fresh chat with a handoff of confirmed facts (call make_handoff)."
    elif score >= 1:
        level, advice = "watch", "Fine for now. Restart if another correction is needed."
    else:
        level, advice = "good", "No action needed."
    return {"level": level, "score": score, "reasons": reasons, "recommendation": advice}


def make_handoff(open_task: str, confirmed_facts: List[str], decisions: List[str],
                 constraints: List[str]) -> str:
    lines = ["Continue this task in a fresh conversation. Use only the confirmed information below; "
             "ignore anything from earlier drafts that is not listed.", "", f"Task: {open_task.strip()}"]
    if confirmed_facts:
        lines += ["", "Confirmed facts:"] + [f"- {f.strip()}" for f in confirmed_facts if f.strip()]
    if decisions:
        lines += ["", "Decisions already made:"] + [f"- {d.strip()}" for d in decisions if d.strip()]
    if constraints:
        lines += ["", "Constraints:"] + [f"- {c.strip()}" for c in constraints if c.strip()]
    lines += ["", "If something you need is not listed, ask instead of assuming."]
    return "\n".join(lines)
