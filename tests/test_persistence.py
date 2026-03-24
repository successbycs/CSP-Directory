"""Tests for Supabase configuration and client setup."""

from services.persistence import supabase_client
from services.extraction.vendor_intel import VendorIntelligence


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTableQuery:
    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name
        self.selected_columns = ""
        self.filters = []
        self.limit_value = None
        self.order_value = None

    def select(self, columns: str):
        self.selected_columns = columns
        self.client.selected_columns.append(columns)
        return self

    def eq(self, column: str, value):
        self.filters.append(("eq", column, value))
        return self

    def ilike(self, column: str, value):
        self.filters.append(("ilike", column, value))
        return self

    def order(self, column: str, desc: bool = False):
        self.order_value = (column, desc)
        return self

    def limit(self, count: int):
        self.limit_value = count
        return self

    def execute(self):
        selected_column_names = {column.strip() for column in self.selected_columns.split(",") if column.strip()}
        if "icp" in selected_column_names and not self.client.icp_available:
            raise RuntimeError("column cs_vendors.icp does not exist")
        rows = self.client.response_data
        for operator, column, value in self.filters:
            if operator == "eq":
                rows = [row for row in rows if row.get(column) == value]
            elif operator == "ilike":
                rows = [row for row in rows if str(row.get(column, "")).lower() == str(value).lower()]
        if self.order_value is not None:
            column, desc = self.order_value
            rows = sorted(rows, key=lambda item: str(item.get(column, "")), reverse=desc)
        if self.limit_value is not None:
            rows = rows[: self.limit_value]
        return FakeResponse(rows)


class FakeSupabaseClient:
    def __init__(self, response_data, *, icp_available: bool = False):
        self.response_data = response_data
        self.icp_available = icp_available
        self.selected_columns = []

    def table(self, table_name: str):
        return FakeTableQuery(self, table_name)


def test_get_supabase_config_returns_none_when_url_is_missing(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_KEY", "test-key")

    assert supabase_client.get_supabase_config() is None
    assert supabase_client.is_configured() is False


def test_get_supabase_config_returns_none_when_key_is_missing(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    assert supabase_client.get_supabase_config() is None
    assert supabase_client.is_configured() is False


def test_get_supabase_client_creates_client_when_config_is_present(monkeypatch):
    created = {}

    def fake_create_supabase_client(supabase_url: str, supabase_key: str):
        created["url"] = supabase_url
        created["key"] = supabase_key
        return {"client": "ok"}

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setattr(
        supabase_client,
        "_create_supabase_client",
        fake_create_supabase_client,
    )

    result = supabase_client.get_supabase_client()

    assert result == {"client": "ok"}
    assert created == {
        "url": "https://example.supabase.co",
        "key": "test-key",
    }


def test_get_supabase_client_raises_clean_error_when_config_is_missing(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    try:
        supabase_client.get_supabase_client()
    except RuntimeError as error:
        assert str(error) == "SUPABASE_URL and SUPABASE_KEY must be set"
    else:
        raise AssertionError("Expected RuntimeError when Supabase config is missing")


def test_build_vendor_row_uses_extracted_vendor_fields():
    row = supabase_client.build_vendor_row(
        vendor={"source": "web_search", "raw_description": "Raw vendor description"},
        homepage_payload={"text": "Homepage fallback text."},
        intelligence=VendorIntelligence(
            vendor_name="ExampleCorp",
            website="https://example.com",
            source="web_search",
            mission="Structured mission",
            usp="Structured usp",
            icp_buyer=[
                {
                    "persona": "VP Customer Success",
                    "confidence": "high",
                    "evidence": ["reduce churn"],
                    "google_queries": ["customer success software for reducing churn"],
                    "geo_queries": ["What AI tools reduce churn for SaaS teams?"],
                }
            ],
            use_cases=["onboarding", "churn prevention"],
            lifecycle_stages=["Onboard", "Renew"],
            pricing=["contact sales", "per seat"],
            free_trial=True,
            soc2=True,
            founded="2021",
        ),
    )

    assert row["name"] == "ExampleCorp"
    assert row["website"] == "https://example.com"
    assert row["source"] == "web_search"
    assert row["mission"] == "Structured mission"
    assert row["usp"] == "Structured usp"
    assert row["icp_buyer"] == [
        {
            "persona": "VP Customer Success",
            "confidence": "high",
            "evidence": ["reduce churn"],
            "google_queries": ["customer success software for reducing churn"],
            "geo_queries": ["What AI tools reduce churn for SaaS teams?"],
        }
    ]
    assert row["pricing"] == "contact sales|per seat"
    assert row["free_trial"] is True
    assert row["soc2"] is True
    assert row["founded"] == "2021"
    assert row["use_cases"] == ["onboarding", "churn prevention"]
    assert row["lifecycle_stages"] == ["Onboard", "Renew"]


def test_is_persistence_unavailable_error_handles_missing_vendor_columns():
    class FakeError(Exception):
        code = ""

    error = FakeError("column cs_vendors.icp does not exist")

    assert supabase_client.is_persistence_unavailable_error(error) is True


def test_is_persistence_unavailable_error_handles_schema_cache_column_errors():
    class FakeError(Exception):
        def __init__(self):
            super().__init__(
                {
                    "message": "Could not find the 'case_studies' column of 'cs_vendors' in the schema cache",
                    "code": "PGRST204",
                }
            )

    assert supabase_client.is_persistence_unavailable_error(FakeError()) is True


def test_is_persistence_unavailable_error_handles_connectivity_errors():
    error = RuntimeError("ConnectError: All connection attempts failed")

    assert supabase_client.is_persistence_unavailable_error(error) is True


def test_list_vendor_profiles_retries_without_missing_columns():
    fake_client = FakeSupabaseClient(
        [
            {
                "name": "ExampleCorp",
                "website": "https://example.com",
                "include_in_directory": True,
                "last_updated": "2026-03-17T00:00:00+00:00",
            }
        ]
    )

    rows = supabase_client.list_vendor_profiles(client=fake_client)

    assert rows == [
        {
            "name": "ExampleCorp",
            "website": "https://example.com",
            "include_in_directory": True,
            "last_updated": "2026-03-17T00:00:00+00:00",
        }
    ]
    selected_column_sets = [
        {column.strip() for column in columns.split(",") if column.strip()}
        for columns in fake_client.selected_columns
    ]
    assert any("icp" in columns for columns in selected_column_sets)
    assert any("icp" not in columns for columns in selected_column_sets)


def test_list_directory_vendors_filters_after_retrying_without_missing_columns():
    fake_client = FakeSupabaseClient(
        [
            {
                "name": "IncludedCorp",
                "website": "https://included.example.com",
                "include_in_directory": True,
            },
            {
                "name": "ExcludedCorp",
                "website": "https://excluded.example.com",
                "include_in_directory": False,
            },
        ]
    )

    rows = supabase_client.list_directory_vendors(client=fake_client)

    assert rows == [
        {
            "name": "IncludedCorp",
            "website": "https://included.example.com",
            "include_in_directory": True,
        }
    ]


def test_get_vendor_write_columns_include_raw_description_and_icp_buyer():
    assert "raw_description" in supabase_client.get_vendor_write_columns()
    assert "icp_buyer" in supabase_client.get_vendor_write_columns()
