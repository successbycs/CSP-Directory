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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

LEAD_CAPTURE_TABLE = "lead_captures"
DEFAULT_CAPTURE_VERSION = "m24a.v1"
DEFAULT_FOLLOW_UP_OWNER = "fractional-head-of-cs"
BOOK_TIME_URL = "https://meetings-ap1.hubspot.com/christopher-sparshott"
LEAD_CAPTURE_WEBHOOK = "csp-lead-capture-intake"
SERVICE_INTENTS = {"shortlist", "advisory", "advisory_follow_up", "audit", "fractional_leadership"}


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

        storage_error = None
        storage_saved = False
        try:
            _upsert(row)
            storage_saved = True
        except Exception as error:
            storage_error = str(error)

        notification = _trigger_n8n_lead_notification(row)
        notification_error = notification.get("error") if isinstance(notification, dict) else None

        if not storage_saved and notification_error:
            self._respond(
                502,
                {
                    "ok": False,
                    "error": "lead_capture_failed",
                    "storage_error": storage_error,
                    "notification": notification,
                },
            )
            return

        self._respond(
            200,
            {
                "ok": True,
                "lead": row,
                "storage_saved": storage_saved,
                "storage_error": storage_error,
                "notification": notification,
                "thank_you_message": notification.get("thank_you_message") if isinstance(notification, dict) else None,
                "booking_url": notification.get("booking_url") if isinstance(notification, dict) else None,
            },
        )

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
    lead_intent = _normalize_intent(payload.get("intent") or payload.get("lead_intent"))

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
    recommended_handoff_channel = _recommended_handoff_channel(lead_intent)
    recommended_next_step = _recommended_next_step(lead_intent)

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
    key = _resolve_supabase_key()
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


def _resolve_supabase_key() -> str:
    for env_name in ("SUPABASE_SERVICE_ROLE_KEY", "SERVICE_ROLE_KEY", "SUPABASE_KEY", "SUPABASE_ANON_KEY"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return ""


def _trigger_n8n_lead_notification(row: dict) -> dict:
    base_url = os.environ.get("N8N_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return {
            "triggered": False,
            "skipped": True,
            "error": "N8N_BASE_URL not set",
            "thank_you_message": _thank_you_message(row["lead_intent"]),
            "booking_url": BOOK_TIME_URL,
        }

    import urllib.request
    import urllib.error

    payload = {
        "lead": row,
        "lead_id": row.get("lead_id"),
        "lead_name": row.get("lead_name"),
        "lead_email": row.get("lead_email"),
        "company_name": row.get("company_name"),
        "lead_intent": row.get("lead_intent"),
        "intent_category": row.get("intent_category"),
        "thank_you_message": _thank_you_message(row["lead_intent"]),
        "booking_url": BOOK_TIME_URL,
        "discord_content": _discord_notification_content(row),
    }
    discord_webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if discord_webhook_url:
        payload["discord_webhook_url"] = discord_webhook_url
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/webhook/{LEAD_CAPTURE_WEBHOOK}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            response_text = resp.read().decode("utf-8") if resp else ""
            parsed = json.loads(response_text) if response_text else {}
    except (urllib.error.URLError, json.JSONDecodeError) as error:
        return {
            "triggered": False,
            "error": str(error),
            "thank_you_message": payload["thank_you_message"],
            "booking_url": BOOK_TIME_URL,
        }
    if not isinstance(parsed, dict):
        parsed = {}
    parsed.setdefault("triggered", True)
    parsed.setdefault("thank_you_message", payload["thank_you_message"])
    parsed.setdefault("booking_url", BOOK_TIME_URL)
    return parsed


def _normalize_intent(value: object) -> str:
    normalized = _clean(value).lower()
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    aliases = {
        "directory": "browse_directory",
        "browse_directory": "browse_directory",
        "browse_the_vendor_directory": "browse_directory",
        "vendor_directory": "browse_directory",
        "advisory_follow_up": "advisory_follow_up",
        "advisory_follow_up_with_successbycs": "advisory_follow_up",
    }
    return aliases.get(slug, slug)


def _recommended_handoff_channel(intent: str) -> str:
    if intent == "advisory_follow_up":
        return "calendar_or_email"
    if intent == "browse_directory":
        return "directory_access"
    if intent in SERVICE_INTENTS:
        return "calendar_or_email"
    return "email_nurture"


def _recommended_next_step(intent: str) -> str:
    if intent == "advisory_follow_up":
        return (
            "Thank the buyer for requesting SuccessByCS help, invite them to book time with Chris at "
            f"{BOOK_TIME_URL}, and confirm the evaluation context."
        )
    if intent == "browse_directory":
        return (
            "Thank the buyer for requesting directory access, encourage them to browse the vendor scan, "
            f"and include the booking link for Chris."
        )
    if intent in SERVICE_INTENTS:
        return "Offer a consultation or shortlist review and confirm the buying timeline."
    return "Send the requested asset and invite a reply with the evaluation context."


def _thank_you_message(intent: str) -> str:
    if intent == "advisory_follow_up":
        return (
            "Thanks for reaching out to SuccessByCS. We have your advisory follow-up request. "
            f"You can book time with Chris here: {BOOK_TIME_URL}"
        )
    if intent == "browse_directory":
        return (
            "Thanks for requesting access to the vendor directory. You can browse the vendor scan now, "
            f"and if you want help interpreting the market, book time with Chris here: {BOOK_TIME_URL}"
        )
    if intent in {"shortlist", "advisory"}:
        return (
            "Thanks for sharing your evaluation context. We have your request and you can also book time "
            f"with Chris here: {BOOK_TIME_URL}"
        )
    return (
        "Thanks for reaching out to SuccessByCS. "
        f"If you want to talk through the next step, book time with Chris here: {BOOK_TIME_URL}"
    )


def _discord_notification_content(row: dict) -> str:
    intent = str(row.get("lead_intent") or "")
    if intent == "advisory_follow_up":
        intent_line = "Advisory follow-up with SuccessByCS"
        action_line = f"Book time with Chris: {BOOK_TIME_URL}"
    elif intent == "browse_directory":
        intent_line = "Browse the vendor directory"
        action_line = f"Optional advisory link: {BOOK_TIME_URL}"
    else:
        intent_line = intent.replace("_", " ") or "Lead capture"
        action_line = f"Follow-up link: {BOOK_TIME_URL}"

    return "\n".join(
        [
            "New CSP lead captured",
            f"Lead: {row.get('lead_name') or 'Unknown lead'}",
            f"Company: {row.get('company_name') or 'Unknown company'}",
            f"Email: {row.get('lead_email') or ''}",
            f"Intent: {intent_line}",
            f"Entry page: {row.get('entry_page') or 'landing.html'}",
            action_line,
        ]
    )


def _clean(value: object) -> str:
    return str(value or "").strip()


def _normalize_email(value: object) -> str:
    email = _clean(value).lower()
    return email if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) else ""
