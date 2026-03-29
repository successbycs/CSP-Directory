"""Tests for use_case_details deterministic extraction (M67)."""

from __future__ import annotations

import pytest

from services.extraction.use_case_details_extractor import (
    _label_from_url,
    _slug_to_title,
    extract_use_case_details,
)


# ---------------------------------------------------------------------------
# _slug_to_title
# ---------------------------------------------------------------------------


def test_slug_to_title_hyphenated():
    assert _slug_to_title("health-scores") == "Health Scores"


def test_slug_to_title_underscored():
    assert _slug_to_title("customer_onboarding") == "Customer Onboarding"


def test_slug_to_title_single_word():
    assert _slug_to_title("onboarding") == "Onboarding"


def test_slug_to_title_too_short():
    assert _slug_to_title("ab") == ""


def test_slug_to_title_strips_special_chars():
    assert _slug_to_title("renewal!") == "Renewal"


# ---------------------------------------------------------------------------
# _label_from_url
# ---------------------------------------------------------------------------


def test_label_from_url_solutions_subpage():
    assert _label_from_url("https://example.com/solutions/customer-onboarding") == "Customer Onboarding"


def test_label_from_url_features_subpage():
    assert _label_from_url("https://example.com/features/health-scores") == "Health Scores"


def test_label_from_url_use_cases_subpage():
    assert _label_from_url("https://example.com/use-cases/renewal-automation") == "Renewal Automation"


def test_label_from_url_product_subpage():
    assert _label_from_url("https://example.com/product/playbooks") == "Playbooks"


def test_label_from_url_platform_subpage():
    assert _label_from_url("https://example.com/platform/analytics") == "Analytics"


def test_label_from_url_top_level_solutions_returns_empty():
    assert _label_from_url("https://example.com/solutions") == ""


def test_label_from_url_homepage_returns_empty():
    assert _label_from_url("https://example.com/") == ""


def test_label_from_url_unrelated_path_returns_empty():
    assert _label_from_url("https://example.com/blog/post-title") == ""


def test_label_from_url_trailing_slash():
    assert _label_from_url("https://example.com/features/health-scores/") == "Health Scores"


# ---------------------------------------------------------------------------
# extract_use_case_details
# ---------------------------------------------------------------------------


def test_extract_use_case_details_returns_records_for_matching_pages():
    explored = {
        "homepage": {"url": "https://example.com", "text": "We help CS teams."},
        "extra_page_1": {
            "url": "https://example.com/solutions/onboarding",
            "text": "Streamline your customer onboarding process with automated workflows.",
        },
        "extra_page_2": {
            "url": "https://example.com/solutions/renewal",
            "text": "Boost renewal rates with early warning signals and playbooks.",
        },
    }
    result = extract_use_case_details(explored)
    labels = [r["label"] for r in result]
    assert "Onboarding" in labels
    assert "Renewal" in labels


def test_extract_use_case_details_skips_top_level_pages():
    explored = {
        "product_page": {
            "url": "https://example.com/solutions",
            "text": "Our full solution suite for customer success.",
        },
    }
    result = extract_use_case_details(explored)
    assert result == []


def test_extract_use_case_details_deduplicates_by_label():
    explored = {
        "extra_page_1": {
            "url": "https://example.com/solutions/onboarding",
            "text": "First onboarding page.",
        },
        "extra_page_2": {
            "url": "https://example.com/features/onboarding",
            "text": "Second onboarding page.",
        },
    }
    result = extract_use_case_details(explored)
    labels = [r["label"] for r in result]
    assert labels.count("Onboarding") == 1


def test_extract_use_case_details_summary_is_first_meaningful_line():
    explored = {
        "extra_page_1": {
            "url": "https://example.com/product/playbooks",
            "text": "\n\nPlaybooks automate your CS team's most critical workflows.\nLearn more.",
        },
    }
    result = extract_use_case_details(explored)
    assert len(result) == 1
    assert "Playbooks automate" in result[0]["summary"]


def test_extract_use_case_details_skips_pages_without_text():
    explored = {
        "extra_page_1": {
            "url": "https://example.com/solutions/expansion",
            "text": "",
        },
    }
    result = extract_use_case_details(explored)
    assert result == []


def test_extract_use_case_details_url_is_preserved():
    url = "https://example.com/features/health-scores"
    explored = {
        "extra_page_1": {
            "url": url,
            "text": "Track customer health in real time with composite scoring.",
        },
    }
    result = extract_use_case_details(explored)
    assert result[0]["url"] == url
