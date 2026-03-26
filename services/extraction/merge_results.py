"""Merge deterministic and LLM extraction into one vendor profile."""

from __future__ import annotations

from typing import Any

from services.extraction import vendor_intel
from services.extraction.llm_extractor import LLMExtractionResult
from services.extraction.vendor_intel import VendorIntelligence


def merge_vendor_intelligence(
    deterministic: VendorIntelligence,
    llm_result: LLMExtractionResult | None,
) -> VendorIntelligence:
    """Merge deterministic extraction with optional LLM output."""
    if llm_result is None:
        return deterministic

    merged_mission = _prefer_text_value(deterministic.mission, llm_result.mission)
    merged_usp = _prefer_text_value(deterministic.usp, llm_result.usp)
    merged_icp = _merge_unique_strings(deterministic.icp, llm_result.icp)
    merged_icp_buyer = _merge_buyer_profiles(deterministic.icp_buyer, llm_result.icp_buyer)
    merged_use_cases = _merge_unique_strings(deterministic.use_cases, llm_result.use_cases)
    merged_pricing = _merge_unique_strings(deterministic.pricing, llm_result.pricing)
    merged_compliance = _merge_unique_strings(deterministic.compliance, llm_result.compliance)
    merged_products = _merge_named_records(deterministic.products, llm_result.products, key_field="name")
    merged_leadership = _merge_named_records(
        deterministic.leadership,
        llm_result.leadership,
        key_field="name",
        secondary_key="title",
    )
    merged_hq_address = _prefer_text_value(
        deterministic.hq_address or deterministic.company_hq,
        llm_result.hq_address or llm_result.company_hq,
    )
    merged_phone_numbers = _merge_unique_strings(deterministic.phone_numbers, llm_result.phone_numbers)
    merged_contact_emails = _merge_unique_strings(
        deterministic.contact_emails or ([deterministic.contact_email] if deterministic.contact_email else []),
        llm_result.contact_emails or ([llm_result.contact_email] if llm_result.contact_email else []),
    )
    merged_integration_categories = _merge_unique_strings(
        deterministic.integration_categories,
        llm_result.integration_categories,
    )
    merged_integrations = _merge_unique_strings(deterministic.integrations, llm_result.integrations)
    merged_external_enrichment = vendor_intel.normalize_external_enrichment_records(deterministic.external_enrichment)
    merged_support_signals = _merge_unique_strings(
        deterministic.support_signals,
        llm_result.support_signals,
    )
    merged_case_studies = _merge_unique_strings(deterministic.case_studies)
    merged_case_study_signals = _merge_unique_strings(deterministic.case_study_signals, llm_result.case_study_signals)
    merged_case_study_details = _merge_named_records(
        deterministic.case_study_details,
        llm_result.case_study_details,
        key_field="client",
        secondary_key="value_realized",
    )
    merged_testimonials = _merge_named_records(
        deterministic.testimonials,
        llm_result.testimonials,
        key_field="company",
        secondary_key="source_url",
    )
    merged_blog_posts = _merge_named_records(
        deterministic.blog_posts,
        llm_result.blog_posts,
        key_field="source_url",
        secondary_key="title",
    )
    merged_customers = _merge_unique_strings(deterministic.customers, llm_result.customers)
    merged_value_statements = _merge_unique_strings(
        deterministic.value_statements,
        llm_result.value_statements,
        vendor_intel._extract_value_statements(_build_signal_text(  # noqa: SLF001
        mission=merged_mission,
        usp=merged_usp,
        icp=merged_icp,
        use_cases=merged_use_cases,
            case_studies=merged_case_study_signals,
            customers=merged_customers,
            pricing=merged_pricing,
            value_statements=llm_result.value_statements,
        ).lower()),
    )

    return VendorIntelligence(
        vendor_name=deterministic.vendor_name,
        website=deterministic.website,
        source=deterministic.source,
        mission=merged_mission,
        usp=merged_usp,
        icp=merged_icp,
        icp_buyer=merged_icp_buyer,
        use_cases=merged_use_cases,
        lifecycle_stages=_merge_unique_strings(deterministic.lifecycle_stages, llm_result.lifecycle_stages),
        pricing=merged_pricing,
        free_trial=_prefer_optional_bool(deterministic.free_trial, llm_result.free_trial),
        soc2=_prefer_optional_bool(deterministic.soc2, llm_result.soc2 or ("SOC 2" in merged_compliance)),
        compliance=merged_compliance,
        founded=_prefer_text_value(deterministic.founded, llm_result.founded),
        products=merged_products,
        leadership=merged_leadership,
        ceo_name=_prefer_text_value(deterministic.ceo_name, llm_result.ceo_name),
        hq_address=merged_hq_address,
        phone_numbers=merged_phone_numbers,
        contact_emails=merged_contact_emails,
        company_hq=merged_hq_address,
        contact_email=_prefer_text_value(
            deterministic.contact_email or (merged_contact_emails[0] if merged_contact_emails else ""),
            llm_result.contact_email or (merged_contact_emails[0] if merged_contact_emails else ""),
        ),
        contact_page_url=deterministic.contact_page_url,
        demo_url=deterministic.demo_url,
        help_center_url=deterministic.help_center_url,
        support_url=deterministic.support_url,
        about_url=deterministic.about_url,
        team_url=deterministic.team_url,
        developer_docs_url=_prefer_text_value(deterministic.developer_docs_url, llm_result.developer_docs_url),
        integration_categories=merged_integration_categories,
        integrations=merged_integrations,
        external_enrichment=merged_external_enrichment,
        support_signals=merged_support_signals,
        case_studies=merged_case_studies,
        case_study_signals=merged_case_study_signals,
        case_study_details=merged_case_study_details,
        testimonials=merged_testimonials,
        blog_posts=merged_blog_posts,
        customers=merged_customers,
        value_statements=merged_value_statements,
        confidence=_prefer_confidence(deterministic.confidence, llm_result.confidence),
        source_urls=_merge_unique_strings(deterministic.source_urls, llm_result.source_urls, deterministic.evidence_urls),
        evidence_urls=deterministic.evidence_urls,
        directory_fit=deterministic.directory_fit,
        directory_category=deterministic.directory_category,
        include_in_directory=deterministic.include_in_directory,
    )


def _merge_unique_strings(*collections: list[str]) -> list[str]:
    merged: list[str] = []
    for collection in collections:
        for value in collection:
            cleaned_value = value.strip()
            if cleaned_value and cleaned_value not in merged:
                merged.append(cleaned_value)
    return merged


def _merge_buyer_profiles(*collections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for collection in collections:
        for item in vendor_intel.normalize_icp_buyer_profiles(collection):
            persona = str(item.get("persona") or "").strip()
            if not persona:
                continue
            key = persona.lower()
            existing = merged.get(key)
            if existing is None:
                merged[key] = item
                continue

            existing_confidence = _confidence_rank(str(existing.get("confidence") or ""))
            candidate_confidence = _confidence_rank(str(item.get("confidence") or ""))
            if candidate_confidence > existing_confidence:
                existing["confidence"] = item.get("confidence", "")
            existing["evidence"] = _merge_unique_strings(existing.get("evidence", []), item.get("evidence", []))
            existing["google_queries"] = _merge_unique_strings(
                existing.get("google_queries", []),
                item.get("google_queries", []),
            )[:5]
            existing["geo_queries"] = _merge_unique_strings(
                existing.get("geo_queries", []),
                item.get("geo_queries", []),
            )[:5]
    return list(merged.values())


def _merge_named_records(
    *collections: list[dict[str, Any]],
    key_field: str,
    secondary_key: str = "",
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for collection in collections:
        for item in collection:
            if not isinstance(item, dict):
                continue
            primary_value = str(item.get(key_field) or "").strip()
            secondary_value = str(item.get(secondary_key) or "").strip() if secondary_key else ""
            if not primary_value:
                continue
            key = (primary_value.lower(), secondary_value.lower())
            existing = merged.get(key)
            if existing is None:
                merged[key] = dict(item)
                continue
            for field_name, field_value in item.items():
                if isinstance(field_value, str):
                    merged[key][field_name] = _prefer_text_value(
                        str(existing.get(field_name) or ""),
                        field_value,
                    )
                elif isinstance(field_value, list):
                    merged[key][field_name] = _merge_unique_strings(
                        existing.get(field_name, []),
                        field_value,
                    )
    return list(merged.values())


def _prefer_text_value(deterministic_value: str, llm_value: str) -> str:
    """Prefer deterministic text unless the LLM output is materially richer."""
    cleaned_deterministic = deterministic_value.strip()
    cleaned_llm = llm_value.strip()

    if not cleaned_deterministic:
        return cleaned_llm
    if not cleaned_llm:
        return cleaned_deterministic
    if len(cleaned_llm) >= len(cleaned_deterministic) + 20:
        return cleaned_llm
    return cleaned_deterministic


def _prefer_optional_bool(deterministic_value: bool | None, llm_value: bool | None) -> bool | None:
    """Prefer known positive deterministic signals over weaker LLM negatives."""
    if deterministic_value is True:
        return True
    if llm_value is not None:
        return llm_value
    return deterministic_value


def _prefer_confidence(deterministic_confidence: str, llm_confidence: str) -> str:
    """Keep the strongest non-empty confidence label."""
    confidence_order = {"": 0, "low": 1, "medium": 2, "high": 3}
    cleaned_deterministic = deterministic_confidence.strip().lower()
    cleaned_llm = llm_confidence.strip().lower()

    if confidence_order.get(cleaned_llm, 0) > confidence_order.get(cleaned_deterministic, 0):
        return cleaned_llm
    return cleaned_deterministic


def _confidence_rank(value: str) -> int:
    return {"": 0, "low": 1, "medium": 2, "high": 3}.get(value.strip().lower(), 0)


def _build_signal_text(
    *,
    mission: str = "",
    usp: str = "",
    icp: list[str] | None = None,
    use_cases: list[str] | None = None,
    pricing: list[str] | None = None,
    case_studies: list[str] | None = None,
    customers: list[str] | None = None,
    value_statements: list[str] | None = None,
) -> str:
    parts = [mission, usp]
    parts.extend(icp or [])
    parts.extend(use_cases or [])
    parts.extend(pricing or [])
    parts.extend(case_studies or [])
    parts.extend(customers or [])
    parts.extend(value_statements or [])
    return " ".join(part for part in parts if part).strip()
