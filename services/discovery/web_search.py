"""Compatibility wrapper around the Apify-based discovery layer."""

from __future__ import annotations

from services.discovery import apify_sources
from services.config.load_config import load_pipeline_config


def search_web(query_or_queries: str | list[str] | None = None) -> list[dict[str, str]]:
    """Return filtered vendor candidates using Apify Google Search."""
    queries = _normalize_queries(query_or_queries)
    candidates = apify_sources.fetch_google_search(queries)
    return [
        {
            "company_name": candidate["company_name"],
            "vendor_name": candidate["company_name"],
            "website": candidate["website"],
            "source": candidate["source"],
            "raw_description": candidate.get("raw_description", ""),
        }
        for candidate in candidates
    ]


def search_web_candidates(query_or_queries: str | list[str] | None = None) -> list[dict[str, object]]:
    """Return structured discovery candidate records using Apify Google Search."""
    queries = _normalize_queries(query_or_queries)
    return apify_sources.fetch_google_search_candidate_records(queries)


def _normalize_queries(query_or_queries: str | list[str] | None) -> list[str]:
    """Normalize discovery input into the ordered list Apify expects."""
    if query_or_queries is None:
        return list(load_pipeline_config().discovery.queries)

    if isinstance(query_or_queries, str):
        return [query_or_queries]

    return [query for query in query_or_queries if query]
