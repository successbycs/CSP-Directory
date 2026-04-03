"""
M76 Ops Workbench — Step 4: G2 Enrichment (per-vendor).

Architectural principle: all enrichment API calls go through n8n workflows.
This module fires the csp-g2-enrichment n8n webhook for a single vendor.

Usage (via pipeline_control):
    python -m services.ops.run_g2 --vendor https://gainsight.com
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from services.ops.ops_logger import OpsLogger

log = OpsLogger(milestone="M76")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendor", required=True, help="Vendor website URL")
    args = parser.parse_args()

    webhook_url = os.environ.get("N8N_G2_ENRICHMENT_WEBHOOK", "").strip()
    rapidapi_key = os.environ.get("RAPIDAPI_KEY", "").strip()
    admin_url = os.environ.get("ADMIN_BASE_URL", "http://127.0.0.1:8787").strip()

    if not webhook_url:
        log.step_error("g2", "N8N_G2_ENRICHMENT_WEBHOOK not set — deploy csp-g2-enrichment workflow and set webhook URL")
        return 1
    if not rapidapi_key:
        log.step_error("g2", "RAPIDAPI_KEY not set")
        return 1

    vendor_website = args.vendor.strip()
    if not vendor_website.startswith("http"):
        vendor_website = "https://" + vendor_website

    log.step_start("g2", f"Firing G2 enrichment webhook for {vendor_website}")

    payload = json.dumps({
        "vendors": [{"website": vendor_website}],
        "rapidapi_key": rapidapi_key,
        "admin_url": admin_url,
    }).encode()

    req = urllib.request.Request(webhook_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
    except Exception as e:
        log.step_error("g2", f"Webhook call failed: {e}")
        return 1

    if data.get("ok"):
        log.step_done("g2", f"G2 enriched — rating={data.get('g2_rating')} reviews={data.get('g2_review_count')}")
    else:
        log.step_done("g2", f"No G2 match — {data.get('reason') or 'no_match'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
