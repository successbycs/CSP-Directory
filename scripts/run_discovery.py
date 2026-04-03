"""
Google Discovery — discovers new vendor candidates via Apify Google Search or n8n.

If N8N_DISCOVERY_WEBHOOK is set: fires the webhook (async, n8n handles Apify + storage).
Otherwise: runs Apify Google Search directly and writes candidates to cs_vendor_candidates.

Usage:
    python scripts/run_discovery.py [--pages N] [--queries-file PATH]
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN", "")
N8N_DISCOVERY_WEBHOOK = os.environ.get("N8N_DISCOVERY_WEBHOOK", "")

DEFAULT_QUERIES = [
    "customer success software platform",
    "customer onboarding software tool",
    "customer health score software",
    "customer expansion revenue software",
    "digital customer success platform",
    "customer adoption software",
    "SaaS customer retention software",
    "customer lifecycle management software",
    "customer engagement platform B2B SaaS",
    "voice of customer software B2B",
    "customer value management software",
    "customer education platform SaaS",
    "revenue operations customer success software",
    "QBR automation software customer success",
    "customer churn prevention software",
]

_REVIEW_SITES = re.compile(
    r"(g2\.com|trustpilot|capterra|getapp|gartner|softwareadvice"
    r"|producthunt|techcrunch|forbes|linkedin|twitter|facebook"
    r"|crunchbase|wikipedia|reddit|medium|quora|youtube)", re.I
)


def _load_queries() -> list[str]:
    try:
        from services.config.load_config import load_pipeline_config
        config = load_pipeline_config()
        qs = config.get("discovery", {}).get("queries", [])
        if qs:
            return [str(q.get("query_text") or q) for q in qs if q]
    except Exception:
        pass
    return DEFAULT_QUERIES


def _fire_n8n(queries: list[str], pages: int) -> bool:
    payload = json.dumps({"queries": queries, "pages_per_query": pages}).encode()
    req = urllib.request.Request(N8N_DISCOVERY_WEBHOOK, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        return True
    except Exception as e:
        print(f"ERROR: n8n webhook failed: {e}", flush=True)
        return False


def _run_apify(queries: list[str], pages: int) -> list[dict]:
    if not APIFY_API_TOKEN:
        print("ERROR: APIFY_API_TOKEN not set", flush=True)
        return []
    actor = "apify~google-search-scraper"
    url = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={APIFY_API_TOKEN}&timeout=180"
    run_input = {
        "queries": "\n".join(queries[:15]),
        "maxPagesPerQuery": pages,
        "resultsPerPage": 10,
        "languageCode": "en",
        "countryCode": "us",
    }
    print(f"Running Apify Google Search ({len(queries)} queries, {pages} pages each)…", flush=True)
    data = json.dumps(run_input).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            return json.loads(r.read()) or []
    except Exception as e:
        print(f"ERROR: Apify run failed: {e}", flush=True)
        return []


def _upsert_candidates(items: list[dict]) -> int:
    rows = []
    seen: set[str] = set()
    for item in items:
        url = str(item.get("url") or item.get("link") or "")
        if not url:
            continue
        domain = url.replace("https://", "").replace("http://", "").rstrip("/").split("/")[0]
        if not domain or domain in seen or _REVIEW_SITES.search(domain):
            continue
        seen.add(domain)
        rows.append({
            "candidate_domain": domain,
            "source_query": str(item.get("searchQuery") or item.get("title") or "")[:500],
            "candidate_status": "new",
        })

    if not rows:
        return 0

    url = f"{SUPABASE_URL}/rest/v1/cs_vendor_candidates"
    data = json.dumps(rows).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "resolution=ignore-duplicates")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    except Exception as e:
        print(f"ERROR: candidate upsert failed: {e}", flush=True)
        return 0
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=2, help="Pages per search query (default 2)")
    parser.add_argument("--queries-file", help="Path to JSON file with query list")
    args = parser.parse_args()

    queries = _load_queries()
    if args.queries_file:
        try:
            queries = json.loads(Path(args.queries_file).read_text())
        except Exception as e:
            print(f"WARNING: Could not load queries file: {e}", flush=True)

    print(f"Discovery: {len(queries)} queries, {args.pages} pages each", flush=True)

    if N8N_DISCOVERY_WEBHOOK:
        print("Using n8n discovery webhook (async)…", flush=True)
        ok = _fire_n8n(queries, args.pages)
        if ok:
            print("Discovery webhook fired — n8n is processing", flush=True)
            return 0
        print("n8n failed — falling back to direct Apify", flush=True)

    items = _run_apify(queries, args.pages)
    if not items:
        print("No results — check APIFY_API_TOKEN or N8N_DISCOVERY_WEBHOOK", flush=True)
        return 1

    print(f"Raw results: {len(items)} items", flush=True)
    count = _upsert_candidates(items)
    print(f"Done: {count} new candidates written to cs_vendor_candidates", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
