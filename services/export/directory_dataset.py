"""Export a public-directory dataset from enriched vendor profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from services.persistence import supabase_client
from services.extraction.vendor_intel import VendorIntelligence, normalize_icp_buyer_profiles

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
    "case_studies",
    "customers",
    "value_statements",
    "confidence",
    "evidence_urls",
    "directory_fit",
    "directory_category",
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
        "case_studies": _list_value(row.get("case_studies")),
        "customers": _list_value(row.get("customers")),
        "value_statements": _list_value(row.get("value_statements")),
        "confidence": _string_value(row.get("confidence")),
        "evidence_urls": _list_value(row.get("evidence_urls")),
        "directory_fit": _string_value(row.get("directory_fit")),
        "directory_category": _string_value(row.get("directory_category")),
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
        "case_studies": profile.case_studies,
        "customers": profile.customers,
        "value_statements": profile.value_statements,
        "confidence": profile.confidence,
        "evidence_urls": profile.evidence_urls,
        "directory_fit": profile.directory_fit,
        "directory_category": profile.directory_category,
    }


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

