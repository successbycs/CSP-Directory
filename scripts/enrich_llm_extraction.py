"""
Batch LLM extraction — thin orchestrator calling services.ops.run_llm_extraction
per vendor.

All extraction logic lives in services/ops/run_llm_extraction.py.

Usage:
    python scripts/enrich_llm_extraction.py [--limit N] [--vendor WEBSITE] [--force]
"""
from __future__ import annotations
import argparse, subprocess, sys, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from services.persistence import supabase_client

PYTHON = sys.executable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--vendor", help="Filter by website substring")
    parser.add_argument("--force", action="store_true", help="Re-extract even if crawl_llm_result exists")
    args = parser.parse_args()

    client = supabase_client.get_supabase_client()
    q = client.table("cs_vendors").select("name, website, crawl_llm_result")
    if args.vendor:
        q = q.ilike("website", f"%{args.vendor}%").limit(5)
    else:
        q = q.eq("include_in_directory", True)
    vendors = q.execute().data

    if not args.force:
        vendors = [v for v in vendors if not v.get("crawl_llm_result")]
    if args.limit:
        vendors = vendors[: args.limit]

    print(f"LLM extraction (embed → RAG → GPT-4o mini): {len(vendors)} vendors", flush=True)
    ok = failed = 0

    for i, v in enumerate(vendors, 1):
        website = v.get("website") or ""
        if not website:
            continue
        print(f"[{i}/{len(vendors)}] {v['name']}", flush=True)
        cmd = [PYTHON, "-m", "services.ops.run_llm_extraction", "--vendor", website]
        if args.force:
            cmd.append("--force")
        result = subprocess.run(cmd, cwd=PROJECT_ROOT)
        if result.returncode == 0:
            ok += 1
        else:
            failed += 1
        time.sleep(0.5)

    print(f"\nDone: {ok} ok, {failed} failed", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
