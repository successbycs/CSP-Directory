"""Tests for merging deterministic and LLM extraction."""

from services.extraction.llm_extractor import LLMExtractionResult
from services.extraction.merge_results import merge_vendor_intelligence
from services.extraction.vendor_intel import VendorIntelligence


def test_merge_vendor_intelligence_keeps_deterministic_result_without_llm():
    deterministic = VendorIntelligence(
        vendor_name="ExampleCorp",
        website="https://example.com",
        mission="Improve retention for customer success teams.",
        use_cases=["health scoring"],
        lifecycle_stages=["Adopt"],
        confidence="medium",
    )

    merged = merge_vendor_intelligence(deterministic, None)

    assert merged == deterministic


def test_merge_vendor_intelligence_prefers_valid_llm_fields_and_keeps_deterministic_stages():
    deterministic = VendorIntelligence(
        vendor_name="ExampleCorp",
        website="https://example.com",
        source="google_search",
        mission="Baseline mission",
        usp="Baseline usp",
        icp=["SaaS companies"],
        icp_buyer=[
            {
                "persona": "VP Customer Success",
                "confidence": "medium",
                "evidence": ["health scoring"],
                "google_queries": ["health scoring software"],
                "geo_queries": ["What software improves customer health scoring?"],
            }
        ],
        use_cases=["health scoring"],
        lifecycle_stages=["Adopt"],
        pricing=["contact sales"],
        free_trial=None,
        soc2=None,
        founded="",
        case_studies=["case study"],
        customers=["Acme"],
        value_statements=["improve customer health"],
        confidence="medium",
        evidence_urls=["https://example.com"],
    )
    llm_result = LLMExtractionResult(
        is_cs_relevant=True,
        mission="AI customer success platform that reduces churn and automates onboarding.",
        usp="Predict churn and speed time to value.",
        icp=["customer success teams"],
        icp_buyer=[
            {
                "persona": "VP Customer Success",
                "confidence": "high",
                "evidence": ["reduce churn"],
                "google_queries": ["customer success software for reducing churn"],
                "geo_queries": ["What AI tools reduce churn for SaaS teams?"],
            },
            {
                "persona": "Chief Customer Officer",
                "confidence": "medium",
                "evidence": ["onboarding automation"],
                "google_queries": ["customer success platform for enterprise saas"],
                "geo_queries": ["Which customer success vendors support the full lifecycle?"],
            },
        ],
        use_cases=["churn prediction", "onboarding automation"],
        pricing=["per seat"],
        free_trial=True,
        soc2=True,
        founded="2024",
        case_studies=["customer story"],
        customers=["Beta"],
        value_statements=["reduce churn"],
        confidence="high",
    )

    merged = merge_vendor_intelligence(deterministic, llm_result)

    assert merged.vendor_name == "ExampleCorp"
    assert merged.website == "https://example.com"
    assert merged.mission == "AI customer success platform that reduces churn and automates onboarding."
    assert merged.usp == "Predict churn and speed time to value."
    assert merged.icp == ["SaaS companies", "customer success teams"]
    assert merged.icp_buyer == [
        {
            "persona": "VP Customer Success",
            "confidence": "high",
            "evidence": ["health scoring", "reduce churn"],
            "google_queries": [
                "health scoring software",
                "customer success software for reducing churn",
            ],
            "geo_queries": [
                "What software improves customer health scoring?",
                "What AI tools reduce churn for SaaS teams?",
            ],
        },
        {
            "persona": "Chief Customer Officer",
            "confidence": "medium",
            "evidence": ["onboarding automation"],
            "google_queries": ["customer success platform for enterprise saas"],
            "geo_queries": ["Which customer success vendors support the full lifecycle?"],
        },
    ]
    assert merged.use_cases == ["health scoring", "churn prediction", "onboarding automation"]
    assert merged.lifecycle_stages == ["Adopt"]
    assert merged.pricing == ["contact sales", "per seat"]
    assert merged.free_trial is True
    assert merged.soc2 is True
    assert merged.founded == "2024"
    assert merged.case_studies == ["case study", "customer story"]
    assert merged.customers == ["Acme", "Beta"]
    assert "reduce churn" in merged.value_statements
    assert merged.confidence == "high"
    assert merged.evidence_urls == ["https://example.com"]


def test_merge_vendor_intelligence_keeps_stronger_deterministic_signals():
    deterministic = VendorIntelligence(
        vendor_name="ExampleCorp",
        website="https://example.com",
        mission="Customer success platform for onboarding and renewals.",
        usp="Reduce churn for CS teams.",
        icp=["SaaS companies"],
        icp_buyer=[
            {
                "persona": "VP Customer Success",
                "confidence": "high",
                "evidence": ["renewals"],
                "google_queries": ["renewal forecasting software"],
                "geo_queries": ["What tools improve SaaS renewals?"],
            }
        ],
        use_cases=["renewal forecasting"],
        lifecycle_stages=["Renew"],
        pricing=["contact sales"],
        free_trial=True,
        soc2=True,
        founded="2020",
        case_studies=["case study"],
        customers=["Acme"],
        value_statements=["reduce churn"],
        confidence="medium",
        evidence_urls=["https://example.com"],
    )
    llm_result = LLMExtractionResult(
        is_cs_relevant=True,
        mission="Short summary.",
        usp="Short usp.",
        icp=["support teams"],
        icp_buyer=[
            {
                "persona": "Customer Support Leader",
                "confidence": "low",
                "evidence": ["support"],
                "google_queries": ["support tools"],
                "geo_queries": ["What support tools use AI?"],
            }
        ],
        use_cases=["onboarding automation"],
        pricing=["per seat"],
        free_trial=False,
        soc2=False,
        founded="",
        case_studies=["customer story"],
        customers=["Beta"],
        value_statements=["improve adoption"],
        confidence="low",
    )

    merged = merge_vendor_intelligence(deterministic, llm_result)

    assert merged.mission == deterministic.mission
    assert merged.usp == deterministic.usp
    assert merged.icp == ["SaaS companies", "support teams"]
    assert merged.icp_buyer == [
        {
            "persona": "VP Customer Success",
            "confidence": "high",
            "evidence": ["renewals"],
            "google_queries": ["renewal forecasting software"],
            "geo_queries": ["What tools improve SaaS renewals?"],
        },
        {
            "persona": "Customer Support Leader",
            "confidence": "low",
            "evidence": ["support"],
            "google_queries": ["support tools"],
            "geo_queries": ["What support tools use AI?"],
        },
    ]
    assert merged.use_cases == ["renewal forecasting", "onboarding automation"]
    assert merged.pricing == ["contact sales", "per seat"]
    assert merged.free_trial is True
    assert merged.soc2 is True
    assert merged.founded == "2020"
    assert merged.case_studies == ["case study", "customer story"]
    assert merged.customers == ["Acme", "Beta"]
    assert "improve adoption" in merged.value_statements
    assert merged.confidence == "medium"


def test_merge_vendor_intelligence_preserves_structured_case_studies_and_company_fields():
    deterministic = VendorIntelligence(
        vendor_name="ExampleCorp",
        website="https://example.com",
        ceo_name="Jane Doe",
        hq_address="Austin, Texas",
        phone_numbers=["+15125550100"],
        contact_emails=["sales@example.com"],
        company_hq="Austin, Texas",
        contact_email="sales@example.com",
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
        value_statements=["reduce churn"],
    )
    llm_result = LLMExtractionResult(
        is_cs_relevant=True,
        products=[
            {
                "name": "Journey Hub",
                "category": "platform",
                "description": "Guided onboarding",
                "source_url": "https://example.com/products/journey-hub",
            }
        ],
        leadership=[
            {
                "name": "Jane Doe",
                "title": "CEO",
                "source_url": "https://example.com/team",
            }
        ],
        hq_address="123 Congress Ave, Austin, Texas 78701",
        phone_numbers=["+1 (415) 555-0100"],
        contact_emails=["support@example.com"],
        integration_categories=["crm"],
        integrations=["Salesforce"],
        support_signals=["help center"],
        case_study_details=[
            {
                "client": "Beta",
                "title": "Beta case study",
                "use_case": "renewal management",
                "value_realized": "improved renewals",
                "source_url": "https://example.com/customers/beta",
            }
        ],
        value_statements=["improve onboarding"],
    )

    merged = merge_vendor_intelligence(deterministic, llm_result)

    assert merged.ceo_name == "Jane Doe"
    assert merged.hq_address == "123 Congress Ave, Austin, Texas 78701"
    assert merged.phone_numbers == ["+15125550100", "+14155550100"]
    assert merged.contact_emails == ["sales@example.com", "support@example.com"]
    assert merged.company_hq == "123 Congress Ave, Austin, Texas 78701"
    assert merged.contact_email == "sales@example.com"
    assert merged.products == [
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
    assert merged.leadership == [
        {
            "name": "Jane Doe",
            "title": "CEO",
            "source_url": "https://example.com/team",
        }
    ]
    assert merged.integration_categories == ["crm"]
    assert merged.integrations == ["Salesforce"]
    assert merged.support_signals == ["help center"]
    assert merged.case_study_details == [
        {
            "client": "Acme",
            "title": "Acme case study",
            "use_case": "onboarding",
            "value_realized": "reduced churn by 20%",
            "metric": "20%",
            "source_url": "https://example.com/customers/acme",
        },
        {
            "client": "Beta",
            "title": "Beta case study",
            "use_case": "renewal management",
            "value_realized": "improved renewals",
            "source_url": "https://example.com/customers/beta",
        },
    ]
    assert merged.value_statements == ["reduce churn", "improve onboarding"]
