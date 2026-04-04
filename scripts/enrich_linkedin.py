"""
LinkedIn enrichment via n8n csp-linkedin-enrichment workflow.

Usage:
    python scripts/enrich_linkedin.py [--vendor WEBSITE] [--limit N] [--all]

Posts vendor batch to the n8n LinkedIn enrichment webhook. The workflow uses
the maintained RapidAPI provider and writes linkedin_url, ceo_linkedin, and
leadership data back to cs_vendors.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
N8N_BASE_URL = os.environ.get("N8N_BASE_URL", "https://successbycs.app.n8n.cloud").rstrip("/")
N8N_LINKEDIN_WEBHOOK = os.environ.get("N8N_LINKEDIN_WEBHOOK", "").strip()
WEBHOOK_PATH = "csp-linkedin-enrichment"


def _sb_get(path: str) -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read())


def _webhook_url() -> str:
    if N8N_LINKEDIN_WEBHOOK:
        return N8N_LINKEDIN_WEBHOOK
    return f"{N8N_BASE_URL}/webhook/{WEBHOOK_PATH}"


def main(vendor_website: str = "", limit: int = 0, skip_existing: bool = True) -> int:
    if not RAPIDAPI_KEY:
        print("ERROR: RAPIDAPI_KEY not set — LinkedIn enrichment cannot run", flush=True)
        return 1
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_KEY not set", flush=True)
        return 1

    vendors = _sb_get(
        "cs_vendors?select=website,name,linkedin_url"
        "&include_in_directory=eq.true&limit=200"
    )

    if vendor_website:
        vendors = [v for v in vendors if vendor_website.lower() in (v.get("website") or "").lower()]
    if skip_existing:
        vendors = [v for v in vendors if not v.get("linkedin_url")]
    if limit:
        vendors = vendors[:limit]

    if not vendors:
        print("No vendors to enrich (all may already have LinkedIn data).", flush=True)
        return 0

    print(f"LinkedIn enrichment: posting {len(vendors)} vendors to n8n", flush=True)

    payload = json.dumps(
        {
            "vendors": [
                {
                    "vendor_name": v.get("name") or "",
                    "website": v.get("website") or "",
                    "linkedin_url": v.get("linkedin_url") or "",
                }
                for v in vendors
            ],
            "rapidapi_key": RAPIDAPI_KEY,
            "supabase_url": SUPABASE_URL,
            "supabase_key": SUPABASE_KEY,
        }
    ).encode()

    req = urllib.request.Request(_webhook_url(), data=payload, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
        result = json.loads(raw) if raw.strip() else {"ok": True, "async": True}
        print(f"Done: {result}", flush=True)
        return 0 if result.get("ok", True) else 1
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")
        print(f"ERROR {error.code}: {body}", flush=True)
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
