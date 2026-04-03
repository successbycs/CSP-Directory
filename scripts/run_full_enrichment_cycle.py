"""
Full enrichment cycle — runs all enrichment sources in sequence for all vendors.

Order:
  1. Site crawl (Tier 1 direct HTTP — fast, free)
  2. LLM extraction batch (GPT-4o)
  3. Datagma firmographic
  4. LinkedIn enrichment
  5. G2 RapidAPI enrichment
  6. Export dataset to Vercel

Use for backfill or full vendor refresh. Each step is independent — a failure
in one step does not stop the others.

Usage:
    python scripts/run_full_enrichment_cycle.py [--limit N] [--vendor WEBSITE] [--skip STEP]

    --skip  Comma-separated step names to skip, e.g. --skip linkedin,g2
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PYTHON = sys.executable


def _run(label: str, script: str, extra_args: list[str] = []) -> int:
    cmd = [PYTHON, script, *extra_args]
    print(f"\n{'='*60}", flush=True)
    print(f"STEP: {label}", flush=True)
    print(f"CMD:  {' '.join(cmd)}", flush=True)
    print(f"{'='*60}", flush=True)
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    rc = result.returncode
    status = "OK" if rc == 0 else f"FAILED (exit {rc})"
    print(f"→ {label}: {status}", flush=True)
    return rc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit vendors per step")
    parser.add_argument("--vendor", help="Run for a single vendor website")
    parser.add_argument("--skip", default="", help="Comma-separated steps to skip: crawl,llm,datagma,linkedin,g2,export")
    args = parser.parse_args()

    skip = {s.strip().lower() for s in args.skip.split(",") if s.strip()}
    extra: list[str] = []
    if args.limit:
        extra += ["--limit", str(args.limit)]
    if args.vendor:
        extra += ["--vendor", args.vendor]

    steps = [
        ("crawl",    "Site Crawl (Tier 1)",           "scripts/enrich_site_crawl.py",    extra + ["--tier", "1"]),
        ("llm",      "Batch LLM Enrichment (GPT-4o)", "scripts/run_batch_enrichment.py", extra),
        ("datagma",  "Firmographic (Datagma)",         "scripts/enrich_firmographic.py",  extra),
        ("linkedin", "LinkedIn Enrichment",            "scripts/enrich_linkedin.py",      extra),
        ("g2",       "G2 RapidAPI Enrichment",         "scripts/enrich_g2_rapidapi.py",   extra),
        ("export",   "Export Dataset → Vercel",        "scripts/export_directory_dataset.py", []),
    ]

    results: dict[str, int] = {}
    for key, label, script, step_args in steps:
        if key in skip:
            print(f"\nSKIP: {label}", flush=True)
            continue
        rc = _run(label, script, step_args)
        results[key] = rc
        if rc != 0:
            print(f"WARNING: {label} failed — continuing with remaining steps", flush=True)
        time.sleep(2)

    print(f"\n{'='*60}", flush=True)
    print("FULL ENRICHMENT CYCLE COMPLETE", flush=True)
    for key, rc in results.items():
        print(f"  {key:12s}: {'OK' if rc == 0 else f'FAILED ({rc})'}", flush=True)
    print(f"{'='*60}", flush=True)

    failed = sum(1 for rc in results.values() if rc != 0)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
