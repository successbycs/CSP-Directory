"""M-OPS1: Pipeline log endpoint — GET /admin/pipeline-log."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.admin.admin_api import _read_pipeline_log, _PIPELINE_LOG_LIMIT


# ---------------------------------------------------------------------------
# _read_pipeline_log unit tests
# ---------------------------------------------------------------------------


def test_read_pipeline_log_returns_empty_list_when_file_missing(tmp_path, monkeypatch):
    import services.admin.admin_api as mod
    monkeypatch.setattr(mod, "RUN_HISTORY_PATH", tmp_path / "nonexistent.json")
    assert _read_pipeline_log() == []


def test_read_pipeline_log_returns_empty_list_for_invalid_json(tmp_path, monkeypatch):
    import services.admin.admin_api as mod
    p = tmp_path / "run_history.json"
    p.write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(mod, "RUN_HISTORY_PATH", p)
    assert _read_pipeline_log() == []


def test_read_pipeline_log_returns_structured_entries(tmp_path, monkeypatch):
    import services.admin.admin_api as mod

    raw = [
        {
            "timestamp": "2026-03-27T10:00:00+00:00",
            "action": "verify",
            "milestone": "M53",
            "command": "scripts/verify.sh",
            "exit_code": 0,
            "success": True,
            "note": "verification passed",
            "phase": "verification",
            "event_type": "complete",
        },
        {
            "timestamp": "2026-03-27T10:01:00+00:00",
            "action": "build",
            "milestone": "M53",
            "command": "python3 scripts/build.py",
            "exit_code": 0,
            "success": True,
            "note": "build complete",
            "phase": "builder",
            "event_type": "complete",
        },
    ]
    p = tmp_path / "run_history.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(mod, "RUN_HISTORY_PATH", p)

    entries = _read_pipeline_log()

    assert len(entries) == 2
    # newest first (reversed)
    assert entries[0]["milestone"] == "M53"
    assert entries[0]["phase"] == "builder"
    assert entries[0]["message"] == "build complete"
    assert entries[0]["success"] is True
    assert entries[1]["phase"] == "verification"


def test_read_pipeline_log_limits_to_50_entries(tmp_path, monkeypatch):
    import services.admin.admin_api as mod

    raw = [
        {"timestamp": f"2026-03-27T{i:02d}:00:00+00:00", "action": "x", "milestone": "M1",
         "command": "", "exit_code": 0, "success": True, "note": f"step {i}",
         "phase": "build", "event_type": ""}
        for i in range(80)
    ]
    p = tmp_path / "run_history.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(mod, "RUN_HISTORY_PATH", p)

    entries = _read_pipeline_log()

    assert len(entries) == _PIPELINE_LOG_LIMIT


def test_read_pipeline_log_falls_back_to_command_when_note_missing(tmp_path, monkeypatch):
    import services.admin.admin_api as mod

    raw = [{"timestamp": "2026-03-27T10:00:00+00:00", "action": "build",
             "milestone": "M1", "command": "python3 build.py",
             "exit_code": 0, "success": True, "phase": "builder", "event_type": ""}]
    p = tmp_path / "run_history.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(mod, "RUN_HISTORY_PATH", p)

    entries = _read_pipeline_log()
    assert entries[0]["message"] == "python3 build.py"


# ---------------------------------------------------------------------------
# HTTP endpoint smoke test via _pipeline_log_response
# ---------------------------------------------------------------------------


def test_pipeline_log_endpoint_returns_ok_and_entries(tmp_path, monkeypatch):
    import services.admin.admin_api as mod

    raw = [
        {"timestamp": "2026-03-27T10:00:00+00:00", "action": "verify",
         "milestone": "M53", "command": "", "exit_code": 0, "success": True,
         "note": "passed", "phase": "verification", "event_type": "complete"},
    ]
    p = tmp_path / "run_history.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(mod, "RUN_HISTORY_PATH", p)

    status_captured = []
    headers_captured = []

    def fake_start_response(status, headers):
        status_captured.append(status)
        headers_captured.append(headers)

    body_bytes = b"".join(mod._pipeline_log_response(fake_start_response))
    body = json.loads(body_bytes)

    assert status_captured[0] == "200 OK"
    assert body["ok"] is True
    assert body["count"] == 1
    assert body["entries"][0]["milestone"] == "M53"
    assert body["entries"][0]["phase"] == "verification"
