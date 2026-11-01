"""Gemini through the google-genai SDK (pin google-genai==2.33.0 for Python 3.10).

Key: a Gemini API key from Google AI Studio, read from GEMINI_API_KEY.
Free-tier rate limits are low, so calls retry with a growing wait on HTTP 429.
"""

from __future__ import annotations

import os
import time
from typing import List, Optional

from google import genai
from google.genai import errors, types

from llm.base import ChatSession, Reply, Usage

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiProvider:
    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None,
                 thinking_budget: Optional[int] = None, temperature: Optional[float] = None,
                 max_retries: int = 5) -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Set GEMINI_API_KEY (create one in Google AI Studio).")
        self.model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        self._client = genai.Client(api_key=key)
        self._max_retries = max_retries
        thinking = types.ThinkingConfig(thinking_budget=thinking_budget) if thinking_budget is not None else None
        self._config = types.GenerateContentConfig(temperature=temperature, thinking_config=thinking)

    def _retry(self, fn):
        delay = 10.0
        for attempt in range(self._max_retries + 1):
            try:
                return fn()
            except errors.APIError as e:
                if e.code in (429, 500, 503) and attempt < self._max_retries:
                    time.sleep(delay)
                    delay = min(delay * 2, 120)
                    continue
                raise

    def generate(self, history: List[dict]) -> Reply:
        contents = [types.Content(role=m["role"], parts=[types.Part(text=m["text"])]) for m in history]
        resp = self._retry(lambda: self._client.models.generate_content(
            model=self.model, contents=contents, config=self._config))
        meta = resp.usage_metadata
        usage = Usage(
            input_tokens=(meta.prompt_token_count or 0) if meta else 0,
            output_tokens=(meta.candidates_token_count or 0) if meta else 0,
            thinking_tokens=(meta.thoughts_token_count or 0) if meta else 0,
        )
        return Reply(text=resp.text or "", usage=usage)

    def count_tokens(self, text: str) -> int:
        resp = self._retry(lambda: self._client.models.count_tokens(model=self.model, contents=text))
        return int(resp.total_tokens or 0)

    def chat(self) -> ChatSession:
        return ChatSession(provider=self)
