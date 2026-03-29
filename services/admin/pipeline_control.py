"""Pipeline control helpers for admin-triggered executions with progress tracking."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import threading
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_STATE_PATH = PROJECT_ROOT / "runs" / "pipeline_control_state.json"
PIPELINE_LOG_DIR = PROJECT_ROOT / "runs" / "pipeline_logs"

_STATE_LOCK = threading.Lock()
_ACTIVE_RUNS: dict[str, subprocess.Popen[Any]] = {}

_PIPELINE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "pipeline_id": "full_pipeline",
        "name": "Full Discovery + Enrichment",
        "description": "Runs discover → enrich → export using configured query set.",
        "command": ["scripts/run_pipeline.py", "--no-serve-preview"],
    },
    {
        "pipeline_id": "weekly_discovery_job",
        "name": "Weekly Discovery Job",
        "description": "Runs scheduler discovery job (weekly by scheduler config).",
        "command": ["-m", "services.pipeline.scheduler", "--run-now", "discovery"],
    },
    {
        "pipeline_id": "weekly_digest_job",
        "name": "Weekly Digest Job",
        "description": "Builds and sends weekly lifecycle digest.",
        "command": ["-m", "services.pipeline.scheduler", "--run-now", "digest"],
    },
    {
        "pipeline_id": "g2_rapidapi_enrichment",
        "name": "G2 RapidAPI Enrichment",
        "description": "Runs G2 enrichment helper over included vendors.",
        "command": ["scripts/enrich_g2_rapidapi.py"],
    },
)


def list_pipeline_controls() -> dict[str, Any]:
    """Return all pipeline controls with runtime status and recent progress."""
    with _STATE_LOCK:
        state = _load_state_unlocked()
        now_iso = _now_iso()
        items: list[dict[str, Any]] = []
        for spec in _PIPELINE_SPECS:
            pipeline_id = str(spec["pipeline_id"])
            pipeline_state = dict(state.get(pipeline_id) or {})
            _refresh_pipeline_status_unlocked(pipeline_id, pipeline_state, now_iso)
            state[pipeline_id] = pipeline_state
            items.append(_build_pipeline_view(spec, pipeline_state))
        _save_state_unlocked(state)
    return {"items": items}


def trigger_pipeline_run(pipeline_id: str) -> dict[str, Any]:
    """Start one pipeline in the background and return updated run metadata."""
    normalized_id = str(pipeline_id or "").strip()
    if not normalized_id:
        raise ValueError("pipeline_id is required")

    spec = next((item for item in _PIPELINE_SPECS if item["pipeline_id"] == normalized_id), None)
    if spec is None:
        raise ValueError(f"Unknown pipeline_id: {normalized_id}")

    with _STATE_LOCK:
        state = _load_state_unlocked()
        current = dict(state.get(normalized_id) or {})
        _refresh_pipeline_status_unlocked(normalized_id, current, _now_iso())
        if current.get("status") == "running":
            return {"ok": False, "error": "already_running", "pipeline": _build_pipeline_view(spec, current)}

        PIPELINE_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = PIPELINE_LOG_DIR / f"{normalized_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
        command = [_python_executable(), *list(spec["command"])]
        with log_path.open("ab") as log_file:
            process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
        _ACTIVE_RUNS[normalized_id] = process

        current.update(
            {
                "status": "running",
                "last_triggered_at": _now_iso(),
                "last_finished_at": "",
                "last_exit_code": None,
                "pid": process.pid,
                "log_path": str(log_path),
                "updated_at": _now_iso(),
            }
        )
        state[normalized_id] = current
        _save_state_unlocked(state)
        return {"ok": True, "pipeline": _build_pipeline_view(spec, current)}


def _python_executable() -> str:
    return os.environ.get("VIRTUAL_ENV", "") and str(Path(os.environ["VIRTUAL_ENV"]) / "bin" / "python") or "python3"


def _build_pipeline_view(spec: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    return {
        "pipeline_id": spec["pipeline_id"],
        "name": spec["name"],
        "description": spec["description"],
        "status": state.get("status") or "idle",
        "last_triggered_at": state.get("last_triggered_at") or "",
        "last_finished_at": state.get("last_finished_at") or "",
        "last_exit_code": state.get("last_exit_code"),
        "pid": state.get("pid"),
        "log_path": state.get("log_path") or "",
        "progress": _tail_log(state.get("log_path") or ""),
    }


def _refresh_pipeline_status_unlocked(pipeline_id: str, state: dict[str, Any], now_iso: str) -> None:
    process = _ACTIVE_RUNS.get(pipeline_id)
    if process is None:
        return
    return_code = process.poll()
    if return_code is None:
        state["status"] = "running"
        state["updated_at"] = now_iso
        return
    state["status"] = "completed" if return_code == 0 else "failed"
    state["last_exit_code"] = return_code
    state["last_finished_at"] = now_iso
    state["updated_at"] = now_iso
    _ACTIVE_RUNS.pop(pipeline_id, None)


def _tail_log(log_path: str, *, max_lines: int = 12) -> str:
    path = Path(log_path)
    if not log_path or not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-max_lines:])


def _load_state_unlocked() -> dict[str, Any]:
    if not PIPELINE_STATE_PATH.exists():
        return {}
    try:
        payload = json.loads(PIPELINE_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_state_unlocked(state: dict[str, Any]) -> None:
    PIPELINE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PIPELINE_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

