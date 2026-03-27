"""Tests for merging vendor page intelligence into a profile."""

from services.extraction.vendor_intel import VendorIntelligence
from services.extraction.vendor_profile_builder import build_vendor_profile


def test_build_vendor_profile_merges_source_and_evidence_urls():
    vendor = {
        "vendor_name": "Search Title",
        "website": "https://example.com",
        "source": "google_search",
    }
    explored_pages = {
        "homepage": {
            "vendor_name": "ExampleCorp",
            "website": "https://example.com",
            "text": "Homepage text",
        },
        "pricing_page": {
            "vendor_name": "",
            "website": "https://example.com/pricing",
            "text": "$99 per seat",
        },
        "extra_pages": [
            {
                "vendor_name": "",
                "url": "https://example.com/ai-copilot",
                "website": "https://example.com/ai-copilot",
                "text": "AI copilot for CSMs",
            }
        ],
    }
    intelligence = VendorIntelligence(
        vendor_name="ExampleCorp",
        website="https://example.com",
        mission="Help customer success teams retain more revenue.",
        usp="reduce churn",
        icp=["SaaS companies"],
        use_cases=["health scoring"],
        lifecycle_stages=["Adopt", "Renew"],
        pricing=["$", "per seat"],
        case_studies=["case study"],
        customers=["Acme"],
        value_statements=["reduce churn"],
        confidence="medium",
    )

    result = build_vendor_profile(vendor, explored_pages, intelligence)

    assert result.vendor_name == "ExampleCorp"
    assert result.source == "google_search"
    assert result.evidence_urls == [
        "https://example.com",
        "https://example.com/pricing",
        "https://example.com/ai-copilot",
    ]
    assert result.directory_fit == "medium"
    assert result.directory_category == "cs_core"
    assert result.include_in_directory is True
    assert result.llm_directory_fit == "medium"
    assert result.llm_directory_category == "cs_core"
    assert result.llm_include_in_directory is True
    assert result.directory_decision_source == "auto"
    assert result.directory_reasoning


def test_build_vendor_profile_falls_back_to_discovery_data_when_homepage_fields_are_missing():
    vendor = {
        "vendor_name": "DiscoveryName",
        "website": "https://fallback.example.com",
        "source": "google_search",
    }
    explored_pages = {"homepage": {"website": "https://fallback.example.com", "text": ""}}
    intelligence = VendorIntelligence(
        vendor_name="",
        website="",
        mission="Help customer success teams improve adoption.",
        confidence="medium",
    )

    result = build_vendor_profile(vendor, explored_pages, intelligence)

    assert result.vendor_name == "DiscoveryName"
    assert result.website == "https://fallback.example.com"
    assert result.source == "google_search"
    assert result.directory_fit == "medium"
    # M45: no lifecycle_stages → lifecycle_stage_gate excludes vendor
    assert result.include_in_directory is False


def test_build_vendor_profile_canonicalizes_vendor_website_identity():
    vendor = {
        "vendor_name": "ExampleCorp",
        "website": "HTTPS://WWW.Example.com/pricing?ref=ad",
        "source": "google_search",
    }
    explored_pages = {
        "homepage": {
            "website": "HTTPS://WWW.Example.com/pricing?ref=ad",
            "text": "Homepage text",
        }
    }
    intelligence = VendorIntelligence(
        vendor_name="ExampleCorp",
        website="HTTPS://WWW.Example.com/pricing?ref=ad",
        mission="Help customer success teams improve adoption.",
        confidence="medium",
    )

    result = build_vendor_profile(vendor, explored_pages, intelligence)

    assert result.website == "https://example.com"


def test_build_vendor_profile_excludes_article_like_or_support_subdomain_vendors():
    vendor = {
        "vendor_name": "What is Customer Onboarding Automation?",
        "website": "https://support.example.com",
        "source": "google_search",
    }
    explored_pages = {
        "homepage": {
            "website": "https://support.example.com",
            "text": "Support center article",
        }
    }
    intelligence = VendorIntelligence(
        vendor_name="What is Customer Onboarding Automation?",
        website="https://support.example.com",
        mission="403 Forbidden",
        confidence="high",
    )

    result = build_vendor_profile(vendor, explored_pages, intelligence)

    assert result.directory_fit == "low"
    assert result.directory_category == "infra"
    assert result.include_in_directory is False
    assert result.llm_directory_fit == "medium"
    assert result.llm_directory_category == "cs_adjacent"
    assert result.llm_include_in_directory is True
    assert any("editorial/noise content" in reason.lower() for reason in result.directory_reasoning)


def test_build_vendor_profile_preserves_m18_rich_fields():
    vendor = {
        "vendor_name": "ExampleCorp",
        "website": "https://example.com",
        "source": "google_search",
    }
    explored_pages = {
        "homepage": {
            "vendor_name": "ExampleCorp",
            "website": "https://example.com",
            "text": "Homepage text",
        }
    }
    intelligence = VendorIntelligence(
        vendor_name="ExampleCorp",
        website="https://example.com",
        products=[
            {
                "name": "Journey Hub",
                "category": "platform",
                "description": "Guided onboarding",
                "use_cases": ["guided onboarding"],
                "integration_categories": ["crm"],
                "integrations": ["Salesforce"],
                "demo_url": "https://example.com/demo/journey-hub",
                "support_url": "https://example.com/support/journey-hub",
                "help_center_url": "https://example.com/help/journey-hub",
                "developer_docs_url": "https://example.com/docs/journey-hub",
                "source_url": "https://example.com/products/journey-hub",
            },
            {
                "name": "Renewal AI",
                "category": "module",
                "description": "Renewal risk automation",
                "use_cases": ["renewal forecasting"],
                "integration_categories": ["crm"],
                "integrations": ["HubSpot"],
                "demo_url": "https://example.com/demo/renewal-ai",
                "support_url": "https://example.com/support/renewal-ai",
                "help_center_url": "https://example.com/help/renewal-ai",
                "developer_docs_url": "",
                "source_url": "https://example.com/products/renewal-ai",
            }
        ],
        leadership=[
            {
                "name": "Jane Doe",
                "title": "CEO",
                "source_url": "https://example.com/team",
            }
        ],
        ceo_name="Jane Doe",
        hq_address="Austin, Texas",
        phone_numbers=["+15125550100"],
        contact_emails=["sales@example.com", "support@example.com"],
        contact_email="sales@example.com",
        contact_page_url="https://example.com/contact",
        demo_url="https://example.com/demo",
        help_center_url="https://example.com/help",
        support_url="https://example.com/support",
        company_hq="Austin, Texas",
        developer_docs_url="https://example.com/docs",
        integration_categories=["crm"],
        integrations=["Salesforce"],
        support_signals=["help center"],
        case_study_details=[
            {
                "client": "Acme",
                "title": "Acme case study",
                "use_case": "onboarding",
                "value_realized": "reduced churn by 20%",
                "metric": "20%",
                "source_url": "https://example.com/customers/acme",
            }
        ],
        confidence="medium",
    )

    result = build_vendor_profile(vendor, explored_pages, intelligence)

    assert result.products == intelligence.products
    assert result.products[0]["demo_url"] == "https://example.com/demo/journey-hub"
    assert result.products[1]["integrations"] == ["HubSpot"]
    assert result.leadership == intelligence.leadership
    assert result.ceo_name == "Jane Doe"
    assert result.hq_address == "Austin, Texas"
    assert result.phone_numbers == ["+15125550100"]
    assert result.contact_emails == ["sales@example.com", "support@example.com"]
    assert result.contact_email == "sales@example.com"
    assert result.help_center_url == "https://example.com/help"
    assert result.developer_docs_url == "https://example.com/docs"
    assert result.integration_categories == ["crm"]
    assert result.integrations == ["Salesforce"]
    assert result.case_study_details == intelligence.case_study_details
