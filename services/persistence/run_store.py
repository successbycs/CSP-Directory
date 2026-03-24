"""Persistence helpers for pipeline run records."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from services.persistence import supabase_client

if TYPE_CHECKING:
    from supabase import Client


PIPELINE_RUNS_TABLE = "pipeline_runs"
PIPELINE_RUN_COLUMNS = (
    "run_id",
    "started_at",
    "completed_at",
    "queries_executed",
    "candidate_count",
    "queued_count",
    "skipped_existing_count",
    "enriched_count",
    "dropped_count",
    "llm_success_count",
    "llm_fallback_count",
    "run_status",
    "error_summary",
)


def upsert_run_record(run_record: dict[str, object], client: "Client | None" = None) -> dict[str, Any]:
    """Persist one pipeline run record using run_id as the conflict key."""
    supabase = client or supabase_client.get_supabase_client()
    row = build_run_row(run_record)
    supabase.table(PIPELINE_RUNS_TABLE).upsert(row, on_conflict="run_id").execute()
    return row


def list_run_records(*, limit: int = 100, client: "Client | None" = None) -> list[dict[str, Any]]:
    """Return recent pipeline run records ordered by newest first."""
    supabase = client or supabase_client.get_supabase_client()
    response = (
        supabase.table(PIPELINE_RUNS_TABLE)
        .select(",".join(PIPELINE_RUN_COLUMNS))
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(response.data or [])


def build_run_row(run_record: dict[str, object]) -> dict[str, Any]:
    """Normalize one pipeline run record into the persisted shape."""
    return {
        "run_id": str(run_record.get("run_id", "")).strip(),
        "started_at": str(run_record.get("started_at", "")).strip() or None,
        "completed_at": str(run_record.get("completed_at", "")).strip() or None,
        "queries_executed": str(
            run_record.get("queries_executed")
            or run_record.get("query")
            or ""
        ).strip()
        or None,
        "candidate_count": _coerce_int(run_record.get("candidate_count")),
        "queued_count": _coerce_int(run_record.get("queued_count")),
        "skipped_existing_count": _coerce_int(run_record.get("skipped_existing_count")),
        "enriched_count": _coerce_int(run_record.get("enriched_count")),
        "dropped_count": _coerce_int(run_record.get("dropped_count")),
        "llm_success_count": _coerce_int(run_record.get("llm_success_count")),
        "llm_fallback_count": _coerce_int(run_record.get("llm_fallback_count")),
        "run_status": str(run_record.get("run_status", "")).strip() or None,
        "error_summary": str(run_record.get("error_summary", "")).strip() or None,
    }


def is_run_store_unavailable_error(error: Exception) -> bool:
    """Return True when the pipeline run table is unavailable."""
    error_code = getattr(error, "code", "")
    if not error_code:
        for arg in getattr(error, "args", ()):
            if isinstance(arg, dict) and isinstance(arg.get("code"), str):
                error_code = arg["code"]
                break
    error_message = str(error).lower()
    if error_code in {"PGRST204", "PGRST205"}:
        return True
    if f"could not find the '{PIPELINE_RUNS_TABLE}' column" in error_message:
        return True
    if supabase_client.is_persistence_unavailable_error(error):
        return True
    return PIPELINE_RUNS_TABLE in error_message and ("does not exist" in error_message or "schema cache" in error_message)


def _coerce_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
