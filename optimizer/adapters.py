"""Per-model prompt layout.

The rules and the content are the same for every model; only the layout
changes. Adding a model means adding one small class here.

The layouts below are reasonable defaults, not vendor-certified formats.
Check each vendor's current prompting guide before relying on them:
- Gemini: Google's "prompt design strategies" guide for the Gemini API.
- Claude: Anthropic's prompt engineering docs (XML tags are recommended there).
"""

from __future__ import annotations

from typing import Dict, List, Tuple

Section = Tuple[str, str]  # (name, body)


class Adapter:
    name = "generic"

    def render(self, sections: List[Section]) -> str:
        parts = []
        for title, body in sections:
            body = body.strip()
            if not body:
                continue
            parts.append(body if title == "task" else f"{title.capitalize()}:\n{body}")
        return "\n\n".join(parts)


class GeminiAdapter(Adapter):
    """Short labelled sections, task first, delimited material."""

    name = "gemini"

    def render(self, sections: List[Section]) -> str:
        labels = {"task": "Task", "context": "Context", "material": "Material", "examples": "Examples",
                  "output": "Output", "constraints": "Constraints", "reasoning": "Approach"}
        parts = []
        for title, body in sections:
            body = body.strip()
            if not body:
                continue
            if title in ("material", "examples"):
                parts.append(f"{labels[title]} (between the markers):\n<<<\n{body}\n>>>")
            else:
                parts.append(f"{labels.get(title, title.capitalize())}: {body}" if "\n" not in body
                             else f"{labels.get(title, title.capitalize())}:\n{body}")
        return "\n\n".join(parts)


class ClaudeAdapter(Adapter):
    """XML-tagged sections."""

    name = "claude"

    def render(self, sections: List[Section]) -> str:
        tags = {"output": "output_format"}
        parts = []
        for title, body in sections:
            body = body.strip()
            if body:
                tag = tags.get(title, title)
                parts.append(f"<{tag}>\n{body}\n</{tag}>")
        return "\n".join(parts)


ADAPTERS: Dict[str, Adapter] = {a.name: a for a in (GeminiAdapter(), ClaudeAdapter(), Adapter())}


def get_adapter(target_model: str) -> Adapter:
    key = (target_model or "").lower()
    for name, adapter in ADAPTERS.items():
        if name != "generic" and key.startswith(name):
            return adapter
    return ADAPTERS["generic"]
