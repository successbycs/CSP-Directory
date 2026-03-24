"""Tests for buyer-role search visibility persistence and reporting."""

from __future__ import annotations

from pathlib import Path

from services.export import search_visibility_report
from services.persistence import search_visibility_store


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTableQuery:
    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name
        self.operations = []
        self.limit_value = None

    def select(self, columns: str):
        self.operations.append(("select", columns))
        return self

    def upsert(self, rows, on_conflict: str):
        stored_rows = list(rows)
        self.client.response_map[self.table_name] = stored_rows
        self.operations.append(("upsert", stored_rows, on_conflict))
        return self

    def order(self, column: str, desc: bool = False):
        self.operations.append(("order", column, desc))
        return self

    def limit(self, count: int):
        self.limit_value = count
        self.operations.append(("limit", count))
        return self

    def execute(self):
        self.operations.append(("execute",))
        rows = list(self.client.response_map.get(self.table_name, []))
        if self.limit_value is not None:
            rows = rows[: self.limit_value]
        return FakeResponse(rows)


class FakeSupabaseClient:
    def __init__(self, response_map):
        self.response_map = response_map
        self.table_calls = []
        self.last_query = None

    def table(self, table_name: str):
        self.table_calls.append(table_name)
        self.last_query = FakeTableQuery(self, table_name)
        return self.last_query


def test_build_buyer_search_query_rows_expands_google_and_geo_queries():
    rows = search_visibility_store.build_buyer_search_query_rows(
        [
            {
                "name": "Example",
                "website": "https://example.com",
                "icp_buyer": [
                    {
                        "persona": "VP Customer Success",
                        "confidence": "high",
                        "evidence": ["reduce churn"],
                        "google_queries": ["customer success software"],
                        "geo_queries": ["What AI tools reduce churn?"],
                    }
                ],
            }
        ],
        generated_at="2026-03-19T00:00:00+00:00",
    )

    assert len(rows) == 2
    assert {row["search_channel"] for row in rows} == {"google", "geo"}
    assert {row["search_provider"] for row in rows} == {"google", "openai"}
    assert {row["query_generation_version"] for row in rows} == {
        search_visibility_store.BUYER_SEARCH_QUERY_GENERATION_VERSION
    }
    assert rows[0]["query_generation_context"]["source"] == "icp_buyer"
    assert all(row["generated_at"] == "2026-03-19T00:00:00+00:00" for row in rows)


def test_list_buyer_search_queries_orders_before_limit():
    fake_client = FakeSupabaseClient(
        {
            search_visibility_store.BUYER_SEARCH_QUERY_TABLE: [
                {
                    "query_signature": "sig-1",
                    "buyer_role": "VP Customer Success",
                    "search_channel": "google",
                    "query_text": "customer success software",
                    "generated_at": "2026-03-19T00:00:00+00:00",
                }
            ]
        }
    )

    rows = search_visibility_store.list_buyer_search_queries(limit=25, client=fake_client)

    assert rows[0]["query_signature"] == "sig-1"
    assert fake_client.last_query.operations == [
        (
            "select",
            "query_signature,source_vendor_name,source_vendor_website,buyer_role,search_channel,search_provider,query_text,persona_confidence,evidence,query_generation_version,query_generation_context,generated_at",
        ),
        ("order", "generated_at", True),
        ("order", "buyer_role", False),
        ("order", "search_channel", False),
        ("order", "query_text", False),
        ("limit", 25),
        ("execute",),
    ]


def test_list_buyer_search_results_orders_latest_runs_and_lowest_ranks_first():
    fake_client = FakeSupabaseClient(
        {
            search_visibility_store.BUYER_SEARCH_RESULT_TABLE: [
                {
                    "query_signature": "sig-1",
                    "buyer_role": "VP Customer Success",
                    "search_channel": "google",
                    "search_provider": "google",
                    "query_text": "tools to improve retention",
                    "observed_rank": 3,
                    "surfaced_vendor_name": "LaterRank",
                    "visibility_score": 70.0,
                    "run_timestamp": "2026-03-19T00:00:00+00:00",
                },
                {
                    "query_signature": "sig-1",
                    "buyer_role": "VP Customer Success",
                    "search_channel": "google",
                    "search_provider": "google",
                    "query_text": "tools to improve retention",
                    "observed_rank": 1,
                    "surfaced_vendor_name": "TopRank",
                    "visibility_score": 100.0,
                    "run_timestamp": "2026-03-19T00:00:00+00:00",
                },
                {
                    "query_signature": "sig-2",
                    "buyer_role": "VP Customer Success",
                    "search_channel": "geo",
                    "search_provider": "openai",
                    "query_text": "What AI tools reduce churn?",
                    "observed_rank": 1,
                    "surfaced_vendor_name": "OlderRun",
                    "visibility_score": 100.0,
                    "run_timestamp": "2026-03-18T00:00:00+00:00",
                },
            ]
        }
    )

    rows = search_visibility_store.list_buyer_search_results(limit=10, client=fake_client)

    assert [row["surfaced_vendor_name"] for row in rows] == ["TopRank", "LaterRank", "OlderRun"]
    assert fake_client.last_query.operations == [
        ("select", "query_signature,buyer_role,search_channel,search_provider,query_text,observed_rank,surfaced_vendor_name,surfaced_vendor_website,source_url,response_reference,visibility_score,run_timestamp"),
        ("order", "run_timestamp", True),
        ("order", "buyer_role", False),
        ("order", "search_channel", False),
        ("order", "query_text", False),
        ("order", "observed_rank", False),
        ("limit", 10),
        ("execute",),
    ]


def test_build_search_visibility_report_falls_back_to_supplied_rows(monkeypatch):
    monkeypatch.setattr(search_visibility_report.supabase_client, "is_configured", lambda: False)

    report = search_visibility_report.build_search_visibility_report(
        fallback_query_rows=[
            {
                "query_signature": "sig-1",
                "source_vendor_name": "ChurnZero",
                "source_vendor_website": "https://churnzero.com",
                "buyer_role": "VP Customer Success",
                "search_channel": "google",
                "search_provider": "google",
                "query_text": "tools to improve SaaS retention",
            }
        ],
        fallback_result_rows=[
            {
                "query_signature": "sig-1",
                "buyer_role": "VP Customer Success",
                "search_channel": "google",
                "search_provider": "google",
                "query_text": "tools to improve SaaS retention",
                "observed_rank": 1,
                "surfaced_vendor_name": "Gainsight",
                "surfaced_vendor_website": "https://www.gainsight.com",
                "visibility_score": 100,
                "run_timestamp": "2026-03-19T00:00:00+00:00",
            },
            {
                "query_signature": "sig-1",
                "buyer_role": "VP Customer Success",
                "search_channel": "google",
                "search_provider": "google",
                "query_text": "tools to improve SaaS retention",
                "observed_rank": 2,
                "surfaced_vendor_name": "ChurnZero",
                "surfaced_vendor_website": "https://churnzero.com",
                "visibility_score": 85,
                "run_timestamp": "2026-03-19T00:00:00+00:00",
            },
        ],
    )

    assert report["metrics"] == {"query_count": 1, "ranking_count": 2, "vendor_count": 2}
    assert report["role_query_rankings"][0]["surfaced_vendor_name"] == "Gainsight"
    assert report["vendor_visibility_summary"][0]["surfaced_vendor_name"] == "Gainsight"
    assert report["vendor_visibility_summary"][0]["best_rank"] == 1


def test_export_search_visibility_artifacts_writes_json_and_html(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        search_visibility_report,
        "build_search_visibility_report",
        lambda client=None, fallback_query_rows=None, fallback_result_rows=None, prefer_fallback_rows=False: {
            "metrics": {"query_count": 2, "ranking_count": 3, "vendor_count": 2},
            "role_query_rankings": [
                {
                    "buyer_role": "VP Customer Success",
                    "search_channel_label": "google",
                    "query_text": "tools to improve SaaS retention",
                    "observed_rank": 1,
                    "surfaced_vendor_name": "Gainsight",
                    "surfaced_vendor_website": "https://www.gainsight.com",
                    "visibility_score": 100.0,
                    "run_timestamp": "2026-03-19T00:00:00+00:00",
                }
            ],
            "vendor_visibility_summary": [
                {
                    "surfaced_vendor_name": "Gainsight",
                    "surfaced_vendor_website": "https://www.gainsight.com",
                    "appearances": 1,
                    "best_rank": 1,
                    "average_rank": 1.0,
                    "average_visibility_score": 100.0,
                    "buyer_roles": ["VP Customer Success"],
                    "search_channels": ["google"],
                    "latest_run_timestamp": "2026-03-19T00:00:00+00:00",
                }
            ],
        },
    )

    report_path = tmp_path / "search_visibility_report.json"
    html_path = tmp_path / "search_visibility_report.html"
    report = search_visibility_report.export_search_visibility_artifacts(
        report_output_path=report_path,
        html_output_path=html_path,
    )

    assert report["metrics"]["vendor_count"] == 2
    assert report_path.exists()
    assert html_path.exists()
    assert '"vendor_count": 2' in report_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    assert "Search visibility report" in html
    assert "Gainsight" in html


def test_build_buyer_search_result_rows_links_query_identity_and_scores():
    rows = search_visibility_store.build_buyer_search_result_rows(
        {
            "query_signature": "sig-1",
            "buyer_role": "VP Customer Success",
            "search_channel": "geo",
            "search_provider": "openai",
            "query_text": "What AI tools reduce churn?",
        },
        [
            {
                "rank": 2,
                "vendor_name": "ChurnZero",
                "vendor_website": "https://www.churnzero.com/",
                "source_url": "https://chat.openai.com/c/example",
                "response_reference": "response-123",
            }
        ],
        run_timestamp="2026-03-19T01:00:00+00:00",
    )

    assert rows == [
        {
            "query_signature": "sig-1",
            "buyer_role": "VP Customer Success",
            "search_channel": "geo",
            "search_provider": "openai",
            "query_text": "What AI tools reduce churn?",
            "observed_rank": 2,
            "surfaced_vendor_name": "ChurnZero",
            "surfaced_vendor_website": "https://churnzero.com",
            "source_url": "https://chat.openai.com/c/example",
            "response_reference": "response-123",
            "visibility_score": 85.0,
            "run_timestamp": "2026-03-19T01:00:00+00:00",
        }
    ]


def test_upsert_buyer_search_results_persists_ranked_rows():
    fake_client = FakeSupabaseClient({})

    rows = search_visibility_store.upsert_buyer_search_results(
        {
            "query_signature": "sig-1",
            "buyer_role": "VP Customer Success",
            "search_channel": "google",
            "search_provider": "google",
            "query_text": "tools to improve SaaS retention",
        },
        [
            {
                "observed_rank": 1,
                "surfaced_vendor_name": "Gainsight",
                "surfaced_vendor_website": "https://www.gainsight.com",
                "visibility_score": 100,
            },
            {
                "observed_rank": 2,
                "surfaced_vendor_name": "ChurnZero",
                "surfaced_vendor_website": "https://churnzero.com",
            },
        ],
        run_timestamp="2026-03-19T00:00:00+00:00",
        client=fake_client,
    )

    assert [row["surfaced_vendor_name"] for row in rows] == ["Gainsight", "ChurnZero"]
    assert rows[1]["visibility_score"] == 85.0
    assert fake_client.last_query.operations == [
        (
            "upsert",
            rows,
            "query_signature,run_timestamp,observed_rank",
        ),
        ("execute",),
    ]


def test_upsert_buyer_search_queries_from_vendor_profiles_persists_google_and_geo_rows():
    fake_client = FakeSupabaseClient({})

    rows = search_visibility_store.upsert_buyer_search_queries_from_vendor_profiles(
        [
            {
                "name": "Example",
                "website": "https://example.com",
                "icp_buyer": [
                    {
                        "persona": "Chief Customer Officer",
                        "confidence": "high",
                        "google_queries": ["customer success platform"],
                        "geo_queries": ["What AI tools improve net retention?"],
                    }
                ],
            }
        ],
        generated_at="2026-03-19T00:00:00+00:00",
        client=fake_client,
    )

    assert {row["search_channel"] for row in rows} == {"google", "geo"}
    assert all(
        row["query_generation_version"] == search_visibility_store.BUYER_SEARCH_QUERY_GENERATION_VERSION
        for row in rows
    )
    assert fake_client.last_query.operations == [
        ("upsert", rows, "query_signature"),
        ("execute",),
    ]
