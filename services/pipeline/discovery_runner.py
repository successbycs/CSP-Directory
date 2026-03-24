"""Helpers for the explicit Phase 1 discovery crawl."""

from __future__ import annotations

from typing import Callable

from services.config.load_config import load_pipeline_config
from services.discovery import web_search

DiscoveryCandidateRecord = dict[str, object]
VendorCandidate = dict[str, str]


def run_discovery_phase(
    query_or_queries: str | list[str] | None,
    *,
    fetch_candidate_records_fn: Callable[[str | list[str] | None], list[DiscoveryCandidateRecord]] | None = None,
    vendor_exists_fn: Callable[[str], bool] | None = None,
) -> tuple[list[DiscoveryCandidateRecord], list[VendorCandidate], int]:
    """Return candidate records plus the queued vendors for enrichment."""
    fetch_candidate_records_fn = fetch_candidate_records_fn or web_search.search_web_candidates
    discovery_config = load_pipeline_config().discovery
    candidate_records = fetch_candidate_records_fn(query_or_queries)

    queued_vendor_candidates: list[VendorCandidate] = []
    deduplicated_records: list[DiscoveryCandidateRecord] = []
    seen_domains: set[str] = set()
    skipped_existing_count = 0

    for candidate_record in candidate_records:
        candidate_domain = str(candidate_record.get("candidate_domain", "")).strip()
        website = str(candidate_record.get("website", "")).strip()
        if not candidate_domain or not website:
            continue
        if candidate_domain in seen_domains:
            continue

        if len(deduplicated_records) >= discovery_config.max_candidate_domains_per_run:
            break

        seen_domains.add(candidate_domain)
        normalized_record = dict(candidate_record)
        status = "queued_for_enrichment"
        if vendor_exists_fn and vendor_exists_fn(website):
            status = "enriched"
            skipped_existing_count += 1
        normalized_record["candidate_status"] = status
        normalized_record["status"] = status
        deduplicated_records.append(normalized_record)

        if status != "queued_for_enrichment":
            continue

        queued_vendor_candidates.append(
            {
                "candidate_domain": candidate_domain,
                "candidate_title": str(normalized_record.get("candidate_title", "")),
                "candidate_description": str(normalized_record.get("candidate_description", "")),
                "source_query": str(normalized_record.get("source_query", "")),
                "source_rank": str(normalized_record.get("source_rank", "")),
                "discovered_at": str(normalized_record.get("discovered_at", "")),
                "candidate_status": status,
                "status": status,
                "company_name": str(normalized_record.get("company_name", "")),
                "vendor_name": str(normalized_record.get("company_name", "")),
                "website": website,
                "source": str(normalized_record.get("source", "google_search")),
                "raw_description": str(normalized_record.get("raw_description", "")),
            }
        )

    return deduplicated_records, queued_vendor_candidates, skipped_existing_count
