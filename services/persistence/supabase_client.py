"""Supabase persistence helpers for vendor deduplication and upserts."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

from services.extraction.vendor_intel import (
    INTEGRATION_BRAND_RULES,
    VendorIntelligence,
    normalize_email_address,
    normalize_email_list,
    normalize_external_enrichment_records,
    normalize_integration_taxonomy,
    normalize_phone_numbers,
    normalize_vendor_website,
    normalize_website_url,
)

if TYPE_CHECKING:
    from supabase import Client


INTEGRATION_CATALOG_TABLE = "integration_catalog"
INTEGRATION_CATALOG_SELECT = "integration_name,category,aliases,source,active,updated_at"


VENDOR_PROFILE_SELECT = ",".join(
    [
        "name",
        "website",
        "source",
        "mission",
        "usp",
        "icp",
        "icp_buyer",
        "use_cases",
        "lifecycle_stages",
        "pricing",
        "free_trial",
        "soc2",
        "compliance",
        "founded",
        "products",
        "leadership",
        "ceo_name",
        "ceo_linkedin",
        "hq_address",
        "phone_numbers",
        "contact_emails",
        "company_hq",
        "contact_email",
        "contact_page_url",
        "demo_url",
        "help_center_url",
        "support_url",
        "about_url",
        "team_url",
        "developer_docs_url",
        "integration_categories",
        "integrations",
        "integration_taxonomy",
        "external_enrichment",
        "support_signals",
        "case_studies",
        "case_study_signals",
        "case_study_details",
        "testimonials",
        "blog_posts",
        "customers",
        "value_statements",
        "source_urls",
        "confidence",
        "evidence_urls",
        "directory_fit",
        "directory_category",
        "include_in_directory",
        "llm_directory_fit",
        "llm_directory_category",
        "llm_include_in_directory",
        "directory_decision_source",
        "directory_reasoning",
        "youtube_channel_url",
        "funding_stage",
        "total_funding",
        "use_case_details",
        "g2_url",
        "g2_rating",
        "g2_review_count",
        "g2_market_segment",
        "g2_categories",
        "has_public_pricing_page",
        "pricing_source",
        "last_enriched_at",
        "last_enriched_pipeline",
        "enrichment_count",
        "enrichment_pipeline_counts",
        "last_updated",
        "is_new",
    ]
)
VENDOR_PROFILE_COLUMNS = tuple(VENDOR_PROFILE_SELECT.split(","))
VENDOR_WRITE_COLUMNS = (
    "name",
    "website",
    "source",
    "confidence",
    "mission",
    "usp",
    "icp",
    "icp_buyer",
    "pricing",
    "free_trial",
    "soc2",
    "compliance",
    "founded",
    "products",
    "leadership",
    "ceo_name",
    "ceo_linkedin",
    "hq_address",
    "phone_numbers",
    "contact_emails",
    "company_hq",
    "contact_email",
    "contact_page_url",
    "demo_url",
    "help_center_url",
    "support_url",
    "about_url",
    "team_url",
    "developer_docs_url",
    "integration_categories",
    "integrations",
    "integration_taxonomy",
    "external_enrichment",
    "support_signals",
    "use_cases",
    "lifecycle_stages",
    "case_studies",
    "case_study_signals",
    "case_study_details",
    "testimonials",
    "blog_posts",
    "customers",
    "value_statements",
    "source_urls",
    "evidence_urls",
    "directory_fit",
    "directory_category",
    "include_in_directory",
    "llm_directory_fit",
    "llm_directory_category",
    "llm_include_in_directory",
    "directory_decision_source",
    "directory_reasoning",
    "youtube_channel_url",
    "funding_stage",
    "total_funding",
    "use_case_details",
    "g2_url",
    "g2_rating",
    "g2_review_count",
    "g2_market_segment",
    "g2_categories",
    "has_public_pricing_page",
    "pricing_source",
    "last_enriched_at",
    "last_enriched_pipeline",
    "enrichment_count",
    "enrichment_pipeline_counts",
    "raw_description",
    "last_updated",
    "is_new",
)
EXPORT_READY_VENDOR_COLUMNS = (
    "mission",
    "usp",
    "confidence",
    "directory_fit",
    "directory_category",
    "include_in_directory",
)


def is_configured() -> bool:
    """Return True when the Supabase environment variables are available."""
    return get_supabase_config() is not None


def get_supabase_config() -> dict[str, str] | None:
    """Return Supabase config from environment variables when present."""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        return None

    return {
        "url": supabase_url,
        "key": supabase_key,
    }


def get_supabase_client() -> "Client":
    """Create a Supabase client from environment variables."""
    config = get_supabase_config()
    if config is None:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")

    return _create_supabase_client(config["url"], config["key"])


def _create_supabase_client(supabase_url: str, supabase_key: str) -> "Client":
    """Create the underlying Supabase client instance."""
    from supabase import create_client

    return create_client(supabase_url, supabase_key)


def vendor_exists(website: str, client: "Client | None" = None) -> bool:
    """Return True when a vendor already exists in cs_vendors and is export-ready."""
    supabase = client or get_supabase_client()
    normalized_website = normalize_vendor_website(website)
    response = (
        supabase.table("cs_vendors")
        .select("website,directory_fit,directory_category,include_in_directory")
        .eq("website", normalized_website or website)
        .limit(1)
        .execute()
    )
    rows = list(response.data or [])
    if not rows:
        return False
    return _vendor_row_has_review_signal(rows[0])


def supports_export_ready_vendor_profiles(client: "Client | None" = None) -> bool:
    """Return True when persisted vendor rows are rich enough to reuse for exports and dedupe."""
    try:
        supabase = client or get_supabase_client()
        available_columns = _available_vendor_profile_columns(supabase)
    except Exception:
        return False
    return all(column in available_columns for column in EXPORT_READY_VENDOR_COLUMNS)


_ENRICHMENT_KEY_FIELDS = ("icp", "lifecycle_stages", "directory_category", "integrations", "pricing")


def get_vendor_enrichment_completeness(website: str, client: "Client | None" = None) -> dict[str, Any]:
    """Return field completeness for a vendor to decide if expensive re-enrichment is needed.

    Returns a dict with:
      - ``fields_populated``: list of key fields that are non-empty
      - ``fields_missing``: list of key fields that are null/empty
      - ``is_sufficiently_enriched``: True when all key fields are populated (skip Playwright/Apify)
    """
    supabase = client or get_supabase_client()
    normalized_website = normalize_vendor_website(website)
    response = (
        supabase.table("cs_vendors")
        .select(",".join(_ENRICHMENT_KEY_FIELDS))
        .eq("website", normalized_website or website)
        .limit(1)
        .execute()
    )
    rows = list(response.data or [])
    if not rows:
        return {"fields_populated": [], "fields_missing": list(_ENRICHMENT_KEY_FIELDS), "is_sufficiently_enriched": False}
    row = rows[0]
    populated = [f for f in _ENRICHMENT_KEY_FIELDS if row.get(f)]
    missing = [f for f in _ENRICHMENT_KEY_FIELDS if not row.get(f)]
    return {
        "fields_populated": populated,
        "fields_missing": missing,
        "is_sufficiently_enriched": len(missing) == 0,
    }


def _vendor_row_has_review_signal(row: dict[str, Any]) -> bool:
    """Return True when a persisted vendor row has the minimum review/export fields populated."""
    return any(
        (
            str(row.get("directory_fit") or "").strip(),
            str(row.get("directory_category") or "").strip(),
            row.get("include_in_directory") is not None,
        )
    )


def upsert_vendor_result(
    vendor: dict[str, str],
    homepage_payload: dict[str, str | int],
    intelligence: VendorIntelligence,
    *,
    enrichment_pipeline: str | None = None,
    preserve_existing: bool = False,
    client: "Client | None" = None,
) -> dict[str, Any]:
    """Upsert a Phase 2 enriched vendor profile into cs_vendors using website as the conflict key.

    When ``preserve_existing=True`` empty/null fields are stripped from the row before upserting
    so that previously-enriched data is not overwritten by empty defaults from a partial run.
    """
    supabase = client or get_supabase_client()
    row = build_vendor_row(vendor, homepage_payload, intelligence)
    if preserve_existing:
        row = _strip_empty_row_fields(row)
    row = _apply_integration_catalog_validation(supabase, row)
    pipeline_name = _normalize_pipeline_name(
        enrichment_pipeline or _infer_enrichment_pipeline_name(vendor, homepage_payload)
    )
    row = _apply_enrichment_tracking(
        supabase,
        website=str(row.get("website") or ""),
        row=row,
        pipeline_name=pipeline_name,
    )
    _upsert_vendor_row_with_tracking_fallback(supabase, row)
    return row


def list_directory_vendors(client: "Client | None" = None) -> list[dict[str, Any]]:
    """Return vendors currently marked for public directory inclusion."""
    supabase = client or get_supabase_client()
    available_columns = _available_vendor_profile_columns(supabase)
    response = (
        supabase.table("cs_vendors")
        .select(",".join(available_columns))
        .execute()
    )
    rows = list(response.data or [])
    return [row for row in rows if row.get("include_in_directory") is True]


def list_vendor_profiles(*, limit: int = 200, client: "Client | None" = None) -> list[dict[str, Any]]:
    """Return enriched vendor profiles for read-only admin visibility."""
    supabase = client or get_supabase_client()
    available_columns = _available_vendor_profile_columns(supabase)
    query = supabase.table("cs_vendors").select(",".join(available_columns))
    if "last_updated" in available_columns:
        query = query.order("last_updated", desc=True)
    response = query.limit(limit).execute()
    return list(response.data or [])


def list_integration_catalog(*, limit: int = 2000, client: "Client | None" = None) -> list[dict[str, Any]]:
    """Return integration catalog rows from Supabase."""
    supabase = client or get_supabase_client()
    try:
        response = (
            supabase.table(INTEGRATION_CATALOG_TABLE)
            .select(INTEGRATION_CATALOG_SELECT)
            .order("integration_name", desc=False)
            .limit(limit)
            .execute()
        )
        rows = list(response.data or [])
        return [row for row in rows if isinstance(row, dict)]
    except Exception as exc:  # treat missing table as empty catalog so callers proceed
        if is_integration_catalog_unavailable_error(exc):
            logger.warning("integration_catalog unavailable; returning empty list: %s", exc)
            return []
        raise


def upsert_integration_catalog_rows(
    rows: list[dict[str, Any]],
    *,
    client: "Client | None" = None,
) -> int:
    """Upsert integration catalog rows keyed by integration_name."""
    if not rows:
        return 0
    supabase = client or get_supabase_client()
    normalized_rows = [_normalize_catalog_row(row) for row in rows if isinstance(row, dict)]
    if not normalized_rows:
        return 0
    supabase.table(INTEGRATION_CATALOG_TABLE).upsert(
        normalized_rows,
        on_conflict="integration_name",
    ).execute()
    return len(normalized_rows)


def sync_default_integration_catalog(*, client: "Client | None" = None) -> dict[str, Any]:
    """Sync the repo's canonical integration rules into Supabase integration_catalog."""
    rows = _default_integration_catalog_rows()
    written = upsert_integration_catalog_rows(rows, client=client)
    return {
        "ok": True,
        "rows_written": written,
        "source": "services/extraction/vendor_intel.py::INTEGRATION_BRAND_RULES",
    }


def update_vendor_admin_fields(
    vendor_lookup: str,
    *,
    include_in_directory: bool | None = None,
    directory_fit: str | None = None,
    directory_category: str | None = None,
    client: "Client | None" = None,
) -> dict[str, Any]:
    """Apply thin admin overrides for public-directory controls."""
    supabase = client or get_supabase_client()
    record = find_vendor_by_lookup(vendor_lookup, client=supabase)
    if not record:
        raise LookupError(f"Vendor {vendor_lookup!r} was not found")

    updates: dict[str, Any] = {"last_updated": datetime.now(timezone.utc).isoformat()}
    if include_in_directory is not None:
        updates["include_in_directory"] = include_in_directory
    if directory_fit:
        updates["directory_fit"] = directory_fit
    if directory_category:
        updates["directory_category"] = directory_category
    if len(updates) > 1:
        updates["directory_decision_source"] = "admin_override"

    if len(updates) == 1:
        raise ValueError("No admin override fields were provided")

    website = str(record.get("website", "")).strip()
    response = (
        supabase.table("cs_vendors")
        .update(updates)
        .eq("website", website)
        .execute()
    )
    updated_rows = list(response.data or [])
    return updated_rows[0] if updated_rows else {**record, **updates}


def find_vendor_by_lookup(vendor_lookup: str, client: "Client | None" = None) -> dict[str, Any] | None:
    """Find one vendor by website or case-insensitive name match."""
    supabase = client or get_supabase_client()
    select_columns = ",".join(_available_vendor_profile_columns(supabase))
    lookup = vendor_lookup.strip()
    if not lookup:
        return None
    normalized_lookup = normalize_vendor_website(lookup if lookup.startswith("http") else f"https://{lookup}")

    website_matches = (
        supabase.table("cs_vendors")
        .select(select_columns)
        .eq("website", normalized_lookup or lookup)
        .limit(1)
        .execute()
    )
    if website_matches.data:
        return website_matches.data[0]

    exact_name_matches = (
        supabase.table("cs_vendors")
        .select(select_columns)
        .ilike("name", lookup)
        .limit(1)
        .execute()
    )
    if exact_name_matches.data:
        return exact_name_matches.data[0]

    return None


def is_persistence_unavailable_error(error: Exception) -> bool:
    """Return True for missing-table or unavailable persistence errors."""
    error_code = _error_code(error)
    error_message = str(error).lower()

    if error_code in {"PGRST204", "PGRST205"}:
        return True

    if "column cs_vendors." in error_message and "does not exist" in error_message:
        return True

    if "could not find the 'cs_vendors' column" in error_message:
        return True

    if _is_connectivity_error_message(error_message):
        return True

    return all(marker in error_message for marker in ["cs_vendors", "does not exist"]) or any(
        marker in error_message for marker in [
            "could not find the table",
            "public.cs_vendors",
            "schema cache",
        ]
    )


def is_integration_catalog_unavailable_error(error: Exception) -> bool:
    """Return True when integration_catalog is missing/unavailable."""
    error_message = str(error).lower()
    if f"column {INTEGRATION_CATALOG_TABLE}." in error_message and "does not exist" in error_message:
        return True
    if f"could not find the '{INTEGRATION_CATALOG_TABLE}' column" in error_message:
        return True
    if INTEGRATION_CATALOG_TABLE in error_message and ("does not exist" in error_message or "schema cache" in error_message):
        return True
    return _is_connectivity_error_message(error_message)


def get_vendor_profile_columns() -> tuple[str, ...]:
    """Return the expected persisted vendor profile columns."""
    return VENDOR_PROFILE_COLUMNS


def get_vendor_write_columns() -> tuple[str, ...]:
    """Return the columns required for vendor upserts to succeed."""
    return VENDOR_WRITE_COLUMNS


def _error_code(error: Exception) -> str:
    """Best-effort extraction of API error codes from Supabase/PostgREST exceptions."""
    direct_code = getattr(error, "code", "")
    if isinstance(direct_code, str) and direct_code.strip():
        return direct_code.strip()

    for arg in getattr(error, "args", ()):
        if isinstance(arg, dict):
            code = arg.get("code")
            if isinstance(code, str) and code.strip():
                return code.strip()
    return ""


def _available_vendor_profile_columns(supabase: "Client") -> tuple[str, ...]:
    """Return the subset of vendor profile columns currently accepted by Supabase."""
    available_columns = list(VENDOR_PROFILE_COLUMNS)
    while available_columns:
        try:
            (
                supabase.table("cs_vendors")
                .select(",".join(available_columns))
                .limit(1)
                .execute()
            )
            return tuple(available_columns)
        except Exception as error:
            missing_column = _missing_vendor_column_name(error)
            if not missing_column or missing_column not in available_columns:
                raise
            available_columns.remove(missing_column)
    raise RuntimeError("No readable vendor profile columns are available in cs_vendors")


def _missing_vendor_column_name(error: Exception) -> str | None:
    """Extract one missing vendor column name from common Supabase/PostgREST errors."""
    error_message = str(error).lower()
    for column in VENDOR_PROFILE_COLUMNS:
        if f"column cs_vendors.{column.lower()} does not exist" in error_message:
            return column
        if f"could not find the '{column.lower()}' column of 'cs_vendors'" in error_message:
            return column
    return None


def _is_connectivity_error_message(error_message: str) -> bool:
    """Return True for network/connectivity failures that should degrade safely."""
    return any(
        marker in error_message
        for marker in [
            "all connection attempts failed",
            "connection refused",
            "connecterror",
            "name or service not known",
            "network is unreachable",
            "server disconnected",
            "temporary failure in name resolution",
            "timed out",
        ]
    )


def build_vendor_row(
    vendor: dict[str, str],
    homepage_payload: dict[str, str | int],
    intelligence: VendorIntelligence,
) -> dict[str, Any]:
    """Build a cs_vendors row payload from an enriched vendor profile."""
    text = str(homepage_payload.get("text", "")).strip()
    raw_description = text or vendor.get("raw_description") or vendor.get("candidate_description")

    return {
        "name": intelligence.vendor_name,
        "website": normalize_vendor_website(intelligence.website),
        "source": vendor.get("source"),
        "confidence": intelligence.confidence or None,
        "mission": intelligence.mission or _extract_mission(raw_description or ""),
        "usp": intelligence.usp or (intelligence.value_statements[0] if intelligence.value_statements else None),
        "icp": intelligence.icp or [],
        "icp_buyer": intelligence.icp_buyer or [],
        "pricing": intelligence.pricing if intelligence.pricing else None,
        "free_trial": intelligence.free_trial if intelligence.free_trial is not None else _detect_text_boolean(
            raw_description or "",
            ["free trial"],
        ),
        "soc2": intelligence.soc2 if intelligence.soc2 is not None else _detect_text_boolean(
            raw_description or "",
            ["soc 2", "soc2"],
        ),
        "compliance": intelligence.compliance or [],
        "founded": intelligence.founded or None,
        "products": intelligence.products or [],
        "leadership": intelligence.leadership or [],
        "ceo_name": intelligence.ceo_name or None,
        "ceo_linkedin": intelligence.ceo_linkedin or None,
        "hq_address": intelligence.hq_address or intelligence.company_hq or None,
        "phone_numbers": normalize_phone_numbers(intelligence.phone_numbers) or [],
        "contact_emails": normalize_email_list(
            intelligence.contact_emails or ([intelligence.contact_email] if intelligence.contact_email else [])
        )
        or [],
        "company_hq": intelligence.company_hq or intelligence.hq_address or None,
        "contact_email": normalize_email_address(
            intelligence.contact_email or (intelligence.contact_emails[0] if intelligence.contact_emails else "")
        )
        or None,
        "contact_page_url": normalize_website_url(intelligence.contact_page_url) or None,
        "demo_url": normalize_website_url(intelligence.demo_url) or None,
        "help_center_url": normalize_website_url(intelligence.help_center_url) or None,
        "support_url": normalize_website_url(intelligence.support_url) or None,
        "about_url": normalize_website_url(intelligence.about_url) or None,
        "team_url": normalize_website_url(intelligence.team_url) or None,
        "developer_docs_url": normalize_website_url(intelligence.developer_docs_url) or None,
        "integration_categories": intelligence.integration_categories or [],
        "integrations": intelligence.integrations or [],
        "integration_taxonomy": normalize_integration_taxonomy(
            intelligence.integration_taxonomy,
            integrations=intelligence.integrations,
            categories=intelligence.integration_categories,
        ),
        "external_enrichment": normalize_external_enrichment_records(intelligence.external_enrichment),
        "support_signals": intelligence.support_signals or [],
        "use_cases": intelligence.use_cases,
        "lifecycle_stages": intelligence.lifecycle_stages,
        "case_studies": intelligence.case_studies or [],
        "case_study_signals": intelligence.case_study_signals or [],
        "case_study_details": intelligence.case_study_details or [],
        "testimonials": intelligence.testimonials or [],
        "blog_posts": intelligence.blog_posts or [],
        "customers": intelligence.customers or [],
        "value_statements": intelligence.value_statements or [],
        "source_urls": [url for url in (normalize_website_url(url) for url in intelligence.source_urls) if url],
        "evidence_urls": [url for url in (normalize_website_url(url) for url in intelligence.evidence_urls) if url],
        "directory_fit": intelligence.directory_fit or None,
        "directory_category": intelligence.directory_category or None,
        "include_in_directory": intelligence.include_in_directory,
        "llm_directory_fit": intelligence.llm_directory_fit or intelligence.directory_fit or None,
        "llm_directory_category": intelligence.llm_directory_category or intelligence.directory_category or None,
        "llm_include_in_directory": (
            intelligence.llm_include_in_directory
            if intelligence.llm_include_in_directory is not None
            else intelligence.include_in_directory
        ),
        "directory_decision_source": intelligence.directory_decision_source or "auto",
        "directory_reasoning": intelligence.directory_reasoning or [],
        "youtube_channel_url": intelligence.youtube_channel_url or None,
        "funding_stage": intelligence.funding_stage or None,
        "total_funding": intelligence.total_funding or None,
        "use_case_details": intelligence.use_case_details or [],
        "g2_url": intelligence.g2_url or None,
        "g2_rating": intelligence.g2_rating,
        "g2_review_count": intelligence.g2_review_count,
        "g2_market_segment": intelligence.g2_market_segment or None,
        "g2_categories": intelligence.g2_categories or [],
        "company_size": intelligence.company_size or None,
        "revenue": intelligence.revenue or None,
        "linkedin_url": intelligence.linkedin_url or None,
        "has_public_pricing_page": intelligence.has_public_pricing_page,
        "pricing_source": intelligence.pricing_source or None,
        "raw_description": raw_description or None,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "is_new": True,
    }


_TRACKING_COLUMNS = (
    "last_enriched_at",
    "last_enriched_pipeline",
    "enrichment_count",
    "enrichment_pipeline_counts",
)


def _infer_enrichment_pipeline_name(
    vendor: dict[str, str],
    homepage_payload: dict[str, str | int],
) -> str:
    source = str(vendor.get("source") or homepage_payload.get("source") or "").strip().lower()
    fetch_backend = str(homepage_payload.get("fetch_backend") or "").strip().lower()
    if fetch_backend == "apify":
        return "apify"
    if "g2" in source:
        return "g2"
    if "tracxn" in source:
        return "tracxn"
    if "pricing" in source:
        return "pricing"
    if "apify" in source:
        return "apify"
    if source:
        return source
    return "pipeline_phase2"


def _normalize_pipeline_name(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or "").strip())
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    normalized = normalized.strip("_")
    return normalized or "unknown"


def _apply_enrichment_tracking(
    supabase: "Client",
    *,
    website: str,
    row: dict[str, Any],
    pipeline_name: str,
) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    updated = dict(row)
    updated["last_enriched_at"] = now_iso
    updated["last_enriched_pipeline"] = pipeline_name
    updated["enrichment_count"] = 1
    updated["enrichment_pipeline_counts"] = {pipeline_name: 1}

    if not website:
        return updated

    try:
        response = (
            supabase.table("cs_vendors")
            .select("enrichment_count,enrichment_pipeline_counts")
            .eq("website", website)
            .limit(1)
            .execute()
        )
    except Exception:
        return updated

    rows = list(response.data or [])
    if not rows:
        return updated

    existing = rows[0] if isinstance(rows[0], dict) else {}
    existing_count = existing.get("enrichment_count")
    try:
        base_count = int(existing_count) if existing_count is not None else 0
    except (TypeError, ValueError):
        base_count = 0

    existing_pipeline_counts = existing.get("enrichment_pipeline_counts")
    base_pipeline_counts: dict[str, int] = {}
    if isinstance(existing_pipeline_counts, dict):
        for key, value in existing_pipeline_counts.items():
            pipeline_key = _normalize_pipeline_name(key)
            try:
                base_pipeline_counts[pipeline_key] = max(int(value), 0)
            except (TypeError, ValueError):
                continue

    base_pipeline_counts[pipeline_name] = base_pipeline_counts.get(pipeline_name, 0) + 1
    updated["enrichment_count"] = base_count + 1
    updated["enrichment_pipeline_counts"] = base_pipeline_counts
    return updated


_ALWAYS_WRITE_FIELDS = frozenset({"website", "name", "last_updated"})


def _strip_empty_row_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Remove None and empty collection values, keeping required identifier fields.

    Used for partial enrichment writes so existing data is not overwritten by empty defaults.
    """
    result = {}
    for k, v in row.items():
        if k in _ALWAYS_WRITE_FIELDS:
            result[k] = v
        elif v is None:
            continue
        elif isinstance(v, (list, dict)) and not v:
            continue
        else:
            result[k] = v
    return result


def _upsert_vendor_row_with_tracking_fallback(supabase: "Client", row: dict[str, Any]) -> None:
    payload = dict(row)
    stripped: list[str] = []
    while True:
        try:
            supabase.table("cs_vendors").upsert(payload, on_conflict="website").execute()
            if stripped:
                logger.warning("Vendor upsert succeeded after stripping unknown columns: %s", stripped)
            return
        except Exception as error:
            missing = _missing_vendor_write_column_name(error, payload.keys())
            if not missing:
                raise
            payload.pop(missing, None)
            stripped.append(missing)
            if len(stripped) > 10:
                raise


def _missing_vendor_write_column_name(error: Exception, candidate_columns: Any) -> str | None:
    error_message = str(error).lower()
    for column in candidate_columns:
        lowered = str(column).lower()
        if f"column cs_vendors.{lowered} does not exist" in error_message:
            return str(column)
        if f"could not find the '{lowered}' column of 'cs_vendors'" in error_message:
            return str(column)
    return None


def _default_integration_catalog_rows() -> list[dict[str, Any]]:
    now_iso = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for integration_name, category, aliases in INTEGRATION_BRAND_RULES:
        rows.append(
            {
                "integration_name": str(integration_name).strip(),
                "category": str(category).strip().lower(),
                "aliases": sorted({str(alias).strip().lower() for alias in aliases if str(alias).strip()}),
                "source": "n8n_catalog_curated",
                "active": True,
                "updated_at": now_iso,
            }
        )
    return rows


def _normalize_catalog_row(row: dict[str, Any]) -> dict[str, Any]:
    integration_name = str(row.get("integration_name") or "").strip()
    category = str(row.get("category") or "").strip().lower()
    aliases = row.get("aliases")
    alias_values = aliases if isinstance(aliases, list) else []
    normalized_aliases = sorted({str(alias).strip().lower() for alias in alias_values if str(alias).strip()})
    return {
        "integration_name": integration_name,
        "category": category or "other",
        "aliases": normalized_aliases,
        "source": str(row.get("source") or "integration_catalog").strip() or "integration_catalog",
        "active": bool(row.get("active", True)),
        "updated_at": str(row.get("updated_at") or datetime.now(timezone.utc).isoformat()),
    }


def _integration_catalog_rules(supabase: "Client") -> tuple[dict[str, str], dict[str, str]]:
    """Return alias->canonical and canonical->category rules from Supabase or fallback constants."""
    alias_to_canonical: dict[str, str] = {}
    canonical_to_category: dict[str, str] = {}

    try:
        rows = list_integration_catalog(client=supabase)
    except Exception as error:
        if not is_integration_catalog_unavailable_error(error):
            raise
        rows = _default_integration_catalog_rows()

    if not rows:
        rows = _default_integration_catalog_rows()

    for row in rows:
        canonical = str(row.get("integration_name") or "").strip()
        if not canonical:
            continue
        category = str(row.get("category") or "").strip().lower()
        aliases = row.get("aliases") if isinstance(row.get("aliases"), list) else []
        canonical_to_category[canonical.lower()] = category
        alias_to_canonical[canonical.lower()] = canonical
        for alias in aliases:
            lowered_alias = str(alias).strip().lower()
            if lowered_alias:
                alias_to_canonical[lowered_alias] = canonical

    if not alias_to_canonical:
        for canonical, category, aliases in INTEGRATION_BRAND_RULES:
            alias_to_canonical[str(canonical).lower()] = canonical
            canonical_to_category[str(canonical).lower()] = str(category).lower()
            for alias in aliases:
                alias_to_canonical[str(alias).lower()] = canonical
    return alias_to_canonical, canonical_to_category


def _apply_integration_catalog_validation(
    supabase: "Client",
    row: dict[str, Any],
) -> dict[str, Any]:
    """Normalize integration fields against integration_catalog source-of-truth."""
    alias_to_canonical, canonical_to_category = _integration_catalog_rules(supabase)
    normalized = dict(row)

    raw_integrations = row.get("integrations")
    integration_values = raw_integrations if isinstance(raw_integrations, list) else []
    canonical_integrations: list[str] = []
    for value in integration_values:
        cleaned = str(value or "").strip()
        if not cleaned:
            continue
        canonical = alias_to_canonical.get(cleaned.lower())
        if canonical and canonical not in canonical_integrations:
            canonical_integrations.append(canonical)

    raw_categories = row.get("integration_categories")
    category_values = raw_categories if isinstance(raw_categories, list) else []
    categories: list[str] = []
    for value in category_values:
        normalized_category = str(value or "").strip().lower()
        if normalized_category and normalized_category not in categories:
            categories.append(normalized_category)
    for integration_name in canonical_integrations:
        category = canonical_to_category.get(integration_name.lower(), "")
        if category and category not in categories:
            categories.append(category)

    normalized["integrations"] = canonical_integrations
    normalized["integration_categories"] = categories
    normalized["integration_taxonomy"] = normalize_integration_taxonomy(
        normalized.get("integration_taxonomy"),
        integrations=canonical_integrations,
        categories=categories,
    )
    return normalized


def _extract_mission(text: str) -> str | None:
    """Return a short mission-style sentence from homepage text."""
    if not text:
        return None

    normalized_text = text.replace("\n", " ").strip()
    for separator in [". ", "! ", "? "]:
        if separator in normalized_text:
            mission = normalized_text.split(separator, maxsplit=1)[0].strip()
            return mission or None

    return normalized_text or None


def _detect_text_boolean(text: str, phrases: list[str]) -> bool | None:
    lowered_text = text.lower()
    if any(phrase in lowered_text for phrase in phrases):
        return True
    return None
