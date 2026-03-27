"""Tests for optional LLM extraction."""

from __future__ import annotations

import requests

from services.extraction import llm_extractor


class FakeResponse:
    def __init__(self, payload: dict, *, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"status={self.status_code}")
            error.response = self
            raise error

    def json(self) -> dict:
        return self._payload


def test_extract_vendor_intelligence_returns_none_without_openai_config(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = llm_extractor.extract_vendor_intelligence(
        {"homepage": {"website": "https://example.com", "text": "Example vendor homepage"}}
    )

    assert result is None


def test_log_runtime_configuration_logs_once(monkeypatch, caplog):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr(llm_extractor, "_runtime_config_logged_for_run", False)
    caplog.set_level("INFO")

    llm_extractor.log_runtime_configuration()
    llm_extractor.log_runtime_configuration()

    assert caplog.text.count("OpenAI LLM extraction config: enabled=False") == 1
    assert llm_extractor.OPENAI_API_URL in caplog.text
    assert llm_extractor.DEFAULT_OPENAI_MODEL in caplog.text
    assert "missing=OPENAI_API_KEY" in caplog.text


def test_get_configured_model_falls_back_when_env_is_blank(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "   ")

    assert llm_extractor.get_configured_model() == llm_extractor.DEFAULT_OPENAI_MODEL


def test_start_pipeline_run_resets_llm_runtime_state(monkeypatch):
    monkeypatch.setattr(llm_extractor, "_llm_is_disabled_for_run", True)
    monkeypatch.setattr(llm_extractor, "_runtime_config_logged_for_run", True)

    llm_extractor.start_pipeline_run()

    assert llm_extractor._llm_is_disabled_for_run is False
    assert llm_extractor._runtime_config_logged_for_run is False


def test_extract_vendor_intelligence_parses_structured_json(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured_request = {}

    def fake_post(url: str, *, headers: dict, json: dict, timeout: int):
        captured_request["url"] = url
        captured_request["headers"] = headers
        captured_request["json"] = json
        captured_request["timeout"] = timeout
        return FakeResponse(
            {
                "output_text": (
                    '{"is_cs_relevant": true, "mission": "Reduce churn for customer success teams.", '
                    '"usp": "Predict churn before it happens.", '
                    '"icp": ["SaaS companies", "customer success teams"], '
                    '"icp_buyer": [{"persona": "VP Customer Success", "confidence": "high", '
                    '"evidence": ["reduce churn", "health scoring"], '
                    '"google_queries": ["customer success software for reducing churn"], '
                    '"geo_queries": ["What AI tools reduce churn for SaaS teams?"]}], '
                    '"use_cases": ["churn prediction", "renewal forecasting"], '
                    '"pricing": ["contact sales", "per seat"], '
                    '"free_trial": false, "soc2": true, "founded": "2022", '
                    '"products": [{"name": "Journey Hub", "category": "platform", "description": "Guided onboarding", "use_cases": ["onboarding"], "integration_categories": ["crm"], "integrations": ["Salesforce"], "demo_url": "https://example.com/demo/journey-hub", "support_url": "https://example.com/support/journey-hub", "help_center_url": "https://example.com/help/journey-hub", "developer_docs_url": "https://example.com/docs/journey-hub", "source_url": "https://example.com/product"}], '
                    '"leadership": [{"name": "Jane Doe", "title": "CEO", "source_url": "https://example.com/team"}], '
                    '"ceo_name": "Jane Doe", "hq_address": "Austin, Texas", '
                    '"phone_numbers": ["+1 (512) 555-0100"], "contact_emails": ["sales@example.com", "support@example.com"], '
                    '"company_hq": "Austin, Texas", "contact_email": "sales@example.com", '
                    '"developer_docs_url": "https://example.com/docs", '
                    '"integration_categories": ["crm"], "integrations": ["Salesforce"], "support_signals": ["help center"], '
                    '"case_studies": ["case study"], '
                    '"case_study_details": [{"client": "Acme", "title": "Acme case study", "use_case": "renewal management", "value_realized": "reduced churn by 20%", "source_url": "https://example.com/customers/acme"}], '
                    '"customers": ["Acme"], '
                    '"value_statements": ["reduce churn"], "confidence": "high"}'
                )
            }
        )

    result = llm_extractor.extract_vendor_intelligence(
        {
            "homepage": {
                "website": "https://example.com",
                "text": "Homepage text about customer success AI.",
            },
            "pricing_page": {
                "website": "https://example.com/pricing",
                "text": "Pricing text.",
            },
        },
        request_post=fake_post,
    )

    assert result is not None
    assert captured_request["url"] == llm_extractor.OPENAI_API_URL
    assert captured_request["timeout"] == 45
    assert "temperature" not in captured_request["json"]
    assert captured_request["json"]["input"][1]["content"][0]["text"].startswith("Review this crawled website evidence")
    assert captured_request["json"]["text"]["format"]["type"] == "json_schema"
    assert result.is_cs_relevant is True
    assert result.mission == "Reduce churn for customer success teams."
    assert result.usp == "Predict churn before it happens."
    assert result.icp == ["SaaS companies", "customer success teams"]
    assert result.icp_buyer == [
        {
            "persona": "VP Customer Success",
            "confidence": "high",
            "evidence": ["reduce churn", "health scoring"],
            "google_queries": ["customer success software for reducing churn"],
            "geo_queries": ["What AI tools reduce churn for SaaS teams?"],
        }
    ]
    assert result.use_cases == ["churn prediction", "renewal forecasting"]
    assert result.pricing == ["contact sales", "per seat"]
    assert result.free_trial is False
    assert result.soc2 is True
    assert result.founded == "2022"
    assert result.products == [
        {
            "name": "Journey Hub",
            "category": "platform",
            "description": "Guided onboarding",
            "use_cases": ["onboarding"],
            "integration_categories": ["crm"],
            "integrations": ["Salesforce"],
            "demo_url": "https://example.com/demo/journey-hub",
            "support_url": "https://example.com/support/journey-hub",
            "help_center_url": "https://example.com/help/journey-hub",
            "developer_docs_url": "https://example.com/docs/journey-hub",
            "source_url": "https://example.com/product",
        }
    ]
    assert result.leadership == [
        {
            "name": "Jane Doe",
            "title": "CEO",
            "linkedin": "",
            "source_url": "https://example.com/team",
        }
    ]
    assert result.ceo_name == "Jane Doe"
    assert result.hq_address == "Austin, Texas"
    assert result.phone_numbers == ["+15125550100"]
    assert result.contact_emails == ["sales@example.com", "support@example.com"]
    assert result.company_hq == "Austin, Texas"
    assert result.contact_email == "sales@example.com"
    assert result.developer_docs_url == "https://example.com/docs"
    assert result.integration_categories == ["crm"]
    assert result.integrations == ["Salesforce"]
    assert result.support_signals == ["help center"]
    assert result.case_study_signals == ["case study"]  # LLM returns signals mapped to case_study_signals
    assert result.case_study_details == [
        {
            "client": "Acme",
            "title": "Acme case study",
            "use_case": "renewal management",
            "value_realized": "reduced churn by 20%",
            "metric": "20%",
            "source_url": "https://example.com/customers/acme",
        }
    ]
    assert result.customers == ["Acme"]
    assert result.value_statements == ["reduce churn"]
    assert result.confidence == "high"


def test_extract_vendor_intelligence_returns_none_when_json_is_invalid(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    result = llm_extractor.extract_vendor_intelligence(
        {"homepage": {"website": "https://example.com", "text": "Example vendor homepage"}},
        request_post=lambda *args, **kwargs: FakeResponse({"output_text": "not-json"}),
    )

    assert result is None


def test_extract_vendor_intelligence_returns_none_when_structured_output_is_missing(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    result = llm_extractor.extract_vendor_intelligence(
        {"homepage": {"website": "https://example.com", "text": "Example vendor homepage"}},
        request_post=lambda *args, **kwargs: FakeResponse({"output": [{"content": [{"type": "refusal"}]}]}),
    )

    assert result is None


def test_extract_vendor_intelligence_parses_nested_output_text(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    result = llm_extractor.extract_vendor_intelligence(
        {"homepage": {"website": "https://example.com", "text": "Customer success AI platform"}},
        request_post=lambda *args, **kwargs: FakeResponse(
            {
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                '{"is_cs_relevant": true, "mission": "Improve adoption.", '
                                '"usp": "Lifecycle intelligence.", '
                                '"icp": ["customer success teams"], '
                                '"icp_buyer": [{"persona": "Head of Customer Success", "confidence": "medium", '
                                '"evidence": ["improve adoption"], '
                                '"google_queries": ["customer adoption software"], '
                                '"geo_queries": ["What tools improve product adoption?"]}], '
                                '"use_cases": ["onboarding"], "pricing": ["contact sales"], '
                                '"free_trial": null, "soc2": true, "founded": "2021", '
                                '"case_studies": [], "customers": [], "value_statements": [], '
                                    '"confidence": "medium"}'
                                ),
                            }
                        ]
                    }
                ]
            }
        ),
    )

    assert result is not None
    assert result.mission == "Improve adoption."
    assert result.icp == ["customer success teams"]
    assert result.icp_buyer[0]["persona"] == "Head of Customer Success"
    assert result.confidence == "medium"


def test_extract_vendor_intelligence_disables_llm_after_first_client_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm_extractor, "_llm_is_disabled_for_run", False)
    call_count = {"count": 0}

    def fake_post(*args, **kwargs):
        call_count["count"] += 1
        return FakeResponse(
            {"error": {"message": "bad request"}},
            status_code=400,
            text='{"error":{"message":"bad request"}}',
        )

    first_result = llm_extractor.extract_vendor_intelligence(
        {"homepage": {"website": "https://example.com", "text": "Customer success software"}},
        request_post=fake_post,
    )
    second_result = llm_extractor.extract_vendor_intelligence(
        {"homepage": {"website": "https://example.com", "text": "Customer success software"}},
        request_post=fake_post,
    )

    assert first_result is None
    assert second_result is None
    assert call_count["count"] == 1


def test_extract_vendor_intelligence_normalizes_list_fields(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    result = llm_extractor.extract_vendor_intelligence(
        {"homepage": {"website": "https://example.com", "text": "Customer success pricing page"}},
        request_post=lambda *args, **kwargs: FakeResponse(
            {
                "output_text": (
                    '{"is_cs_relevant": true, "mission": "", "usp": "", '
                    '"icp": "SaaS companies|Mid-market", '
                    '"icp_buyer": [{"persona": "VP Customer Success", "confidence": "high", '
                    '"evidence": "reduce churn|renewals", '
                    '"google_queries": "query 1|query 2|query 3|query 4|query 5|query 6", '
                    '"geo_queries": ["prompt 1", "prompt 2"]}], '
                    '"use_cases": "onboarding,health scoring", '
                    '"pricing": ["contact sales", "annual pricing"], '
                    '"free_trial": null, "soc2": null, "founded": "", '
                    '"case_studies": "case study|customer story", '
                    '"customers": "Acme, Beta", '
                    '"value_statements": "reduce churn|improve adoption", '
                    '"confidence": "medium"}'
                )
            }
        ),
    )

    assert result is not None
    assert result.icp == ["SaaS companies", "Mid-market"]
    assert result.icp_buyer == [
        {
            "persona": "VP Customer Success",
            "confidence": "high",
            "evidence": ["reduce churn", "renewals"],
            "google_queries": ["query 1", "query 2", "query 3", "query 4", "query 5"],
            "geo_queries": ["prompt 1", "prompt 2"],
        }
    ]
    assert result.use_cases == ["onboarding", "health scoring"]
    assert result.pricing == ["contact sales", "annual pricing"]
    assert result.case_study_signals == ["case study", "customer story"]  # LLM returns signals mapped to case_study_signals
    assert result.customers == ["Acme", "Beta"]
    assert result.value_statements == ["reduce churn", "improve adoption"]


def test_build_site_text_truncates_each_page_and_total_size():
    long_text = "A" * (llm_extractor.MAX_PAGE_TEXT_CHARS + 500)
    site_text = llm_extractor._build_site_text(  # noqa: SLF001
        {
            "homepage": {"website": "https://example.com", "text": long_text},
            "product_page": {"website": "https://example.com/product", "text": long_text},
            "pricing_page": {"website": "https://example.com/pricing", "text": long_text},
            "about_page": {"website": "https://example.com/about", "text": long_text},
            "security_page": {"website": "https://example.com/security", "text": long_text},
        }
    )

    assert len(site_text) <= llm_extractor.MAX_SITE_TEXT_CHARS
    assert "A" * (llm_extractor.MAX_PAGE_TEXT_CHARS + 100) not in site_text
