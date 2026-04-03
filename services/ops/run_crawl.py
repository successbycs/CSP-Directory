"""
M76 Ops Workbench — Step 2: Three-Tier Website Crawl (per-vendor).

Tier 1 — Direct HTTP (free): fetches pages directly with urllib, stores in vendor_pages.
Tier 2 — Apify RAG: fires N8N_CRAWL_TIER2_WEBHOOK if configured, else falls back to Tier 1.
Tier 3 — Apify WCC + Proxy: fires N8N_CRAWL_TIER3_WEBHOOK if configured, else falls back to Tier 1.

The n8n workflow is responsible for calling Apify and POSTing results back to
/admin/ops/store-pages. This script just triggers the webhook and exits.

Usage (via pipeline_control):
    python -m services.ops.run_crawl --tier 1 --vendor https://gainsight.com
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from services.ops.ops_logger import OpsLogger

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

_TIER_WEBHOOKS = {
    2: os.environ.get("N8N_CRAWL_TIER2_WEBHOOK", ""),
    3: os.environ.get("N8N_CRAWL_TIER3_WEBHOOK", ""),
}

log = OpsLogger(milestone="M76")

# ── Tier 1: direct HTTP crawl ──────────────────────────────────────────────────

_HIGH_VALUE_PATHS = [
    "/about", "/about-us", "/pricing", "/features", "/product",
    "/solutions", "/customers", "/integrations", "/platform",
    "/how-it-works", "/why-us", "/resources",
]

_SKIP_EXT = re.compile(r"\.(png|jpg|jpeg|gif|svg|ico|pdf|zip|css|js|woff|woff2)$", re.I)


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
        if not self._skip:
            text = data.strip()
            if text:
                self.chunks.append(text)


def _extract_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return " ".join(parser.chunks)


def _fetch_page(url: str, timeout: int = 15) -> tuple[str, str]:
    """Return (title, clean_text). Raises on non-2xx."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; CSP-Crawler/1.0)",
        "Accept": "text/html,application/xhtml+xml,*/*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        html = r.read().decode("utf-8", errors="replace")
    # Extract title
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
    return title, _extract_text(html)


def _crawl_tier1(vendor_website: str, max_pages: int) -> list[dict]:
    """Fetch homepage + high-value subpages. Return list of page dicts."""
    base = vendor_website.rstrip("/")
    pages: list[dict] = []
    seen: set[str] = set()

    urls_to_try = [base] + [base + p for p in _HIGH_VALUE_PATHS]

    for url in urls_to_try[:max_pages]:
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
            log.step_progress("crawl_tier1", f"Fetched {url} ({len(words)} words)")
        except Exception as e:
            log.step_progress("crawl_tier1", f"Skip {url}: {e}")

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


def _store_crawl_result(vendor_website: str, column: str, payload: dict) -> None:
    if not SUPABASE_KEY:
        return
    url = f"{SUPABASE_URL}/rest/v1/cs_vendors?website=eq.{urllib.parse.quote(vendor_website, safe='')}"
    data = json.dumps({column: payload}).encode()
    req = urllib.request.Request(url, data=data, method="PATCH")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()


def _fire_n8n_webhook(webhook_url: str, vendor_website: str, tier: int) -> bool:
    """POST vendor_website to the n8n webhook. Returns True if accepted."""
    payload = json.dumps({"vendor_website": vendor_website, "tier": tier}).encode()
    req = urllib.request.Request(webhook_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        return True
    except Exception as e:
        log.step_error(f"crawl_tier{tier}", f"n8n webhook failed: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--vendor", required=True, help="Vendor website URL")
    parser.add_argument("--max-pages", type=int, default=20)
    args = parser.parse_args()

    vendor_website = args.vendor.strip()
    if not vendor_website.startswith("http"):
        vendor_website = "https://" + vendor_website
    tier = args.tier

    log.step_start(f"crawl_tier{tier}", f"Crawl Tier {tier} for {vendor_website}")

    # Tier 2 / 3 — use n8n webhook if configured
    if tier in (2, 3):
        webhook = _TIER_WEBHOOKS.get(tier, "")
        if webhook:
            ok = _fire_n8n_webhook(webhook, vendor_website, tier)
            if ok:
                log.step_done(f"crawl_tier{tier}", f"Tier {tier} webhook fired — n8n/Apify will store pages asynchronously")
                return 0
        log.step_progress(f"crawl_tier{tier}", f"No Tier {tier} webhook configured — falling back to Tier 1 direct HTTP")

    # Tier 1 (or fallback)
    pages = _crawl_tier1(vendor_website, args.max_pages)
    if not pages:
        log.step_error("crawl_tier1", f"No pages fetched for {vendor_website}")
        return 1

    if SUPABASE_KEY:
        _store_pages(pages)
        column = f"crawl_tier{tier}_result"
        _store_crawl_result(vendor_website, column, {
            "tier": tier,
            "actual_tier": 1,
            "pages_fetched": len(pages),
            "page_urls": [p["page_url"] for p in pages],
        })

    log.step_done(f"crawl_tier{tier}", f"Stored {len(pages)} pages for {vendor_website}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
