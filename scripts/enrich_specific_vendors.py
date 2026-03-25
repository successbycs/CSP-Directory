#!/usr/bin/env python3
"""Run full enrichment on specific vendors and upsert to Supabase."""
from __future__ import annotations
import os, sys, json, logging
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

for line in (PROJECT_ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ[k.strip()] = v.strip()

from services.enrichment import vendor_fetcher, site_explorer
from services.extraction import vendor_intel, llm_extractor, merge_results, vendor_profile_builder
from services.export import google_sheets
from services.persistence import supabase_client

VENDORS = [
    {"vendor_name": "Gainsight", "website": "https://www.gainsight.com", "source": "manual", "candidate_domain": "gainsight.com"},
    {"vendor_name": "ChurnZero", "website": "https://www.churnzero.com", "source": "manual", "candidate_domain": "churnzero.com"},
    {"vendor_name": "Totango", "website": "https://www.totango.com", "source": "manual", "candidate_domain": "totango.com"},
    {"vendor_name": "Vitally", "website": "https://www.vitally.io", "source": "manual", "candidate_domain": "vitally.io"},
    {"vendor_name": "Planhat", "website": "https://www.planhat.com", "source": "manual", "candidate_domain": "planhat.com"},
]

upsert_fn = supabase_client.upsert_vendor_result if supabase_client.is_configured() else None
print(f"Supabase configured: {supabase_client.is_configured()}")

results = []
for vendor in VENDORS:
    name = vendor["vendor_name"]
    print(f"\nEnriching {name}...")
    try:
        homepage = vendor_fetcher.fetch_vendor_homepage(vendor)
        backend = homepage.get("fetch_backend", "?")
        text_len = len(homepage.get("text", ""))
        print(f"  Fetched: backend={backend} text={text_len}chars")
        
        explored = site_explorer.explore_vendor_site(homepage)
        det_intel = vendor_intel.extract_vendor_intelligence(explored)
        llm_result = llm_extractor.extract_vendor_intelligence(explored)
        intel = merge_results.merge_vendor_intelligence(det_intel, llm_result)
        profile = vendor_profile_builder.build_vendor_profile(vendor, explored, intel)
        
        # Check field completeness
        enrichment_fields = ['mission', 'usp', 'icp', 'use_cases', 'lifecycle_stages', 
                             'pricing', 'free_trial', 'confidence', 'directory_fit', 'directory_category']
        filled = [f for f in enrichment_fields if getattr(profile, f, None)]
        empty = [f for f in enrichment_fields if not getattr(profile, f, None)]
        print(f"  Fields filled: {len(filled)}/10: {filled}")
        print(f"  Empty: {empty}")
        
        if upsert_fn:
            upsert_fn(vendor, homepage, profile)
            print(f"  Upserted to Supabase")
        
        results.append({"vendor": name, "filled": len(filled), "empty": empty, "backend": backend})
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append({"vendor": name, "error": str(e)})

print(f"\n\nSummary: {len(results)} vendors processed")
for r in results:
    if "error" in r:
        print(f"  FAIL {r['vendor']}: {r['error'][:60]}")
    else:
        print(f"  {r['vendor']}: {r['filled']}/10 fields filled, backend={r.get('backend','?')}")
