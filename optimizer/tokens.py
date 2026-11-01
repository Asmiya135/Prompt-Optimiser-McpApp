"""Token counting.

The default is a rough local estimate (about 4 characters per token for English
text). It needs no network and no key, but it is only approximate. When a
model provider is configured, pass its counter in to get that model's exact
count instead. Different models tokenize differently, so only compare counts
taken with the same counter.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

TokenCounter = Callable[[str], int]


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def count(text: str, counter: Optional[TokenCounter] = None) -> Tuple[int, str]:
    """Return (tokens, method). Falls back to the estimate if the counter fails."""
    if counter is not None:
        try:
            return int(counter(text)), "model count"
        except Exception:  # network error, quota, missing key: never break the build
            pass
    return estimate_tokens(text), "estimate (~4 chars/token)"
