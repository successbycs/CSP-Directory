"""M46: Pipeline health check — post-cycle quality gate."""

from scripts.pipeline_health_check import (
    check_junk_domain_violations,
    check_lifecycle_stage_violations,
    check_missing_category_violations,
    check_other_category_violations,
    run_health_check,
)


DENYLIST = ("reddit.com", "gartner.com", "forbes.com", "linkedin.com")


# --- check_junk_domain_violations ---

def test_junk_domain_check_flags_exact_match():
    rows = [{"website": "https://reddit.com/r/CustomerSuccess"}]
    assert check_junk_domain_violations(rows, DENYLIST) == ["https://reddit.com/r/CustomerSuccess"]


def test_junk_domain_check_flags_subdomain():
    rows = [{"website": "https://news.forbes.com/article/ai-cs"}]
    assert check_junk_domain_violations(rows, DENYLIST) == ["https://news.forbes.com/article/ai-cs"]


def test_junk_domain_check_passes_clean_vendor():
    rows = [{"website": "https://gainsight.com"}]
    assert check_junk_domain_violations(rows, DENYLIST) == []


# --- check_lifecycle_stage_violations ---

def test_lifecycle_check_flags_included_vendor_with_no_stages():
    rows = [{"website": "https://vendor.com", "include_in_directory": True, "lifecycle_stages": []}]
    assert check_lifecycle_stage_violations(rows) == ["https://vendor.com"]


def test_lifecycle_check_flags_included_vendor_with_null_stages():
    rows = [{"website": "https://vendor.com", "include_in_directory": True, "lifecycle_stages": None}]
    assert check_lifecycle_stage_violations(rows) == ["https://vendor.com"]


def test_lifecycle_check_passes_included_vendor_with_stages():
    rows = [{"website": "https://vendor.com", "include_in_directory": True, "lifecycle_stages": ["onboard"]}]
    assert check_lifecycle_stage_violations(rows) == []


def test_lifecycle_check_ignores_excluded_vendor():
    rows = [{"website": "https://vendor.com", "include_in_directory": False, "lifecycle_stages": []}]
    assert check_lifecycle_stage_violations(rows) == []


# --- check_missing_category_violations ---

def test_category_check_flags_included_vendor_with_no_category():
    rows = [{"website": "https://vendor.com", "include_in_directory": True, "directory_category": None}]
    assert check_missing_category_violations(rows) == ["https://vendor.com"]


def test_category_check_passes_vendor_with_category():
    rows = [{"website": "https://vendor.com", "include_in_directory": True, "directory_category": "csp"}]
    assert check_missing_category_violations(rows) == []


# --- check_other_category_violations ---

def test_other_category_check_flags_included_vendor_with_other():
    rows = [{"website": "https://vendor.com", "include_in_directory": True, "directory_category": "other"}]
    assert check_other_category_violations(rows) == ["https://vendor.com"]


def test_other_category_check_passes_non_other_category():
    rows = [{"website": "https://vendor.com", "include_in_directory": True, "directory_category": "csp"}]
    assert check_other_category_violations(rows) == []


# --- run_health_check (integration) ---

def test_run_health_check_passes_with_clean_data():
    rows = [
        {
            "website": "https://gainsight.com",
            "include_in_directory": True,
            "lifecycle_stages": ["onboard", "adopt"],
            "directory_category": "csp",
        }
    ]
    assert run_health_check(vendor_rows=rows) is True


def test_run_health_check_fails_with_violations():
    rows = [
        {
            "website": "https://vendor.com",
            "include_in_directory": True,
            "lifecycle_stages": [],
            "directory_category": "csp",
        }
    ]
    assert run_health_check(vendor_rows=rows) is False
