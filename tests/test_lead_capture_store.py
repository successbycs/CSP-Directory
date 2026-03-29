"""Tests for lead capture persistence and follow-up operations."""

import json

from services.persistence import lead_capture_store


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

    def update(self, payload):
        self.operations.append(("update", payload))
        return self

    def eq(self, column: str, value: str):
        self.operations.append(("eq", column, value))
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


def test_build_lead_capture_row_normalizes_service_intent_and_attribution():
    row = lead_capture_store.build_lead_capture_row(
        {
            "capture_version": "m24a.v1",
            "name": "Casey Smith",
            "email": "Casey@Example.com",
            "company": "Example Co",
            "intent": "shortlist",
            "entry_page": "vendor.html",
            "entry_url": "http://127.0.0.1:8787/vendor.html?utm_source=linkedin",
            "cta_surface": "vendor-sidebar",
            "cta_variant": "shortlist-card",
            "cta_label": "Request shortlist",
            "vendor_name": "Gainsight",
            "vendor_website": "https://www.gainsight.com/platform/",
            "vendor_category": "Customer Success Platform",
            "utm_source": "linkedin",
            "utm_campaign": "q2-market-map",
            "captured_at": "2026-03-20T10:00:00+00:00",
        }
    )

    assert row["capture_version"] == "m24a.v1"
    assert row["lead_email"] == "casey@example.com"
    assert row["lead_intent"] == "shortlist"
    assert row["intent_category"] == "service"
    assert row["follow_up_priority"] == "high"
    assert row["recommended_handoff_channel"] == "calendar_or_email"
    assert row["vendor_website"] == "https://gainsight.com"
    assert row["attribution_context"]["cta_surface"] == "vendor-sidebar"
    assert row["attribution_context"]["utm_campaign"] == "q2-market-map"
    assert row["follow_up_status"] == "new"


def test_create_lead_capture_uses_lead_id_conflict_key(monkeypatch):
    fake_client = FakeSupabaseClient([])
    monkeypatch.setattr(lead_capture_store.supabase_client, "is_configured", lambda: True)

    row = lead_capture_store.create_lead_capture(
        {
            "name": "Taylor",
            "email": "taylor@example.com",
            "company": "Example",
            "intent": "market-map",
        },
        client=fake_client,
    )

    assert fake_client.table_calls == ["lead_captures"]
    assert fake_client.last_query.operations[0][0] == "upsert"
    assert fake_client.last_query.operations[0][2] == "lead_id"
    assert row["intent_category"] == "content"


def test_build_lead_capture_row_normalizes_browse_directory_intent():
    row = lead_capture_store.build_lead_capture_row(
        {
            "name": "Taylor",
            "email": "taylor@example.com",
            "company": "Example",
            "intent": "directory",
        }
    )

    assert row["lead_intent"] == "browse_directory"
    assert row["intent_category"] == "content"
    assert row["recommended_handoff_channel"] == "directory_access"


def test_build_lead_capture_row_preserves_advisory_follow_up_intent():
    row = lead_capture_store.build_lead_capture_row(
        {
            "name": "Taylor",
            "email": "taylor@example.com",
            "company": "Example",
            "intent": "advisory_follow_up",
        }
    )

    assert row["lead_intent"] == "advisory_follow_up"
    assert row["intent_category"] == "service"
    assert "book time with Chris" in row["recommended_next_step"]


def test_create_lead_capture_falls_back_to_local_dataset(monkeypatch, tmp_path):
    results_path = tmp_path / "lead_capture_dataset.json"
    monkeypatch.setattr(lead_capture_store.supabase_client, "is_configured", lambda: False)

    row = lead_capture_store.create_lead_capture(
        {
            "name": "Jordan",
            "email": "jordan@example.com",
            "company": "Example",
            "intent": "advisory",
        },
        results_path=results_path,
    )

    stored_rows = json.loads(results_path.read_text(encoding="utf-8"))
    assert stored_rows[0]["lead_id"] == row["lead_id"]
    assert stored_rows[0]["intent_category"] == "service"


def test_update_lead_follow_up_updates_local_dataset(monkeypatch, tmp_path):
    results_path = tmp_path / "lead_capture_dataset.json"
    monkeypatch.setattr(lead_capture_store.supabase_client, "is_configured", lambda: False)
    row = lead_capture_store.create_lead_capture(
        {
            "name": "Morgan",
            "email": "morgan@example.com",
            "company": "Example",
            "intent": "market-map",
        },
        results_path=results_path,
    )

    updated = lead_capture_store.update_lead_follow_up(
        row["lead_id"],
        follow_up_status="qualified",
        follow_up_notes="Booked for next week.",
        results_path=results_path,
    )

    assert updated["follow_up_status"] == "qualified"
    assert updated["follow_up_notes"] == "Booked for next week."
    persisted = lead_capture_store.read_local_lead_captures(results_path)
    assert persisted[0]["follow_up_status"] == "qualified"


def test_export_lead_capture_dashboard_returns_metrics(monkeypatch, tmp_path):
    results_path = tmp_path / "lead_capture_dataset.json"
    monkeypatch.setattr(lead_capture_store.supabase_client, "is_configured", lambda: False)
    lead_capture_store.create_lead_capture(
        {
            "name": "Alex",
            "email": "alex@example.com",
            "company": "Example",
            "intent": "market-map",
        },
        results_path=results_path,
    )
    row = lead_capture_store.create_lead_capture(
        {
            "name": "Riley",
            "email": "riley@example.com",
            "company": "Example",
            "intent": "advisory",
        },
        results_path=results_path,
    )
    lead_capture_store.update_lead_follow_up(
        row["lead_id"],
        follow_up_status="qualified",
        results_path=results_path,
    )

    payload = lead_capture_store.export_lead_capture_dashboard(results_path=results_path)

    assert payload["metrics"]["lead_count"] == 2
    assert payload["metrics"]["service_lead_count"] == 1
    assert payload["metrics"]["qualified_lead_count"] == 1
    assert len(payload["items"]) == 2
