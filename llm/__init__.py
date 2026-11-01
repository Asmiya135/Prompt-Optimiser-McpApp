"""Model providers behind one small interface.

The optimizer core never imports this package. Only the server (optional
exact token counts) and the benchmark use it. To support another model,
add a class with the same three methods as GeminiProvider.
"""

from llm.base import ChatSession, LLMProvider, Reply, Usage


def get_provider(name: str, **kwargs) -> LLMProvider:
    name = (name or "").lower()
    if name == "gemini":
        from llm.gemini import GeminiProvider
        return GeminiProvider(**kwargs)
    if name == "fake":
        from llm.fake import FakeProvider
        return FakeProvider(**kwargs)
    raise ValueError(f"Unknown provider {name!r}; available: gemini, fake")


__all__ = ["ChatSession", "LLMProvider", "Reply", "Usage", "get_provider"]
