"""GeminiProvider against real google-genai response objects, with the network call stubbed."""

from google.genai import errors, types

from llm.gemini import GeminiProvider


def _response(text: str) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text=text)]))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=12, candidates_token_count=5, thoughts_token_count=7, total_token_count=24),
    )


def test_generate_reads_usage_and_text(monkeypatch):
    p = GeminiProvider(api_key="test-key", model="gemini-2.5-flash", max_retries=0)
    seen = {}

    def fake_generate(model, contents, config):
        seen["model"], seen["contents"] = model, contents
        return _response("Canberra.")

    monkeypatch.setattr(p._client.models, "generate_content", fake_generate)
    chat = p.chat()
    reply = chat.send("What is the capital of Australia?")
    assert reply.text == "Canberra."
    assert (reply.usage.input_tokens, reply.usage.output_tokens, reply.usage.thinking_tokens) == (12, 5, 7)
    assert reply.usage.total == 24
    chat.send("Shorter.")
    roles = [c.role for c in seen["contents"]]
    assert roles == ["user", "model", "user"]  # history is re-sent, like a chat app


def test_retries_on_rate_limit(monkeypatch):
    p = GeminiProvider(api_key="test-key", max_retries=2)
    calls = {"n": 0}

    def flaky(model, contents, config):
        calls["n"] += 1
        if calls["n"] < 3:
            raise errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})
        return _response("ok")

    monkeypatch.setattr(p._client.models, "generate_content", flaky)
    monkeypatch.setattr("llm.gemini.time.sleep", lambda s: None)
    assert p.generate([{"role": "user", "text": "hi"}]).text == "ok"
    assert calls["n"] == 3


def test_count_tokens(monkeypatch):
    p = GeminiProvider(api_key="test-key")
    monkeypatch.setattr(p._client.models, "count_tokens",
                        lambda model, contents: types.CountTokensResponse(total_tokens=42))
    assert p.count_tokens("hello") == 42
