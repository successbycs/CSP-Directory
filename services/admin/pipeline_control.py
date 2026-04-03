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
        "description": "Runs G2 RapidAPI enrichment over all include_in_directory vendors. Fills g2_url, g2_rating, g2_review_count, g2_categories.",
        "command": ["scripts/enrich_g2_rapidapi.py"],
    },
    {
        "pipeline_id": "firmographic_enrichment",
        "name": "Firmographic Enrichment (Datagma)",
        "description": "Enriches vendors with firmographic data via Datagma (RapidAPI). Fills founded, hq_address, funding_stage, total_funding, ceo_name, company_size, revenue. Requires RAPIDAPI_KEY + Datagma subscription.",
        "command": ["scripts/enrich_firmographic.py"],
    },
    {
        "pipeline_id": "linkedin_enrichment",
        "name": "LinkedIn Enrichment",
        "description": "Enriches vendors with LinkedIn data via LinkedIn Data API (RapidAPI). Fills ceo_linkedin, linkedin_url, leadership. Requires RAPIDAPI_KEY + LinkedIn Data API subscription.",
        "command": ["scripts/enrich_linkedin.py"],
    },
    {
        "pipeline_id": "site_crawl_enrichment",
        "name": "Site Crawl (Tiered)",
        "description": "Re-crawls vendor homepages using three-tier strategy: Tier 1 (free HTTP) → Tier 2 (Apify RAG) → Tier 3 (Apify WCC + proxy). Requires N8N_CRAWL_TIER1/2/3_WEBHOOK env vars.",
        "command": ["scripts/enrich_site_crawl.py"],
    },
    {
        "pipeline_id": "google_discovery",
        "name": "Google Discovery",
        "description": "Discovers new vendor candidates via Apify Google Search. Requires N8N_DISCOVERY_WEBHOOK and APIFY_API_TOKEN.",
        "command": ["scripts/run_discovery.py"],
    },
    {
        "pipeline_id": "full_enrichment_cycle",
        "name": "Full Enrichment Cycle",
        "description": "Runs all enrichment sources in sequence: site crawl → LLM extraction → Datagma firmographic → LinkedIn → G2 → pricing. Use for backfill or full vendor refresh.",
        "command": ["scripts/run_full_enrichment_cycle.py"],
    },
    # M76 Ops Enrichment Workbench — per-step pipelines
    {
        "pipeline_id": "ops_discovery_run",
        "name": "Step 1 — Google Discovery",
        "description": "Discover new vendor candidates via Apify Google Search. Writes to cs_vendor_candidates.",
        "command": ["-m", "services.ops.run_discovery"],
    },
    {
        "pipeline_id": "ops_crawl_tier1",
        "name": "Step 2a — Tier 1 Crawl (Direct HTTP)",
        "description": "Crawl vendor website via direct HTTP fetch (free). Writes to vendor_pages + crawl_tier1_result.",
        "command": ["-m", "services.ops.run_crawl", "--tier", "1"],
    },
    {
        "pipeline_id": "ops_crawl_tier2",
        "name": "Step 2b — Tier 2 Crawl (Apify RAG)",
        "description": "Crawl vendor website via Apify RAG Web Browser (~$0.001/page). Writes to vendor_pages + crawl_tier2_result.",
        "command": ["-m", "services.ops.run_crawl", "--tier", "2"],
    },
    {
        "pipeline_id": "ops_crawl_tier3",
        "name": "Step 2c — Tier 3 Crawl (Apify WCC + Proxy)",
        "description": "Crawl vendor website via Apify WCC with anti-bot proxy (~$0.004/page). Writes to vendor_pages + crawl_tier3_result.",
        "command": ["-m", "services.ops.run_crawl", "--tier", "3"],
    },
    {
        "pipeline_id": "ops_crawl_datagma",
        "name": "Step 3 — Datagma Firmographic",
        "description": "Enrich vendor firmographic data via Datagma (RapidAPI). Writes to crawl_datagma_result. Requires RAPIDAPI_KEY.",
        "command": ["-m", "services.ops.run_datagma"],
    },
    {
        "pipeline_id": "ops_crawl_g2",
        "name": "Step 4 — G2 Enrichment",
        "description": "Enrich vendor G2 data via RapidAPI G2 API. Writes to crawl_g2_result. Requires RAPIDAPI_KEY.",
        "command": ["-m", "services.ops.run_g2"],
    },
    {
        "pipeline_id": "ops_crawl_llm",
        "name": "Step 5 — LLM Extraction (Ollama RAG)",
        "description": "Extract structured fields from vendor_pages using Ollama Mistral + nomic-embed-text pgvector RAG. Writes to crawl_llm_result. Requires vendor_pages >= 10 rows.",
        "command": ["-m", "services.ops.run_llm_extraction"],
    },
    {
        "pipeline_id": "ops_merge",
        "name": "Step 6 — Clean Merge",
        "description": "Merge all crawl_*_result columns into main cs_vendors schema columns using priority rules. Writes source_field_map.",
        "command": ["-m", "services.ops.run_merge"],
    },
    {
        "pipeline_id": "ops_llm_enrichment_batch",
        "name": "Step 7 — Batch LLM Enrichment (GPT-4o)",
        "description": "Run crawl → embed → GPT-4o RAG extraction for all vendors not yet enriched. Updates directory_dataset.json incrementally. Falls back to local Ollama if available.",
        "command": ["scripts/run_batch_enrichment.py"],
    },
    {
        "pipeline_id": "ops_ai_summary",
        "name": "Step 8 — AI Summary (GPT-4o mini)",
        "description": "Generate a 400-word vendor summary using GPT-4o mini from live web fetch + stored pages. Stored in ai_summary column and exported to directory dataset. Skips vendors that already have a summary.",
        "command": ["-m", "services.ops.run_ai_summary"],
    },
    {
        "pipeline_id": "ops_export_dataset",
        "name": "Step 9 — Export Dataset to Vercel",
        "description": "Pull latest vendor data from Supabase and write docs/website/data/directory_dataset.json. Run after any enrichment to update the live directory.",
        "command": ["scripts/export_directory_dataset.py"],
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


def trigger_pipeline_run(pipeline_id: str, vendor_website: str = "") -> dict[str, Any]:
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
        if vendor_website:
            command += ["--vendor", str(vendor_website)]
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


def reset_pipeline_state(pipeline_id: str) -> dict[str, Any]:
    """Force a stuck pipeline back to failed so it can be re-triggered."""
    normalized_id = str(pipeline_id or "").strip()
    spec = next((s for s in _PIPELINE_SPECS if s["pipeline_id"] == normalized_id), None)
    if spec is None:
        raise ValueError(f"Unknown pipeline_id: {normalized_id}")
    with _STATE_LOCK:
        state = _load_state_unlocked()
        current = dict(state.get(normalized_id) or {})
        current.update({
            "status": "failed",
            "last_finished_at": _now_iso(),
            "last_exit_code": -1,
            "updated_at": _now_iso(),
        })
        state[normalized_id] = current
        _save_state_unlocked(state)
        _ACTIVE_RUNS.pop(normalized_id, None)
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

