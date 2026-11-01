"""Settings from environment variables (Cloud Run sets them at deploy time)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def _list(name: str) -> List[str]:
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


@dataclass
class Settings:
    # "google": require a Google OAuth access token from Gemini Enterprise (production).
    # "none": no user auth (local testing only; never deploy publicly like this).
    auth_mode: str = field(default_factory=lambda: os.environ.get("AUTH_MODE", "google").lower())
    oauth_client_id: str = field(default_factory=lambda: os.environ.get("OAUTH_CLIENT_ID", ""))
    allowed_email_domains: List[str] = field(default_factory=lambda: _list("ALLOWED_EMAIL_DOMAINS"))
    allowed_emails: List[str] = field(default_factory=lambda: _list("ALLOWED_EMAILS"))
    public_url: str = field(default_factory=lambda: os.environ.get("PUBLIC_URL", "").rstrip("/"))
    # Optional: your own Gemini key, used only for exact token counts. Leave empty for zero model calls.
    gemini_api_key: str = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))
    target_model: str = field(default_factory=lambda: os.environ.get("TARGET_MODEL", "gemini"))
    # In stateless mode an older-protocol host may not re-send its capabilities on each call, so the
    # server cannot always tell whether the form is visible. "true" assumes it is (Gemini Enterprise
    # renders MCP Apps) and still gives the model the questions in case the user says they see no form.
    assume_ui: bool = field(default_factory=lambda: os.environ.get("ASSUME_UI", "true").lower() == "true")
    port: int = field(default_factory=lambda: int(os.environ.get("PORT", "8080")))

    def validate(self) -> None:
        if self.auth_mode not in ("google", "none"):
            raise ValueError("AUTH_MODE must be 'google' or 'none'")
        if self.auth_mode == "google" and not self.oauth_client_id:
            raise ValueError("AUTH_MODE=google needs OAUTH_CLIENT_ID (the Web OAuth client from README step 3)")
