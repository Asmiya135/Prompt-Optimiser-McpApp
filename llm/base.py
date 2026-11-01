"""Provider-neutral types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Protocol


@dataclass
class Usage:
    """Tokens billed for one model call, as the provider reports them."""

    input_tokens: int = 0      # everything sent, including the re-sent chat history
    output_tokens: int = 0     # visible answer
    thinking_tokens: int = 0   # hidden reasoning, if the model reports it (billed as output on Gemini)

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens + self.thinking_tokens


@dataclass
class Reply:
    text: str
    usage: Usage


@dataclass
class ChatSession:
    """A multi-turn conversation. Each send re-sends the full history, as chat apps do."""

    provider: "LLMProvider"
    history: List[dict] = field(default_factory=list)  # [{"role": "user"|"model", "text": ...}]

    def send(self, message: str) -> Reply:
        self.history.append({"role": "user", "text": message})
        reply = self.provider.generate(self.history)
        self.history.append({"role": "model", "text": reply.text})
        return reply


class LLMProvider(Protocol):
    model: str

    def generate(self, history: List[dict]) -> Reply:
        """Send the whole history; return the reply and its usage."""
        ...

    def count_tokens(self, text: str) -> int:
        """Exact token count for this model."""
        ...

    def chat(self) -> ChatSession:
        ...
