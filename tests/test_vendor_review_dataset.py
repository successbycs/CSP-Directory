"""Tests for the slim vendor review dataset and HTML export."""

from pathlib import Path

from services.export import vendor_review_dataset
from services.extraction.vendor_intel import VendorIntelligence


def test_build_vendor_review_dataset_normalizes_and_sorts_rows(monkeypatch):
    monkeypatch.setattr(vendor_review_dataset.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        vendor_review_dataset.supabase_client,
        "list_vendor_profiles",
        lambda limit=500, client=None: [
            {
                "name": "Zeta",
                "website": "https://zeta.example.com",
                "source": "google_search",
                "mission": "Zeta helps teams reduce churn and improve adoption with AI guidance.",
                "products": [
                    {
                        "name": "Journey Hub",
                        "category": "platform",
                        "description": "Guided onboarding",
                    },
                    {
                        "name": "Renewal AI",
                        "category": "module",
                        "description": "Renewal forecasting",
                    },
                ],
                "icp_buyer": [
                    {
                        "persona": "VP Customer Success",
                        "confidence": "high",
                        "evidence": ["reduce churn"],
                        "google_queries": ["customer success software for reducing churn"],
                        "geo_queries": ["What AI tools reduce churn for SaaS teams?"],
                    }
                ],
                "use_cases": ["health scoring", "renewal management"],
                "pricing": "contact sales|per seat",
                "lifecycle_stages": ["Adopt", "Renew"],
                "integration_taxonomy": [
                    {"category": "crm", "integrations": ["Salesforce", "HubSpot"]},
                    {"category": "support", "integrations": ["Zendesk"]},
                ],
                "external_enrichment": [
                    {
                        "provider": "G2",
                        "source_id": "g2-zeta",
                        "source_type": "review_directory",
                        "status": "staged",
                        "source_url": "https://www.g2.com/products/zeta/reviews",
                        "captured_at": "2026-03-19T00:00:00Z",
                        "freshness_days": 14,
                        "fields": ["rating", "review_count"],
                        "notes": "Deferred review signal",
                    }
                ],
                "directory_category": "cs_core",
                "directory_fit": "high",
                "include_in_directory": True,
                "confidence": "high",
                "free_trial": "false",
                "soc2": True,
                "founded": "2022",
                "case_study_details": [
                    {
                        "client": "Acme",
                        "title": "Acme case study",
                        "use_case": "renewal management",
                        "value_realized": "reduced churn by 20%",
                        "metric": "20%",
                        "source_url": "https://zeta.example.com/customers/acme",
                    }
                ],
                "evidence_urls": ["https://zeta.example.com", "https://zeta.example.com/pricing"],
                "last_updated": "2026-03-17T00:00:00+00:00",
            },
            {
                "name": "Alpha",
                "website": "https://alpha.example.com",
                "source": "google_search",
                "mission": "Alpha onboarding platform",
                "use_cases": [],
                "pricing": [],
                "lifecycle_stages": ["Onboard"],
                "directory_category": "cs_core",
                "directory_fit": "medium",
                "include_in_directory": False,
                "confidence": "medium",
                "free_trial": True,
                "soc2": None,
                "founded": "",
                "evidence_urls": [],
                "last_updated": "2026-03-16T00:00:00+00:00",
            },
        ],
    )

    dataset = vendor_review_dataset.build_vendor_review_dataset()

    assert [item["vendor_name"] for item in dataset] == ["Alpha", "Zeta"]
    assert dataset[1]["icp_buyer_summary"] == "VP Customer Success"
    assert dataset[1]["product_count"] == 2
    assert dataset[1]["product_summary"] == "Journey Hub, Renewal AI"
    assert dataset[1]["integration_summary"] == "CRM: Salesforce, HubSpot; Support: Zendesk"
    assert dataset[1]["external_enrichment_summary"] == "G2 (review_directory, 14d freshness)"
    assert dataset[1]["pricing_summary"] == "contact sales, per seat"
    assert dataset[1]["case_study_count"] == 1
    assert dataset[1]["case_study_details"][0]["metric"] == "20%"
    assert dataset[1]["evidence_url_count"] == 2
    assert dataset[0]["include_in_directory"] is False


def test_build_vendor_review_dataset_falls_back_to_current_profiles_when_supabase_is_unavailable(monkeypatch):
    monkeypatch.setattr(vendor_review_dataset.supabase_client, "is_configured", lambda: False)

    dataset = vendor_review_dataset.build_vendor_review_dataset(
        fallback_profiles=[
            VendorIntelligence(
                vendor_name="Bravo",
                website="https://bravo.example.com",
                mission="Renewal automation for SaaS teams",
                products=[
                    {
                        "name": "Journey Hub",
                        "category": "platform",
                        "description": "Guided onboarding",
                        "use_cases": ["guided onboarding"],
                        "integration_categories": ["crm"],
                        "integrations": ["Salesforce"],
                        "demo_url": "https://bravo.example.com/demo/journey-hub",
                        "support_url": "",
                        "help_center_url": "",
                        "developer_docs_url": "",
                        "source_url": "https://bravo.example.com/products/journey-hub",
                    }
                ],
                icp_buyer=[
                    {
                        "persona": "VP Customer Success",
                        "confidence": "high",
                        "evidence": ["renewal automation"],
                        "google_queries": ["renewal management software"],
                        "geo_queries": ["Which tools improve SaaS renewals?"],
                    }
                ],
                use_cases=["renewal management", "churn prevention"],
                pricing=["contact sales"],
                lifecycle_stages=["Renew"],
                external_enrichment=[
                    {
                        "provider": "Product Hunt",
                        "source_id": "bravo-launch",
                        "source_type": "launch_directory",
                        "status": "deferred",
                        "source_url": "https://producthunt.com/posts/bravo",
                        "captured_at": "2026-03-18T00:00:00Z",
                        "freshness_days": 30,
                        "fields": ["launch_date", "tagline"],
                        "notes": "Launch evidence",
                    }
                ],
                directory_category="cs_core",
                directory_fit="high",
                include_in_directory=True,
                confidence="high",
                free_trial=True,
                soc2=True,
                founded="2024",
                case_study_details=[
                    {
                        "client": "Bravo Health",
                        "title": "Bravo Health case study",
                        "use_case": "renewal management",
                        "value_realized": "increased renewal rate by 18%",
                        "metric": "18%",
                        "source_url": "https://bravo.example.com/customers/bravo-health",
                    }
                ],
                evidence_urls=["https://bravo.example.com"],
            )
        ]
    )

    assert dataset == [
        {
            "vendor_name": "Bravo",
            "website": "https://bravo.example.com",
            "source": "",
            "mission_summary": "Renewal automation for SaaS teams",
            "products": [
                {
                    "name": "Journey Hub",
                    "category": "platform",
                    "description": "Guided onboarding",
                    "use_cases": ["guided onboarding"],
                    "integration_categories": ["crm"],
                    "integrations": ["Salesforce"],
                    "demo_url": "https://bravo.example.com/demo/journey-hub",
                    "support_url": "",
                    "help_center_url": "",
                    "developer_docs_url": "",
                    "source_url": "https://bravo.example.com/products/journey-hub",
                }
            ],
            "product_count": 1,
            "product_summary": "Journey Hub",
            "integration_taxonomy": [{"category": "crm", "integrations": ["Salesforce"]}],
            "integration_summary": "CRM: Salesforce",
            "external_enrichment": [
                {
                    "provider": "Product Hunt",
                    "source_id": "bravo-launch",
                    "source_type": "launch_directory",
                    "status": "deferred",
                    "source_url": "https://producthunt.com/posts/bravo",
                    "captured_at": "2026-03-18T00:00:00Z",
                    "freshness_days": 30,
                    "fields": ["launch_date", "tagline"],
                    "notes": "Launch evidence",
                }
            ],
            "external_enrichment_summary": "Product Hunt (launch_directory, 30d freshness)",
            "icp_buyer": [
                {
                    "persona": "VP Customer Success",
                    "confidence": "high",
                    "evidence": ["renewal automation"],
                    "google_queries": ["renewal management software"],
                    "geo_queries": ["Which tools improve SaaS renewals?"],
                }
            ],
            "icp_buyer_summary": "VP Customer Success",
            "use_case_summary": "renewal management, churn prevention",
            "pricing_summary": "contact sales",
            "lifecycle_stages": ["Renew"],
            "directory_category": "cs_core",
            "directory_fit": "high",
            "include_in_directory": True,
            "auto_directory_category": "",
            "auto_directory_fit": "",
            "auto_include_in_directory": None,
            "directory_decision_source": "auto",
            "directory_reasoning": [],
            "confidence": "high",
            "free_trial": True,
            "soc2": True,
            "founded": "2024",
            "case_study_details": [
                {
                    "client": "Bravo Health",
                    "title": "Bravo Health case study",
                    "use_case": "renewal management",
                    "value_realized": "increased renewal rate by 18%",
                    "metric": "18%",
                    "source_url": "https://bravo.example.com/customers/bravo-health",
                }
            ],
            "case_study_count": 1,
            "evidence_url_count": 1,
            "last_updated": "",
        }
    ]


def test_write_vendor_review_html_renders_external_enrichment_summary(tmp_path: Path):
    output_path = tmp_path / "vendor_review.html"

    vendor_review_dataset.write_vendor_review_html(
        [
            {
                "vendor_name": "Alpha",
                "website": "https://alpha.example.com",
                "mission_summary": "Alpha onboarding platform",
                "products": [],
                "product_count": 0,
                "product_summary": "",
                "integration_taxonomy": [],
                "integration_summary": "",
                "external_enrichment": [],
                "external_enrichment_summary": "G2 (review_directory, 14d freshness)",
                "icp_buyer": [],
                "icp_buyer_summary": "",
                "use_case_summary": "",
                "pricing_summary": "",
                "lifecycle_stages": [],
                "directory_category": "cs_core",
                "directory_fit": "high",
                "include_in_directory": True,
                "auto_directory_category": "",
                "auto_directory_fit": "",
                "auto_include_in_directory": None,
                "directory_decision_source": "auto",
                "directory_reasoning": [],
                "confidence": "high",
                "free_trial": None,
                "soc2": None,
                "founded": "",
                "case_study_details": [],
                "case_study_count": 0,
                "evidence_url_count": 0,
                "last_updated": "",
            }
        ],
        output_path,
    )

    html = output_path.read_text(encoding="utf-8")
    assert "External enrichment:" in html
    assert "G2 (review_directory, 14d freshness)" in html


def test_export_vendor_review_artifacts_writes_json_and_html(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        vendor_review_dataset,
        "build_vendor_review_dataset",
        lambda client=None, fallback_profiles=None, prefer_fallback_profiles=False: [
            {
                "vendor_name": "Alpha",
                "website": "https://alpha.example.com",
                "source": "google_search",
                "mission_summary": "Alpha onboarding platform",
                "products": [{"name": "Alpha Core"}],
                "product_count": 1,
                "product_summary": "Alpha Core",
                "use_case_summary": "onboarding",
                "pricing_summary": "contact sales",
                "lifecycle_stages": ["Onboard"],
                "directory_category": "cs_core",
                "directory_fit": "high",
                "include_in_directory": True,
                "confidence": "high",
                "free_trial": True,
                "soc2": False,
                "founded": "2023",
                "case_study_details": [
                    {
                        "client": "Acme",
                        "title": "Acme case study",
                        "use_case": "onboarding",
                        "value_realized": "cut time-to-value by 30 days",
                        "metric": "30 days",
                        "source_url": "https://alpha.example.com/customers/acme",
                    }
                ],
                "case_study_count": 1,
                "evidence_url_count": 2,
                "last_updated": "2026-03-17T00:00:00+00:00",
            }
        ],
    )

    dataset_path = tmp_path / "vendor_review_dataset.json"
    html_path = tmp_path / "vendor_review.html"
    dataset = vendor_review_dataset.export_vendor_review_artifacts(
        dataset_output_path=dataset_path,
        html_output_path=html_path,
    )

    assert dataset[0]["vendor_name"] == "Alpha"
    assert dataset_path.exists()
    assert html_path.exists()
    assert '"vendor_name": "Alpha"' in dataset_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    assert "Vendor review report" in html
    assert "Alpha" in html
    assert "Acme" in html


def test_build_vendor_review_dataset_prefers_fallback_profiles_when_requested(monkeypatch):
    monkeypatch.setattr(vendor_review_dataset.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        vendor_review_dataset.supabase_client,
        "list_vendor_profiles",
        lambda limit=500, client=None: (_ for _ in ()).throw(RuntimeError("supabase unavailable")),
    )

    dataset = vendor_review_dataset.build_vendor_review_dataset(
        fallback_profiles=[
            VendorIntelligence(
                vendor_name="Fallback",
                website="https://fallback.example.com",
                mission="Fallback mission",
                include_in_directory=True,
                confidence="high",
            )
        ],
        prefer_fallback_profiles=True,
    )

    assert dataset[0]["vendor_name"] == "Fallback"
