"""Export a public-directory dataset from enriched vendor profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from services.persistence import supabase_client
from services.extraction.vendor_intel import VendorIntelligence, normalize_case_study_details, normalize_icp_buyer_profiles

if TYPE_CHECKING:
    from supabase import Client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIRECTORY_DATASET_PATH = PROJECT_ROOT / "outputs" / "directory_dataset.json"
DIRECTORY_DATASET_FIELDS = (
    "vendor_name",
    "website",
    "mission",
    "usp",
    "icp",
    "icp_buyer",
    "lifecycle_stages",
    "pricing",
    "free_trial",
    "founded",
    "case_study_details",
    "customers",
    "value_statements",
    "confidence",
    "evidence_urls",
    "directory_fit",
    "directory_category",
    "use_case_details",
)


def export_directory_dataset(
    *,
    output_path: Path | None = None,
    client: "Client | None" = None,
    fallback_profiles: list[VendorIntelligence] | None = None,
    prefer_fallback_profiles: bool = False,
) -> list[dict[str, Any]]:
    """Fetch included vendors from Supabase and write a deterministic JSON dataset."""
    dataset = build_directory_dataset(
        client=client,
        fallback_profiles=fallback_profiles,
        prefer_fallback_profiles=prefer_fallback_profiles,
    )
    output_path = output_path or DEFAULT_DIRECTORY_DATASET_PATH
    write_directory_dataset(dataset, output_path)
    return dataset


def build_directory_dataset(
    client: "Client | None" = None,
    *,
    fallback_profiles: list[VendorIntelligence] | None = None,
    prefer_fallback_profiles: bool = False,
) -> list[dict[str, Any]]:
    """Return a clean public-directory dataset from persisted vendor rows."""
    rows: list[dict[str, Any]]
    if prefer_fallback_profiles:
        rows = []
    elif client is not None or supabase_client.is_configured():
        try:
            rows = supabase_client.list_directory_vendors(client=client)
        except Exception:
            rows = []
    else:
        rows = []
    if not rows and fallback_profiles:
        rows = [_profile_to_vendor_row(profile) for profile in fallback_profiles if profile.include_in_directory is True]
    rows = [row for row in rows if (row.get("directory_category") or row.get("llm_directory_category") or "") != "other"]
    dataset = [_normalize_vendor_row(row) for row in rows]
    return sorted(dataset, key=lambda item: item["vendor_name"].lower())


def write_directory_dataset(dataset: list[dict[str, Any]], output_path: Path) -> None:
    """Write the public directory dataset to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")


def _normalize_vendor_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "vendor_name": _string_value(row.get("name") or row.get("vendor_name")),
        "website": _string_value(row.get("website")),
        "mission": _string_value(row.get("mission")),
        "usp": _string_value(row.get("usp")),
        "icp": _list_value(row.get("icp")),
        "icp_buyer": normalize_icp_buyer_profiles(row.get("icp_buyer")),
        "use_cases": _list_value(row.get("use_cases")),
        "lifecycle_stages": _list_value(row.get("lifecycle_stages")),
        "pricing": _list_value(row.get("pricing")),
        "free_trial": _bool_value(row.get("free_trial")),
        "soc2": _bool_value(row.get("soc2")),
        "founded": _string_value(row.get("founded")),
        "case_study_details": _case_study_details_value(row.get("case_study_details")),
        "customers": _list_value(row.get("customers")),
        "value_statements": _list_value(row.get("value_statements")),
        "confidence": _string_value(row.get("confidence")),
        "evidence_urls": _list_value(row.get("evidence_urls")),
        "directory_fit": _string_value(row.get("directory_fit")),
        "directory_category": _string_value(row.get("directory_category")),
        "use_case_details": _use_case_details_value(row.get("use_case_details")),
        "blog_posts": _blog_posts_value(row.get("blog_posts")),
        "g2_url": _string_value(row.get("g2_url")),
        "g2_rating": row.get("g2_rating"),
        "g2_review_count": row.get("g2_review_count"),
        "g2_categories": _list_value(row.get("g2_categories")),
        "linkedin_url": _string_value(row.get("linkedin_url")),
        "company_size": _string_value(row.get("company_size")),
        "hq_address": _string_value(row.get("hq_address")),
        "integrations": _list_value(row.get("integrations")),
        "how_it_works": _string_value(row.get("how_it_works")),
        "key_features": _list_value(row.get("key_features")),
        "outcomes": _list_value(row.get("outcomes")),
        "ai_summary": _string_value(row.get("ai_summary")),
    }


def _profile_to_vendor_row(profile: VendorIntelligence) -> dict[str, Any]:
    return {
        "name": profile.vendor_name,
        "website": profile.website,
        "mission": profile.mission,
        "usp": profile.usp,
        "icp": profile.icp,
        "icp_buyer": profile.icp_buyer,
        "use_cases": profile.use_cases,
        "lifecycle_stages": profile.lifecycle_stages,
        "pricing": profile.pricing,
        "free_trial": profile.free_trial,
        "soc2": profile.soc2,
        "founded": profile.founded,
        "case_study_details": profile.case_study_details,
        "customers": profile.customers,
        "value_statements": profile.value_statements,
        "confidence": profile.confidence,
        "evidence_urls": profile.evidence_urls,
        "directory_fit": profile.directory_fit,
        "directory_category": profile.directory_category,
    }



def _blog_posts_value(value: object) -> list[dict[str, Any]]:
    """Return a normalized list of blog post objects with {title, summary, source_url}."""
    if not value:
        return []
    if isinstance(value, str):
        try:
            import json as _json
            value = _json.loads(value)
        except Exception:
            return []
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str):
            try:
                import json as _json
                item = _json.loads(item)
            except Exception:
                continue
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        source_url = str(item.get("source_url") or "").strip()
        if not title or not source_url:
            continue
        result.append({
            "title": title[:200],
            "summary": str(item.get("summary") or "")[:300].strip(),
            "source_url": source_url,
        })
    return result


def _use_case_details_value(value: object) -> list[dict[str, Any]]:
    """Return normalized use_case_details list with {label, url, summary}."""
    if not value:
        return []
    if isinstance(value, str):
        try:
            import json as _json
            value = _json.loads(value)
        except Exception:
            return []
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        result.append({
            "label": label,
            "url": str(item.get("url") or "").strip(),
            "summary": str(item.get("summary") or "")[:200].strip(),
        })
    return result


def _case_study_details_value(value: object) -> list[dict[str, Any]]:
    """Return a normalized list of case-study detail objects, each with only URL-based source_url.

    Accepts a list of dicts or a JSON string. Keyword-only strings are rejected.
    Only dict items are included (keyword detection strings stored in case_study_signals
    are never included here).
    """
    return normalize_case_study_details(value)


def _string_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _list_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                import json as _json
                parsed = _json.loads(stripped)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except (ValueError, TypeError):
                pass
        separators_normalized = stripped.replace("\n", "|").replace(",", "|")
        return [segment.strip() for segment in separators_normalized.split("|") if segment.strip()]
    return []


def _bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None

