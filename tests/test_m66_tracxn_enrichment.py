"""M66: Milestone tests for Tracxn teaser enrichment.

Acceptance criteria verified:
- Canary check passes for known Tracxn slug (gainsight)
- Live crawl of one real vendor returns at least one field (founded, hq_address,
  funding_stage, or total_funding)
- enrich_vendors_from_tracxn() returns correct summary shape
- Safe-upsert: populated fields are never overwritten
- Miss vendors are counted, not errored
- Admin API enrich-write endpoint accepts funding_stage and total_funding
  (regression: these were missing from _SCALAR_FIELDS before this milestone)

Live tests (marked @pytest.mark.live) make real HTTP requests to tracxn.com.
Run with:  pytest tests/test_m66_tracxn_enrichment.py -m live -v
Skip with: pytest tests/test_m66_tracxn_enrichment.py -m "not live"
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from services.enrichment.tracxn_enricher import (
    derive_tracxn_slug,
    enrich_vendors_from_tracxn,
    fetch_tracxn_teaser,
    run_canary_check,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_response(html: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = html
    return resp


GAINSIGHT_HTML = """
<html><head><title>Gainsight - Tracxn</title></head><body>
<script type="application/ld+json">
{"@type": "Organization", "name": "Gainsight",
 "address": {"addressLocality": "San Francisco", "addressRegion": "CA", "addressCountry": "US"}}
</script>
<p>Gainsight was founded in 2013 by Nick Mehta and serves enterprise SaaS companies.</p>
<p>Funding Stage: Series E. Total Funding: $145M raised across multiple rounds.</p>
<p>Headquarters: San Francisco, CA, United States.</p>
</body></html>
"""


# ── 1. Canary check (unit) ────────────────────────────────────────────────────

def test_canary_passes_with_valid_gainsight_page():
    ok = run_canary_check(request_get=lambda *a, **k: _mock_response(GAINSIGHT_HTML))
    assert ok is True


def test_canary_fails_on_404():
    ok = run_canary_check(request_get=lambda *a, **k: _mock_response("", 404))
    assert ok is False


def test_canary_fails_on_empty_page():
    ok = run_canary_check(request_get=lambda *a, **k: _mock_response("<html></html>"))
    assert ok is False


# ── 2. Field extraction from Gainsight page (unit) ───────────────────────────

def test_gainsight_founded_extracted():
    result = fetch_tracxn_teaser("gainsight", request_get=lambda *a, **k: _mock_response(GAINSIGHT_HTML))
    assert result is not None
    assert result.get("founded") == "2013"


def test_gainsight_hq_extracted_from_json_ld():
    result = fetch_tracxn_teaser("gainsight", request_get=lambda *a, **k: _mock_response(GAINSIGHT_HTML))
    assert result is not None
    assert "San Francisco" in result.get("hq_address", "")


def test_gainsight_funding_stage_extracted():
    result = fetch_tracxn_teaser("gainsight", request_get=lambda *a, **k: _mock_response(GAINSIGHT_HTML))
    assert result is not None
    assert "Series E" in result.get("funding_stage", "")


def test_gainsight_total_funding_extracted():
    result = fetch_tracxn_teaser("gainsight", request_get=lambda *a, **k: _mock_response(GAINSIGHT_HTML))
    assert result is not None
    assert result.get("total_funding", "").startswith("$")


# ── 3. Slug derivation ────────────────────────────────────────────────────────

def test_slug_from_gainsight_website():
    assert derive_tracxn_slug("Gainsight", "https://gainsight.com") == "gainsight"


def test_slug_from_vitally_website():
    assert derive_tracxn_slug("Vitally", "https://vitally.io") == "vitally"


def test_slug_fallback_to_vendor_name():
    assert derive_tracxn_slug("ChurnZero") == "churnzero"


def test_slug_multi_word_name():
    assert derive_tracxn_slug("Staircase AI") == "staircase-ai"


# ── 4. Safe-upsert behaviour ──────────────────────────────────────────────────

def test_safe_upsert_does_not_overwrite_founded():
    """If founded is already set it must not be overwritten."""
    vendors = [{
        "vendor_name": "Gainsight",
        "website": "https://gainsight.com",
        "founded": "2013",          # already populated
        "hq_address": "",
        "funding_stage": "",
        "total_funding": "",
    }]
    upserts = []
    enrich_vendors_from_tracxn(
        vendors,
        upsert_fn=lambda k, v: upserts.append(v),
        request_get=lambda *a, **k: _mock_response(GAINSIGHT_HTML),
        skip_canary=True,
    )
    assert len(upserts) == 1
    assert "founded" not in upserts[0], "founded was already set — should not be overwritten"


def test_safe_upsert_skips_fully_enriched_vendor():
    vendors = [{
        "vendor_name": "Gainsight",
        "website": "https://gainsight.com",
        "founded": "2013",
        "hq_address": "San Francisco, CA",
        "funding_stage": "Series E",
        "total_funding": "$145M",
    }]
    upserts = []
    enrich_vendors_from_tracxn(
        vendors,
        upsert_fn=lambda k, v: upserts.append(v),
        request_get=lambda *a, **k: _mock_response(GAINSIGHT_HTML),
        skip_canary=True,
    )
    assert len(upserts) == 0


# ── 5. Batch summary shape ────────────────────────────────────────────────────

def test_batch_summary_has_expected_keys():
    vendors = [{"vendor_name": "Gainsight", "website": "https://gainsight.com"}]
    result = enrich_vendors_from_tracxn(
        vendors,
        request_get=lambda *a, **k: _mock_response(GAINSIGHT_HTML),
        skip_canary=True,
    )
    assert "attempted" in result
    assert "enriched" in result
    assert "miss_count" in result
    assert "errors" in result
    assert "skipped_canary" in result


def test_batch_miss_counted_not_errored():
    vendors = [{"vendor_name": "UnknownCorp", "website": "https://unknowncorp.example"}]
    result = enrich_vendors_from_tracxn(
        vendors,
        request_get=lambda *a, **k: _mock_response("", 404),
        skip_canary=True,
    )
    assert result["miss_count"] == 1
    assert result["errors"] == []


def test_batch_aborts_when_canary_fails():
    vendors = [{"vendor_name": "Gainsight", "website": "https://gainsight.com"}]
    result = enrich_vendors_from_tracxn(
        vendors,
        request_get=lambda *a, **k: _mock_response("", 404),
        skip_canary=False,
    )
    assert result["skipped_canary"] is True
    assert result["attempted"] == 0


# ── 6. Admin API regression: funding_stage and total_funding accepted ─────────

def test_admin_api_enrich_write_accepts_funding_fields():
    """Regression: funding_stage and total_funding were missing from _SCALAR_FIELDS.
    This test confirms they are recognised and included in fields_written (not silently dropped).
    A Supabase upsert error is acceptable here; a validation_error or missing fields_written is not.
    """
    from services.admin.admin_api import _run_enrich_write

    result = _run_enrich_write({
        "website": "https://gainsight.com",
        "vendor_name": "Gainsight",
        "founded": "2013",
        "hq_address": "San Francisco, CA",
        "funding_stage": "Series E",
        "total_funding": "$145M",
    })
    # Fields must be recognised — present in fields_written means _SCALAR_FIELDS accepted them
    fields_written = result.get("fields_written", [])
    assert "funding_stage" in fields_written, f"funding_stage was dropped (not in _SCALAR_FIELDS?): {result}"
    assert "total_funding" in fields_written, f"total_funding was dropped (not in _SCALAR_FIELDS?): {result}"
    # Must not be a schema/type validation error (Supabase connectivity errors are acceptable)
    validation_errors = [e for e in result.get("validation_errors", []) if not e.startswith("upsert_failed")]
    assert validation_errors == [], f"Unexpected validation errors: {validation_errors}"


# ── 7. Live crawl — real HTTP request to tracxn.com ──────────────────────────

@pytest.mark.live
def test_live_canary_check_gainsight():
    """Canary check against real tracxn.com — confirms the slug and layout still work."""
    ok = run_canary_check()
    assert ok is True, (
        "Tracxn canary failed for 'gainsight'. Either the page is down, "
        "the slug has changed, or the HTML layout no longer matches the parser."
    )


@pytest.mark.live
def test_live_crawl_gainsight_returns_at_least_one_field():
    """Live crawl of gainsight.com on Tracxn — must return at least one structured field.

    This is the milestone acceptance proof: the enricher extracts real data
    from a known-good vendor without mocking.
    """
    result = fetch_tracxn_teaser("gainsight")

    assert result is not None, (
        "Tracxn returned no data for 'gainsight'. "
        "Check https://tracxn.com/d/companies/gainsight/ manually."
    )

    fields_found = [f for f in ("founded", "hq_address", "funding_stage", "total_funding") if result.get(f)]
    assert len(fields_found) >= 1, (
        f"Tracxn page was reachable but no fields extracted. Raw result: {result}"
    )

    # Log what was found to make milestone proof readable
    print(f"\n[live] Gainsight Tracxn result: {json.dumps(result, indent=2)}")


@pytest.mark.live
def test_live_enrich_single_vendor_end_to_end():
    """Full enrichment pipeline for one vendor — canary + fetch + extract.

    Simulates the n8n workflow: vendor in → Tracxn data out.
    Does NOT write to Supabase (no upsert_fn provided).
    """
    vendors = [{
        "vendor_name": "Gainsight",
        "website": "https://gainsight.com",
    }]

    summary = enrich_vendors_from_tracxn(vendors, skip_canary=False)

    assert summary["skipped_canary"] is False, "Canary failed — Tracxn may be down or layout changed"
    assert summary["attempted"] == 1
    assert summary["enriched"] >= 1, (
        f"No fields enriched for Gainsight. Summary: {summary}"
    )
    assert summary["errors"] == []

    print(f"\n[live] Batch summary: {json.dumps(summary, indent=2)}")
