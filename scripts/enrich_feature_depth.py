"""
Feature depth enrichment via n8n csp-feature-depth-enrichment workflow.

Usage:
    python scripts/enrich_feature_depth.py [--vendor WEBSITE] [--limit N] [--all]

Posts vendor batch to the n8n feature depth enrichment webhook. The workflow
crawls vendor help/docs sites, runs LLM feature taxonomy extraction across
6 dimensions, and writes feature_depth_score and feature_signals back to
cs_vendors via the admin API.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
N8N_BASE_URL = os.environ.get("N8N_BASE_URL", "https://successbycs.app.n8n.cloud")
WEBHOOK_PATH = "csp-feature-depth-enrichment"


def _sb_get(path: str) -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def main(vendor_website: str = "", limit: int = 0, skip_existing: bool = True) -> int:
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_KEY not set", flush=True)
        return 1

    vendors = _sb_get(
        "cs_vendors?select=website,name,help_center_url,developer_docs_url,feature_depth_score,directory_category"
        "&include_in_directory=eq.true&limit=200"
    )

    if vendor_website:
        vendors = [v for v in vendors if vendor_website.lower() in (v.get("website") or "").lower()]
    if skip_existing:
        vendors = [v for v in vendors if v.get("feature_depth_score") is None]
    if limit:
        vendors = vendors[:limit]

    if not vendors:
        print("No vendors to enrich (all may already have feature_depth_score).", flush=True)
        return 0

    print(f"Feature depth enrichment: posting {len(vendors)} vendors to n8n", flush=True)

    payload = json.dumps({
        "vendors": [
            {
                "vendor_name": v.get("name") or "",
                "website": v.get("website") or "",
                "help_center_url": v.get("help_center_url") or "",
                "developer_docs_url": v.get("developer_docs_url") or "",
                "directory_category": v.get("directory_category") or "",
            }
            for v in vendors
        ],
        "admin_url": "http://127.0.0.1:8787",
    }).encode()

    webhook_url = f"{N8N_BASE_URL}/webhook/{WEBHOOK_PATH}"
    req = urllib.request.Request(webhook_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            result = json.loads(raw) if raw.strip() else {"ok": True, "async": True}
        print(f"Done: {result}", flush=True)
        return 0
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"ERROR {e.code}: {body}", flush=True)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendor", default="", help="Filter to one vendor website")
    parser.add_argument("--limit", type=int, default=0, help="Max vendors to process")
    parser.add_argument("--all", dest="run_all", action="store_true", help="Include already-enriched vendors")
    args = parser.parse_args()
    raise SystemExit(main(vendor_website=args.vendor, limit=args.limit, skip_existing=not args.run_all))
