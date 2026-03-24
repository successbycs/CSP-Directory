"""Supabase persistence helpers for vendor deduplication and upserts."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from services.extraction.vendor_intel import (
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
        "auto_directory_fit",
        "auto_directory_category",
        "auto_include_in_directory",
        "directory_decision_source",
        "directory_reasoning",
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
    "auto_directory_fit",
    "auto_directory_category",
    "auto_include_in_directory",
    "directory_decision_source",
    "directory_reasoning",
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
    client: "Client | None" = None,
) -> dict[str, Any]:
    """Upsert a Phase 2 enriched vendor profile into cs_vendors using website as the conflict key."""
    supabase = client or get_supabase_client()
    row = build_vendor_row(vendor, homepage_payload, intelligence)
    supabase.table("cs_vendors").upsert(row, on_conflict="website").execute()
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
        "pricing": "|".join(intelligence.pricing) if intelligence.pricing else None,
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
        "auto_directory_fit": intelligence.auto_directory_fit or intelligence.directory_fit or None,
        "auto_directory_category": intelligence.auto_directory_category or intelligence.directory_category or None,
        "auto_include_in_directory": (
            intelligence.auto_include_in_directory
            if intelligence.auto_include_in_directory is not None
            else intelligence.include_in_directory
        ),
        "directory_decision_source": intelligence.directory_decision_source or "auto",
        "directory_reasoning": intelligence.directory_reasoning or [],
        "raw_description": raw_description or None,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "is_new": True,
    }


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
