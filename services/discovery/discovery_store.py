"""Persistence helpers for Phase 1 discovery candidate records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from services.persistence import supabase_client

if TYPE_CHECKING:
    from supabase import Client


DISCOVERY_CANDIDATE_TABLE = "discovery_candidates"
DISCOVERY_CANDIDATE_COLUMNS = (
    "candidate_domain",
    "candidate_title",
    "candidate_description",
    "source_query",
    "source_engine",
    "source_rank",
    "discovered_at",
    "candidate_status",
    "drop_reason",
    "updated_at",
)


def upsert_candidate_records(
    candidate_records: list[dict[str, object]],
    client: "Client | None" = None,
) -> list[dict[str, Any]]:
    """Persist Phase 1 candidate records for later review and reruns."""
    if not candidate_records:
        return []

    supabase = client or supabase_client.get_supabase_client()
    rows = [build_candidate_row(record) for record in candidate_records if record.get("candidate_domain")]
    if not rows:
        return []

    supabase.table(DISCOVERY_CANDIDATE_TABLE).upsert(rows, on_conflict="candidate_domain").execute()
    return rows


def list_candidate_records(
    *,
    limit: int = 200,
    client: "Client | None" = None,
) -> list[dict[str, Any]]:
    """Return persisted discovery candidates ordered by most recent discovery."""
    supabase = client or supabase_client.get_supabase_client()
    response = (
        supabase.table(DISCOVERY_CANDIDATE_TABLE)
        .select(",".join(DISCOVERY_CANDIDATE_COLUMNS[:-1]))
        .order("discovered_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(response.data or [])


def build_candidate_row(candidate_record: dict[str, object]) -> dict[str, Any]:
    """Normalize one candidate record into the persisted discovery shape."""
    discovered_at = str(candidate_record.get("discovered_at", "")).strip() or datetime.now(timezone.utc).isoformat()
    candidate_status = str(
        candidate_record.get("candidate_status") or candidate_record.get("status") or "new"
    ).strip()

    return {
        "candidate_domain": str(candidate_record.get("candidate_domain", "")).strip(),
        "candidate_title": str(candidate_record.get("candidate_title", "")).strip() or None,
        "candidate_description": str(candidate_record.get("candidate_description", "")).strip() or None,
        "source_query": str(candidate_record.get("source_query", "")).strip() or None,
        "source_engine": str(candidate_record.get("source_engine", "")).strip() or None,
        "source_rank": _coerce_int(candidate_record.get("source_rank")),
        "discovered_at": discovered_at,
        "candidate_status": candidate_status,
        "drop_reason": str(candidate_record.get("drop_reason", "")).strip() or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def is_discovery_store_unavailable_error(error: Exception) -> bool:
    """Return True when the discovery candidate table is unavailable."""
    error_code = getattr(error, "code", "")
    if not error_code:
        for arg in getattr(error, "args", ()):
            if isinstance(arg, dict) and isinstance(arg.get("code"), str):
                error_code = arg["code"]
                break
    error_message = str(error).lower()
    if error_code in {"PGRST204", "PGRST205"}:
        return True
    if f"could not find the '{DISCOVERY_CANDIDATE_TABLE}' column" in error_message:
        return True
    if supabase_client.is_persistence_unavailable_error(error):
        return True
    return DISCOVERY_CANDIDATE_TABLE in error_message and ("does not exist" in error_message or "schema cache" in error_message)


def _coerce_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
