"""Tracxn teaser enrichment: extract founded, hq_address, funding_stage, total_funding.

Crawls tracxn.com/d/companies/{slug}/ teaser pages (no auth required).
Safe-upsert mode: only writes fields that are currently null/empty in Supabase.
Includes a canary check before each batch to detect Tracxn layout changes.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable
from urllib.parse import quote

import requests

from services.extraction.page_text_extractor import extract_visible_text

logger = logging.getLogger(__name__)

TRACXN_BASE = "https://tracxn.com/d/companies"
CANARY_SLUG = "gainsight"  # Known Tracxn entry used to validate scraping still works
REQUEST_TIMEOUT = 15
BATCH_DELAY_SECONDS = 1.5  # Polite delay between requests

_FUNDING_STAGE_PATTERNS = [
    r"Series\s+[A-Z]",
    r"Seed(?:\s+Round)?",
    r"Pre-Seed",
    r"Series\s+[A-Z]{2,}",
    r"IPO",
    r"Acquired",
    r"Growth",
    r"Private Equity",
    r"Bootstrapped",
    r"Angel",
]
_FUNDING_STAGE_RE = re.compile(
    "|".join(f"({p})" for p in _FUNDING_STAGE_PATTERNS), re.IGNORECASE
)
_TOTAL_FUNDING_RE = re.compile(r"\$[\d.,]+\s*[BMK]", re.IGNORECASE)
_FOUNDED_RE = re.compile(r"\b(19|20)\d{2}\b")


def derive_tracxn_slug(vendor_name: str, website: str = "") -> str:
    """Derive a Tracxn slug from the vendor name or domain."""
    if website:
        domain = re.sub(r"^https?://(?:www\.)?", "", website).split("/")[0]
        base = domain.split(".")[0]
        if len(base) >= 3:
            return base.lower()
    slug = re.sub(r"[^a-z0-9 ]", "", vendor_name.lower())
    slug = slug.strip().replace(" ", "-")
    return slug


def fetch_tracxn_teaser(
    slug: str,
    *,
    request_get: Callable[..., Any] | None = None,
) -> dict[str, str] | None:
    """Fetch and parse the Tracxn teaser page for the given slug.

    Returns a dict with any of: founded, hq_address, funding_stage, total_funding.
    Returns None if the page is unreachable or the layout is unrecognised.
    """
    url = f"{TRACXN_BASE}/{quote(slug)}/"
    get_fn = request_get or requests.get
    try:
        response = get_fn(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    except requests.RequestException as exc:
        logger.warning("Tracxn fetch failed for %s: %s", slug, exc)
        return None

    if response.status_code == 404:
        logger.debug("Tracxn: no page for slug %s", slug)
        return None
    if response.status_code != 200:
        logger.warning("Tracxn returned %s for slug %s", response.status_code, slug)
        return None

    return _parse_tracxn_page(response.text, slug)


def _parse_tracxn_page(html: str, slug: str) -> dict[str, str] | None:
    """Extract structured fields from Tracxn teaser HTML."""
    text = extract_visible_text(html)

    if not text or len(text) < 50:
        logger.debug("Tracxn: empty or too-short page for %s", slug)
        return None

    result: dict[str, str] = {}

    # Founded year
    year_match = _FOUNDED_RE.search(text)
    if year_match:
        result["founded"] = year_match.group(0)

    # HQ address — look for JSON-LD structured data or label heuristics
    hq = _extract_hq_from_html(html, text)
    if hq:
        result["hq_address"] = hq

    # Funding stage
    stage_match = _FUNDING_STAGE_RE.search(text)
    if stage_match:
        result["funding_stage"] = stage_match.group(0).strip()

    # Total funding
    funding_match = _TOTAL_FUNDING_RE.search(text)
    if funding_match:
        result["total_funding"] = funding_match.group(0).strip()

    return result if result else None


def _extract_hq_from_html(html: str, text: str) -> str:
    """Try to extract HQ city/country from JSON-LD or text heuristics."""
    import json
    # Look for JSON-LD structured data in raw HTML
    for match in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(match.group(1))
            address = data.get("address", {})
            if isinstance(address, dict):
                parts = [
                    address.get("addressLocality", ""),
                    address.get("addressRegion", ""),
                    address.get("addressCountry", ""),
                ]
                hq = ", ".join(p for p in parts if p)
                if hq:
                    return hq
        except Exception:
            pass

    # Text heuristics
    for pattern in [r"Headquarters[:\s]+([A-Z][^\n,;|]{3,50})", r"HQ[:\s]+([A-Z][^\n,;|]{3,50})"]:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()

    return ""


def run_canary_check(*, request_get: Callable[..., Any] | None = None) -> bool:
    """Verify the Tracxn layout still returns parseable data for a known slug.

    Returns True if canary passes, False if the page is unusable.
    Callers should abort the batch if this returns False.
    """
    result = fetch_tracxn_teaser(CANARY_SLUG, request_get=request_get)
    if result is None:
        logger.warning("Tracxn canary failed: no data returned for %s", CANARY_SLUG)
        return False
    if not result:
        logger.warning("Tracxn canary returned empty dict for %s — layout may have changed", CANARY_SLUG)
        return False
    logger.info("Tracxn canary passed: %s → %s", CANARY_SLUG, result)
    return True


def enrich_vendors_from_tracxn(
    vendor_rows: list[dict[str, Any]],
    *,
    upsert_fn: Callable[[str, dict[str, Any]], None] | None = None,
    request_get: Callable[..., Any] | None = None,
    skip_canary: bool = False,
) -> dict[str, Any]:
    """Enrich a list of vendor rows with Tracxn teaser data.

    Safe-upsert: only writes fields that are currently null/empty.
    Runs a canary check before the batch; aborts if it fails.

    Returns a summary dict: {attempted, enriched, skipped_canary, miss_count, errors}.
    """
    if not skip_canary:
        if not run_canary_check(request_get=request_get):
            return {"attempted": 0, "enriched": 0, "skipped_canary": True, "miss_count": 0, "errors": []}

    FIELDS = ("founded", "hq_address", "funding_stage", "total_funding")
    enriched = 0
    miss_count = 0
    errors: list[str] = []

    for vendor in vendor_rows:
        website = vendor.get("website", "")
        vendor_name = vendor.get("vendor_name", "")
        if not vendor_name and not website:
            continue

        # Only enrich fields that are currently empty
        needs = [f for f in FIELDS if not vendor.get(f)]
        if not needs:
            logger.debug("Tracxn: %s already fully enriched, skipping", vendor_name)
            continue

        slug = derive_tracxn_slug(vendor_name, website)
        try:
            data = fetch_tracxn_teaser(slug, request_get=request_get)
        except Exception as exc:
            errors.append(f"{vendor_name}: {exc}")
            continue

        if not data:
            miss_count += 1
            logger.debug("Tracxn: no data for %s (slug=%s)", vendor_name, slug)
            time.sleep(BATCH_DELAY_SECONDS)
            continue

        # Safe-upsert: only write fields that were empty and that Tracxn found
        updates = {f: data[f] for f in needs if data.get(f)}
        if updates and upsert_fn:
            try:
                upsert_fn(website or vendor_name, updates)
                enriched += 1
                logger.info("Tracxn enriched %s: %s", vendor_name, list(updates.keys()))
            except Exception as exc:
                errors.append(f"{vendor_name} upsert: {exc}")
        elif updates:
            enriched += 1  # dry-run / no upsert_fn

        time.sleep(BATCH_DELAY_SECONDS)

    return {
        "attempted": len(vendor_rows),
        "enriched": enriched,
        "skipped_canary": False,
        "miss_count": miss_count,
        "errors": errors,
    }
