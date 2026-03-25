"""Vercel serverless function — lead capture endpoint.

Self-contained: no services/ imports. Requires SUPABASE_URL and SUPABASE_KEY
environment variables set in the Vercel project settings.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from uuid import uuid4

LEAD_CAPTURE_TABLE = "lead_captures"
DEFAULT_CAPTURE_VERSION = "m24a.v1"
DEFAULT_FOLLOW_UP_OWNER = "fractional-head-of-cs"
SERVICE_INTENTS = {"shortlist", "advisory", "audit", "fractional-leadership"}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b""

        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._respond(400, {"ok": False, "error": "invalid_json"})
            return

        if not isinstance(payload, dict):
            self._respond(400, {"ok": False, "error": "payload_must_be_object"})
            return

        try:
            row = _build_row(payload)
        except ValueError as error:
            self._respond(400, {"ok": False, "error": str(error)})
            return

        try:
            _upsert(row)
            self._respond(200, {"ok": True, "lead": row})
        except Exception as error:
            self._respond(500, {"ok": False, "error": str(error)})

    def do_OPTIONS(self):
        self._respond(200, {"ok": True})

    def _respond(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)


def _build_row(payload: dict) -> dict:
    lead_name = _clean(payload.get("name") or payload.get("lead_name"))
    lead_email = _normalize_email(payload.get("email") or payload.get("lead_email"))
    company_name = _clean(payload.get("company") or payload.get("company_name"))
    lead_intent = _clean(payload.get("intent") or payload.get("lead_intent")).lower()

    if not lead_name:
        raise ValueError("lead_name is required")
    if not lead_email:
        raise ValueError("lead_email is required")
    if not company_name:
        raise ValueError("company_name is required")
    if not lead_intent:
        raise ValueError("lead_intent is required")

    lead_id = _clean(payload.get("lead_id")) or str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    created_at = _clean(payload.get("captured_at") or payload.get("created_at")) or now

    intent_category = "service" if lead_intent in SERVICE_INTENTS else "content"
    follow_up_priority = "high" if intent_category == "service" else "normal"
    recommended_handoff_channel = "calendar_or_email" if intent_category == "service" else "email_nurture"
    recommended_next_step = (
        "Offer a consultation or shortlist review and confirm the buying timeline."
        if intent_category == "service"
        else "Send the requested asset and invite a reply with the evaluation context."
    )

    attribution = {k: _clean(payload.get(k)) or None for k in (
        "entry_page", "entry_url", "cta_surface", "cta_variant", "cta_label",
        "vendor_name", "vendor_website", "vendor_category",
        "referrer", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    )}

    return {
        "lead_id": lead_id,
        "capture_version": _clean(payload.get("capture_version")) or DEFAULT_CAPTURE_VERSION,
        "lead_name": lead_name,
        "lead_email": lead_email,
        "company_name": company_name,
        "lead_intent": lead_intent,
        "intent_category": intent_category,
        "follow_up_priority": follow_up_priority,
        "notes": _clean(payload.get("notes")) or None,
        **attribution,
        "attribution_context": {k: v for k, v in attribution.items() if v},
        "follow_up_status": "new",
        "follow_up_owner": DEFAULT_FOLLOW_UP_OWNER,
        "recommended_handoff_channel": recommended_handoff_channel,
        "recommended_next_step": recommended_next_step,
        "follow_up_notes": None,
        "created_at": created_at,
        "updated_at": created_at,
    }


def _upsert(row: dict) -> None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")

    import urllib.request

    body = json.dumps([row]).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/rest/v1/{LEAD_CAPTURE_TABLE}",
        data=body,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status not in (200, 201):
            raise RuntimeError(f"Supabase returned {resp.status}")


def _clean(value: object) -> str:
    return str(value or "").strip()


def _normalize_email(value: object) -> str:
    email = _clean(value).lower()
    return email if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) else ""
