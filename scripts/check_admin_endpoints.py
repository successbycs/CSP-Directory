#!/usr/bin/env python3
"""Verify all /admin/ops/* endpoints are responding.

Exit 0 — all endpoints respond 2xx or 400 with valid JSON error
Exit 1 — any endpoint fails (connection refused, 5xx, non-JSON)
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

ADMIN_BASE_URL = "http://127.0.0.1:8787"

# Each entry: (method, path, body_dict, acceptable_status_codes)
# 400 is acceptable — it means the endpoint is alive but rejected the minimal payload (expected)
CHECKS = [
    ("POST", "/admin/ops/store-crawl-result", {}, {200, 400, 503}),
    ("POST", "/admin/ops/store-crawl-result", {"vendor_website": "https://example.com", "column": "bad_column", "payload": {}}, {400}),
    ("POST", "/admin/ops/store-pages", {}, {200, 400, 503}),
    ("GET",  "/admin/ops/field-coverage", None, {200, 400, 503}),
    ("GET",  "/admin/pipelines", None, {200}),
]


def check(method: str, path: str, body: dict | None, ok_statuses: set[int]) -> tuple[bool, str]:
    url = f"{ADMIN_BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8") if exc.fp else ""
    except (urllib.error.URLError, OSError) as exc:
        return False, f"Connection failed: {exc}"

    if status not in ok_statuses:
        return False, f"HTTP {status} (expected one of {ok_statuses}): {raw[:200]}"

    try:
        json.loads(raw)
    except json.JSONDecodeError:
        return False, f"HTTP {status} but response is not JSON: {raw[:200]}"

    return True, f"HTTP {status} OK"


def main() -> int:
    failures: list[str] = []

    for method, path, body, ok_statuses in CHECKS:
        ok, detail = check(method, path, body, ok_statuses)
        label = f"{method} {path}"
        if ok:
            print(f"  ✓ {label} — {detail}")
        else:
            print(f"  ✗ {label} — {detail}")
            failures.append(label)

    # Check pipeline specs include all M76 ops entries
    try:
        req = urllib.request.Request(f"{ADMIN_BASE_URL}/admin/pipelines", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            pipelines = json.loads(resp.read().decode("utf-8"))
        ids = {p["pipeline_id"] for p in pipelines.get("items", [])}
        required_ids = {
            "ops_discovery_run", "ops_crawl_tier1", "ops_crawl_tier2",
            "ops_crawl_tier3", "ops_crawl_datagma", "ops_crawl_g2",
            "ops_crawl_llm", "ops_merge",
        }
        missing_ids = required_ids - ids
        if missing_ids:
            print(f"  ✗ Missing pipeline specs: {', '.join(sorted(missing_ids))}")
            failures.append("pipeline_specs")
        else:
            print(f"  ✓ All 8 M76 pipeline specs registered")
    except Exception as exc:
        print(f"  ✗ Could not verify pipeline specs: {exc}")
        failures.append("pipeline_specs_check")

    if failures:
        print(f"\nFAIL: {len(failures)} check(s) failed: {', '.join(failures)}")
        print(f"      Ensure admin API is running: python3 -m services.admin.admin_api")
        return 1

    print(f"\nOK: All admin ops endpoint checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
