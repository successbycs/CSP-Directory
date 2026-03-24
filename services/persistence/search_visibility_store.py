"""Persistence helpers for buyer-role search query and ranking visibility data."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import hashlib
from typing import TYPE_CHECKING, Any, Iterable

from services.extraction.vendor_intel import (
    normalize_icp_buyer_profiles,
    normalize_vendor_website,
    normalize_website_url,
)
from services.persistence import supabase_client

if TYPE_CHECKING:
    from supabase import Client


BUYER_SEARCH_QUERY_TABLE = "buyer_search_queries"
BUYER_SEARCH_RESULT_TABLE = "buyer_search_results"
BUYER_SEARCH_QUERY_GENERATION_VERSION = "m23.v1"

BUYER_SEARCH_QUERY_COLUMNS = (
    "query_signature",
    "source_vendor_name",
    "source_vendor_website",
    "buyer_role",
    "search_channel",
    "search_provider",
    "query_text",
    "persona_confidence",
    "evidence",
    "query_generation_version",
    "query_generation_context",
    "generated_at",
)

BUYER_SEARCH_RESULT_COLUMNS = (
    "query_signature",
    "buyer_role",
    "search_channel",
    "search_provider",
    "query_text",
    "observed_rank",
    "surfaced_vendor_name",
    "surfaced_vendor_website",
    "source_url",
    "response_reference",
    "visibility_score",
    "run_timestamp",
)


def get_buyer_search_query_columns() -> tuple[str, ...]:
    """Return the columns required for buyer-role query persistence."""
    return BUYER_SEARCH_QUERY_COLUMNS


def get_buyer_search_result_columns() -> tuple[str, ...]:
    """Return the columns required for ranked visibility persistence."""
    return BUYER_SEARCH_RESULT_COLUMNS


def list_buyer_search_queries(*, limit: int = 500, client: "Client | None" = None) -> list[dict[str, Any]]:
    """Return persisted buyer-role query rows."""
    supabase = client or supabase_client.get_supabase_client()
    response = (
        supabase.table(BUYER_SEARCH_QUERY_TABLE)
        .select(",".join(BUYER_SEARCH_QUERY_COLUMNS))
        .order("generated_at", desc=True)
        .order("buyer_role")
        .order("search_channel")
        .order("query_text")
        .limit(limit)
        .execute()
    )
    return _sort_buyer_search_queries(list(response.data or []))


def list_buyer_search_results(*, limit: int = 1000, client: "Client | None" = None) -> list[dict[str, Any]]:
    """Return persisted ranked search visibility rows."""
    supabase = client or supabase_client.get_supabase_client()
    response = (
        supabase.table(BUYER_SEARCH_RESULT_TABLE)
        .select(",".join(BUYER_SEARCH_RESULT_COLUMNS))
        .order("run_timestamp", desc=True)
        .order("buyer_role")
        .order("search_channel")
        .order("query_text")
        .order("observed_rank")
        .limit(limit)
        .execute()
    )
    return _sort_buyer_search_results(list(response.data or []))


def build_query_signature(
    *,
    source_vendor_website: str,
    buyer_role: str,
    search_channel: str,
    search_provider: str,
    query_text: str,
) -> str:
    """Build a deterministic query identity for cross-table persistence."""
    normalized_vendor_website = normalize_vendor_website(source_vendor_website)
    normalized = "|".join(
        [
            normalized_vendor_website,
            buyer_role.strip().lower(),
            search_channel.strip().lower(),
            search_provider.strip().lower(),
            query_text.strip().lower(),
        ]
    )
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def build_buyer_search_query_rows(
    vendor_profiles: Iterable[object],
    *,
    generated_at: str | None = None,
) -> list[dict[str, Any]]:
    """Expand vendor buyer-persona profiles into persisted google/geo query rows."""
    normalized_generated_at = _normalize_timestamp(generated_at)
    rows: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()

    for vendor_profile in vendor_profiles:
        profile_row = _coerce_vendor_profile(vendor_profile)
        source_vendor_name = str(profile_row.get("name") or profile_row.get("vendor_name") or "").strip()
        source_vendor_website = normalize_vendor_website(profile_row.get("website"))
        if not source_vendor_name or not source_vendor_website:
            continue

        buyer_profiles = normalize_icp_buyer_profiles(profile_row.get("icp_buyer"))
        for buyer_profile in buyer_profiles:
            buyer_role = str(buyer_profile.get("persona") or "").strip()
            if not buyer_role:
                continue

            for search_channel, search_provider, queries in (
                ("google", "google", buyer_profile.get("google_queries")),
                ("geo", "openai", buyer_profile.get("geo_queries")),
            ):
                for query_text in _string_list(queries):
                    query_signature = build_query_signature(
                        source_vendor_website=source_vendor_website,
                        buyer_role=buyer_role,
                        search_channel=search_channel,
                        search_provider=search_provider,
                        query_text=query_text,
                    )
                    if query_signature in seen_signatures:
                        continue

                    rows.append(
                        {
                            "query_signature": query_signature,
                            "source_vendor_name": source_vendor_name,
                            "source_vendor_website": source_vendor_website,
                            "buyer_role": buyer_role,
                            "search_channel": search_channel,
                            "search_provider": search_provider,
                            "query_text": query_text,
                            "persona_confidence": str(buyer_profile.get("confidence") or "").strip(),
                            "evidence": _string_list(buyer_profile.get("evidence")),
                            "query_generation_version": BUYER_SEARCH_QUERY_GENERATION_VERSION,
                            "query_generation_context": {
                                "source": "icp_buyer",
                                "persona": buyer_role,
                                "query_field": f"{search_channel}_queries",
                                "search_provider": search_provider,
                            },
                            "generated_at": normalized_generated_at,
                        }
                    )
                    seen_signatures.add(query_signature)

    return rows


def upsert_buyer_search_queries_from_vendor_profiles(
    vendor_profiles: Iterable[object],
    *,
    generated_at: str | None = None,
    client: "Client | None" = None,
) -> list[dict[str, Any]]:
    """Persist generated google and geo prompts for each buyer-role profile."""
    rows = build_buyer_search_query_rows(vendor_profiles, generated_at=generated_at)
    if not rows:
        return []

    supabase = client or supabase_client.get_supabase_client()
    response = (
        supabase.table(BUYER_SEARCH_QUERY_TABLE)
        .upsert(rows, on_conflict="query_signature")
        .execute()
    )
    return list(response.data or rows)


def calculate_visibility_score(observed_rank: int) -> int:
    """Return a simple rank-derived visibility score."""
    if observed_rank <= 0:
        raise ValueError("observed_rank must be greater than zero")
    return max(0, 100 - ((observed_rank - 1) * 15))


def build_buyer_search_result_rows(
    query_row: dict[str, Any],
    ranked_results: Iterable[dict[str, Any]],
    *,
    run_timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Build ranked result rows linked to one persisted buyer-role query."""
    query_signature = str(query_row.get("query_signature") or "").strip()
    buyer_role = str(query_row.get("buyer_role") or "").strip()
    search_channel = str(query_row.get("search_channel") or "").strip().lower()
    search_provider = str(query_row.get("search_provider") or "").strip().lower()
    query_text = str(query_row.get("query_text") or "").strip()
    if not all((query_signature, buyer_role, search_channel, query_text)):
        raise ValueError("query_row must include query_signature, buyer_role, search_channel, and query_text")

    normalized_run_timestamp = _normalize_timestamp(run_timestamp)
    rows: list[dict[str, Any]] = []
    for ranked_result in ranked_results:
        observed_rank = int(ranked_result.get("observed_rank") or ranked_result.get("rank") or 0)
        surfaced_vendor_name = str(
            ranked_result.get("surfaced_vendor_name") or ranked_result.get("vendor_name") or ""
        ).strip()
        if observed_rank <= 0 or not surfaced_vendor_name:
            continue

        raw_visibility_score = ranked_result.get("visibility_score")
        visibility_score = (
            float(raw_visibility_score)
            if raw_visibility_score is not None
            else float(calculate_visibility_score(observed_rank))
        )

        rows.append(
            {
                "query_signature": query_signature,
                "buyer_role": buyer_role,
                "search_channel": search_channel,
                "search_provider": search_provider,
                "query_text": query_text,
                "observed_rank": observed_rank,
                "surfaced_vendor_name": surfaced_vendor_name,
                "surfaced_vendor_website": normalize_website_url(
                    ranked_result.get("surfaced_vendor_website") or ranked_result.get("vendor_website")
                )
                or None,
                "source_url": normalize_website_url(ranked_result.get("source_url")) or None,
                "response_reference": str(ranked_result.get("response_reference") or "").strip() or None,
                "visibility_score": visibility_score,
                "run_timestamp": normalized_run_timestamp,
            }
        )

    return rows


def upsert_buyer_search_results(
    query_row: dict[str, Any],
    ranked_results: Iterable[dict[str, Any]],
    *,
    run_timestamp: str | None = None,
    client: "Client | None" = None,
) -> list[dict[str, Any]]:
    """Persist ranked search visibility rows for one buyer-role query."""
    rows = build_buyer_search_result_rows(query_row, ranked_results, run_timestamp=run_timestamp)
    if not rows:
        return []

    supabase = client or supabase_client.get_supabase_client()
    response = (
        supabase.table(BUYER_SEARCH_RESULT_TABLE)
        .upsert(rows, on_conflict="query_signature,run_timestamp,observed_rank")
        .execute()
    )
    return list(response.data or rows)


def format_search_channel_label(search_channel: object, search_provider: object) -> str:
    """Return a display-friendly channel label for review outputs."""
    normalized_channel = str(search_channel or "").strip().lower()
    normalized_provider = str(search_provider or "").strip().lower()
    if normalized_channel == "geo" and normalized_provider == "openai":
        return "geo - openai"
    return normalized_channel or normalized_provider


def is_search_visibility_store_unavailable_error(error: Exception) -> bool:
    """Return True when the search-visibility persistence tables are unavailable."""
    error_code = _error_code(error)
    error_message = str(error).lower()

    if error_code in {"PGRST204", "PGRST205"}:
        return True

    if supabase_client.is_persistence_unavailable_error(error):
        return True

    for table_name, columns in (
        (BUYER_SEARCH_QUERY_TABLE, BUYER_SEARCH_QUERY_COLUMNS),
        (BUYER_SEARCH_RESULT_TABLE, BUYER_SEARCH_RESULT_COLUMNS),
    ):
        if any(
            (
                f"column {table_name}.{column.lower()} does not exist" in error_message,
                f"could not find the '{column.lower()}' column of '{table_name}'" in error_message,
            )
            for column in columns
        ):
            return True
        if table_name in error_message and ("does not exist" in error_message or "schema cache" in error_message):
            return True

    return False


def _coerce_vendor_profile(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        data = asdict(value)
        if isinstance(data, dict):
            return data
    raise TypeError("vendor_profiles must contain dict or dataclass-like vendor rows")


def _normalize_timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat()


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned
    return []


def _sort_buyer_search_queries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: str(row.get("query_text") or "").lower())
    ordered = sorted(ordered, key=lambda row: str(row.get("search_channel") or "").lower())
    ordered = sorted(ordered, key=lambda row: str(row.get("buyer_role") or "").lower())
    ordered = sorted(ordered, key=lambda row: str(row.get("generated_at") or ""), reverse=True)
    return ordered


def _sort_buyer_search_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(  # keep top-ranked results first within each role/query bucket
        rows,
        key=lambda row: (
            int(row.get("observed_rank") or 0),
            str(row.get("surfaced_vendor_name") or "").lower(),
        ),
    )
    ordered = sorted(ordered, key=lambda row: str(row.get("query_text") or "").lower())
    ordered = sorted(ordered, key=lambda row: str(row.get("search_channel") or "").lower())
    ordered = sorted(ordered, key=lambda row: str(row.get("buyer_role") or "").lower())
    ordered = sorted(ordered, key=lambda row: str(row.get("run_timestamp") or ""), reverse=True)
    return ordered


def _error_code(error: Exception) -> str:
    direct_code = getattr(error, "code", "")
    if isinstance(direct_code, str) and direct_code.strip():
        return direct_code.strip()

    for arg in getattr(error, "args", ()):
        if isinstance(arg, dict):
            code = arg.get("code")
            if isinstance(code, str) and code.strip():
                return code.strip()
    return ""
