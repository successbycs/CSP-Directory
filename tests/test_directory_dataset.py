"""Tests for public directory dataset export."""

from pathlib import Path

from services.export import directory_dataset
from services.extraction.vendor_intel import VendorIntelligence


def test_build_directory_dataset_normalizes_and_sorts_rows(monkeypatch):
    monkeypatch.setattr(directory_dataset.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        directory_dataset.supabase_client,
        "list_directory_vendors",
        lambda client=None: [
            {
                "name": "Zeta",
                "website": "https://zeta.example.com",
                "mission": None,
                "usp": "Reduce churn",
                "icp": "SaaS companies|Mid-market",
                "icp_buyer": [
                    {
                        "persona": "VP Customer Success",
                        "confidence": "high",
                        "evidence": ["reduce churn"],
                        "google_queries": ["customer success software for reducing churn"],
                        "geo_queries": ["What AI tools reduce churn for SaaS teams?"],
                    }
                ],
                "use_cases": ["renewal management"],
                "lifecycle_stages": ["Renew"],
                "pricing": "contact sales|per seat",
                "free_trial": "false",
                "soc2": True,
                "founded": "2021",
                "case_studies": [],
                "customers": "Acme,Beta",
                "value_statements": ["reduce churn"],
                "confidence": "high",
                "evidence_urls": "https://zeta.example.com|https://zeta.example.com/pricing",
                "directory_fit": "high",
                "directory_category": "cs_core",
            },
            {
                "name": "Alpha",
                "website": "https://alpha.example.com",
                "mission": "Onboarding platform",
                "usp": "",
                "icp": [],
                "use_cases": [],
                "lifecycle_stages": ["Onboard"],
                "pricing": [],
                "free_trial": True,
                "soc2": None,
                "founded": "",
                "case_studies": [],
                "customers": [],
                "value_statements": [],
                "confidence": "medium",
                "evidence_urls": [],
                "directory_fit": "medium",
                "directory_category": "cs_core",
            },
        ],
    )

    dataset = directory_dataset.build_directory_dataset()

    assert [item["vendor_name"] for item in dataset] == ["Alpha", "Zeta"]
    assert dataset[1]["icp_buyer"][0]["persona"] == "VP Customer Success"
    assert dataset[1]["pricing"] == ["contact sales", "per seat"]
    assert dataset[1]["customers"] == ["Acme", "Beta"]
    assert dataset[1]["free_trial"] is False


def test_export_directory_dataset_writes_json_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        directory_dataset,
        "build_directory_dataset",
        lambda client=None, fallback_profiles=None, prefer_fallback_profiles=False: [
            {"vendor_name": "Alpha", "website": "https://alpha.example.com"}
        ],
    )

    output_path = tmp_path / "directory_dataset.json"
    directory_dataset.export_directory_dataset(output_path=output_path)

    assert output_path.exists()
    assert '"vendor_name": "Alpha"' in output_path.read_text(encoding="utf-8")


def test_build_directory_dataset_falls_back_to_current_profiles_when_supabase_is_unavailable(monkeypatch):
    monkeypatch.setattr(directory_dataset.supabase_client, "is_configured", lambda: False)

    dataset = directory_dataset.build_directory_dataset(
        fallback_profiles=[
            VendorIntelligence(
                vendor_name="Bravo",
                website="https://bravo.example.com",
                mission="Renewal automation",
                icp_buyer=[
                    {
                        "persona": "VP Customer Success",
                        "confidence": "high",
                        "evidence": ["renewal automation"],
                        "google_queries": ["renewal management software"],
                        "geo_queries": ["Which tools improve SaaS renewals?"],
                    }
                ],
                include_in_directory=True,
                directory_fit="high",
                directory_category="cs_core",
            )
        ]
    )

    assert dataset == [
        {
            "vendor_name": "Bravo",
            "website": "https://bravo.example.com",
            "mission": "Renewal automation",
            "usp": "",
            "icp": [],
            "icp_buyer": [
                {
                    "persona": "VP Customer Success",
                    "confidence": "high",
                    "evidence": ["renewal automation"],
                    "google_queries": ["renewal management software"],
                    "geo_queries": ["Which tools improve SaaS renewals?"],
                }
            ],
            "use_cases": [],
            "lifecycle_stages": [],
            "pricing": [],
            "free_trial": None,
            "soc2": None,
            "founded": "",
            "case_studies": [],
            "customers": [],
            "value_statements": [],
            "confidence": "",
            "evidence_urls": [],
            "directory_fit": "high",
            "directory_category": "cs_core",
        }
    ]


def test_build_directory_dataset_prefers_fallback_profiles_when_requested(monkeypatch):
    monkeypatch.setattr(directory_dataset.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        directory_dataset.supabase_client,
        "list_directory_vendors",
        lambda client=None: (_ for _ in ()).throw(RuntimeError("supabase unavailable")),
    )

    dataset = directory_dataset.build_directory_dataset(
        fallback_profiles=[
            VendorIntelligence(
                vendor_name="Fallback",
                website="https://fallback.example.com",
                mission="Fallback mission",
                include_in_directory=True,
                directory_fit="high",
                directory_category="cs_core",
            )
        ],
        prefer_fallback_profiles=True,
    )

    assert dataset[0]["vendor_name"] == "Fallback"
