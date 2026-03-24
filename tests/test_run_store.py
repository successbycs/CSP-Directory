"""Tests for pipeline run persistence."""

from services.persistence import run_store


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


def test_upsert_run_record_uses_run_id_conflict_key():
    fake_client = FakeSupabaseClient([])

    row = run_store.upsert_run_record(
        {
            "run_id": "20260316000000",
            "started_at": "2026-03-16T00:00:00+00:00",
            "completed_at": "2026-03-16T00:05:00+00:00",
            "queries_executed": "query one, query two",
            "candidate_count": 10,
            "queued_count": 6,
            "skipped_existing_count": 2,
            "enriched_count": 3,
            "dropped_count": 1,
            "llm_success_count": 2,
            "llm_fallback_count": 1,
            "run_status": "completed_with_warnings",
            "error_summary": "",
        },
        client=fake_client,
    )

    assert fake_client.table_calls == ["pipeline_runs"]
    assert fake_client.last_query.operations[0][0] == "upsert"
    assert fake_client.last_query.operations[0][2] == "run_id"
    assert row["run_status"] == "completed_with_warnings"


def test_list_run_records_reads_newest_runs():
    fake_client = FakeSupabaseClient([{"run_id": "20260316000000"}])

    rows = run_store.list_run_records(client=fake_client)

    assert rows == [{"run_id": "20260316000000"}]
    assert fake_client.last_query.operations == [
        ("select", "run_id,started_at,completed_at,queries_executed,candidate_count,queued_count,skipped_existing_count,enriched_count,dropped_count,llm_success_count,llm_fallback_count,run_status,error_summary"),
        ("order", "started_at", True),
        ("limit", 100),
        ("execute",),
    ]


def test_is_run_store_unavailable_error_handles_schema_cache_column_errors():
    class FakeError(Exception):
        def __init__(self):
            super().__init__(
                {
                    "message": "Could not find the 'run_status' column of 'pipeline_runs' in the schema cache",
                    "code": "PGRST204",
                }
            )

    assert run_store.is_run_store_unavailable_error(FakeError()) is True


def test_is_run_store_unavailable_error_handles_connectivity_errors():
    error = RuntimeError("Server disconnected without sending a response")

    assert run_store.is_run_store_unavailable_error(error) is True
