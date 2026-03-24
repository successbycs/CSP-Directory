"""Thin Apify Google Search discovery adapter."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import re
from urllib.parse import urlparse

from services.config.load_config import DiscoveryConfig, load_pipeline_config
from services.extraction.identity import (
    company_name_from_website,
    normalize_domain,
    normalize_vendor_website,
    normalize_website_url,
)

logger = logging.getLogger(__name__)
GOOGLE_SEARCH_ACTOR = "apify/google-search-scraper"
WEBSITE_CONTENT_CRAWLER_ACTOR = "apify/website-content-crawler"


def fetch_google_search(queries: list[str]) -> list[dict[str, str]]:
    """Fetch and normalize vendor candidates from Apify Google Search."""
    candidate_records = fetch_google_search_candidate_records(queries)
    unique_candidates: list[dict[str, str]] = []
    seen_domains: set[str] = set()

    for record in candidate_records:
        candidate_domain = str(record.get("candidate_domain", "")).strip()
        if not candidate_domain or candidate_domain in seen_domains:
            continue

        seen_domains.add(candidate_domain)
        unique_candidates.append(
            {
                "company_name": str(record.get("company_name", "")),
                "website": str(record.get("website", "")),
                "raw_description": str(record.get("raw_description", "")),
                "source": str(record.get("source", "")),
            }
        )

    logger.info(
        "Google Search deduplicated %s candidate records down to %s unique domains",
        len(candidate_records),
        len(unique_candidates),
    )
    return unique_candidates


def fetch_google_search_candidate_records(queries: list[str]) -> list[dict[str, object]]:
    """Fetch structured candidate records from Apify Google Search."""
    if not queries:
        return []

    client = get_apify_client()
    google_search_config = load_pipeline_config().discovery
    candidate_records: list[dict[str, object]] = []
    logger.info(
        "Using Google Search config: actor_id=%s, max_pages_per_query=%s, results_per_page=%s",
        google_search_config.actor_id,
        google_search_config.max_pages_per_query,
        google_search_config.results_per_page,
    )

    for query in queries:
        run = client.actor(google_search_config.actor_id).call(
            run_input={
                "queries": query,
                "maxPagesPerQuery": google_search_config.max_pages_per_query,
                "resultsPerPage": google_search_config.results_per_page,
            }
        )
        items = client.dataset(run["defaultDatasetId"]).list_items().items
        raw_results = _extract_google_search_results(items)
        query_candidates = _normalize_google_search_results(raw_results, google_search_config)
        query_candidate_records = _build_candidate_records(query, query_candidates)
        logger.info(
            'Google Search query "%s" returned %s raw results and %s filtered candidates',
            query,
            len(raw_results),
            len(query_candidates),
        )
        candidate_records.extend(query_candidate_records)

    return candidate_records


def discover_vendor_candidates(query: str) -> list[dict[str, str]]:
    """Compatibility wrapper for the current discovery layer."""
    return fetch_google_search([query])


def get_apify_client():
    """Create an Apify client from APIFY_API_TOKEN."""
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        raise RuntimeError("APIFY_API_TOKEN must be set")

    from apify_client import ApifyClient

    return ApifyClient(api_token)


def fetch_rendered_page(
    url: str,
    *,
    actor_id: str = WEBSITE_CONTENT_CRAWLER_ACTOR,
    max_pages: int = 1,
    use_proxy: bool = True,
) -> dict[str, object] | None:
    """Fetch one rendered page through Apify and normalize the first matching result."""
    normalized_url = normalize_website_url(url)
    if not normalized_url:
        return None

    client = get_apify_client()
    run = client.actor(actor_id).call(
        run_input={
            "startUrls": [{"url": normalized_url}],
            "includeUrlGlobs": [normalized_url, f"{normalized_url}/"],
            "maxCrawlPages": max(1, max_pages),
            "saveHtml": True,
            "saveMarkdown": True,
            "removeCookieWarnings": True,
            "proxyConfiguration": {"useApifyProxy": bool(use_proxy)},
        }
    )
    dataset_items = client.dataset(run["defaultDatasetId"]).list_items().items
    normalized_items = _normalize_rendered_page_items(dataset_items, actor_id=actor_id)
    if not normalized_items:
        return None
    return _select_rendered_page_result(normalized_url, normalized_items)


def _extract_google_search_results(
    items: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Extract raw Google Search result records from dataset items."""
    results: list[dict[str, object]] = []

    for item in items:
        organic_results = item.get("organicResults")
        if isinstance(organic_results, list) and organic_results:
            for organic_result in organic_results:
                if isinstance(organic_result, dict):
                    results.append(organic_result)
            continue

        results.append(item)

    return results


def _normalize_rendered_page_items(
    items: list[dict[str, object]],
    *,
    actor_id: str,
) -> list[dict[str, object]]:
    """Normalize Website Content Crawler dataset items into page payloads."""
    normalized_items: list[dict[str, object]] = []
    for item in items:
        normalized_url = normalize_website_url(item.get("url"))
        if not normalized_url:
            continue

        status_code = item.get("statusCode", item.get("httpStatusCode", 200))
        text = _clean_text(item.get("text")) or _clean_text(item.get("markdown"))
        html = _clean_text(item.get("html"))
        if not html and text:
            html = f"<html><body>{text}</body></html>"
        normalized_items.append(
            {
                "url": normalized_url,
                "status_code": int(status_code) if isinstance(status_code, int) else 200,
                "html": html,
                "text": text,
                "fetch_backend": "apify",
                "fetch_actor_id": actor_id,
            }
        )
    return normalized_items


def _select_rendered_page_result(
    requested_url: str,
    normalized_items: list[dict[str, object]],
) -> dict[str, object] | None:
    requested_domain = _domain_from_website(requested_url)
    for item in normalized_items:
        if item["url"] == requested_url:
            return item

    requested_path = urlparse(requested_url).path.rstrip("/")
    for item in normalized_items:
        item_url = str(item.get("url", ""))
        if _domain_from_website(item_url) != requested_domain:
            continue
        item_path = urlparse(item_url).path.rstrip("/")
        if requested_path and item_path.startswith(requested_path):
            return item

    for item in normalized_items:
        item_url = str(item.get("url", ""))
        if _domain_from_website(item_url) == requested_domain:
            return item
    return normalized_items[0] if normalized_items else None


def _normalize_google_search_results(
    items: list[dict[str, object]],
    config: DiscoveryConfig,
) -> list[dict[str, str]]:
    """Normalize raw Google Search results into vendor candidates."""
    candidates: list[dict[str, str]] = []

    for item in items:
        candidate = _normalize_google_search_result(item, config)
        if candidate:
            candidates.append(candidate)

    return candidates


def _normalize_google_search_result(
    item: dict[str, object],
    config: DiscoveryConfig,
) -> dict[str, str] | None:
    """Normalize one Google Search result into a vendor candidate."""
    raw_url = _clean_text(item.get("url"))
    if not _should_keep_google_search_result(raw_url, item, config):
        return None

    website = _normalize_website(raw_url)
    if not website:
        return None

    company_name = _select_company_name(
        title=_clean_text(item.get("title")),
        raw_url=raw_url,
        website=website,
        config=config,
    )
    return {
        "company_name": company_name,
        "website": website,
        "raw_description": _clean_text(item.get("description")),
        "source": "google_search",
    }


def _deduplicate_candidates_by_domain(
    candidates: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Deduplicate candidates by website domain."""
    unique_candidates: list[dict[str, str]] = []
    seen_domains: set[str] = set()

    for candidate in candidates:
        website = _normalize_website(candidate.get("website"))
        if not website:
            continue

        domain = _domain_from_website(website)
        if domain in seen_domains:
            continue

        seen_domains.add(domain)
        normalized_candidate = dict(candidate)
        normalized_candidate["website"] = website
        unique_candidates.append(normalized_candidate)

    return unique_candidates


def _build_candidate_records(
    query: str,
    candidates: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Return candidate records with discovery metadata for one query."""
    discovered_at = datetime.now(timezone.utc).isoformat()
    source_engine = load_pipeline_config().discovery.source_engine
    candidate_records: list[dict[str, object]] = []

    for source_rank, candidate in enumerate(candidates, start=1):
        candidate_domain = _domain_from_website(candidate["website"])
        candidate_records.append(
            {
                "candidate_domain": candidate_domain,
                "candidate_title": candidate["company_name"],
                "candidate_description": candidate.get("raw_description", ""),
                "source_query": query,
                "source_rank": source_rank,
                "discovered_at": discovered_at,
                "candidate_status": "new",
                "status": "new",
                "company_name": candidate["company_name"],
                "website": candidate["website"],
                "raw_description": candidate.get("raw_description", ""),
                "source": candidate.get("source", "google_search"),
                "source_engine": source_engine,
                "discovery_notes": "",
                "drop_reason": "",
            }
        )

    return candidate_records


def _normalize_website(value: object) -> str:
    """Normalize a website to a simple https://domain format."""
    return normalize_vendor_website(value)


def _domain_from_website(website: str) -> str:
    """Return the normalized domain for a website."""
    return normalize_domain(website)


def _company_name_from_website(website: str) -> str:
    """Build a simple fallback company name from a website domain."""
    return company_name_from_website(website)


def _select_company_name(title: str, raw_url: str, website: str, config: DiscoveryConfig) -> str:
    """Prefer the domain name when the result title looks like article content."""
    if not title:
        return _company_name_from_website(website)

    parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
    if (
        _has_article_like_path(parsed.path.lower(), config)
        or _looks_like_generic_content(title.lower(), config)
        or _looks_like_listicle_title(title.lower())
    ):
        return _company_name_from_website(website)

    return title


def _clean_text(value: object) -> str:
    """Return a stripped string value."""
    if value is None:
        return ""
    return str(value).strip()


def _should_keep_google_search_result(
    raw_url: str,
    item: dict[str, object],
    config: DiscoveryConfig,
) -> bool:
    """Return True when a search result looks like a vendor candidate."""
    if not raw_url:
        return False

    parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
    domain = parsed.netloc.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    if not domain or _is_denylisted_domain(domain, config):
        return False
    if _has_noise_subdomain(domain, config):
        return False
    if _has_noise_domain_hint(domain, config):
        return False

    path = parsed.path.lower()
    title = _clean_text(item.get("title")).lower()
    description = _clean_text(item.get("description")).lower()
    text = f"{title} {description}".strip()
    if _looks_like_access_interstitial(text, config):
        return False
    if _looks_like_job_or_career_content(path, title, description, config):
        return False
    if not _looks_like_customer_success_result(text, config):
        return False

    if _looks_like_listicle_title(title) and not _looks_like_product_description(description, config):
        return False

    if _has_article_like_path(path, config) and _looks_like_generic_content(
        text, config
    ) and not _looks_like_product_description(
        description, config
    ):
        return False

    return True


def _is_denylisted_domain(domain: str, config: DiscoveryConfig) -> bool:
    """Return True when the domain is an obvious non-vendor source."""
    return domain in config.junk_domain_denylist or any(
        domain.endswith(f".{blocked_domain}") for blocked_domain in config.junk_domain_denylist
    )


def _has_noise_subdomain(domain: str, config: DiscoveryConfig) -> bool:
    """Return True when the domain is an obvious content or jobs subdomain."""
    return any(domain.startswith(prefix) for prefix in config.noise_subdomain_prefixes)


def _has_noise_domain_hint(domain: str, config: DiscoveryConfig) -> bool:
    """Return True when the domain clearly belongs to job or content infrastructure."""
    return any(hint in domain for hint in config.noise_domain_hints)


def _has_article_like_path(path: str, config: DiscoveryConfig) -> bool:
    """Return True for paths that look like blogs, articles, or community pages."""
    return any(hint in path for hint in config.article_path_hints)


def _looks_like_generic_content(text: str, config: DiscoveryConfig) -> bool:
    """Return True for titles and descriptions that read like content pages."""
    return any(hint in text for hint in config.content_hints)


def _looks_like_access_interstitial(text: str, config: DiscoveryConfig) -> bool:
    """Return True when the result looks like a blocked page or challenge screen."""
    return any(hint in text for hint in config.interstitial_hints)


def _looks_like_listicle_title(title: str) -> bool:
    """Return True when a title looks like a roundup, comparison, or review page."""
    return bool(
        re.search(r"\b\d+\b", title) or re.search(r"\b\d{4}\b", title)
    ) and any(
        hint in title for hint in ["platform", "platforms", "tool", "tools", "review", "reviews", "vendor", "vendors"]
    )


def _looks_like_product_description(description: str, config: DiscoveryConfig) -> bool:
    """Return True when the description sounds like software, not editorial content."""
    return any(hint in description for hint in config.product_hints)


def _looks_like_job_or_career_content(
    path: str,
    title: str,
    description: str,
    config: DiscoveryConfig,
) -> bool:
    """Return True when the result is clearly a job posting or careers page."""
    combined_text = f"{title} {description}".strip()
    return any(path_hint in path for path_hint in config.job_path_hints) or any(
        hint in combined_text for hint in ("career", "careers", "job application", "jobs")
    )


def _looks_like_customer_success_result(text: str, config: DiscoveryConfig) -> bool:
    """Return True when the result text maps to the Customer Success lifecycle."""
    return any(hint in text for hint in config.customer_success_hints)
