"""Helpers for loading repo-level export configuration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import tomllib

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPORT_CONFIG_PATH = PROJECT_ROOT / "config" / "export.toml"
DEFAULT_GOOGLE_WORKSHEET_NAME = "vendors"
DEFAULT_GOOGLE_SHEETS_COLUMNS = (
    "vendor_name",
    "website",
    "mission",
    "usp",
    "icp",
    "use_cases",
    "lifecycle_stages",
    "pricing",
    "free_trial",
    "soc2",
    "founded",
    "case_studies",
    "customers",
    "value_statements",
    "confidence",
    "evidence_urls",
)


@dataclass(frozen=True)
class ExportConfig:
    """Configurable settings for human-facing exports."""

    google_worksheet_name: str = DEFAULT_GOOGLE_WORKSHEET_NAME
    google_sheets_columns: tuple[str, ...] = DEFAULT_GOOGLE_SHEETS_COLUMNS


def load_export_config(config_path: Path | None = None) -> ExportConfig:
    """Load export settings from TOML."""
    config_path = config_path or EXPORT_CONFIG_PATH
    if not config_path.exists():
        return ExportConfig()

    try:
        with config_path.open("rb") as config_file:
            raw_config = tomllib.load(config_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        logger.warning("Could not load export config at %s: %s", config_path, error)
        return ExportConfig()

    export_config = raw_config.get("google_sheets", {})
    if not isinstance(export_config, dict):
        logger.warning("Export config at %s is missing [google_sheets]", config_path)
        return ExportConfig()

    return ExportConfig(
        google_worksheet_name=_normalized_string(
            export_config.get("worksheet_name"),
            setting_name="google_sheets.worksheet_name",
            config_path=config_path,
            default=DEFAULT_GOOGLE_WORKSHEET_NAME,
        ),
        google_sheets_columns=_normalized_columns(
            export_config.get("columns"),
            config_path=config_path,
        ),
    )


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


def _normalized_columns(value: object, *, config_path: Path) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_GOOGLE_SHEETS_COLUMNS
    if not isinstance(value, list):
        logger.warning("Invalid google_sheets.columns in %s; using defaults", config_path)
        return DEFAULT_GOOGLE_SHEETS_COLUMNS

    columns = tuple(str(column).strip() for column in value if str(column).strip())
    if not columns:
        logger.warning("Invalid google_sheets.columns in %s; using defaults", config_path)
        return DEFAULT_GOOGLE_SHEETS_COLUMNS
    return columns
