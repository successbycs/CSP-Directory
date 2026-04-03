"""
M76 Ops Workbench — Step 1: Google Discovery (per-run).

Fires the n8n discovery webhook if N8N_DISCOVERY_WEBHOOK is configured,
otherwise calls Apify Google Search Actor directly using APIFY_API_TOKEN.

Results land in cs_vendor_candidates via the n8n workflow callback or direct upsert.

Usage (via pipeline_control):
    python -m services.ops.run_discovery
    python -m services.ops.run_discovery --pages 10
"""
from __future__ import annotations

import argparse
import json
import os
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

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN", "")
N8N_DISCOVERY_WEBHOOK = os.environ.get("N8N_DISCOVERY_WEBHOOK", "")

# Default discovery queries for CS tools
DEFAULT_QUERIES = [
    "customer success software platform",
    "customer onboarding software tool",
    "customer health score software",
    "customer expansion revenue software",
    "digital customer success platform",
    "customer adoption software",
    "SaaS customer retention software",
    "customer lifecycle management software",
    "customer engagement platform B2B",
    "voice of customer software B2B SaaS",
]

log = OpsLogger(milestone="M76")


def _load_queries() -> list[str]:
    """Load discovery queries from pipeline config or use defaults."""
    try:
        from services.config.load_config import load_pipeline_config
        config = load_pipeline_config()
        queries = config.get("discovery", {}).get("queries", [])
        if queries:
            return [str(q.get("query_text") or q) for q in queries if q]
    except Exception:
        pass
    return DEFAULT_QUERIES


def _fire_n8n_webhook(webhook_url: str, queries: list[str], pages: int) -> bool:
    payload = json.dumps({"queries": queries, "pages_per_query": pages}).encode()
    req = urllib.request.Request(webhook_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        return True
    except Exception as e:
        log.step_error("discovery", f"n8n webhook failed: {e}")
        return False


def _run_apify_discovery(queries: list[str], pages: int) -> list[dict]:
    """Run Apify Google Search and collect results. Returns raw result items."""
    if not APIFY_API_TOKEN:
        log.step_error("discovery", "APIFY_API_TOKEN not set — cannot run Apify discovery")
        return []

    actor_id = "apify~google-search-scraper"
    run_url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items?token={APIFY_API_TOKEN}&timeout=120"

    run_input = {
        "queries": "\n".join(queries[:10]),  # Apify takes newline-separated
        "maxPagesPerQuery": pages,
        "resultsPerPage": 10,
        "languageCode": "en",
        "countryCode": "us",
    }
    data = json.dumps(run_input).encode()
    req = urllib.request.Request(run_url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    log.step_progress("discovery", f"Running Apify Google Search for {len(queries)} queries…")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read()) or []
    except Exception as e:
        log.step_error("discovery", f"Apify run failed: {e}")
        return []


def _upsert_candidates(items: list[dict]) -> int:
    """Write discovered domains to cs_vendor_candidates. Returns count inserted."""
    if not SUPABASE_KEY:
        return 0

    _SKIP = re.compile(
        r"(g2\.com|trustpilot|capterra|getapp|software|review|comparison"
        r"|linkedin|twitter|facebook|instagram|youtube|reddit|medium"
        r"|crunchbase|techcrunch|forbes|bloomberg|gartner)", re.I
    )

    rows = []
    seen: set[str] = set()
    for item in items:
        url = str(item.get("url") or item.get("link") or "")
        if not url:
            continue
        domain = url.replace("https://", "").replace("http://", "").rstrip("/").split("/")[0]
        if not domain or domain in seen or _SKIP.search(domain):
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
        log.step_error("discovery", f"Candidate upsert failed: {e}")
        return 0
    return len(rows)


import re


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=2, help="Pages per query")
    parser.add_argument("--vendor", default="", help="Ignored for discovery (accepted for pipeline compat)")
    args = parser.parse_args()

    queries = _load_queries()
    log.step_start("discovery", f"Starting discovery — {len(queries)} queries, {args.pages} pages each")

    # Try n8n webhook first
    if N8N_DISCOVERY_WEBHOOK:
        ok = _fire_n8n_webhook(N8N_DISCOVERY_WEBHOOK, queries, args.pages)
        if ok:
            log.step_done("discovery", "Discovery webhook fired — n8n will process and store candidates")
            return 0

    # Fall back to direct Apify call
    items = _run_apify_discovery(queries, args.pages)
    if not items:
        log.step_done("discovery", "No results from Apify (or not configured)")
        return 0

    count = _upsert_candidates(items)
    log.step_done("discovery", f"Discovery complete — {count} new candidates written to cs_vendor_candidates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
