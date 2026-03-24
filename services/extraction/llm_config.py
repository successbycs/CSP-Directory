"""Helpers for loading repo-level LLM extraction configuration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import tomllib

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LLM_CONFIG_PATH = PROJECT_ROOT / "config" / "llm.toml"
DEFAULT_OPENAI_MODEL = "gpt-5-mini"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 45
DEFAULT_MAX_PAGE_TEXT_CHARS = 1800
DEFAULT_MAX_SITE_TEXT_CHARS = 8000
DEFAULT_MAX_ERROR_BODY_CHARS = 300


@dataclass(frozen=True)
class LLMConfig:
    """Configurable runtime settings for optional OpenAI enrichment."""

    enabled: bool = True
    model: str = DEFAULT_OPENAI_MODEL
    request_timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS
    max_page_text_chars: int = DEFAULT_MAX_PAGE_TEXT_CHARS
    max_site_text_chars: int = DEFAULT_MAX_SITE_TEXT_CHARS
    max_error_body_chars: int = DEFAULT_MAX_ERROR_BODY_CHARS


def load_llm_config(config_path: Path | None = None) -> LLMConfig:
    """Load LLM extraction settings from TOML."""
    config_path = config_path or LLM_CONFIG_PATH
    if not config_path.exists():
        return LLMConfig()

    try:
        with config_path.open("rb") as config_file:
            raw_config = tomllib.load(config_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        logger.warning("Could not load LLM config at %s: %s", config_path, error)
        return LLMConfig()

    llm_config = raw_config.get("openai", {})
    if not isinstance(llm_config, dict):
        logger.warning("LLM config at %s is missing [openai]", config_path)
        return LLMConfig()

    return LLMConfig(
        enabled=_normalized_bool(llm_config.get("enabled"), default=True),
        model=_normalized_string(
            llm_config.get("model"),
            setting_name="openai.model",
            config_path=config_path,
            default=DEFAULT_OPENAI_MODEL,
        ),
        request_timeout_seconds=_bounded_int(
            llm_config.get("request_timeout_seconds"),
            setting_name="openai.request_timeout_seconds",
            config_path=config_path,
            default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
            minimum=1,
            maximum=180,
        ),
        max_page_text_chars=_bounded_int(
            llm_config.get("max_page_text_chars"),
            setting_name="openai.max_page_text_chars",
            config_path=config_path,
            default=DEFAULT_MAX_PAGE_TEXT_CHARS,
            minimum=200,
            maximum=10000,
        ),
        max_site_text_chars=_bounded_int(
            llm_config.get("max_site_text_chars"),
            setting_name="openai.max_site_text_chars",
            config_path=config_path,
            default=DEFAULT_MAX_SITE_TEXT_CHARS,
            minimum=1000,
            maximum=50000,
        ),
        max_error_body_chars=_bounded_int(
            llm_config.get("max_error_body_chars"),
            setting_name="openai.max_error_body_chars",
            config_path=config_path,
            default=DEFAULT_MAX_ERROR_BODY_CHARS,
            minimum=50,
            maximum=2000,
        ),
    )


def _normalized_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _normalized_string(
    value: object,
    *,
    setting_name: str,
    config_path: Path,
    default: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        if value is not None:
            logger.warning(
                "Invalid %s in %s; using default %s",
                setting_name,
                config_path,
                default,
            )
        return default
    return value.strip()


def _bounded_int(
    value: object,
    *,
    setting_name: str,
    config_path: Path,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if not isinstance(value, int):
        if value is not None:
            logger.warning(
                "Invalid %s in %s; expected an integer and using default %s",
                setting_name,
                config_path,
                default,
            )
        return default
    if value < minimum:
        logger.warning("%s in %s was below %s; using %s", setting_name, config_path, minimum, minimum)
        return minimum
    if value > maximum:
        logger.warning("%s in %s exceeded %s; using %s", setting_name, config_path, maximum, maximum)
        return maximum
    return value
