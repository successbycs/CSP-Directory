"""
M76 Ops Workbench — Step 3: Datagma Firmographic Enrichment (per-vendor).

Fetches firmographic data for a single vendor via Datagma (RapidAPI) and writes
the raw result to crawl_datagma_result in cs_vendors. Run Step 6 (merge) after
this to promote values to main schema columns.

Usage (via pipeline_control):
    python -m services.ops.run_datagma --vendor https://gainsight.com
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from services.ops.ops_logger import OpsLogger

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "enrichment-b2b-linkedin-crunchbase-datagma.p.rapidapi.com"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

log = OpsLogger(milestone="M76")


def _domain(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").rstrip("/").split("/")[0]


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


def fetch_datagma(domain: str) -> dict | None:
    url = f"https://{RAPIDAPI_HOST}/api/search?domain={domain}"
    req = urllib.request.Request(url)
    req.add_header("x-rapidapi-key", RAPIDAPI_KEY)
    req.add_header("x-rapidapi-host", RAPIDAPI_HOST)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
            return data if isinstance(data, dict) and data.get("domain") else None
    except urllib.error.HTTPError as e:
        if e.code in (404, 402):
            return None
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendor", required=True, help="Vendor website URL")
    args = parser.parse_args()

    vendor_website = args.vendor.strip()
    if not vendor_website.startswith("http"):
        vendor_website = "https://" + vendor_website
    domain = _domain(vendor_website)

    if not RAPIDAPI_KEY:
        log.step_error("datagma", "RAPIDAPI_KEY not set")
        return 1
    if not SUPABASE_KEY:
        log.step_error("datagma", "SUPABASE_KEY not set")
        return 1

    log.step_start("datagma", f"Fetching Datagma firmographic for {domain}")

    try:
        data = fetch_datagma(domain)
    except Exception as e:
        log.step_error("datagma", f"API error: {e}")
        return 1

    if not data:
        log.step_done("datagma", f"No Datagma record found for {domain}")
        return 0

    result: dict = {
        "source": "datagma",
        "domain": domain,
        "raw": data,
    }
    if data.get("foundedYear"):
        result["founded"] = str(data["foundedYear"])
    if data.get("city") or data.get("country"):
        result["hq_address"] = ", ".join(p for p in [data.get("city"), data.get("country")] if p)
    if data.get("employeesRange"):
        result["company_size"] = data["employeesRange"]
    if data.get("fundingStage"):
        result["funding_stage"] = data["fundingStage"]
    if data.get("totalFunding"):
        result["total_funding"] = str(data["totalFunding"])
    if data.get("ceoFullName"):
        result["ceo_name"] = data["ceoFullName"]
    if data.get("revenue"):
        result["revenue"] = str(data["revenue"])

    _sb_patch(vendor_website, {"crawl_datagma_result": result})
    log.step_done("datagma", f"Stored Datagma result for {domain} — {len(result)-3} fields")
    return 0


if __name__ == "__main__":
    sys.exit(main())
