"""The real HTTP app (Streamable HTTP, stateless JSON) with Google-token auth.

Google's tokeninfo endpoint is replaced by a fake, so no network is needed.
"""

from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn

from server.config import Settings

CLIENT_ID = "test-client.apps.googleusercontent.com"
GOOD = {"aud": CLIENT_ID, "azp": CLIENT_ID, "expires_in": "3000", "scope": "openid email profile",
        "email": "asmiya@example.com", "email_verified": "true", "sub": "123"}
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def server_url(monkeypatch):
    from server import auth
    from server.app import create_app

    async def fake_tokeninfo(self, token):
        return {"good-token": GOOD, "other-client": {**GOOD, "aud": "x", "azp": "x"}}.get(token)

    monkeypatch.setattr(auth.GoogleAccessTokenVerifier, "_tokeninfo", fake_tokeninfo)
    settings = Settings(auth_mode="google", oauth_client_id=CLIENT_ID, gemini_api_key="")
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(timeout=5)


def _rpc(method, params, id_=1):
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params}


def test_health_is_open(server_url):
    assert httpx.get(server_url + "/healthz").json() == {"status": "ok"}


def test_requires_a_token_for_our_client(server_url):
    body = _rpc("tools/list", {})
    assert httpx.post(server_url + "/mcp", json=body, headers=HEADERS).status_code == 401
    bad = {**HEADERS, "Authorization": "Bearer other-client"}
    assert httpx.post(server_url + "/mcp", json=body, headers=bad).status_code == 401


def test_old_protocol_clients_work_statelessly(server_url):
    h = {**HEADERS, "Authorization": "Bearer good-token"}
    init = _rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                               "clientInfo": {"name": "test", "version": "1"}})
    r = httpx.post(server_url + "/mcp", json=init, headers=h)
    assert r.status_code == 200 and r.json()["result"]["protocolVersion"] == "2025-06-18"

    h["MCP-Protocol-Version"] = "2025-06-18"
    tools = httpx.post(server_url + "/mcp", json=_rpc("tools/list", {}, 2), headers=h).json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"start_intake", "build_prompt", "check_output", "context_health", "make_handoff"} <= names
    start = next(t for t in tools if t["name"] == "start_intake")
    assert start["_meta"]["ui"]["resourceUri"] == "ui://prompt-optimizer/intake.html"
    assert all(t["annotations"]["readOnlyHint"] for t in tools)

    call = _rpc("tools/call", {"name": "build_prompt", "arguments": {
        "draft": "explain photosynthesis", "audience": "class 9 student", "length": "under 120 words"}}, 3)
    result = httpx.post(server_url + "/mcp", json=call, headers=h).json()["result"]
    assert "You are a patient teacher" in result["structuredContent"]["prompt"]
    assert result["structuredContent"]["contract"].startswith("po1;type=explanation")

    read = _rpc("resources/read", {"uri": "ui://prompt-optimizer/intake.html"}, 4)
    res = httpx.post(server_url + "/mcp", json=read, headers=h).json()["result"]["contents"][0]
    assert res["mimeType"] == "text/html;profile=mcp-app" and "McpExtApps" in res["text"]
