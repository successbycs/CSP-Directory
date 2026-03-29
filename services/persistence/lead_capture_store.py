"""Persistence helpers for lead capture, attribution, and follow-up operations."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from services.extraction.identity import normalize_email_address, normalize_vendor_website
from services import lead_capture_notifications
from services.persistence import supabase_client

if TYPE_CHECKING:
    from supabase import Client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEAD_CAPTURE_RESULTS_PATH = PROJECT_ROOT / "outputs" / "lead_capture_dataset.json"
LEAD_CAPTURE_TABLE = "lead_captures"
LEAD_CAPTURE_COLUMNS = (
    "lead_id",
    "capture_version",
    "lead_name",
    "lead_email",
    "company_name",
    "lead_intent",
    "intent_category",
    "follow_up_priority",
    "notes",
    "entry_page",
    "entry_url",
    "cta_surface",
    "cta_variant",
    "cta_label",
    "vendor_name",
    "vendor_website",
    "vendor_category",
    "referrer",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "attribution_context",
    "follow_up_status",
    "follow_up_owner",
    "recommended_handoff_channel",
    "recommended_next_step",
    "follow_up_notes",
    "created_at",
    "updated_at",
)
FOLLOW_UP_UPDATE_COLUMNS = (
    "follow_up_status",
    "follow_up_owner",
    "follow_up_notes",
)
DEFAULT_CAPTURE_VERSION = "m24a.v1"
DEFAULT_FOLLOW_UP_OWNER = "fractional-head-of-cs"
logger = logging.getLogger(__name__)


def create_lead_capture(
    payload: dict[str, object],
    *,
    client: "Client | None" = None,
    results_path: Path | None = None,
) -> dict[str, Any]:
    """Persist one lead capture row, falling back to a local dataset when needed."""
    row = build_lead_capture_row(payload)
    results_path = results_path or DEFAULT_LEAD_CAPTURE_RESULTS_PATH
    if supabase_client.is_configured():
        try:
            supabase = client or supabase_client.get_supabase_client()
            supabase.table(LEAD_CAPTURE_TABLE).upsert(row, on_conflict="lead_id").execute()
            return row
        except Exception as error:
            if not (
                is_lead_capture_store_unavailable_error(error)
                or supabase_client.is_persistence_unavailable_error(error)
            ):
                raise
            logger.warning("Lead capture persistence unavailable, falling back to local dataset: %s", error)
    return _write_local_lead_capture(row, results_path=results_path)


def list_lead_captures(
    *,
    limit: int = 200,
    client: "Client | None" = None,
    results_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return persisted lead captures ordered by newest first."""
    results_path = results_path or DEFAULT_LEAD_CAPTURE_RESULTS_PATH
    if supabase_client.is_configured():
        try:
            supabase = client or supabase_client.get_supabase_client()
            response = (
                supabase.table(LEAD_CAPTURE_TABLE)
                .select(",".join(LEAD_CAPTURE_COLUMNS))
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return list(response.data or [])
        except Exception as error:
            if not (
                is_lead_capture_store_unavailable_error(error)
                or supabase_client.is_persistence_unavailable_error(error)
            ):
                raise
            logger.warning("Lead capture listing unavailable, falling back to local dataset: %s", error)
    rows = read_local_lead_captures(results_path)
    return _sort_lead_captures(rows)[:limit]


def update_lead_follow_up(
    lead_id: str,
    *,
    follow_up_status: str | None = None,
    follow_up_owner: str | None = None,
    follow_up_notes: str | None = None,
    client: "Client | None" = None,
    results_path: Path | None = None,
) -> dict[str, Any]:
    """Update the follow-up state for one lead."""
    normalized_lead_id = str(lead_id or "").strip()
    if not normalized_lead_id:
        raise ValueError("lead_id is required")

    updates = build_follow_up_update(
        follow_up_status=follow_up_status,
        follow_up_owner=follow_up_owner,
        follow_up_notes=follow_up_notes,
    )
    if not updates:
        raise ValueError("At least one follow-up field is required")

    results_path = results_path or DEFAULT_LEAD_CAPTURE_RESULTS_PATH
    if supabase_client.is_configured():
        try:
            supabase = client or supabase_client.get_supabase_client()
            response = (
                supabase.table(LEAD_CAPTURE_TABLE)
                .update(updates)
                .eq("lead_id", normalized_lead_id)
                .execute()
            )
            updated_rows = list(response.data or [])
            if not updated_rows:
                raise LookupError(f"Lead {normalized_lead_id!r} was not found")
            return updated_rows[0]
        except Exception as error:
            if isinstance(error, LookupError):
                raise
            if not (
                is_lead_capture_store_unavailable_error(error)
                or supabase_client.is_persistence_unavailable_error(error)
            ):
                raise
            logger.warning("Lead follow-up update unavailable, falling back to local dataset: %s", error)
    return _update_local_lead_follow_up(normalized_lead_id, updates, results_path=results_path)


def export_lead_capture_dashboard(
    *,
    limit: int = 200,
    client: "Client | None" = None,
    results_path: Path | None = None,
) -> dict[str, Any]:
    """Return lead rows plus lightweight metrics for the internal dashboard."""
    items = list_lead_captures(limit=limit, client=client, results_path=results_path)
    return {
        "metrics": build_lead_capture_metrics(items),
        "items": items,
    }


def build_lead_capture_row(
    payload: dict[str, object],
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Normalize a public lead submission into the persisted contract."""
    lead_name = _clean_text(payload.get("name") or payload.get("lead_name"))
    lead_email = normalize_email_address(payload.get("email") or payload.get("lead_email"))
    company_name = _clean_text(payload.get("company") or payload.get("company_name"))
    lead_intent = _normalize_intent(payload.get("intent") or payload.get("lead_intent"))
    if not lead_name:
        raise ValueError("lead_name is required")
    if not lead_email:
        raise ValueError("lead_email is required")
    if not company_name:
        raise ValueError("company_name is required")
    if not lead_intent:
        raise ValueError("lead_intent is required")

    normalized_created_at = _normalize_timestamp(created_at or payload.get("captured_at") or payload.get("created_at"))
    normalized_updated_at = normalized_created_at
    lead_id = _clean_text(payload.get("lead_id")) or str(uuid4())
    intent_category = classify_intent_category(lead_intent)
    follow_up_priority = "high" if intent_category == "service" else "normal"
    recommended_handoff_channel = _recommended_handoff_channel(lead_intent)
    recommended_next_step = _recommended_next_step(lead_intent)
    entry_page = _clean_text(payload.get("entry_page"))
    entry_url = _clean_text(payload.get("entry_url"))
    cta_surface = _clean_text(payload.get("cta_surface"))
    cta_variant = _clean_text(payload.get("cta_variant"))
    cta_label = _clean_text(payload.get("cta_label"))
    vendor_name = _clean_text(payload.get("vendor_name"))
    vendor_website = normalize_vendor_website(payload.get("vendor_website")) or None
    vendor_category = _clean_text(payload.get("vendor_category"))
    referrer = _clean_text(payload.get("referrer"))
    utm_source = _clean_text(payload.get("utm_source"))
    utm_medium = _clean_text(payload.get("utm_medium"))
    utm_campaign = _clean_text(payload.get("utm_campaign"))
    utm_term = _clean_text(payload.get("utm_term"))
    utm_content = _clean_text(payload.get("utm_content"))

    attribution_context = {
        "entry_page": entry_page,
        "entry_url": entry_url,
        "cta_surface": cta_surface,
        "cta_variant": cta_variant,
        "cta_label": cta_label,
        "vendor_name": vendor_name,
        "vendor_website": vendor_website,
        "vendor_category": vendor_category,
        "referrer": referrer,
        "utm_source": utm_source,
        "utm_medium": utm_medium,
        "utm_campaign": utm_campaign,
        "utm_term": utm_term,
        "utm_content": utm_content,
    }

    return {
        "lead_id": lead_id,
        "capture_version": _clean_text(payload.get("capture_version")) or DEFAULT_CAPTURE_VERSION,
        "lead_name": lead_name,
        "lead_email": lead_email,
        "company_name": company_name,
        "lead_intent": lead_intent,
        "intent_category": intent_category,
        "follow_up_priority": follow_up_priority,
        "notes": _clean_text(payload.get("notes")) or None,
        "entry_page": entry_page or None,
        "entry_url": entry_url or None,
        "cta_surface": cta_surface or None,
        "cta_variant": cta_variant or None,
        "cta_label": cta_label or None,
        "vendor_name": vendor_name or None,
        "vendor_website": vendor_website,
        "vendor_category": vendor_category or None,
        "referrer": referrer or None,
        "utm_source": utm_source or None,
        "utm_medium": utm_medium or None,
        "utm_campaign": utm_campaign or None,
        "utm_term": utm_term or None,
        "utm_content": utm_content or None,
        "attribution_context": {key: value for key, value in attribution_context.items() if value},
        "follow_up_status": _normalize_follow_up_status(payload.get("follow_up_status")) or "new",
        "follow_up_owner": _clean_text(payload.get("follow_up_owner")) or DEFAULT_FOLLOW_UP_OWNER,
        "recommended_handoff_channel": recommended_handoff_channel,
        "recommended_next_step": recommended_next_step,
        "follow_up_notes": _clean_text(payload.get("follow_up_notes")) or None,
        "created_at": normalized_created_at,
        "updated_at": normalized_updated_at,
    }


def build_follow_up_update(
    *,
    follow_up_status: str | None = None,
    follow_up_owner: str | None = None,
    follow_up_notes: str | None = None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    """Build a normalized follow-up update payload."""
    updates: dict[str, Any] = {}
    normalized_status = _normalize_follow_up_status(follow_up_status)
    if normalized_status:
        updates["follow_up_status"] = normalized_status
    normalized_owner = _clean_text(follow_up_owner)
    if normalized_owner:
        updates["follow_up_owner"] = normalized_owner
    normalized_notes = _clean_text(follow_up_notes)
    if normalized_notes:
        updates["follow_up_notes"] = normalized_notes
    if updates:
        updates["updated_at"] = _normalize_timestamp(updated_at)
    return updates


def build_lead_capture_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return lightweight attribution and follow-up metrics for admin review."""
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("follow_up_status") or "new").strip() or "new"
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "lead_count": len(rows),
        "service_lead_count": sum(1 for row in rows if row.get("intent_category") == "service"),
        "content_lead_count": sum(1 for row in rows if row.get("intent_category") == "content"),
        "qualified_lead_count": status_counts.get("qualified", 0),
        "status_counts": status_counts,
    }


def read_local_lead_captures(results_path: Path | None = None) -> list[dict[str, Any]]:
    """Read locally persisted lead captures."""
    results_path = results_path or DEFAULT_LEAD_CAPTURE_RESULTS_PATH
    if not results_path.exists():
        return []
    try:
        payload = json.loads(results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def is_lead_capture_store_unavailable_error(error: Exception) -> bool:
    """Return True when the lead capture table is unavailable."""
    error_message = str(error).lower()
    error_code = getattr(error, "code", "")
    if error_code in {"PGRST204", "PGRST205"}:
        return True
    if f"column {LEAD_CAPTURE_TABLE}." in error_message and "does not exist" in error_message:
        return True
    if f"could not find the '{LEAD_CAPTURE_TABLE}' column" in error_message:
        return True
    return LEAD_CAPTURE_TABLE in error_message and ("does not exist" in error_message or "schema cache" in error_message)


def classify_intent_category(intent: str) -> str:
    """Map one lead intent to a content or service motion."""
    if intent in {"shortlist", "advisory", "advisory_follow_up", "audit", "fractional-leadership"}:
        return "service"
    return "content"


def _write_local_lead_capture(row: dict[str, Any], *, results_path: Path) -> dict[str, Any]:
    rows = read_local_lead_captures(results_path)
    rows = [existing_row for existing_row in rows if existing_row.get("lead_id") != row["lead_id"]]
    rows.append(row)
    _write_local_rows(rows, results_path)
    return row


def _update_local_lead_follow_up(
    lead_id: str,
    updates: dict[str, Any],
    *,
    results_path: Path,
) -> dict[str, Any]:
    rows = read_local_lead_captures(results_path)
    for index, row in enumerate(rows):
        if str(row.get("lead_id") or "").strip() != lead_id:
            continue
        updated_row = {**row, **updates}
        rows[index] = updated_row
        _write_local_rows(rows, results_path)
        return updated_row
    raise LookupError(f"Lead {lead_id!r} was not found")


def _write_local_rows(rows: list[dict[str, Any]], results_path: Path) -> None:
    results_path.parent.mkdir(parents=True, exist_ok=True)
    sorted_rows = _sort_lead_captures(rows)
    results_path.write_text(json.dumps(sorted_rows, indent=2), encoding="utf-8")


def _sort_lead_captures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: str(row.get("created_at") or ""), reverse=True)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_intent(value: object) -> str:
    normalized = _clean_text(value).lower()
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
    if classify_intent_category(intent) == "service":
        return "calendar_or_email"
    return "email_nurture"


def _recommended_next_step(intent: str) -> str:
    if intent == "advisory_follow_up":
        return (
            "Thank the buyer for requesting SuccessByCS help, invite them to book time with Chris at "
            f"{lead_capture_notifications.BOOK_TIME_URL}, and confirm the evaluation context."
        )
    if intent == "browse_directory":
        return (
            "Thank the buyer for requesting directory access, encourage them to browse the vendor scan, "
            f"and include the booking link for Chris: {lead_capture_notifications.BOOK_TIME_URL}."
        )
    if classify_intent_category(intent) == "service":
        return "Offer a consultation or shortlist review and confirm the buying timeline."
    return "Send the requested asset and invite a reply with the evaluation context."


def _normalize_follow_up_status(value: object) -> str:
    normalized = _clean_text(value).lower().replace(" ", "_")
    if normalized in {"new", "in_progress", "contacted", "qualified", "closed"}:
        return normalized
    return ""


def _normalize_timestamp(value: object) -> str:
    text = _clean_text(value)
    if text:
        return text
    return datetime.now(timezone.utc).isoformat()
