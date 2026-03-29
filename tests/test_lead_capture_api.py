"""Tests for the Vercel lead-capture handler helpers."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import urllib.request


MODULE_PATH = Path(__file__).resolve().parents[1] / "api" / "lead-capture.py"
SPEC = importlib.util.spec_from_file_location("lead_capture_api", MODULE_PATH)
lead_capture_api = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(lead_capture_api)


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_trigger_n8n_lead_notification_includes_discord_webhook(monkeypatch):
    monkeypatch.setenv("N8N_BASE_URL", "https://example.n8n.cloud")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")

    captured = {}

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"ok": True, "discord_sent": True})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = lead_capture_api._trigger_n8n_lead_notification(
        {
            "lead_id": "lead-1",
            "lead_name": "Taylor",
            "lead_email": "taylor@example.com",
            "company_name": "Example",
            "lead_intent": "browse_directory",
            "intent_category": "content",
            "entry_page": "landing.html",
        }
    )

    assert captured["url"] == "https://example.n8n.cloud/webhook/csp-lead-capture-intake"
    assert captured["timeout"] == 15
    assert captured["payload"]["discord_webhook_url"] == "https://discord.example/webhook"
    assert result["ok"] is True
    assert result["discord_sent"] is True
