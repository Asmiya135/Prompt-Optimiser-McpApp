"""Layer 2 auth: check the user's Google OAuth access token.

Gemini Enterprise sends two tokens on every call (per Google's custom MCP
server docs):
- X-Serverless-Authorization: a Google-signed ID token for its service agent.
  Cloud Run checks this one itself (layer 1, the run.invoker IAM role).
- Authorization: Bearer <the user's OAuth access token>. Cloud Run does not
  check it, so this module does.

Google access tokens are opaque (not JWTs), so they are checked against
Google's tokeninfo endpoint. The token must have been issued to OUR OAuth
client (aud/azp == OAUTH_CLIENT_ID), otherwise any Google token would pass.
Results are cached briefly so each chat turn does not cost a network call.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import httpx

from mcp.server.auth.provider import AccessToken

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
CACHE_SECONDS = 300


class GoogleAccessTokenVerifier:
    """Implements the MCP SDK's TokenVerifier protocol (async verify_token)."""

    def __init__(self, client_id: str, allowed_domains: Optional[List[str]] = None,
                 allowed_emails: Optional[List[str]] = None,
                 http: Optional[httpx.AsyncClient] = None) -> None:
        self.client_id = client_id
        self.allowed_domains = [d.lower() for d in (allowed_domains or [])]
        self.allowed_emails = [e.lower() for e in (allowed_emails or [])]
        self._http = http
        self._cache: Dict[str, Tuple[float, AccessToken]] = {}

    async def _tokeninfo(self, token: str) -> Optional[dict]:
        client = self._http or httpx.AsyncClient(timeout=5.0)
        try:
            resp = await client.get(TOKENINFO_URL, params={"access_token": token})
        except httpx.HTTPError:
            return None
        finally:
            if self._http is None:
                await client.aclose()
        if resp.status_code != 200:
            return None
        return resp.json()

    def _allowed(self, info: dict) -> bool:
        if self.client_id not in (info.get("aud"), info.get("azp")):
            return False
        email = (info.get("email") or "").lower()
        if self.allowed_emails and email not in self.allowed_emails:
            return False
        if self.allowed_domains and email.rsplit("@", 1)[-1] not in self.allowed_domains:
            return False
        if self.allowed_emails or self.allowed_domains:
            return str(info.get("email_verified", "")).lower() == "true"
        return True

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        now = time.time()
        hit = self._cache.get(token)
        if hit and hit[0] > now:
            return hit[1]
        info = await self._tokeninfo(token)
        if not info or not self._allowed(info):
            return None
        try:
            expires_in = int(info.get("expires_in", 0))
        except (TypeError, ValueError):
            expires_in = 0
        if expires_in <= 0:
            return None
        access = AccessToken(
            token=token,
            client_id=str(info.get("azp") or info.get("aud")),
            scopes=str(info.get("scope", "")).split(),
            expires_at=int(now) + expires_in,
            subject=info.get("sub"),
            claims={"email": info.get("email")},
        )
        self._cache[token] = (now + min(CACHE_SECONDS, expires_in), access)
        if len(self._cache) > 1000:  # keep memory bounded on a long-lived instance
            self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
        return access
