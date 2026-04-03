"""Unit tests for /admin/ops/* endpoints in admin_api.py"""
import io
import json
import pytest
from unittest.mock import MagicMock, patch


def _make_environ(method, path, body=None, query_string=""):
    raw = json.dumps(body).encode("utf-8") if body is not None else b""
    return {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query_string,
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
    }


def _call(app, method, path, body=None, query_string=""):
    responses = []
    def start_response(status, headers):
        responses.append(status)
    result = app(_make_environ(method, path, body, query_string), start_response)
    body_bytes = b"".join(result)
    return responses[0], json.loads(body_bytes)


@pytest.fixture
def app():
    from services.admin.admin_api import build_admin_app
    return build_admin_app()


class TestStoreCrawlResult:
    def test_missing_vendor_website(self, app):
        status, data = _call(app, "POST", "/admin/ops/store-crawl-result", {})
        assert status.startswith("400")
        assert not data["ok"]

    def test_unknown_column_rejected(self, app):
        status, data = _call(app, "POST", "/admin/ops/store-crawl-result", {
            "vendor_website": "https://example.com",
            "column": "bad_column",
            "payload": {}
        })
        assert status.startswith("400")
        assert "unknown column" in data["error"].lower()

    def test_known_column_accepted_when_supabase_configured(self, app):
        mock_client = MagicMock()
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        with patch("services.persistence.supabase_client.is_configured", return_value=True), \
             patch("services.persistence.supabase_client.get_supabase_client", return_value=mock_client):
            status, data = _call(app, "POST", "/admin/ops/store-crawl-result", {
                "vendor_website": "https://gainsight.com",
                "column": "crawl_datagma_result",
                "payload": {"ok": True, "fields": {"founded": "2013"}}
            })
        assert status.startswith("200")
        assert data["ok"] is True
        assert data["column"] == "crawl_datagma_result"

    def test_supabase_not_configured_returns_503(self, app):
        with patch("services.persistence.supabase_client.is_configured", return_value=False):
            status, data = _call(app, "POST", "/admin/ops/store-crawl-result", {
                "vendor_website": "https://gainsight.com",
                "column": "crawl_g2_result",
                "payload": {}
            })
        assert status.startswith("503")


class TestStorePages:
    def test_missing_vendor_website(self, app):
        status, data = _call(app, "POST", "/admin/ops/store-pages", {})
        assert status.startswith("400")

    def test_empty_pages_list(self, app):
        status, data = _call(app, "POST", "/admin/ops/store-pages", {
            "vendor_website": "https://gainsight.com",
            "pages": []
        })
        assert status.startswith("400")

    def test_pages_without_url_filtered(self, app):
        with patch("services.persistence.supabase_client.is_configured", return_value=True):
            mock_client = MagicMock()
            mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[])
            with patch("services.persistence.supabase_client.get_supabase_client", return_value=mock_client):
                status, data = _call(app, "POST", "/admin/ops/store-pages", {
                    "vendor_website": "https://gainsight.com",
                    "pages": [{"page_url": "", "clean_text": "something"}]
                })
        # all pages filtered — should return 400
        assert status.startswith("400")

    def test_valid_pages_stored(self, app):
        mock_client = MagicMock()
        mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[])
        with patch("services.persistence.supabase_client.is_configured", return_value=True), \
             patch("services.persistence.supabase_client.get_supabase_client", return_value=mock_client):
            status, data = _call(app, "POST", "/admin/ops/store-pages", {
                "vendor_website": "https://gainsight.com",
                "tier_used": "tier1_direct",
                "pages": [
                    {"page_url": "https://gainsight.com", "clean_text": "Gainsight is...", "word_count": 3, "page_depth": 0}
                ]
            })
        assert status.startswith("200")
        assert data["ok"] is True
        assert data["pages_stored"] == 1


class TestFieldCoverage:
    def test_missing_vendor_website(self, app):
        status, data = _call(app, "GET", "/admin/ops/field-coverage")
        assert status.startswith("400")

    def test_vendor_pages_count_check(self, app):
        mock_result = MagicMock()
        mock_result.count = 47
        mock_result.data = [{}] * 47
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_result
        with patch("services.persistence.supabase_client.is_configured", return_value=True), \
             patch("services.persistence.supabase_client.get_supabase_client", return_value=mock_client):
            status, data = _call(
                app, "GET", "/admin/ops/field-coverage",
                query_string="vendor_website=https%3A%2F%2Fgainsight.com&check=vendor_pages_count"
            )
        assert status.startswith("200")
        assert data["ok"] is True
        assert "vendor_pages_count" in data
