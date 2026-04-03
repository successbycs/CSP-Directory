"""
Batch site crawl — re-crawls vendor homepages for all include_in_directory vendors.

Uses three-tier strategy:
  Tier 1 (free): Direct HTTP fetch — always attempted first
  Tier 2 (Apify RAG ~$0.001/page): Fired via N8N_CRAWL_TIER2_WEBHOOK if configured
  Tier 3 (Apify WCC + proxy ~$0.004/page): Fired via N8N_CRAWL_TIER3_WEBHOOK if configured

For Tier 2/3: fires the n8n webhook and moves on (async — n8n stores pages back).
For Tier 1: fetches synchronously and stores directly to vendor_pages.

Usage:
    python scripts/enrich_site_crawl.py [--limit N] [--vendor WEBSITE] [--tier 1|2|3]
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
from html.parser import HTMLParser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
N8N_CRAWL_TIER2_WEBHOOK = os.environ.get("N8N_CRAWL_TIER2_WEBHOOK", "")
N8N_CRAWL_TIER3_WEBHOOK = os.environ.get("N8N_CRAWL_TIER3_WEBHOOK", "")

_HIGH_VALUE_PATHS = [
    "/about", "/about-us", "/pricing", "/features", "/product",
    "/solutions", "/customers", "/integrations", "/platform",
]

_SKIP_EXT = re.compile(r"\.(png|jpg|jpeg|gif|svg|ico|pdf|zip|css|js|woff)$", re.I)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip = False
        self.chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "head"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "head"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip and (text := data.strip()):
            self.chunks.append(text)


def _extract_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return " ".join(parser.chunks)


def _fetch_page(url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; CSP-Crawler/1.0)",
        "Accept": "text/html,*/*",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", errors="replace")
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
    return title, _extract_text(html)


def _crawl_tier1(vendor_website: str) -> list[dict]:
    base = vendor_website.rstrip("/")
    pages = []
    seen: set[str] = set()
    for path in [""] + _HIGH_VALUE_PATHS:
        url = base + path
        if url in seen:
            continue
        seen.add(url)
        try:
            title, text = _fetch_page(url)
            words = text.split()
            if len(words) < 50:
                continue
            pages.append({
                "vendor_website": vendor_website,
                "page_url": url,
                "title": title[:500],
                "clean_text": text,
                "word_count": len(words),
                "tier_used": "tier1_direct",
            })
        except Exception:
            pass
    return pages


def _store_pages(pages: list[dict]) -> None:
    if not SUPABASE_KEY or not pages:
        return
    url = f"{SUPABASE_URL}/rest/v1/vendor_pages"
    data = json.dumps(pages).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "resolution=merge-duplicates")
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def _store_tier_result(vendor_website: str, tier: int, pages_count: int) -> None:
    if not SUPABASE_KEY:
        return
    col = f"crawl_tier{tier}_result"
    url = f"{SUPABASE_URL}/rest/v1/cs_vendors?website=eq.{urllib.parse.quote(vendor_website, safe='')}"
    data = json.dumps({col: {"tier": tier, "pages_fetched": pages_count}}).encode()
    req = urllib.request.Request(url, data=data, method="PATCH")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()


def _fire_webhook(webhook_url: str, vendor_website: str, tier: int) -> bool:
    payload = json.dumps({"vendor_website": vendor_website, "tier": tier}).encode()
    req = urllib.request.Request(webhook_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
        return True
    except Exception:
        return False


def _load_vendors(vendor_filter: str | None) -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/cs_vendors?select=website,name&include_in_directory=eq.true&limit=500"
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    with urllib.request.urlopen(req, timeout=15) as r:
        vendors = json.loads(r.read()) or []
    if vendor_filter:
        vendors = [v for v in vendors if vendor_filter.lower() in (v.get("website") or "").lower()]
    return vendors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--vendor")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], default=1)
    args = parser.parse_args()

    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_KEY not set", flush=True)
        return 1

    vendors = _load_vendors(args.vendor)
    if args.limit:
        vendors = vendors[: args.limit]

    print(f"Site crawl (Tier {args.tier}): {len(vendors)} vendors", flush=True)
    success = failed = skipped = 0

    for i, v in enumerate(vendors, 1):
        website = v.get("website") or ""
        name = v.get("name") or website
        if not website:
            skipped += 1
            continue
        if not website.startswith("http"):
            website = "https://" + website

        print(f"[{i}/{len(vendors)}] {name}", flush=True)

        if args.tier == 1:
            try:
                pages = _crawl_tier1(website)
                if pages:
                    _store_pages(pages)
                    _store_tier_result(website, 1, len(pages))
                    print(f"  ✓ {len(pages)} pages stored", flush=True)
                    success += 1
                else:
                    print(f"  ✗ no pages fetched", flush=True)
                    failed += 1
            except Exception as e:
                print(f"  ERROR: {e}", flush=True)
                failed += 1
        else:
            webhook = N8N_CRAWL_TIER2_WEBHOOK if args.tier == 2 else N8N_CRAWL_TIER3_WEBHOOK
            if not webhook:
                print(f"  SKIP — N8N_CRAWL_TIER{args.tier}_WEBHOOK not configured", flush=True)
                skipped += 1
                continue
            ok = _fire_webhook(webhook, website, args.tier)
            if ok:
                print(f"  → Tier {args.tier} webhook fired (async)", flush=True)
                success += 1
            else:
                print(f"  ✗ webhook failed", flush=True)
                failed += 1

        time.sleep(0.3)

    print(f"\nDone: {success} ok, {failed} failed, {skipped} skipped", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
