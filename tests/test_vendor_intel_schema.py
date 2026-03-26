"""Tests for the VendorIntelligence schema."""

from services.extraction.vendor_intel import VendorIntelligence, normalize_icp_buyer_profiles


def test_vendor_intelligence_schema_fields_and_types():
    vendor = VendorIntelligence(
        vendor_name="ExampleCorp",
        website="https://example.com",
        source="web_search",
        mission="Improve retention",
        usp="reduce churn",
        icp=["SaaS", "Mid-market"],
        icp_buyer=[
            {
                "persona": "VP Customer Success",
                "confidence": "high",
                "evidence": ["reduce churn", "health scoring"],
                "google_queries": [
                    "customer success software for reducing churn",
                    "best customer health scoring tools",
                ],
                "geo_queries": [
                    "What AI tools help reduce SaaS churn?",
                    "Which customer success platforms improve retention?",
                ],
            }
        ],
        use_cases=["health scoring", "renewal management"],
        lifecycle_stages=["Adopt", "Support", "Renew"],
        case_studies=["Increased retention by 20%", "Reduced churn"],
        customers=["Acme"],
        value_statements=["Increases retention", "Boosts ARR"],
        pricing=["$99/mo", "$199/mo"],
        free_trial=True,
        soc2=True,
        founded="2022",
        products=[{"name": "Journey Hub", "category": "platform", "description": "Guided onboarding", "source_url": "https://www.example.com/products/journey-hub/"}],
        leadership=[{"name": "Jane Doe", "title": "CEO", "source_url": "https://www.example.com/team/"}],
        ceo_name=" Jane Doe ",
        hq_address="Austin, Texas",
        phone_numbers=["+1 (512) 555-0100", "512-555-0100"],
        contact_emails=["Support@example.com", "INFO@EXAMPLE.COM "],
        company_hq="Austin, Texas",
        contact_email="INFO@EXAMPLE.COM ",
        contact_page_url="https://www.example.com/contact/",
        demo_url="example.com/demo",
        help_center_url="https://www.example.com/help/",
        support_url="https://www.example.com/support/",
        about_url="https://www.example.com/about/",
        team_url="https://www.example.com/team/",
        developer_docs_url="https://www.example.com/docs/",
        integration_categories=["crm", "support"],
        integrations=["Salesforce", "Zendesk"],
        support_signals=["help center", "knowledge base"],
        confidence="high",
        case_study_details=[
            {
                "client": "Acme",
                "title": "Acme case study",
                "use_case": "renewal management",
                "value_realized": "reduced churn by 20%",
                "metric": "20%",
                "source_url": "https://www.example.com/customers/acme/",
            }
        ],
        evidence_urls=["https://example.com/proof"],
        directory_fit="strong",
        directory_category="Renew",
        include_in_directory=True,
    )

    # Validate schema structure and type enforcement
    vendor.validate()

    assert vendor.vendor_name == "ExampleCorp"
    assert vendor.website == "https://example.com"
    assert vendor.source == "web_search"
    assert isinstance(vendor.icp, list)
    assert isinstance(vendor.icp_buyer, list)
    assert isinstance(vendor.use_cases, list)
    assert isinstance(vendor.lifecycle_stages, list)
    assert vendor.products == [
        {
            "name": "Journey Hub",
            "category": "platform",
            "description": "Guided onboarding",
            "use_cases": [],
            "integration_categories": [],
            "integrations": [],
            "demo_url": "",
            "support_url": "",
            "help_center_url": "",
            "developer_docs_url": "",
            "source_url": "https://example.com/products/journey-hub",
        }
    ]
    assert vendor.leadership == [
        {
            "name": "Jane Doe",
            "title": "CEO",
            "linkedin": "",
            "source_url": "https://example.com/team",
        }
    ]
    assert vendor.ceo_name == "Jane Doe"
    assert vendor.hq_address == "Austin, Texas"
    assert vendor.phone_numbers == ["+15125550100", "5125550100"]
    assert vendor.contact_emails == ["support@example.com", "info@example.com"]
    assert vendor.contact_email == "info@example.com"
    assert vendor.demo_url == "https://example.com/demo"
    assert vendor.help_center_url == "https://example.com/help"
    assert vendor.support_url == "https://example.com/support"
    assert vendor.developer_docs_url == "https://example.com/docs"
    assert vendor.integration_categories == ["crm", "support"]
    assert vendor.integrations == ["Salesforce", "Zendesk"]
    assert vendor.integration_taxonomy == [
        {"category": "crm", "integrations": ["Salesforce"]},
        {"category": "support", "integrations": ["Zendesk"]},
    ]
    assert vendor.support_signals == ["help center", "knowledge base"]
    assert isinstance(vendor.case_studies, list)
    assert isinstance(vendor.case_study_details, list)
    assert isinstance(vendor.customers, list)
    assert isinstance(vendor.value_statements, list)
    assert isinstance(vendor.pricing, list)
    assert isinstance(vendor.evidence_urls, list)
    assert vendor.directory_fit == "strong"
    assert vendor.directory_category == "Renew"
    assert vendor.include_in_directory is True


def test_normalize_icp_buyer_profiles_dedupes_and_limits_queries():
    profiles = normalize_icp_buyer_profiles(
        [
            {
                "persona": "VP Customer Success",
                "confidence": "high",
                "evidence": ["reduce churn", "renewals"],
                "google_queries": [
                    "query 1",
                    "query 2",
                    "query 3",
                    "query 4",
                    "query 5",
                    "query 6",
                ],
                "geo_queries": "prompt 1|prompt 2|prompt 3|prompt 4|prompt 5|prompt 6",
            },
            {
                "persona": "vp customer success",
                "confidence": "low",
                "evidence": ["duplicate"],
                "google_queries": ["ignored"],
                "geo_queries": ["ignored"],
            },
        ]
    )

    assert profiles == [
        {
            "persona": "VP Customer Success",
            "confidence": "high",
            "evidence": ["reduce churn", "renewals"],
            "google_queries": ["query 1", "query 2", "query 3", "query 4", "query 5"],
            "geo_queries": ["prompt 1", "prompt 2", "prompt 3", "prompt 4", "prompt 5"],
        }
    ]
