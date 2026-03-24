"""Vendor enrichment service.

This module provides functions to fetch and enrich vendor website data.
"""

from __future__ import annotations

import html
import logging
import re

import requests

from services.config.load_config import load_pipeline_config
from services.extraction.identity import company_name_from_website
from services.extraction.page_text_extractor import extract_visible_text
from services.enrichment.discovery_mode import fetch_page_with_fallback

logger = logging.getLogger(__name__)

BLOCKED_PAGE_HINTS = (
    "403 forbidden",
    "access denied",
    "just a moment",
)


def fetch_vendor_homepage(vendor: dict[str, str]) -> dict[str, str | int]:
    """Fetch the homepage for a vendor and return structured page data.

    Uses Apify Website Content Crawler as the primary fetch backend when configured
    (external_fetch_backend == "apify"). Falls back to plain HTTP requests if Apify
    fails or is not configured.

    Args:
        vendor: A dictionary with vendor information, including 'website'.

    Returns:
        A dictionary with vendor name, website, page type, status code, HTML, and extracted text.
        If fetch fails, status_code is 0 and html/text are empty.
    """
    website = vendor["website"]
    vendor_name = _resolve_vendor_name(vendor.get("vendor_name", ""), website, "")
    config = load_pipeline_config().enrichment

    # Apify-first path: use Website Content Crawler as the primary enrichment source
    if config.external_fetch_backend == "apify":
        logger.info("Fetching %s via Apify Website Content Crawler (primary path)", website)
        apify_payload = fetch_page_with_fallback(website, config=config)
        if apify_payload:
            status_code = int(apify_payload.get("status_code", 200))
            html_content = str(apify_payload.get("html", ""))
            text = str(apify_payload.get("text", "")) or extract_visible_text(html_content)
            vendor_name = _resolve_vendor_name(vendor.get("vendor_name", ""), website, html_content)
            fetch_backend = str(apify_payload.get("fetch_backend", "apify"))
            logger.info(
                "Apify fetch succeeded for %s: status=%s, text_length=%s",
                website,
                status_code,
                len(text),
            )
            return {
                "vendor_name": vendor_name,
                "website": website,
                "url": website,
                "source": vendor.get("source", ""),
                "page_type": "homepage",
                "status_code": status_code,
                "html": html_content,
                "text": text,
                "fetch_backend": fetch_backend,
            }
        else:
            logger.warning("Apify fetch returned no result for %s, falling back to HTTP", website)

    # Plain HTTP fallback (or primary when Apify not configured)
    request_timeout_seconds = config.request_timeout_seconds
    try:
        response = requests.get(website, timeout=request_timeout_seconds)
        status_code = response.status_code
        html_content = response.text
        fetch_backend = "requests"
        if _should_skip_page(response.status_code, response.text):
            fallback_payload = fetch_page_with_fallback(website, config=config)
            if fallback_payload:
                status_code = int(fallback_payload.get("status_code", status_code))
                html_content = str(fallback_payload.get("html", ""))
                vendor_name = _resolve_vendor_name(vendor.get("vendor_name", ""), website, html_content)
                text = str(fallback_payload.get("text", "")) or extract_visible_text(html_content)
                fetch_backend = str(fallback_payload.get("fetch_backend", "fallback"))
            else:
                html_content = ""
                text = ""
        else:
            vendor_name = _resolve_vendor_name(vendor.get("vendor_name", ""), website, html_content)
            text = extract_visible_text(html_content)
    except requests.RequestException:
        fetch_backend = ""
        fallback_payload = fetch_page_with_fallback(website, config=config)
        if fallback_payload:
            status_code = int(fallback_payload.get("status_code", 200))
            html_content = str(fallback_payload.get("html", ""))
            vendor_name = _resolve_vendor_name(vendor.get("vendor_name", ""), website, html_content)
            text = str(fallback_payload.get("text", "")) or extract_visible_text(html_content)
            fetch_backend = str(fallback_payload.get("fetch_backend", "fallback"))
        else:
            html_content = ""
            text = ""
            status_code = 0
    return {
        "vendor_name": vendor_name,
        "website": website,
        "url": website,
        "source": vendor.get("source", ""),
        "page_type": "homepage",
        "status_code": status_code,
        "html": html_content,
        "text": text,
        "fetch_backend": fetch_backend,
    }


def _should_skip_page(status_code: int, html_content: str) -> bool:
    """Return True when the fetched page should not be used for extraction."""
    if status_code >= 400:
        return True

    lowered_html = html_content.lower()
    return any(hint in lowered_html for hint in BLOCKED_PAGE_HINTS)


def _resolve_vendor_name(search_name: str, website: str, html_content: str) -> str:
    """Prefer homepage-derived naming, then cleaned search hint, then domain fallback."""
    for candidate in _homepage_name_candidates(html_content):
        cleaned_candidate = _clean_vendor_name_candidate(candidate)
        if cleaned_candidate:
            return cleaned_candidate

    cleaned_search_name = _clean_vendor_name_candidate(search_name)
    if cleaned_search_name:
        return cleaned_search_name

    return _company_name_from_website(website)


def _homepage_name_candidates(html_content: str) -> list[str]:
    """Return possible vendor names extracted from homepage HTML."""
    if not html_content:
        return []

    patterns = [
        r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']application-name["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']apple-mobile-web-app-title["\'][^>]+content=["\'](.*?)["\']',
        r"<title[^>]*>(.*?)</title>",
        r"<h1[^>]*>(.*?)</h1>",
    ]

    candidates: list[str] = []
    for pattern in patterns:
        match = re.search(pattern, html_content, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        candidate = re.sub(r"<[^>]+>", " ", match.group(1))
        candidate = re.sub(r"\s+", " ", html.unescape(candidate)).strip()
        if candidate:
            candidates.append(candidate)

    return candidates


def _clean_vendor_name_candidate(candidate: str) -> str:
    """Return a vendor-like name or an empty string when the candidate looks weak."""
    normalized_candidate = re.sub(r"\s+", " ", html.unescape(candidate)).strip()
    if not normalized_candidate:
        return ""

    for separator in (" | ", " - ", " – ", " — ", ": "):
        if separator in normalized_candidate:
            for segment in normalized_candidate.split(separator):
                cleaned_segment = _clean_vendor_name_candidate(segment)
                if cleaned_segment:
                    return cleaned_segment

    lowered = normalized_candidate.lower()
    if _looks_like_article_title(lowered):
        return ""
    if len(normalized_candidate.split()) > 5:
        return ""
    if len(normalized_candidate) > 40:
        return ""

    return normalized_candidate


def _looks_like_article_title(text: str) -> bool:
    """Return True when a title looks like an article, listicle, or category page."""
    generic_name_hints = (
        "customer success platform",
        "customer success software",
        "customer onboarding automation",
        "onboarding platform",
        "customer onboarding platform",
        "customer health score",
    )
    if text in generic_name_hints:
        return True

    if re.search(r"\b\d{4}\b", text):
        return True

    article_hints = (
        "best ",
        "blog",
        "case studies",
        "case study",
        "compare",
        "comparison",
        "guide",
        "guides",
        "maximize ",
        "maximizing",
        "how to",
        "releases for",
        "review",
        "reviews",
        "top ",
        "what is ",
        " vs ",
    )
    return any(hint in text for hint in article_hints)


def _company_name_from_website(website: str) -> str:
    """Build a simple fallback name from the website domain."""
    return company_name_from_website(website)
