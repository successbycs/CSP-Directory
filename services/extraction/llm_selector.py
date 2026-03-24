"""Task-based LLM model selector for CSP Directory.

Maps task types to the appropriate OpenAI model based on cost and capability
requirements. Config-driven via config/llm.toml [task_models] section.

Task types:
    classification  — lifecycle_stages, use_cases, icp_buyer, directory_fit
    extraction      — mission, usp, pricing, case_study_details (default)
    complex         — reserved for future richer reasoning tasks

This module is designed to be absorbed into the Autonomous Framework as a
general LLM task router capability. When AF gains a central LLM selector,
this module should delegate to it.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import tomllib

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LLM_CONFIG_PATH = PROJECT_ROOT / "config" / "llm.toml"

# Fallback models when config is unavailable
_FALLBACK_MODELS: dict[str, str] = {
    "classification": "gpt-4o-mini",
    "extraction": "gpt-4o-mini",
    "complex": "gpt-4o",
    "default": "gpt-4o-mini",
}


def get_model_for_task(task_type: str = "default") -> str:
    """Return the configured model for the given task type.

    Resolution order:
    1. OPENAI_MODEL env var (overrides everything — useful for testing)
    2. config/llm.toml [task_models] section
    3. config/llm.toml [openai] model (applies to all tasks)
    4. Hardcoded fallback per task type
    """
    env_override = os.getenv("OPENAI_MODEL", "").strip()
    if env_override and env_override.lower() not in ("auto", ""):
        return env_override

    config = _load_task_models()
    model = config.get(task_type) or config.get("default") or _FALLBACK_MODELS.get(task_type) or _FALLBACK_MODELS["default"]
    return model


def _load_task_models() -> dict[str, str]:
    """Load task→model mapping from llm.toml."""
    if not LLM_CONFIG_PATH.exists():
        return {}
    try:
        with LLM_CONFIG_PATH.open("rb") as f:
            raw = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        logger.warning("Could not load LLM config: %s", e)
        return {}

    task_models = raw.get("task_models", {})
    # Also read the [openai] model as a fallback for all task types
    openai_model = raw.get("openai", {}).get("model", "")
    if openai_model and "default" not in task_models:
        task_models["default"] = openai_model

    return {k: v for k, v in task_models.items() if isinstance(v, str) and v.strip()}
