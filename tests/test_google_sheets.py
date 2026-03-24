"""Tests for the Google Sheets export module."""

import csv
import json
from pathlib import Path

from services.extraction.vendor_intel import VendorIntelligence
from services.export import google_sheets


def test_vendor_intelligence_to_sheet_row():
    vendor = VendorIntelligence(
        vendor_name="ExampleCorp",
        website="https://example.com",
        source="web_search",
        mission="Improve customer retention",
        usp="reduce churn",
        icp=["SaaS companies", "Mid-market teams"],
        use_cases=["health scoring", "renewal management"],
        lifecycle_stages=["Adopt", "Support", "Renew"],
        case_studies=["Increased retention by 20%", "Reduced churn"],
        customers=["Acme", "Beta"],
        value_statements=["Increases retention", "Boosts ARR"],
        pricing=["$99/mo", "$199/mo"],
        free_trial=True,
        soc2=True,
        founded="2021",
        confidence="high",
        evidence_urls=["https://example.com/proof"],
    )

    result = google_sheets.vendor_intelligence_to_sheet_row(vendor)

    expected = {
        "vendor_name": "ExampleCorp",
        "website": "https://example.com",
        "source": "web_search",
        "mission": "Improve customer retention",
        "usp": "reduce churn",
        "icp": "SaaS companies|Mid-market teams",
        "use_cases": "health scoring|renewal management",
        "lifecycle_stages": "Adopt|Support|Renew",
        "pricing": "$99/mo|$199/mo",
        "free_trial": "TRUE",
        "soc2": "TRUE",
        "founded": "2021",
        "case_studies": "Increased retention by 20%|Reduced churn",
        "customers": "Acme|Beta",
        "value_statements": "Increases retention|Boosts ARR",
        "confidence": "high",
        "evidence_urls": "https://example.com/proof",
        "directory_fit": "",
        "directory_category": "",
        "include_in_directory": "",
    }

    assert result == expected


def test_write_rows_to_csv(tmp_path: Path):
    rows = [
        {
            "vendor_name": "ExampleCorp",
            "website": "https://example.com",
            "source": "web_search",
            "mission": "Improve customer retention",
            "usp": "reduce churn",
            "icp": "SaaS companies|Mid-market teams",
            "use_cases": "health scoring|renewal management",
            "lifecycle_stages": "Adopt|Support|Renew",
            "pricing": "$99/mo|$199/mo",
            "free_trial": "TRUE",
            "soc2": "TRUE",
            "founded": "2021",
            "case_studies": "Increased retention by 20%|Reduced churn",
            "customers": "Acme|Beta",
            "value_statements": "Increases retention|Boosts ARR",
            "confidence": "high",
            "evidence_urls": "https://example.com/proof",
            "directory_fit": "",
            "directory_category": "",
            "include_in_directory": "",
        }
    ]

    output_path = tmp_path / "outputs" / "vendor_rows.csv"

    google_sheets.write_rows_to_csv(rows, output_path)

    assert output_path.exists()
    with output_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        result = list(reader)

    assert reader.fieldnames == [
        "vendor_name",
        "website",
        "source",
        "mission",
        "usp",
        "icp",
        "use_cases",
        "lifecycle_stages",
        "pricing",
        "free_trial",
        "soc2",
        "founded",
        "case_studies",
        "customers",
        "value_statements",
        "confidence",
        "evidence_urls",
        "directory_fit",
        "directory_category",
        "include_in_directory",
    ]
    assert result == rows


class FakeAppendRequest:
    def __init__(self, recorder: dict):
        self.recorder = recorder

    def execute(self):
        self.recorder["executed"] = True
        return {"updates": {"updatedRows": 1}}


class FakeValuesResource:
    def __init__(self, recorder: dict, get_response: dict | None = None):
        self.recorder = recorder
        self.get_response = get_response or {}

    def get(self, **kwargs):
        self.recorder.setdefault("get_calls", []).append(kwargs)
        return FakeGetRequest(self.recorder, self.get_response)

    def update(self, **kwargs):
        self.recorder.setdefault("update_calls", []).append(kwargs)
        return FakeUpdateRequest(self.recorder)

    def append(self, **kwargs):
        self.recorder["append_kwargs"] = kwargs
        return FakeAppendRequest(self.recorder)


class FakeSpreadsheetsResource:
    def __init__(
        self,
        recorder: dict,
        *,
        get_values_response: dict | None = None,
        spreadsheet_metadata: dict | None = None,
    ):
        self.recorder = recorder
        self.get_values_response = get_values_response or {}
        self.spreadsheet_metadata = spreadsheet_metadata or {}

    def values(self):
        return FakeValuesResource(self.recorder, self.get_values_response)

    def get(self, **kwargs):
        self.recorder.setdefault("spreadsheet_get_calls", []).append(kwargs)
        return FakeSpreadsheetGetRequest(self.recorder, self.spreadsheet_metadata)

    def batchUpdate(self, **kwargs):
        self.recorder.setdefault("batch_update_calls", []).append(kwargs)
        return FakeBatchUpdateRequest(self.recorder)


class FakeSheetsService:
    def __init__(
        self,
        recorder: dict,
        *,
        get_values_response: dict | None = None,
        spreadsheet_metadata: dict | None = None,
    ):
        self.recorder = recorder
        self.get_values_response = get_values_response or {}
        self.spreadsheet_metadata = spreadsheet_metadata or {}

    def spreadsheets(self):
        return FakeSpreadsheetsResource(
            self.recorder,
            get_values_response=self.get_values_response,
            spreadsheet_metadata=self.spreadsheet_metadata,
        )


class FakeGetRequest:
    def __init__(self, recorder: dict, response: dict):
        self.recorder = recorder
        self.response = response

    def execute(self):
        self.recorder["get_executed"] = True
        return self.response


class FakeUpdateRequest:
    def __init__(self, recorder: dict):
        self.recorder = recorder

    def execute(self):
        self.recorder["update_executed"] = True
        return {"updatedRows": 1}


class FakeSpreadsheetGetRequest:
    def __init__(self, recorder: dict, response: dict):
        self.recorder = recorder
        self.response = response

    def execute(self):
        self.recorder["spreadsheet_get_executed"] = True
        return self.response


class FakeBatchUpdateRequest:
    def __init__(self, recorder: dict):
        self.recorder = recorder

    def execute(self):
        self.recorder["batch_update_executed"] = True
        return {"replies": []}


def test_load_google_sheets_credentials_info_from_json_env(monkeypatch):
    credentials_info = {"type": "service_account", "client_email": "json@example.com"}

    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS", raising=False)
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON", json.dumps(credentials_info))

    result = google_sheets._load_google_sheets_credentials_info()

    assert result == credentials_info


def test_load_google_sheets_credentials_info_from_legacy_env_key(monkeypatch):
    credentials_info = {"type": "service_account", "client_email": "legacy@example.com"}

    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_JSON", raising=False)
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS", json.dumps(credentials_info))

    result = google_sheets._load_google_sheets_credentials_info()

    assert result == credentials_info


def test_append_rows_to_google_sheet_warns_and_skips_without_credentials(monkeypatch, caplog):
    monkeypatch.setenv("GOOGLE_SHEETS_ID", "sheet-id")
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_JSON", raising=False)

    google_sheets.append_rows_to_google_sheet(
        [{"vendor_name": "ExampleCorp", "website": "https://example.com"}]
    )

    assert "Google Sheets credentials are unavailable" in caplog.text


def test_append_rows_to_google_sheet_uses_correct_column_order(monkeypatch, tmp_path: Path):
    rows = [
        {
            "vendor_name": "ExampleCorp",
            "website": "https://example.com",
            "mission": "Improve customer retention",
            "usp": "reduce churn",
            "icp": "SaaS companies|Mid-market teams",
            "use_cases": "health scoring|renewal management",
            "lifecycle_stages": "Adopt|Support|Renew",
            "pricing": "$99/mo|$199/mo",
            "free_trial": "TRUE",
            "soc2": "TRUE",
            "founded": "2021",
            "case_studies": "Increased retention by 20%|Reduced churn",
            "customers": "Acme|Beta",
            "value_statements": "Increases retention|Boosts ARR",
            "confidence": "high",
            "evidence_urls": "https://example.com/proof",
        }
    ]

    monkeypatch.setenv("GOOGLE_SHEETS_ID", "sheet-id")
    monkeypatch.setenv(
        "GOOGLE_SHEETS_CREDENTIALS_JSON",
        json.dumps({"type": "service_account", "client_email": "test@example.com"}),
    )
    fake_recorder = {}

    def fake_build_google_sheets_service(credentials_info):
        fake_recorder["credentials_info"] = credentials_info
        return FakeSheetsService(
            fake_recorder,
            get_values_response={"values": [google_sheets.GOOGLE_SHEETS_COLUMNS]},
        )

    monkeypatch.setattr(
        google_sheets,
        "_build_google_sheets_service",
        fake_build_google_sheets_service,
    )

    google_sheets.append_rows_to_google_sheet(rows)

    assert fake_recorder["append_kwargs"] == {
        "spreadsheetId": "sheet-id",
        "range": "vendors!A:T",
        "valueInputOption": "USER_ENTERED",
        "body": {
            "values": [[
                "ExampleCorp",
                "https://example.com",
                "",
                "Improve customer retention",
                "reduce churn",
                "SaaS companies|Mid-market teams",
                "health scoring|renewal management",
                "Adopt|Support|Renew",
                "$99/mo|$199/mo",
                "TRUE",
                "TRUE",
                "2021",
                "Increased retention by 20%|Reduced churn",
                "Acme|Beta",
                "Increases retention|Boosts ARR",
                "high",
                "https://example.com/proof",
                "",
                "",
                "",
            ]]
        },
    }
    assert fake_recorder["executed"] is True


def test_append_rows_to_google_sheet_initializes_header_row_when_missing(monkeypatch):
    rows = [{"vendor_name": "ExampleCorp", "website": "https://example.com"}]

    monkeypatch.setenv("GOOGLE_SHEETS_ID", "sheet-id")
    monkeypatch.setenv(
        "GOOGLE_SHEETS_CREDENTIALS_JSON",
        json.dumps({"type": "service_account", "client_email": "test@example.com"}),
    )
    fake_recorder = {}

    monkeypatch.setattr(
        google_sheets,
        "_build_google_sheets_service",
        lambda _credentials: FakeSheetsService(fake_recorder, get_values_response={}),
    )

    google_sheets.append_rows_to_google_sheet(rows)

    assert fake_recorder["update_calls"] == [{
        "spreadsheetId": "sheet-id",
        "range": "vendors!A1:T1",
        "valueInputOption": "RAW",
        "body": {"values": [google_sheets.GOOGLE_SHEETS_COLUMNS]},
    }]
    assert fake_recorder["append_kwargs"]["range"] == "vendors!A:T"


def test_append_rows_to_google_sheet_inserts_header_row_when_first_row_is_data(monkeypatch):
    rows = [{"vendor_name": "ExampleCorp", "website": "https://example.com"}]

    monkeypatch.setenv("GOOGLE_SHEETS_ID", "sheet-id")
    monkeypatch.setenv(
        "GOOGLE_SHEETS_CREDENTIALS_JSON",
        json.dumps({"type": "service_account", "client_email": "test@example.com"}),
    )
    monkeypatch.setenv("GOOGLE_SHEETS_WORKSHEET", "directory_ops")
    fake_recorder = {}

    monkeypatch.setattr(
        google_sheets,
        "_build_google_sheets_service",
        lambda _credentials: FakeSheetsService(
            fake_recorder,
            get_values_response={"values": [["Existing vendor", "https://example.com"]]},
            spreadsheet_metadata={
                "sheets": [{"properties": {"title": "directory_ops", "sheetId": 12345}}]
            },
        ),
    )

    google_sheets.append_rows_to_google_sheet(rows)

    assert fake_recorder["batch_update_calls"] == [{
        "spreadsheetId": "sheet-id",
        "body": {
            "requests": [{
                "insertDimension": {
                    "range": {
                        "sheetId": 12345,
                        "dimension": "ROWS",
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    "inheritFromBefore": False,
                }
            }]
        },
    }]
    assert fake_recorder["update_calls"] == [{
        "spreadsheetId": "sheet-id",
        "range": "directory_ops!A1:T1",
        "valueInputOption": "RAW",
        "body": {"values": [google_sheets.GOOGLE_SHEETS_COLUMNS]},
    }]
    assert fake_recorder["append_kwargs"]["range"] == "directory_ops!A:T"


def test_publish_ops_review_export_writes_runs_candidates_and_vendors_tabs(monkeypatch):
    monkeypatch.setattr(
        google_sheets,
        "append_rows_to_google_sheet_tab",
        lambda rows, *, worksheet_name=None, columns=None: recorded.append(
            (worksheet_name, list(columns or []), rows)
        ),
    )
    recorded = []

    profile = VendorIntelligence(
        vendor_name="ExampleCorp",
        website="https://example.com",
        source="google_search",
        mission="ExampleCorp helps customer success teams reduce churn and improve adoption.",
        use_cases=["health scoring", "renewal management", "onboarding automation"],
        pricing=["contact sales", "per seat"],
        free_trial=True,
        soc2=True,
        founded="2021",
        confidence="high",
        evidence_urls=["https://example.com", "https://example.com/pricing"],
        lifecycle_stages=["Onboard", "Renew"],
        directory_fit="high",
        directory_category="cs_core",
        include_in_directory=True,
    )

    google_sheets.publish_ops_review_export(
        run_record={
            "run_id": "run-1",
            "started_at": "2026-03-16T00:00:00+00:00",
            "completed_at": "2026-03-16T00:10:00+00:00",
            "queries_executed": "query one",
            "candidate_count": 10,
            "queued_count": 5,
            "enriched_count": 3,
            "dropped_count": 2,
            "run_status": "completed_with_warnings",
            "error_summary": "",
        },
        candidate_records=[
            {
                "candidate_domain": "example.com",
                "candidate_title": "ExampleCorp",
                "source_query": "query one",
                "source_rank": 1,
                "candidate_status": "enriched",
                "drop_reason": "",
                "discovered_at": "2026-03-16T00:00:00+00:00",
            }
        ],
        enrichment_results=[
            {
                "status": "enriched",
                "candidate_domain": "example.com",
                "profile": profile,
                "completed_at": "2026-03-16T00:09:00+00:00",
            }
        ],
    )

    assert [item[0] for item in recorded] == ["runs", "candidates", "vendors"]
    assert recorded[0][2][0]["run_status"] == "completed_with_warnings"
    assert recorded[1][2][0]["candidate_status"] == "enriched"
    assert recorded[2][2][0]["mission_summary"].startswith("ExampleCorp helps customer success teams")
