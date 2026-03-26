#!/usr/bin/env python3
"""Deterministic vendor enrichment — no LLM.

Strategy per vendor:
  1. Plain HTTP GET for raw HTML → extract meta description, JSON-LD (head only, fast)
  2. n8n Website Content Crawl → clean markdown text for keyword classifiers
  3. Feed clean text to existing vendor_intel.py keyword rules
  4. Run directory_relevance.py to compute directory_fit/category/include
  5. Upsert to Supabase

No LLM required. All classification is rule/keyword-based.

Usage:
    python3 scripts/enrich_vendors_deterministic.py [--limit N] [--vendor-id ID]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests as _requests
from supabase import create_client

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import n8n_client
from services.extraction.structured_page_extractor import extract_structured_fields
from services.extraction.page_text_extractor import extract_visible_text
from services.extraction.vendor_intel import extract_vendor_intelligence
from services.extraction.directory_relevance import evaluate_directory_relevance_decision
from services.extraction.identity import company_name_from_website

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Junk domains that should not be in the directory.
# Both apex domains (hubspot.com) and specific subdomains (academy.hubspot.com)
# are supported — see _is_junk_domain() for matching logic.
JUNK_DOMAINS = {
    # Search / aggregators / review sites
    "google.com", "gartner.com", "capterra.com", "g2.com", "trustradius.com",
    "peerspot.com", "getapp.com", "producthunt.com", "softwareadvice.com",
    "alternativeto.net",
    # Social / community
    "reddit.com", "linkedin.com", "glassdoor.com", "indeed.com", "medium.com",
    # Analyst / media / editorial (not SaaS vendors)
    "forrester.com", "techcrunch.com", "zdnet.com", "venturebeat.com",
    "wikipedia.org", "forbes.com",
    # Large platform vendors (not CS-specific SaaS)
    "salesforce.com", "microsoft.com", "hubspot.com",
    # Learning / knowledge sites (subdomains handled by apex match)
    "academy.hubspot.com", "knowledge.hubspot.com",
}

HTTP_TIMEOUT = 12
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CSP-enrichment/1.0)"}

# Name quality enforcement (M43)
_ARTICLE_WORDS = frozenset({"what", "how", "best", "top", "guide", "the", "a", "an"})
_TITLE_SEPARATORS = ("|", "—", " - ", " > ")


def _name_fails_quality_check(name: str) -> bool:
    """Return True if name contains title separators, is too long, or starts with an article word."""
    if not name:
        return True
    if len(name) > 60:
        return True
    if any(sep in name for sep in _TITLE_SEPARATORS):
        return True
    first_word = name.strip().split()[0].lower().rstrip(",:") if name.strip() else ""
    if first_word in _ARTICLE_WORDS:
        return True
    return False


def _derive_canonical_name(meta_name: str, website: str) -> str:
    """Canonical name = og:site_name if ≤40 chars and clean, else domain-name fallback."""
    domain_name = company_name_from_website(website)
    if meta_name and len(meta_name) <= 40 and not _name_fails_quality_check(meta_name):
        return meta_name
    return domain_name


def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def fetch_html(url: str) -> str:
    """Fast plain HTTP fetch for HTML head extraction (meta/OG/JSON-LD)."""
    try:
        r = _requests.get(url, timeout=HTTP_TIMEOUT, headers=HTTP_HEADERS)
        return r.text
    except Exception as exc:
        logger.warning("HTTP fetch failed for %s: %s", url, exc)
        return ""


def fetch_markdown(url: str) -> str:
    """Fetch clean markdown via n8n Website Content Crawler."""
    try:
        result = n8n_client.post_webhook(
            "framework-website-content-crawl",
            {"start_url": url, "max_crawl_pages": 3, "include_full_content": True},
            timeout_seconds=180,
        )
        pages = result.get("pages") or []
        # Combine content from all returned pages
        parts = [str(p.get("content") or p.get("text_excerpt") or "") for p in pages]
        return "\n\n".join(p for p in parts if p.strip())
    except Exception as exc:
        logger.warning("n8n WCC failed for %s: %s", url, exc)
        return ""


def fetch_icp(url: str, page_text: str, openai_key: str) -> list[str]:
    """Extract ICP buyer titles via n8n ICP extraction workflow.

    Passes pre-fetched page_text to avoid a second Apify call and stay
    under the Cloudflare 100s timeout. Returns list of buyer title strings,
    or empty list on failure.
    """
    if not openai_key or not page_text:
        return []
    try:
        result = n8n_client.post_webhook(
            "framework-icp-extraction",
            {"url": url, "page_text": page_text, "openai_api_key": openai_key},
            timeout_seconds=90,
        )
        return result.get("icp_titles") or []
    except Exception as exc:
        logger.warning("n8n ICP extraction failed for %s: %s", url, exc)
        return []


def _is_junk_domain(website: str) -> bool:
    domain = website.lower().replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
    # Exact match (covers specific subdomains like academy.hubspot.com)
    if domain in JUNK_DOMAINS:
        return True
    # Apex domain match: academy.hubspot.com → hubspot.com
    parts = domain.split(".")
    if len(parts) > 2:
        apex = ".".join(parts[-2:])
        if apex in JUNK_DOMAINS:
            return True
    return False


def enrich_vendor(vendor: dict) -> dict | None:
    """Enrich one vendor deterministically. Returns update dict or None to skip."""
    vendor_id = vendor["id"]
    website = vendor.get("website", "")
    name = vendor.get("name", website)

    if not website:
        logger.info("SKIP %s — no website", name)
        return None

    if _is_junk_domain(website):
        logger.info("JUNK %s — deleting", name)
        return {"_action": "delete", "id": vendor_id}

    logger.info("Enriching %s (%s)", name, website)

    # Step 1: Fast HTTP fetch for structured head data
    html = fetch_html(website)
    structured = extract_structured_fields(html) if html else {}
    meta_description = structured.get("description", "")
    meta_name = structured.get("name", "")
    founded = structured.get("founded", "")

    # Derive canonical name: og:site_name if ≤40 chars and clean, else domain-name fallback
    canonical_name = _derive_canonical_name(meta_name, website)
    # Safety net: domain fallback can still fail quality check in rare edge cases
    if _name_fails_quality_check(canonical_name):
        logger.warning("Name still fails quality check after derivation for %s: '%s'", website, canonical_name)
        canonical_name = company_name_from_website(website)

    # Step 2: n8n markdown for keyword classification
    markdown_text = fetch_markdown(website)

    # Fallback: if n8n fails, use visible text from HTML
    page_text = markdown_text or extract_visible_text(html)

    if not page_text and not meta_description:
        logger.warning("No content for %s — skipping enrichment", website)
        return None

    # Step 3: Build page payload for vendor_intel extractors
    page_payload = {
        "homepage": {
            "vendor_name": meta_name or name,
            "website": website,
            "url": website,
            "source": vendor.get("source", ""),
            "page_type": "homepage",
            "text": page_text,
            "html": html,
        }
    }

    # Step 4: Deterministic keyword extraction
    intelligence = extract_vendor_intelligence(page_payload)

    # Override mission with clean meta description if available
    if meta_description and len(meta_description) > 20:
        # Monkey-patch: VendorIntelligence is frozen, so rebuild the field
        from dataclasses import replace
        intelligence = replace(intelligence, mission=meta_description)

    # Step 5: ICP extraction via LLM (uses pre-fetched page_text, skips second Apify call)
    openai_key = os.getenv("OPENAI_API_KEY", "")
    icp_titles = fetch_icp(website, page_text[:8000], openai_key)
    # Merge with keyword-detected icp hints (deduplicated)
    combined_icp = list(dict.fromkeys(icp_titles + (intelligence.icp or [])))

    # Step 6: Directory classification
    decision = evaluate_directory_relevance_decision(intelligence)

    # Build update record
    update = {
        "name": canonical_name,
        "mission": intelligence.mission or meta_description,
        "usp": intelligence.usp,
        "icp": combined_icp,
        "use_cases": intelligence.use_cases or [],
        "lifecycle_stages": intelligence.lifecycle_stages or [],
        "pricing": intelligence.pricing,
        "free_trial": intelligence.free_trial,
        "founded": founded or intelligence.founded,
        "confidence": intelligence.confidence,
        "evidence_urls": intelligence.evidence_urls or [],
        "directory_fit": decision.directory_fit,
        "directory_category": decision.directory_category,
        "include_in_directory": decision.include_in_directory,
        "llm_directory_fit": decision.directory_fit,
        "llm_directory_category": decision.directory_category,
        "llm_include_in_directory": decision.include_in_directory,
        "directory_decision_source": "deterministic_v2",
        "directory_reasoning": decision.reasoning,
    }

    # Log what we found
    logger.info(
        "  mission=%s... icp=%s lifecycle=%s fit=%s cat=%s",
        (update["mission"] or "")[:60],
        combined_icp[:3] if combined_icp else [],
        intelligence.lifecycle_stages[:3] if intelligence.lifecycle_stages else [],
        decision.directory_fit,
        decision.directory_category,
    )

    return {"_action": "update", "id": vendor_id, **update}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Max vendors to process (0=all)")
    parser.add_argument("--vendor-id", type=str, default="", help="Process only this vendor ID")
    parser.add_argument("--unenriched-only", action="store_true", help="Only process vendors with no lifecycle_stages")
    parser.add_argument("--dry-run", action="store_true", help="Print updates without writing to Supabase")
    args = parser.parse_args()

    client = get_supabase()

    # Fetch vendors
    if args.vendor_id:
        result = client.table("cs_vendors").select("*").eq("id", args.vendor_id).execute()
    elif args.unenriched_only:
        result = client.table("cs_vendors").select("id, name, website, source").is_("lifecycle_stages", "null").execute()
        # Also fetch empty-array rows (supabase client can't filter empty arrays directly)
        all_result = client.table("cs_vendors").select("id, name, website, source, lifecycle_stages").execute()
        result_data = [r for r in all_result.data if not r.get("lifecycle_stages")]
        result = type("R", (), {"data": result_data})()
    else:
        result = client.table("cs_vendors").select("id, name, website, source").execute()

    vendors = result.data
    if args.limit > 0:
        vendors = vendors[:args.limit]

    logger.info("Processing %d vendors", len(vendors))

    updated = 0
    deleted = 0
    skipped = 0

    for i, vendor in enumerate(vendors, 1):
        logger.info("[%d/%d] %s", i, len(vendors), vendor.get("name", vendor.get("website")))
        try:
            result_update = enrich_vendor(vendor)
        except Exception as exc:
            logger.error("Error enriching %s: %s", vendor.get("website"), exc)
            skipped += 1
            continue

        if result_update is None:
            skipped += 1
            continue

        action = result_update.pop("_action")
        vendor_id = result_update.pop("id")

        if args.dry_run:
            print(f"  DRY RUN {action} {vendor_id}: mission={result_update.get('mission','')[:80]}")
            continue

        if action == "delete":
            client.table("cs_vendors").delete().eq("id", vendor_id).execute()
            deleted += 1
            logger.info("Deleted junk vendor %s", vendor_id)
        elif action == "update":
            # Remove None values to avoid overwriting good data with nulls
            clean_update = {k: v for k, v in result_update.items() if v is not None}
            client.table("cs_vendors").update(clean_update).eq("id", vendor_id).execute()
            updated += 1

        time.sleep(0.5)  # Be polite to n8n

    logger.info("Done: %d updated, %d deleted, %d skipped", updated, deleted, skipped)


if __name__ == "__main__":
    main()
