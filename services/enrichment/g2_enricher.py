"""G2 enrichment: augment vendors with G2 profile data.

For each vendor, finds their G2 product page (heuristic slug construction
first, then Google Search fallback) and fetches it with a three-tier strategy:
  Tier 1 — direct HTTP (requests)
  Tier 2 — Playwright (headless browser, local)
  Tier 3 — Apify WCC (JS-heavy fallback, via n8n Cloud)

Extracts structured data into G2-specific fields and augments existing fields.
Safe-upsert mode: only writes fields that are currently null/empty.
Includes a canary check before each batch to detect G2 layout changes.
G2 must remain in junk_domain_denylist for discovery — it is an enrichment
source only, never a vendor entry.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable
from urllib.parse import urlparse

import requests

from services.extraction.page_text_extractor import extract_visible_text

logger = logging.getLogger(__name__)

_G2_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

CANARY_VENDOR_NAME = "Gainsight"
CANARY_EXPECTED_URL_FRAGMENT = "g2.com/products/"
REQUEST_TIMEOUT = 30
BATCH_DELAY_SECONDS = 2.0  # G2 is rate-sensitive

# Regex patterns for parsing G2 profile text
_RATING_RE = re.compile(r"(\d+\.\d+)\s*(?:out of 5|stars?|\/ ?5)", re.IGNORECASE)
_REVIEW_COUNT_RE = re.compile(r"([\d,]+)\s+reviews?", re.IGNORECASE)
_MARKET_SEGMENT_RE = re.compile(
    r"(Small-Business|Mid-Market|Enterprise)\s+(?:users?|segment|customers?|buyers?)",
    re.IGNORECASE,
)
_G2_URL_RE = re.compile(r"https?://(?:www\.)?g2\.com/products/[^\s\"'<>]+", re.IGNORECASE)
_SOC2_RE = re.compile(r"SOC\s*2", re.IGNORECASE)
_GDPR_RE = re.compile(r"\bGDPR\b", re.IGNORECASE)


def _guess_g2_url(vendor_name: str) -> str | None:
    """Construct a probable G2 product URL from vendor name."""
    slug = re.sub(r"[^a-z0-9]+", "-", vendor_name.lower()).strip("-")
    if not slug:
        return None
    return f"https://www.g2.com/products/{slug}"


def _validate_g2_url(url: str) -> bool:
    """Return True if the URL resolves to a real G2 product page (not a search/redirect).

    Uses _is_g2_product_url on the final URL after redirects to avoid false
    positives from query-string redirects like g2.com/products?query=foo.
    """
    try:
        resp = requests.get(
            url, timeout=REQUEST_TIMEOUT, headers=_G2_REQUEST_HEADERS, allow_redirects=True
        )
        return resp.status_code < 400 and _is_g2_product_url(resp.url)
    except Exception:
        return False


def _fetch_g2_page_tiered(url: str) -> dict[str, object] | None:
    """Fetch a G2 page with three-tier fallback: HTTP → Playwright → Apify."""
    from services.config.load_config import load_pipeline_config
    from services.enrichment.discovery_mode import fetch_page_with_fallback

    # Tier 1: direct HTTP
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=_G2_REQUEST_HEADERS)
        if resp.status_code < 400:
            text = extract_visible_text(resp.text)
            if text and len(text) > 200:
                logger.debug("G2 HTTP tier succeeded for %s", url)
                return {
                    "url": url,
                    "status_code": resp.status_code,
                    "html": resp.text,
                    "text": text,
                    "fetch_backend": "requests",
                }
    except Exception as exc:
        logger.debug("G2 HTTP tier failed for %s: %s", url, exc)

    # Tier 2 (Playwright) → Tier 3 (Apify) via existing fallback chain
    config = load_pipeline_config().enrichment
    return fetch_page_with_fallback(url, config=config)


def _search_g2_raw(vendor_name: str) -> str | None:
    """Search for a G2 product URL by calling n8n directly, bypassing the
    junk_domain_denylist (g2.com is denylisted for discovery but is a valid
    enrichment source).

    Returns the first g2.com/products/ URL from the raw search results.
    """
    from services import n8n_client
    from services.config.load_config import load_pipeline_config

    config = load_pipeline_config().discovery
    query = f"{vendor_name} site:g2.com"
    try:
        response = n8n_client.post_webhook(
            "framework-web-research",
            {
                "query": query,
                "max_results": config.results_per_page,
                "actor_id": config.actor_id,
            },
        )
    except Exception as exc:
        logger.warning("G2 raw search failed for %s: %s", vendor_name, exc)
        raise

    for source in response.get("sources") or []:
        url = source.get("url", "")
        if _is_g2_product_url(url):
            return url
    return None


def find_g2_url(
    vendor_name: str,
    *,
    search_fn: Callable[[list[str]], list[dict[str, str]]] | None = None,
) -> str | None:
    """Find a vendor's G2 profile URL.

    Tries heuristic URL construction first, then falls back to a raw n8n
    Google Search (bypassing the junk_domain_denylist so g2.com results
    are not filtered out).

    Returns the first g2.com/products/ URL found, or None if not found.
    """
    # Tier 1: construct from vendor name and validate with a GET
    guessed = _guess_g2_url(vendor_name)
    if guessed and _validate_g2_url(guessed):
        logger.debug("G2 URL resolved via heuristic for %s: %s", vendor_name, guessed)
        return guessed

    # Tier 2: raw n8n Google Search (bypasses denylist)
    # search_fn injection is used in tests; production always uses _search_g2_raw
    if search_fn is not None:
        query = f"{vendor_name} site:g2.com"
        try:
            results = search_fn([query])
        except Exception as exc:
            logger.warning("G2 search failed for %s: %s", vendor_name, exc)
            raise
        for result in results:
            website = result.get("website", "")
            if _is_g2_product_url(website):
                return website
        return None

    return _search_g2_raw(vendor_name)


def _is_g2_product_url(url: str) -> bool:
    """Return True if the URL is a G2 product profile page."""
    if not url:
        return False
    parsed = urlparse(url)
    domain = parsed.netloc.lower().lstrip("www.")
    return domain == "g2.com" and "/products/" in parsed.path


def fetch_g2_profile(
    g2_url: str,
    *,
    fetch_page_fn: Callable[[str], dict[str, object] | None] | None = None,
) -> dict[str, Any] | None:
    """Fetch and parse a G2 product profile page.

    Returns a dict with any of: g2_rating, g2_review_count, g2_market_segment,
    g2_categories, testimonials, icp, soc2, compliance.
    Returns None if the page is unreachable or the layout is unrecognised.
    """
    fetch_fn = fetch_page_fn or _fetch_g2_page_tiered
    try:
        page = fetch_fn(g2_url)
    except Exception as exc:
        logger.warning("G2 fetch failed for %s: %s", g2_url, exc)
        return None

    if not page:
        logger.debug("G2: no page returned for %s", g2_url)
        return None

    text = str(page.get("text", "") or page.get("html", ""))
    if not text or len(text) < 100:
        logger.debug("G2: empty or too-short page for %s", g2_url)
        return None

    return _parse_g2_profile(text, g2_url)


def _parse_g2_profile(text: str, g2_url: str) -> dict[str, Any] | None:
    """Extract structured fields from G2 profile text."""
    if not text or len(text) < 50:
        return None

    result: dict[str, Any] = {}

    # g2_url (confirmed — we successfully fetched it)
    result["g2_url"] = g2_url

    # g2_rating
    rating_match = _RATING_RE.search(text)
    if rating_match:
        try:
            result["g2_rating"] = float(rating_match.group(1))
        except ValueError:
            pass

    # g2_review_count
    review_match = _REVIEW_COUNT_RE.search(text)
    if review_match:
        try:
            result["g2_review_count"] = int(review_match.group(1).replace(",", ""))
        except ValueError:
            pass

    # g2_market_segment — take the first/dominant one mentioned
    segment_match = _MARKET_SEGMENT_RE.search(text)
    if segment_match:
        raw = segment_match.group(1).strip()
        # Normalise to spec values
        if "small" in raw.lower():
            result["g2_market_segment"] = "SMB"
        elif "mid" in raw.lower():
            result["g2_market_segment"] = "Mid-Market"
        else:
            result["g2_market_segment"] = "Enterprise"

    # g2_categories — look for G2 category tag patterns
    result["g2_categories"] = _extract_g2_categories(text)

    # testimonials — pros extracted from reviews
    result["testimonials"] = _extract_testimonials(text)

    # icp — reviewer job titles
    result["icp"] = _extract_reviewer_titles(text)

    # compliance — SOC2, GDPR signals
    compliance: list[str] = []
    if _SOC2_RE.search(text):
        compliance.append("SOC 2")
        result["soc2"] = True
    if _GDPR_RE.search(text):
        compliance.append("GDPR")
    if compliance:
        result["compliance"] = compliance

    return result if len(result) > 1 else None  # must have more than just g2_url


def _extract_g2_categories(text: str) -> list[str]:
    """Extract G2 category tags from profile text."""
    categories: list[str] = []
    # G2 categories appear as "Categories: X, Y, Z" or near "In G2 categories"
    for pattern in [
        r"Categor(?:y|ies)[:\s]+([A-Za-z ,&]+?)(?:\n|\.|\|)",
        r"Listed in[:\s]+([A-Za-z ,&]+?)(?:\n|\.|\|)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            cats = [c.strip() for c in re.split(r"[,&]", raw) if c.strip() and len(c.strip()) > 2]
            categories.extend(cats)
            break
    return list(dict.fromkeys(categories))  # deduplicate, preserve order


def _extract_testimonials(text: str) -> list[dict[str, str]]:
    """Extract testimonial snippets (pros) from G2 review text."""
    testimonials: list[dict[str, str]] = []
    # G2 review pros appear after "What do you like best" or "Pros:"
    for pattern in [
        r"What do you like best[^?]*\?\s*(.{30,300}?)(?:\n\n|What do you|Cons:|$)",
        r"Pros?:\s*(.{30,300}?)(?:\n\n|Cons?:|$)",
    ]:
        for m in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
            snippet = m.group(1).strip().replace("\n", " ")
            if len(snippet) > 30:
                testimonials.append({"source": "G2", "quote": snippet[:300]})
            if len(testimonials) >= 5:
                break
        if testimonials:
            break
    return testimonials


def _extract_reviewer_titles(text: str) -> list[str]:
    """Extract reviewer job titles from G2 profile."""
    titles: list[str] = []
    # G2 shows reviewer titles like "John D. | Director of Customer Success"
    for m in re.finditer(r"\|\s*([A-Z][a-zA-Z\s]{5,50}?)(?:\s+at\s+|\s+in\s+|\n|$)", text):
        title = m.group(1).strip()
        if _looks_like_job_title(title):
            titles.append(title)
        if len(titles) >= 10:
            break
    return list(dict.fromkeys(titles))


def _looks_like_job_title(text: str) -> bool:
    """Heuristic: return True if the text looks like a job title."""
    title_hints = (
        "director", "manager", "vp ", "vice president", "head of", "chief",
        "analyst", "specialist", "lead", "engineer", "success", "operations",
        "owner", "founder", "president", "consultant",
    )
    lowered = text.lower()
    return any(hint in lowered for hint in title_hints) and len(text.split()) <= 8


def run_canary_check(
    *,
    search_fn: Callable[[list[str]], list[dict[str, str]]] | None = None,
    fetch_page_fn: Callable[[str], dict[str, object] | None] | None = None,
) -> bool:
    """Verify G2 URL finding AND page parsing work for a known vendor.

    Stage 1: find the G2 URL for the canary vendor.
    Stage 2: fetch the page and assert at least one structured field is extracted.
             This catches G2 layout changes that leave URLs intact but break parsing.

    Returns True if both stages pass, False otherwise.
    Callers should abort the batch if this returns False.
    """
    g2_url = find_g2_url(CANARY_VENDOR_NAME, search_fn=search_fn)
    if not g2_url:
        logger.warning("G2 canary failed: no G2 URL found for %s", CANARY_VENDOR_NAME)
        return False
    if CANARY_EXPECTED_URL_FRAGMENT not in g2_url:
        logger.warning("G2 canary: URL for %s looks wrong: %s", CANARY_VENDOR_NAME, g2_url)
        return False

    data = fetch_g2_profile(g2_url, fetch_page_fn=fetch_page_fn)
    if not data:
        logger.warning(
            "G2 canary failed: URL found (%s) but page returned no parseable fields — "
            "G2 layout may have changed",
            g2_url,
        )
        return False

    # Exclude g2_url — it's the input URL, not an extracted field.
    # At least one of rating/review_count/segment/categories must be present.
    _CANARY_CHECK_FIELDS = ("g2_rating", "g2_review_count", "g2_market_segment", "g2_categories")
    parsed_fields = [f for f in _CANARY_CHECK_FIELDS if data.get(f)]
    if not parsed_fields:
        logger.warning(
            "G2 canary failed: page fetched for %s but no structured fields extracted — "
            "check regex patterns against current G2 HTML",
            CANARY_VENDOR_NAME,
        )
        return False

    logger.info("G2 canary passed: %s → %s (fields: %s)", CANARY_VENDOR_NAME, g2_url, parsed_fields)
    return True


# Fields we write to (new G2-specific + existing augmented fields)
_G2_NEW_FIELDS = ("g2_url", "g2_rating", "g2_review_count", "g2_market_segment", "g2_categories")
_G2_AUGMENTED_FIELDS = ("testimonials", "soc2", "compliance")
# Note: reviewer job titles from G2 are NOT written to `icp` — icp holds canonical
# segment labels (Enterprise/SMB/Mid-Market), not individual reviewer titles.
_ALL_G2_FIELDS = _G2_NEW_FIELDS + _G2_AUGMENTED_FIELDS


def enrich_vendors_from_g2(
    vendor_rows: list[dict[str, Any]],
    *,
    upsert_fn: Callable[[str, dict[str, Any]], None] | None = None,
    search_fn: Callable[[list[str]], list[dict[str, str]]] | None = None,
    fetch_page_fn: Callable[[str], dict[str, object] | None] | None = None,
    skip_canary: bool = False,
) -> dict[str, Any]:
    """Enrich a list of vendor rows with G2 profile data (Python-side implementation).

    Safe-upsert: only writes fields that are currently null/empty.
    Runs a canary check before the batch; aborts if it fails.

    In production, prefer trigger_g2_via_n8n() which delegates to the n8n
    Cloud workflow. This function is used for local testing and as a fallback.

    Returns a summary dict: {attempted, enriched, skipped_canary, miss_count, errors}.
    """
    if not skip_canary:
        if not run_canary_check(search_fn=search_fn):
            return {
                "attempted": 0,
                "enriched": 0,
                "skipped_canary": True,
                "miss_count": 0,
                "errors": [],
            }

    enriched = 0
    miss_count = 0
    errors: list[str] = []

    for vendor in vendor_rows:
        vendor_name = vendor.get("vendor_name", "")
        website = vendor.get("website", "")
        if not vendor_name and not website:
            continue

        g2_url = vendor.get("g2_url", "")
        needs = [f for f in _ALL_G2_FIELDS if not vendor.get(f)]
        if not needs:
            logger.debug("G2: %s already fully enriched, skipping", vendor_name)
            continue

        if not g2_url:
            try:
                g2_url = find_g2_url(vendor_name, search_fn=search_fn)
            except Exception as exc:
                errors.append(f"{vendor_name} search: {exc}")
                time.sleep(BATCH_DELAY_SECONDS)
                continue

        if not g2_url:
            miss_count += 1
            logger.debug("G2: no profile found for %s", vendor_name)
            time.sleep(BATCH_DELAY_SECONDS)
            continue

        try:
            data = fetch_g2_profile(g2_url, fetch_page_fn=fetch_page_fn)
        except Exception as exc:
            errors.append(f"{vendor_name} fetch: {exc}")
            time.sleep(BATCH_DELAY_SECONDS)
            continue

        if not data:
            miss_count += 1
            logger.debug("G2: no parseable data for %s (%s)", vendor_name, g2_url)
            time.sleep(BATCH_DELAY_SECONDS)
            continue

        updates = {f: data[f] for f in needs if data.get(f) is not None}
        if updates and upsert_fn:
            try:
                upsert_fn(website or vendor_name, updates)
                enriched += 1
                logger.info("G2 enriched %s: %s", vendor_name, list(updates.keys()))
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


def trigger_g2_via_n8n(
    vendor_rows: list[dict[str, Any]],
    *,
    skip_canary: bool = False,
    fallback_to_python: bool = True,
    upsert_fn: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Trigger the n8n Cloud G2 enrichment workflow for a list of vendors.

    n8n handles URL finding, page fetching (HTTP → Playwright → Apify), field
    extraction, and writes results back via POST /admin/enrich-write.

    If n8n is unreachable and fallback_to_python=True (default), falls back to
    enrich_vendors_from_g2() so the batch is never silently abandoned.

    Returns the n8n webhook response or a fallback/error summary.
    """
    from services import n8n_client

    vendors_payload = [
        {
            "vendor_name": v.get("vendor_name", ""),
            "website": v.get("website", ""),
            "g2_url": v.get("g2_url", ""),
        }
        for v in vendor_rows
        if v.get("vendor_name") or v.get("website")
    ]

    if not vendors_payload:
        return {"attempted": 0, "triggered": False, "error": "no_vendors"}

    logger.info("Triggering n8n G2 enrichment for %d vendors", len(vendors_payload))
    try:
        response = n8n_client.post_webhook(
            n8n_client.WEBHOOK_G2_ENRICHMENT,
            {"vendors": vendors_payload, "skip_canary": skip_canary},
        )
        return {"attempted": len(vendors_payload), "triggered": True, "n8n_response": response}
    except Exception as exc:
        logger.error("G2 n8n trigger failed: %s", exc)
        if fallback_to_python:
            logger.info("Falling back to Python-side G2 enrichment for %d vendors", len(vendor_rows))
            result = enrich_vendors_from_g2(
                vendor_rows,
                upsert_fn=upsert_fn,
                skip_canary=skip_canary,
            )
            result["triggered"] = False
            result["n8n_error"] = str(exc)
            result["fallback"] = "python"
            return result
        return {"attempted": len(vendors_payload), "triggered": False, "error": str(exc)}
