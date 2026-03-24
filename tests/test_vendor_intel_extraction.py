"""Tests for deterministic vendor intelligence extraction."""

from services.extraction.vendor_intel import extract_vendor_intelligence


def test_extract_vendor_intelligence_populates_directory_fields_from_explored_pages():
    explored_pages = {
        "homepage": {
            "vendor_name": "ExampleCorp",
            "website": "https://example.com",
            "source": "google_search",
            "text": (
                "ExampleCorp helps customer success teams at SaaS companies reduce churn and improve adoption. "
                "Our customer success platform offers conversational intelligence, onboarding automation, "
                "implementation portals, health scoring, usage analytics, support automation, ticket triage, "
                "renewal automation, voice of customer programs, and stakeholder mapping. Founded in 2021."
            ),
        },
        "pricing_page": {
            "vendor_name": "",
            "website": "https://example.com/pricing",
            "text": "Plans start at $99 per user per month. Start free with a free trial or contact sales.",
        },
        "case_studies_page": {
            "vendor_name": "",
            "website": "https://example.com/customers",
            "text": "Customer stories and case studies show how Acme uses ExampleCorp.",
        },
        "security_page": {
            "vendor_name": "",
            "website": "https://example.com/security",
            "text": "SOC 2 compliant and ISO 27001 certified.",
        },
    }

    result = extract_vendor_intelligence(explored_pages)

    assert result.vendor_name == "ExampleCorp"
    assert result.website == "https://example.com"
    assert result.source == "google_search"
    assert result.mission.startswith("ExampleCorp helps customer success teams")
    assert result.usp == "reduce churn"
    assert result.icp == ["SaaS companies", "customer success teams"]
    assert result.use_cases == [
        "meeting intelligence",
        "onboarding",
        "health scoring",
        "usage analytics",
        "support automation",
        "ticket triage",
        "stakeholder mapping",
        "renewal management",
        "churn prevention",
        "voice of customer",
        "customer advocacy",
    ]
    assert result.lifecycle_stages == ["Sign", "Onboard", "Adopt", "Support", "Expand", "Renew", "Advocate"]
    assert result.pricing == ["$", "per user", "per month", "contact sales"]
    assert result.free_trial is True
    assert result.soc2 is True
    assert result.founded == "2021"
    assert result.case_studies == ["case study", "customer story", "how customers use the product"]
    assert result.customers == ["Acme"]
    assert result.value_statements == [
        "reduce churn",
        "improve adoption",
        "improve customer health",
        "reduce support workload",
        "automate onboarding",
        "increase retention",
        "improve renewal forecasting",
        "strengthen customer advocacy",
    ]
    assert result.confidence == "high"
    assert result.evidence_urls == [
        "https://example.com",
        "https://example.com/pricing",
        "https://example.com/customers",
        "https://example.com/security",
    ]


def test_extract_vendor_intelligence_returns_empty_lists_when_no_keywords_match():
    homepage_payload = {
        "vendor_name": "ExampleCorp",
        "website": "https://example.com",
        "text": "Customer platform for modern teams.",
    }

    result = extract_vendor_intelligence(homepage_payload)

    assert result.icp == []
    assert result.use_cases == []
    assert result.value_statements == []
    assert result.lifecycle_stages == []
    assert result.pricing == []
    assert result.case_studies == []
    assert result.customers == []
    assert result.confidence == "low"


def test_extract_vendor_intelligence_strips_navigation_boilerplate_from_mission():
    homepage_payload = {
        "vendor_name": "Hyperengage",
        "website": "https://hyperengage.io",
        "text": (
            "Skip to content Book a Demo Sign In "
            "The GTM Intelligence layer for post-sales Hyperengage unifies CRM, product usage, and customer comms into one model. "
            "Trigger the right signals, answer hard questions with your copilot."
        ),
    }

    result = extract_vendor_intelligence(homepage_payload)

    assert result.mission == (
        "The GTM Intelligence layer for post-sales Hyperengage unifies CRM, product usage, and customer comms into one model."
    )


def test_extract_vendor_intelligence_maps_onboarding_signals_to_onboard():
    homepage_payload = {
        "vendor_name": "OnboardAI",
        "website": "https://onboard.example.com",
        "text": "Implementation portals and onboarding automation help teams speed time to value.",
    }

    result = extract_vendor_intelligence(homepage_payload)

    assert result.lifecycle_stages == ["Onboard"]


def test_extract_vendor_intelligence_maps_health_and_usage_signals_to_adopt():
    homepage_payload = {
        "vendor_name": "AdoptAI",
        "website": "https://adopt.example.com",
        "text": "Health scoring, customer health dashboards, and usage analytics drive playbook automation.",
    }

    result = extract_vendor_intelligence(homepage_payload)

    assert result.lifecycle_stages == ["Adopt"]


def test_extract_vendor_intelligence_maps_support_signals_to_support():
    homepage_payload = {
        "vendor_name": "SupportAI",
        "website": "https://support.example.com",
        "text": "Support automation, ticket triage, agent assist, and knowledge base workflows reduce support workload.",
    }

    result = extract_vendor_intelligence(homepage_payload)

    assert result.lifecycle_stages == ["Support"]


def test_extract_vendor_intelligence_maps_churn_and_renewal_signals_to_renew():
    homepage_payload = {
        "vendor_name": "RenewAI",
        "website": "https://renew.example.com",
        "text": "Churn prediction, renewal automation, and risk alerts improve forecasting for renewals.",
    }

    result = extract_vendor_intelligence(homepage_payload)

    assert result.lifecycle_stages == ["Renew"]


def test_extract_vendor_intelligence_maps_advocacy_signals_to_advocate():
    homepage_payload = {
        "vendor_name": "AdvocateAI",
        "website": "https://advocate.example.com",
        "text": "NPS, voice of customer programs, reference management, and case studies power advocacy.",
    }

    result = extract_vendor_intelligence(homepage_payload)

    assert result.lifecycle_stages == ["Advocate"]


def test_extract_vendor_intelligence_detects_icp_pricing_soc2_and_case_study_signals():
    explored_pages = {
        "homepage": {
            "vendor_name": "SignalsAI",
            "website": "https://signals.example.com",
            "text": "Built for B2B startups and product-led teams.",
        },
        "pricing_page": {
            "vendor_name": "",
            "website": "https://signals.example.com/pricing",
            "text": "$49 per seat per month.",
        },
        "case_studies_page": {
            "vendor_name": "",
            "website": "https://signals.example.com/customers",
            "text": "Customer stories and case studies.",
        },
        "security_page": {
            "vendor_name": "",
            "website": "https://signals.example.com/security",
            "text": "SOC2 ready.",
        },
    }

    result = extract_vendor_intelligence(explored_pages)

    assert result.icp == ["B2B startups", "product-led teams"]
    assert result.pricing == ["$", "per seat", "per month"]
    assert result.soc2 is True
    assert result.case_studies == ["case study", "customer story"]


def test_extract_vendor_intelligence_uses_extra_pages_in_combined_text():
    explored_pages = {
        "homepage": {
            "vendor_name": "SignalsAI",
            "website": "https://signals.example.com",
            "text": "Built for customer success teams.",
        },
        "extra_pages": [
            {
                "website": "https://signals.example.com/ai-copilot",
                "url": "https://signals.example.com/ai-copilot",
                "text": "AI copilot supports onboarding automation and health scoring.",
            }
        ],
    }

    result = extract_vendor_intelligence(explored_pages)

    assert result.use_cases == ["onboarding", "health scoring"]
    assert result.evidence_urls == [
        "https://signals.example.com",
        "https://signals.example.com/ai-copilot",
    ]


def test_extract_vendor_intelligence_supports_multiple_exact_lifecycle_stages():
    homepage_payload = {
        "vendor_name": "LifecycleAI",
        "website": "https://lifecycle.example.com",
        "text": (
            "Conversational intelligence and meeting summaries improve sales-to-cs handoff. "
            "Our onboarding automation and time-to-value tooling support implementation teams. "
            "In-app guidance and product walkthroughs boost activation. "
            "Usage analytics and health scoring help customer health teams. "
            "Support automation and ticket triage reduce support workload. "
            "Stakeholder mapping drives expansion revenue. "
            "Churn prediction and risk alerts improve renewals. "
            "NPS and voice of customer programs help advocacy."
        ),
    }

    result = extract_vendor_intelligence(homepage_payload)

    assert result.lifecycle_stages == [
        "Sign",
        "Onboard",
        "Activate",
        "Adopt",
        "Support",
        "Expand",
        "Renew",
        "Advocate",
    ]


def test_extract_vendor_intelligence_captures_richer_company_contact_and_case_study_fields():
    explored_pages = {
        "homepage": {
            "vendor_name": "ExampleCorp",
            "website": "https://www.example.com/",
            "text": (
                "ExampleCorp helps customer success teams improve adoption. "
                "Products include Journey Hub and Renewal AI."
            ),
        },
        "about_page": {
            "website": "https://www.example.com/about/",
            "text": (
                "ExampleCorp is headquartered in Austin, Texas. "
                "Founded by Jane Doe. Jane Doe, CEO, leads the company."
            ),
        },
        "team_page": {
            "website": "https://www.example.com/team/",
            "text": "Leadership team: Jane Doe, CEO.",
        },
        "contact_page": {
            "website": "https://www.example.com/contact/",
            "text": (
                "Email us at Sales@Example.com or Support@Example.com for more details. "
                "Call +1 (512) 555-0100 for sales."
            ),
        },
        "demo_page": {
            "website": "https://www.example.com/demo/",
            "text": "Book a demo today.",
        },
        "help_page": {
            "website": "https://www.example.com/help/",
            "text": "Browse our help center and knowledge base.",
        },
        "support_page": {
            "website": "https://www.example.com/support/",
            "text": "Customer support portal and training academy.",
        },
        "developer_docs_page": {
            "website": "https://www.example.com/docs/",
            "text": "Developer docs and API reference.",
        },
        "integrations_page": {
            "website": "https://www.example.com/integrations/",
            "text": "Integrations with Salesforce, Slack, and Zendesk.",
        },
        "case_studies_page": {
            "website": "https://www.example.com/customers/acme/",
            "text": "Acme used ExampleCorp to reduce churn by 20% and improve onboarding.",
        },
    }

    result = extract_vendor_intelligence(explored_pages)

    assert result.website == "https://example.com"
    assert result.products == [
        {
            "name": "Journey Hub",
            "category": "platform",
            "description": "ExampleCorp helps customer success teams improve adoption. Products include Journey Hub and Renewal AI.",
            "use_cases": [],
            "integration_categories": [],
            "integrations": [],
            "demo_url": "",
            "support_url": "",
            "help_center_url": "",
            "developer_docs_url": "",
            "source_url": "https://example.com",
        },
        {
            "name": "Renewal AI",
            "category": "platform",
            "description": "ExampleCorp helps customer success teams improve adoption. Products include Journey Hub and Renewal AI.",
            "use_cases": [],
            "integration_categories": [],
            "integrations": [],
            "demo_url": "",
            "support_url": "",
            "help_center_url": "",
            "developer_docs_url": "",
            "source_url": "https://example.com",
        },
    ]
    assert result.leadership == [
        {
            "name": "Jane Doe",
            "title": "CEO",
            "source_url": "https://example.com/team",
        },
        {
            "name": "Jane Doe",
            "title": "Founder",
            "source_url": "https://example.com/team",
        },
    ]
    assert result.ceo_name == "Jane Doe"
    assert result.hq_address == "Austin, Texas"
    assert result.phone_numbers == ["+15125550100"]
    assert result.contact_emails == ["sales@example.com", "support@example.com"]
    assert result.company_hq == "Austin, Texas"
    assert result.contact_email == "sales@example.com"
    assert result.contact_page_url == "https://example.com/contact"
    assert result.demo_url == "https://example.com/demo"
    assert result.help_center_url == "https://example.com/help"
    assert result.support_url == "https://example.com/support"
    assert result.about_url == "https://example.com/about"
    assert result.team_url == "https://example.com/team"
    assert result.developer_docs_url == "https://example.com/docs"
    assert result.integration_categories == ["crm", "communication", "support"]
    assert result.integrations == ["Salesforce", "Slack", "Zendesk"]
    assert result.integration_taxonomy == [
        {"category": "crm", "integrations": ["Salesforce"]},
        {"category": "communication", "integrations": ["Slack"]},
        {"category": "support", "integrations": ["Zendesk"]},
    ]
    assert result.support_signals == ["help center", "knowledge base", "support portal", "training"]
    assert result.case_study_details == [
        {
            "client": "Acme",
            "title": "Acme case study",
            "use_case": "churn prevention",
            "value_realized": "reduce churn by 20% and improve onboarding",
            "metric": "20%",
            "source_url": "https://example.com/customers/acme",
        }
    ]
    assert "reduce churn" in result.value_statements


def test_extract_vendor_intelligence_groups_raw_integrations_into_normalized_taxonomy():
    explored_pages = {
        "homepage": {
            "vendor_name": "IntegrateAI",
            "website": "https://integrate.example.com",
            "text": "IntegrateAI helps customer success teams orchestrate handoffs.",
        },
        "integrations_page": {
            "website": "https://integrate.example.com/integrations",
            "text": (
                "Native integrations include Gainsight, HubSpot, Jira, Zapier, Gmail, "
                "Snowflake, and Acme Data Cloud."
            ),
        },
    }

    result = extract_vendor_intelligence(explored_pages)

    assert result.integration_categories == ["crm", "csp", "pm", "workflow", "email/calendar", "warehouse", "other"]
    assert result.integrations == [
        "HubSpot",
        "Gainsight",
        "Jira",
        "Zapier",
        "Gmail",
        "Snowflake",
        "Acme Data Cloud",
    ]
    assert result.integration_taxonomy == [
        {"category": "crm", "integrations": ["HubSpot"]},
        {"category": "csp", "integrations": ["Gainsight"]},
        {"category": "pm", "integrations": ["Jira"]},
        {"category": "workflow", "integrations": ["Zapier"]},
        {"category": "email/calendar", "integrations": ["Gmail"]},
        {"category": "warehouse", "integrations": ["Snowflake"]},
        {"category": "other", "integrations": ["Acme Data Cloud"]},
    ]


def test_extract_vendor_intelligence_caps_confidence_when_cs_relevance_is_weak():
    explored_pages = {
        "homepage": {
            "vendor_name": "GenericTool",
            "website": "https://generic.example.com",
            "text": "Trusted by modern teams with customer stories and pricing available.",
        },
        "pricing_page": {
            "vendor_name": "",
            "website": "https://generic.example.com/pricing",
            "text": "$99 per user per month.",
        },
        "case_studies_page": {
            "vendor_name": "",
            "website": "https://generic.example.com/customers",
            "text": "Customer stories and case studies.",
        },
    }

    result = extract_vendor_intelligence(explored_pages)

    assert result.pricing == ["$", "per user", "per month"]
    assert result.case_studies == ["case study", "customer story"]
    assert result.confidence == "low"
