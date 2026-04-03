"""
M76 Ops Workbench — Step 4: G2 Enrichment (per-vendor).

Fetches G2 product data for a single vendor via RapidAPI G2 Data API and writes
the raw result to crawl_g2_result in cs_vendors. Run Step 6 (merge) after this
to promote values to main schema columns.

Usage (via pipeline_control):
    python -m services.ops.run_g2 --vendor https://gainsight.com
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from services.ops.ops_logger import OpsLogger

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "g2-data-api.p.rapidapi.com"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

log = OpsLogger(milestone="M76")


def _domain(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").rstrip("/").split("/")[0]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _slug_variants(vendor_name: str, domain: str) -> list[str]:
    clean = re.sub(
        r"\s+(Software|Inc\.?|LLC|Ltd\.?|Corp\.?|Group|Technologies|Tech|Solutions|Platform|Systems)$",
        "", vendor_name, flags=re.I,
    ).strip()
    base = _slug(vendor_name)
    clean_base = _slug(clean)
    domain_slug = re.sub(r"[^a-z0-9]+", "-", domain.split(".")[0].lower()).strip("-")

    seen: set[str] = set()
    variants: list[str] = []
    for s in [clean_base, domain_slug, base]:
        if s and s not in seen:
            variants.append(s)
            seen.add(s)
    for suffix in ["customer-success", "cs", "platform", "crm", "software"]:
        candidate = f"{clean_base}-{suffix}"
        if candidate not in seen:
            variants.append(candidate)
            seen.add(candidate)
    return variants


def fetch_g2(slug: str) -> dict | None:
    url = f"https://{RAPIDAPI_HOST}/g2-products?product={urllib.parse.quote(slug)}&max_reviews=1"
    req = urllib.request.Request(url)
    req.add_header("x-rapidapi-key", RAPIDAPI_KEY)
    req.add_header("x-rapidapi-host", RAPIDAPI_HOST)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
            return data if isinstance(data, dict) and data.get("product_name") else None
    except Exception:
        return None


def _sb_get_vendor(website: str) -> dict | None:
    url = f"{SUPABASE_URL}/rest/v1/cs_vendors?website=eq.{urllib.parse.quote(website, safe='')}&select=name,website&limit=1"
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    with urllib.request.urlopen(req, timeout=15) as r:
        rows = json.loads(r.read())
        return rows[0] if rows else None


def _sb_patch(website: str, fields: dict) -> None:
    url = f"{SUPABASE_URL}/rest/v1/cs_vendors?website=eq.{urllib.parse.quote(website, safe='')}"
    data = json.dumps(fields).encode()
    req = urllib.request.Request(url, data=data, method="PATCH")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendor", required=True, help="Vendor website URL")
    args = parser.parse_args()

    vendor_website = args.vendor.strip()
    if not vendor_website.startswith("http"):
        vendor_website = "https://" + vendor_website
    domain = _domain(vendor_website)

    if not RAPIDAPI_KEY:
        log.step_error("g2", "RAPIDAPI_KEY not set")
        return 1

    log.step_start("g2", f"Fetching G2 data for {domain}")

    vendor_row = _sb_get_vendor(vendor_website) if SUPABASE_KEY else None
    vendor_name = (vendor_row or {}).get("name", domain)

    variants = _slug_variants(vendor_name, domain)
    data = None
    hit_slug = None
    for slug in variants:
        data = fetch_g2(slug)
        if data:
            hit_slug = slug
            break
        time.sleep(0.3)

    if not data:
        log.step_done("g2", f"No G2 record found for {domain} (tried {len(variants)} slugs)")
        return 0

    cats = data.get("categories") or []
    g2_categories = [c["name"] for c in cats if isinstance(c, dict) and c.get("name")]

    result = {
        "source": "g2_rapidapi",
        "slug": hit_slug,
        "g2_url": data.get("g2_link") or data.get("g2_reviews_link") or "",
        "g2_rating": data.get("rating"),
        "g2_review_count": data.get("reviews"),
        "g2_categories": g2_categories,
        "product_name": data.get("product_name"),
    }

    if SUPABASE_KEY:
        _sb_patch(vendor_website, {"crawl_g2_result": result})
    log.step_done("g2", f"Stored G2 result for {domain} — rating={result['g2_rating']} reviews={result['g2_review_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
