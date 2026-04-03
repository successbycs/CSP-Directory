"""
LinkedIn enrichment via RapidAPI Real-Time LinkedIn Scraper API.

Usage:
    python scripts/enrich_linkedin.py [--dry-run] [--limit N] [--vendor WEBSITE]

Fetches company profile by domain for each vendor in cs_vendors and writes
linkedin_url, ceo_linkedin, leadership fields via admin enrich-write.

Requires:
    RAPIDAPI_KEY env var
    RapidAPI subscription to 'linkedin-api8.p.rapidapi.com'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import urllib.request
import urllib.error

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "linkedin-api8.p.rapidapi.com"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


def _sb_get(path: str) -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _sb_patch(website: str, fields: dict) -> None:
    url = f"{SUPABASE_URL}/rest/v1/cs_vendors?website=eq.{urllib.request.quote(website, safe='')}"
    data = json.dumps(fields).encode()
    req = urllib.request.Request(url, data=data, method="PATCH")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()


def fetch_linkedin_company(domain: str) -> dict | None:
    if not RAPIDAPI_KEY:
        raise RuntimeError("RAPIDAPI_KEY not set")
    url = f"https://{RAPIDAPI_HOST}/getCompanyByDomain?domain={domain}"
    req = urllib.request.Request(url)
    req.add_header("x-rapidapi-key", RAPIDAPI_KEY)
    req.add_header("x-rapidapi-host", RAPIDAPI_HOST)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
            return data if isinstance(data, dict) and data.get("linkedInUrl") else None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def main(dry_run: bool = False, limit: int | None = None, vendor_filter: str | None = None) -> int:
    if not RAPIDAPI_KEY:
        print("ERROR: RAPIDAPI_KEY not set — LinkedIn enrichment cannot run", flush=True)
        return 1
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_KEY not set", flush=True)
        return 1

    vendors = _sb_get("cs_vendors?select=website,name,linkedin_url&include_in_directory=eq.true&limit=200")
    if vendor_filter:
        vendors = [v for v in vendors if vendor_filter.lower() in (v.get("website") or "").lower()]
    if limit:
        vendors = vendors[:limit]

    print(f"LinkedIn enrichment: {len(vendors)} vendors", flush=True)
    hits = misses = errors = 0

    for v in vendors:
        website = v.get("website") or ""
        name = v.get("name") or ""
        if v.get("linkedin_url"):
            print(f"  SKIP {name} — already has linkedin_url", flush=True)
            continue

        domain = website.replace("https://", "").replace("http://", "").rstrip("/").split("/")[0]
        print(f"  {name} ({domain})… ", end="", flush=True)

        try:
            data = fetch_linkedin_company(domain)
            if not data:
                print("miss", flush=True)
                misses += 1
                continue

            fields: dict[str, Any] = {}
            if data.get("linkedInUrl"):
                fields["linkedin_url"] = data["linkedInUrl"]
            if data.get("staffCount"):
                fields["company_size"] = str(data["staffCount"])
            if data.get("headquarter"):
                hq = data["headquarter"]
                parts = [hq.get("city"), hq.get("country")]
                fields["hq_address"] = ", ".join(p for p in parts if p)
            if data.get("foundedOn", {}).get("year"):
                fields["founded"] = str(data["foundedOn"]["year"])

            print(f"hit → {fields.get('linkedin_url', '?')}", flush=True)
            hits += 1

            if not dry_run and fields:
                _sb_patch(website, fields)

        except Exception as e:
            print(f"ERROR: {e}", flush=True)
            errors += 1

        time.sleep(0.5)

    print(f"\nDone: {hits} hits, {misses} misses, {errors} errors", flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--vendor")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run, limit=args.limit, vendor_filter=args.vendor))
