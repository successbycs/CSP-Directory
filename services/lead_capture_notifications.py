"""Lead-capture notification helpers routed through n8n workflows."""

from __future__ import annotations

import logging
from typing import Any, Callable

from services import n8n_client

logger = logging.getLogger(__name__)

BOOK_TIME_URL = "https://meetings-ap1.hubspot.com/christopher-sparshott"


def build_lead_thank_you_message(intent: str) -> str:
    """Return the user-facing thank-you message for one canonical intent."""
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


def build_discord_notification_content(lead_row: dict[str, Any]) -> str:
    """Return a concise Discord notification message for one persisted lead row."""
    lead_name = str(lead_row.get("lead_name") or "Unknown lead").strip()
    company_name = str(lead_row.get("company_name") or "Unknown company").strip()
    lead_email = str(lead_row.get("lead_email") or "").strip()
    intent = str(lead_row.get("lead_intent") or "").strip()
    entry_page = str(lead_row.get("entry_page") or "landing.html").strip()

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
            f"Lead: {lead_name}",
            f"Company: {company_name}",
            f"Email: {lead_email}",
            f"Intent: {intent_line}",
            f"Entry page: {entry_page}",
            action_line,
        ]
    )


def build_lead_capture_notification_payload(lead_row: dict[str, Any]) -> dict[str, Any]:
    """Build the webhook payload sent to the n8n lead-capture workflow."""
    intent = str(lead_row.get("lead_intent") or "").strip()
    return {
        "lead": lead_row,
        "lead_id": lead_row.get("lead_id"),
        "lead_name": lead_row.get("lead_name"),
        "lead_email": lead_row.get("lead_email"),
        "company_name": lead_row.get("company_name"),
        "lead_intent": intent,
        "intent_category": lead_row.get("intent_category"),
        "thank_you_message": build_lead_thank_you_message(intent),
        "booking_url": BOOK_TIME_URL,
        "discord_content": build_discord_notification_content(lead_row),
    }


def trigger_lead_capture_notification(
    lead_row: dict[str, Any],
    *,
    post_webhook_fn: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Trigger the n8n lead-capture notification workflow."""
    webhook_post = post_webhook_fn or n8n_client.post_webhook
    payload = build_lead_capture_notification_payload(lead_row)
    logger.info("Triggering n8n lead-capture notification for %s", lead_row.get("lead_email"))
    response = webhook_post(n8n_client.WEBHOOK_LEAD_CAPTURE_INTAKE, payload)
    return {
        "triggered": True,
        "webhook": n8n_client.WEBHOOK_LEAD_CAPTURE_INTAKE,
        "thank_you_message": payload["thank_you_message"],
        "booking_url": BOOK_TIME_URL,
        "n8n_response": response,
    }
