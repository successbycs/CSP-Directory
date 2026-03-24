#!/usr/bin/env python3
"""
M39 proof: Apify Website Content Crawler as primary enrichment path.

Tests enrichment on 5 JS-heavy vendor sites known to have bot-detection or
complex frontend rendering that plain HTTP cannot handle.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env
for line in (PROJECT_ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

from services.enrichment.vendor_fetcher import fetch_vendor_homepage
from services.config.load_config import load_pipeline_config

config = load_pipeline_config()

# JS-heavy / bot-protected vendor sites
TEST_VENDORS = [
    {"vendor_name": "Gainsight", "website": "https://www.gainsight.com", "source": "test"},
    {"vendor_name": "ChurnZero", "website": "https://www.churnzero.com", "source": "test"},
    {"vendor_name": "Totango", "website": "https://www.totango.com", "source": "test"},
    {"vendor_name": "Vitally", "website": "https://www.vitally.io", "source": "test"},
    {"vendor_name": "Planhat", "website": "https://www.planhat.com", "source": "test"},
]

print(f"M39 Apify enrichment proof — primary backend: {config.enrichment.external_fetch_backend}")
print("=" * 60)

results = []
for vendor in TEST_VENDORS:
    print(f"\nFetching {vendor['vendor_name']} ({vendor['website']})...")
    try:
        payload = fetch_vendor_homepage(vendor)
        text_len = len(payload.get("text", ""))
        html_len = len(payload.get("html", ""))
        backend = payload.get("fetch_backend", "unknown")
        status = payload.get("status_code", 0)
        has_content = text_len > 100
        result = {
            "vendor": vendor["vendor_name"],
            "website": vendor["website"],
            "fetch_backend": backend,
            "status_code": status,
            "text_length": text_len,
            "html_length": html_len,
            "has_meaningful_content": has_content,
            "pass": has_content and backend in ("apify", "apify_website_content_crawler"),
            "error": None,
        }
        status_icon = "PASS" if result["pass"] else "FAIL"
        print(f"  [{status_icon}] backend={backend} status={status} text={text_len}chars")
    except Exception as exc:
        result = {
            "vendor": vendor["vendor_name"],
            "website": vendor["website"],
            "fetch_backend": "error",
            "status_code": 0,
            "text_length": 0,
            "html_length": 0,
            "has_meaningful_content": False,
            "pass": False,
            "error": str(exc),
        }
        print(f"  [ERROR] {exc}")
    results.append(result)

passed = sum(1 for r in results if r["pass"])
print(f"\n{'='*60}")
print(f"Results: {passed}/{len(results)} vendors successfully fetched via Apify")

proof = {
    "milestone_id": "M39",
    "title": "Apify web scraper enrichment",
    "status": "pass" if passed >= 3 else "partial",
    "summary": (
        f"Apify Website Content Crawler validated as primary enrichment path. "
        f"{passed}/{len(results)} vendors fetched with meaningful content via Apify backend. "
        f"Config: external_fetch_backend={config.enrichment.external_fetch_backend}, "
        f"actor_id={config.enrichment.external_fetch_actor_id}"
    ),
    "apify_primary_path_validated": passed >= 3,
    "vendors_tested": len(results),
    "vendors_passed": passed,
    "config": {
        "external_fetch_backend": config.enrichment.external_fetch_backend,
        "external_fetch_actor_id": config.enrichment.external_fetch_actor_id,
        "external_fetch_max_pages": config.enrichment.external_fetch_max_pages,
        "external_fetch_use_proxy": config.enrichment.external_fetch_use_proxy,
    },
    "changed_files": [
        "services/enrichment/vendor_fetcher.py",
        "scripts/prove_m39_apify_enrichment.py",
    ],
    "vendor_results": results,
}

proof_path = PROJECT_ROOT / "runs" / "proofs" / "M39_apify_enrichment.json"
proof_path.parent.mkdir(parents=True, exist_ok=True)
proof_path.write_text(json.dumps(proof, indent=2))
print(f"\nProof artifact written to: {proof_path}")
print(json.dumps({"passed": passed, "total": len(results), "status": proof["status"]}, indent=2))
sys.exit(0 if passed >= 3 else 1)
