"""Tests for scripts/publish_to_github.py."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.publish_to_github import _count_vendors, publish_to_github


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dataset(count: int = 3) -> bytes:
    vendors = [{"vendor_name": f"Vendor{i}", "website": f"https://vendor{i}.com"} for i in range(count)]
    return json.dumps(vendors).encode()


def _fake_get(sha: str | None = "abc123", status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"sha": sha} if sha else {}
    resp.raise_for_status = MagicMock()
    return lambda *args, **kwargs: resp


def _fake_put(commit_url: str = "https://github.com/successbycs/CSP-Directory/commit/abc"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"commit": {"html_url": commit_url}}
    resp.raise_for_status = MagicMock()
    return lambda *args, **kwargs: resp


# ---------------------------------------------------------------------------
# _count_vendors
# ---------------------------------------------------------------------------


def test_count_vendors_returns_list_length():
    content = _make_dataset(5)
    assert _count_vendors(content) == 5


def test_count_vendors_returns_zero_for_invalid_json():
    assert _count_vendors(b"not-json") == 0


def test_count_vendors_returns_zero_for_non_list():
    assert _count_vendors(json.dumps({"key": "value"}).encode()) == 0


# ---------------------------------------------------------------------------
# dry_run
# ---------------------------------------------------------------------------


def test_publish_to_github_dry_run_returns_without_calling_api(tmp_path):
    local_file = tmp_path / "directory_dataset.json"
    local_file.write_bytes(_make_dataset(10))

    get_called = {"count": 0}
    put_called = {"count": 0}

    def spy_get(*a, **k):
        get_called["count"] += 1

    def spy_put(*a, **k):
        put_called["count"] += 1

    result = publish_to_github(
        local_file=local_file,
        token="test-token",
        dry_run=True,
        request_get=spy_get,
        request_put=spy_put,
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["vendor_count"] == 10
    assert get_called["count"] == 0
    assert put_called["count"] == 0


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_publish_to_github_commits_file_when_sha_exists(tmp_path):
    local_file = tmp_path / "directory_dataset.json"
    local_file.write_bytes(_make_dataset(7))
    captured_put = {}

    def fake_put(url, *, headers, json, **kwargs):
        captured_put["url"] = url
        captured_put["json"] = json
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"commit": {"html_url": "https://github.com/abc"}}
        resp.raise_for_status = MagicMock()
        return resp

    result = publish_to_github(
        local_file=local_file,
        token="test-token",
        repo="successbycs/CSP-Directory",
        branch="main",
        request_get=_fake_get(sha="existing-sha"),
        request_put=fake_put,
    )

    assert result["ok"] is True
    assert result["vendor_count"] == 7
    assert result["commit_url"] == "https://github.com/abc"
    assert captured_put["json"]["sha"] == "existing-sha"
    assert "content" in captured_put["json"]
    # Verify content is valid base64 of the original file
    decoded = base64.b64decode(captured_put["json"]["content"])
    assert json.loads(decoded)[0]["vendor_name"] == "Vendor0"


def test_publish_to_github_omits_sha_when_file_is_new(tmp_path):
    local_file = tmp_path / "directory_dataset.json"
    local_file.write_bytes(_make_dataset(2))
    captured_put = {}

    def fake_put(url, *, headers, json, **kwargs):
        captured_put["json"] = json
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {"commit": {"html_url": ""}}
        resp.raise_for_status = MagicMock()
        return resp

    result = publish_to_github(
        local_file=local_file,
        token="test-token",
        request_get=_fake_get(sha=None, status_code=404),
        request_put=fake_put,
    )

    assert result["ok"] is True
    assert "sha" not in captured_put["json"]


# ---------------------------------------------------------------------------
# auth / error handling
# ---------------------------------------------------------------------------


def test_publish_to_github_raises_when_token_is_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    local_file = tmp_path / "directory_dataset.json"
    local_file.write_bytes(_make_dataset(1))

    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        publish_to_github(local_file=local_file, token="")


def test_publish_to_github_uses_env_token(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    local_file = tmp_path / "directory_dataset.json"
    local_file.write_bytes(_make_dataset(1))
    captured_headers = {}

    def fake_get(url, *, headers, params, **kwargs):
        captured_headers.update(headers)
        resp = MagicMock()
        resp.status_code = 404
        resp.raise_for_status = MagicMock()
        return resp

    def fake_put(url, *, headers, json, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {"commit": {"html_url": ""}}
        resp.raise_for_status = MagicMock()
        return resp

    publish_to_github(local_file=local_file, request_get=fake_get, request_put=fake_put)

    assert captured_headers.get("Authorization") == "Bearer env-token"


def test_publish_to_github_propagates_http_error_from_put(tmp_path):
    import requests as req

    local_file = tmp_path / "directory_dataset.json"
    local_file.write_bytes(_make_dataset(1))

    def fake_put(url, *, headers, json, **kwargs):
        resp = MagicMock()
        resp.status_code = 422
        resp.raise_for_status.side_effect = req.HTTPError("422 Unprocessable")
        return resp

    with pytest.raises(req.HTTPError):
        publish_to_github(
            local_file=local_file,
            token="test-token",
            request_get=_fake_get(sha="abc"),
            request_put=fake_put,
        )
