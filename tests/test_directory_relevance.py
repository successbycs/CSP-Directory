"""Tests for deterministic directory relevance scoring."""

from services.extraction.directory_relevance import evaluate_directory_relevance, evaluate_directory_relevance_decision
from services.extraction.vendor_intel import VendorIntelligence


def test_evaluate_directory_relevance_marks_core_vendor_for_inclusion():
    vendor = VendorIntelligence(
        vendor_name="ExampleCorp",
        website="https://example.com",
        mission="Customer success platform for onboarding and renewals.",
        use_cases=["onboarding automation", "renewal management"],
        lifecycle_stages=["Onboard", "Renew"],
        confidence="high",
    )

    directory_fit, directory_category, include_in_directory = evaluate_directory_relevance(vendor)

    assert directory_fit == "high"
    assert directory_category == "cs_core"
    assert include_in_directory is True


def test_evaluate_directory_relevance_excludes_infra_vendor():
    vendor = VendorIntelligence(
        vendor_name="InfraCorp",
        website="https://infra.example.com",
        mission="Messaging API for contact center infrastructure.",
        use_cases=["messaging api", "contact center routing"],
        confidence="high",
    )

    directory_fit, directory_category, include_in_directory = evaluate_directory_relevance(vendor)

    assert directory_fit == "low"
    assert directory_category == "infra"
    assert include_in_directory is False


def test_evaluate_directory_relevance_decision_returns_reasoning_for_operator_review():
    vendor = VendorIntelligence(
        vendor_name="ExampleCorp",
        website="https://example.com",
        mission="Customer success platform for onboarding and renewals.",
        use_cases=["onboarding automation", "renewal management"],
        lifecycle_stages=["Onboard", "Renew"],
        confidence="medium",
    )

    decision = evaluate_directory_relevance_decision(vendor)

    assert decision.directory_fit == "medium"
    assert decision.directory_category == "cs_core"
    assert decision.include_in_directory is True
    assert decision.decision_source == "auto"
    assert any("core lifecycle stages" in reason.lower() for reason in decision.reasoning)
