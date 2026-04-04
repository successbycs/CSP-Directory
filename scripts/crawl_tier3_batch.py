"""
Batch Tier 3 crawl — runs csp-crawl-tier3-wcc for all include_in_directory vendors.

Usage:
    python scripts/crawl_tier3_batch.py [--limit N] [--max-pages N] [--vendor WEBSITE] [--force]

By default skips vendors that already have 20+ pages in vendor_pages.
Use --force to re-crawl all vendors regardless.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN", "")
N8N_BASE_URL = os.environ.get("N8N_BASE_URL", "https://successbycs.app.n8n.cloud")
WEBHOOK_PATH = "csp-crawl-tier3-wcc"

MIN_PAGES_THRESHOLD = 20  # skip vendors already at this many pages
BATCH_SIZE = 8            # max concurrent Apify runs (8 × 2048MB = 16384MB, well under 32768MB cap)
BATCH_SLEEP = 120         # seconds to wait between batches for earlier runs to free memory


def _sb_get(path: str) -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get_page_counts() -> dict[str, int]:
    """Return {domain: page_count} for all vendors in vendor_pages."""
    rows = _sb_get("vendor_pages?select=vendor_website&limit=5000")
    counts: dict[str, int] = {}
    for r in rows:
        domain = r.get("vendor_website", "")
        counts[domain] = counts.get(domain, 0) + 1
    return counts


def trigger_crawl(vendor: dict, max_pages: int) -> bool:
    website = vendor.get("website", "")
    name = vendor.get("name", "")
    payload = json.dumps({
        "website": website,
        "vendor_name": name,
        "apify_token": APIFY_API_TOKEN,
        "max_pages": max_pages,
        "supabase_url": SUPABASE_URL,
        "supabase_key": SUPABASE_KEY,
    }).encode()

    url = f"{N8N_BASE_URL}/webhook/{WEBHOOK_PATH}"
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            result = json.loads(raw) if raw.strip() else {"ok": True}
        # Webhook responds immediately (onReceived mode); Apify runs in background
        print(f"    triggered (async)", flush=True)
        return True
    except urllib.error.HTTPError as e:
        print(f"    ERROR {e.code}: {e.read().decode(errors='replace')[:200]}", flush=True)
        return False
    except Exception as exc:
        print(f"    ERROR: {exc}", flush=True)
        return False


def main(limit: int = 0, max_pages: int = 10, vendor_filter: str = "", force: bool = False) -> int:
    if not APIFY_API_TOKEN:
        print("ERROR: APIFY_API_TOKEN not set", flush=True)
        return 1
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_KEY not set", flush=True)
        return 1

    vendors = _sb_get(
        "cs_vendors?select=website,name&include_in_directory=eq.true&limit=200"
    )

    if vendor_filter:
        vendors = [v for v in vendors if vendor_filter.lower() in (v.get("website") or "").lower()]

    if not force:
        page_counts = get_page_counts()
        skipped = []
        to_crawl = []
        for v in vendors:
            domain = (v.get("website") or "").replace("https://", "").replace("http://", "").rstrip("/")
            count = page_counts.get(domain, 0)
            if count >= MIN_PAGES_THRESHOLD:
                skipped.append((v, count))
            else:
                to_crawl.append((v, count))
        print(f"Skipping {len(skipped)} vendors already at {MIN_PAGES_THRESHOLD}+ pages", flush=True)
        vendors_with_counts = to_crawl
    else:
        page_counts = get_page_counts()
        vendors_with_counts = [(v, page_counts.get(
            (v.get("website") or "").replace("https://", "").replace("http://", "").rstrip("/"), 0
        )) for v in vendors]

    if limit:
        vendors_with_counts = vendors_with_counts[:limit]

    total = len(vendors_with_counts)
    if total == 0:
        print("Nothing to crawl — all vendors already have sufficient pages. Use --force to re-crawl.", flush=True)
        return 0

    batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"\nTier 3 batch crawl: {total} vendors at max {max_pages} pages each", flush=True)
    print(f"Batches: {batches} × {BATCH_SIZE} vendors, {BATCH_SLEEP}s pause between batches", flush=True)
    print(f"Estimated cost: ~${total * max_pages * 0.004:.2f}\n", flush=True)

    success = failed = 0
    for i, (vendor, existing) in enumerate(vendors_with_counts, 1):
        name = vendor.get("name") or vendor.get("website", "")
        print(f"[{i}/{total}] {name} ({existing} existing pages)… ", end="", flush=True)

        ok = trigger_crawl(vendor, max_pages)
        if ok:
            success += 1
        else:
            failed += 1

        # After each full batch (except the last), pause to let Apify free memory
        if i < total and i % BATCH_SIZE == 0:
            print(f"\n--- Batch {i // BATCH_SIZE}/{batches} complete — waiting {BATCH_SLEEP}s for Apify to free memory ---\n", flush=True)
            time.sleep(BATCH_SLEEP)
        elif i < total:
            time.sleep(2)

    print(f"\nDone: {success} crawled, {failed} failed out of {total}", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch Tier 3 crawl for all directory vendors")
    parser.add_argument("--limit", type=int, default=0, help="Max vendors to process")
    parser.add_argument("--max-pages", type=int, default=10, help="Max pages per vendor (default 10)")
    parser.add_argument("--vendor", default="", help="Filter to one vendor website")
    parser.add_argument("--force", action="store_true", help="Re-crawl vendors that already have pages")
    args = parser.parse_args()
    raise SystemExit(main(
        limit=args.limit,
        max_pages=args.max_pages,
        vendor_filter=args.vendor,
        force=args.force,
    ))
