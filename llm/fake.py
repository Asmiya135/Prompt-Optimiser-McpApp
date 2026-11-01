"""A deterministic stand-in model for tests and dry runs. Its numbers are NOT real.

It mimics two behaviours that matter for the benchmark: it follows explicit
format and length instructions, and it ignores what was never asked for.
Never present results from this provider as measurements.
"""

from __future__ import annotations

import re
from typing import List, Optional

from llm.base import ChatSession, Reply, Usage
from optimizer.tokens import estimate_tokens


class FakeProvider:
    def __init__(self, model: Optional[str] = None, **_: object) -> None:
        self.model = model or "fake-model"

    def _answer(self, prompt: str) -> str:
        low = prompt.lower()
        m = re.search(r"(\d+)\s*(bullet points|ideas|names|items|steps|rows)", low)
        n = int(m.group(1)) if m else 3
        if "markdown table" in low:
            body = "\n".join(f"| aspect {i} | a | b |" for i in range(1, n + 1))
            text = "| Aspect | A | B |\n|---|---|---|\n" + body
        elif "code block" in low:
            text = "```python\ndef solution(x):\n    return x\n```\nCall solution()."
        elif "numbered list" in low or "bulleted list" in low:
            text = "\n".join(f"{i}. point {i}" for i in range(1, n + 1))
        else:
            w = re.search(r"(\d+)\s*words", low)
            text = " ".join(["word"] * (int(w.group(1)) if w else 250))
        inc = re.search(r"must include: ([^.\n]+)", prompt, re.I)
        if inc:
            text += "\n" + inc.group(1)
        for later in re.findall(r"also cover: ([^.\n]+)", prompt, re.I):
            text += "\n" + later
        return text

    def generate(self, history: List[dict]) -> Reply:
        last = history[-1]["text"]
        # Follow-ups refer back to the first request, like a real chat model would.
        prompt = history[0]["text"] + "\n" + "\n".join(m["text"] for m in history[1:] if m["role"] == "user")
        if last.lower().startswith(("shorten", "expand", "give exactly", "put", "format", "also", "keep", "remove", "answer all")):
            prompt = last + "\n" + prompt
        text = self._answer(prompt)
        sent = "\n".join(m["text"] for m in history)
        return Reply(text=text, usage=Usage(input_tokens=estimate_tokens(sent), output_tokens=estimate_tokens(text)))

    def count_tokens(self, text: str) -> int:
        return estimate_tokens(text)

    def chat(self) -> ChatSession:
        return ChatSession(provider=self)
