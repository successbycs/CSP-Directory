#!/usr/bin/env python3
"""Proof script for M43 — Canonical vendor name enforcement.

Checks:
1. Unit tests pass (test_canonical_name.py)
2. Zero vendors with names that fail quality check after enriching all violators
3. Gainsight and Outreach names pass quality check
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_env_path = Path(__file__).resolve().parents[1] / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"'))

from supabase import create_client
from scripts.enrich_vendors_deterministic import _name_fails_quality_check

GAINSIGHT_ID = "d8534ba8-a337-4182-aef8-43a597624dda"
OUTREACH_ID = "a7e9d46d-33c4-459a-bb11-bb31249dd123"
PROOF_PATH = Path(__file__).resolve().parents[1] / "runs" / "proofs" / "M43_canonical_name_enforcement.json"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_unit_tests() -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_canonical_name.py", "-v", "--tb=short"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    return {
        "passed": result.returncode == 0,
        "exit_code": result.returncode,
        "output": (result.stdout or result.stderr)[-2000:],
    }


def enrich_vendor(vendor_id: str) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/enrich_vendors_deterministic.py", "--vendor-id", vendor_id],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Enrichment failed for {vendor_id}: {result.stderr[-300:]}")


def fetch_name(client, vendor_id: str) -> str:
    row = client.table("cs_vendors").select("name").eq("id", vendor_id).execute()
    return row.data[0]["name"] if row.data else ""


def find_violations(client) -> list[dict]:
    rows = client.table("cs_vendors").select("id, name, website").execute()
    return [
        {"id": r["id"], "name": r.get("name") or "", "website": r.get("website") or ""}
        for r in rows.data
        if _name_fails_quality_check(r.get("name") or "")
    ]


def main() -> int:
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    print("Step 1: Unit tests...")
    test_result = run_unit_tests()
    print(f"  {'PASS' if test_result['passed'] else 'FAIL'}")

    print("\nStep 2: Find and fix all name violations...")
    pre_violations = find_violations(client)
    print(f"  Pre-fix violations: {len(pre_violations)}")
    for v in pre_violations:
        print(f"    Enriching {v['website']} ('{v['name']}')")
        enrich_vendor(v["id"])

    print("\nStep 3: Re-check all names...")
    post_violations = find_violations(client)
    print(f"  Post-fix violations: {len(post_violations)}")
    for v in post_violations:
        print(f"    {v['website']}: '{v['name']}'")

    print("\nStep 4: Spot-check Gainsight and Outreach...")
    gainsight_name = fetch_name(client, GAINSIGHT_ID)
    outreach_name = fetch_name(client, OUTREACH_ID)
    gainsight_pass = not _name_fails_quality_check(gainsight_name)
    outreach_pass = outreach_name == "Outreach"
    print(f"  Gainsight: '{gainsight_name}' quality={'PASS' if gainsight_pass else 'FAIL'}")
    print(f"  Outreach:  '{outreach_name}' — {'PASS' if outreach_pass else 'FAIL'}")

    overall = test_result["passed"] and len(post_violations) == 0 and gainsight_pass and outreach_pass

    proof = {
        "milestone": "M43",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if overall else "fail",
        "checks": {
            "unit_tests": {"passed": test_result["passed"], "output": test_result["output"]},
            "name_violations": {
                "pre_fix": len(pre_violations),
                "pre_fix_details": pre_violations,
                "post_fix": len(post_violations),
                "post_fix_details": post_violations,
                "passed": len(post_violations) == 0,
            },
            "gainsight": {"name": gainsight_name, "quality_pass": gainsight_pass},
            "outreach": {"name": outreach_name, "passed": outreach_pass},
        },
        "summary": (
            f"Unit tests {'passed' if test_result['passed'] else 'failed'}. "
            f"{len(pre_violations)} pre-fix violations, {len(post_violations)} post-fix. "
            f"Gainsight='{gainsight_name}', Outreach='{outreach_name}'."
        ),
    }

    PROOF_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROOF_PATH.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(f"\nProof: {PROOF_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Overall: {'PASS' if overall else 'FAIL'}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
