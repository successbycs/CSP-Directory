"""Tests for discovery candidate persistence."""

from services.discovery import discovery_store


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTableQuery:
    def __init__(self, response_data):
        self.response_data = response_data
        self.operations = []

    def upsert(self, payload, on_conflict: str):
        self.operations.append(("upsert", payload, on_conflict))
        return self

    def select(self, columns: str):
        self.operations.append(("select", columns))
        return self

    def order(self, column: str, desc: bool = False):
        self.operations.append(("order", column, desc))
        return self

    def limit(self, count: int):
        self.operations.append(("limit", count))
        return self

    def execute(self):
        self.operations.append(("execute",))
        return FakeResponse(self.response_data)


class FakeSupabaseClient:
    def __init__(self, response_data):
        self.response_data = response_data
        self.table_calls = []
        self.last_query = None

    def table(self, table_name: str):
        self.table_calls.append(table_name)
        self.last_query = FakeTableQuery(self.response_data)
        return self.last_query


def test_upsert_candidate_records_uses_candidate_domain_conflict_key():
    fake_client = FakeSupabaseClient([])
    candidate_records = [
        {
            "candidate_domain": "renewai.com",
            "candidate_title": "RenewAI",
            "candidate_description": "Renewal automation",
            "source_query": "ai customer success platform",
            "source_engine": "google_search",
            "source_rank": 1,
            "discovered_at": "2026-03-16T00:00:00+00:00",
            "candidate_status": "queued_for_enrichment",
            "drop_reason": "",
        }
    ]

    rows = discovery_store.upsert_candidate_records(candidate_records, client=fake_client)

    assert fake_client.table_calls == ["discovery_candidates"]
    assert fake_client.last_query.operations[0][0] == "upsert"
    assert fake_client.last_query.operations[0][2] == "candidate_domain"
    assert rows[0]["candidate_status"] == "queued_for_enrichment"


def test_list_candidate_records_reads_most_recent_candidates():
    fake_client = FakeSupabaseClient([{"candidate_domain": "renewai.com"}])

    rows = discovery_store.list_candidate_records(client=fake_client)

    assert rows == [{"candidate_domain": "renewai.com"}]
    assert fake_client.last_query.operations == [
        ("select", "candidate_domain,candidate_title,candidate_description,source_query,source_engine,source_rank,discovered_at,candidate_status,drop_reason"),
        ("order", "discovered_at", True),
        ("limit", 200),
        ("execute",),
    ]


def test_is_discovery_store_unavailable_error_handles_schema_cache_column_errors():
    class FakeError(Exception):
        def __init__(self):
            super().__init__(
                {
                    "message": "Could not find the 'candidate_status' column of 'discovery_candidates' in the schema cache",
                    "code": "PGRST204",
                }
            )

    assert discovery_store.is_discovery_store_unavailable_error(FakeError()) is True


def test_is_discovery_store_unavailable_error_handles_connectivity_errors():
    error = RuntimeError("Temporary failure in name resolution")

    assert discovery_store.is_discovery_store_unavailable_error(error) is True
