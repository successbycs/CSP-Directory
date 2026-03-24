"""Helpers for loading repo-level scheduler configuration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import tomllib

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEDULER_CONFIG_PATH = PROJECT_ROOT / "config" / "scheduler.toml"


@dataclass(frozen=True)
class DiscoveryScheduleConfig:
    hour: int = 7
    minute: int = 0


@dataclass(frozen=True)
class DigestScheduleConfig:
    day_of_week: str = "mon"
    hour: int = 8
    minute: int = 0
    lookback_days: int = 7
    slack_timeout_seconds: int = 30


@dataclass(frozen=True)
class SchedulerConfig:
    discovery: DiscoveryScheduleConfig = DiscoveryScheduleConfig()
    digest: DigestScheduleConfig = DigestScheduleConfig()


def load_scheduler_config(config_path: Path | None = None) -> SchedulerConfig:
    """Load scheduler settings from TOML."""
    config_path = config_path or SCHEDULER_CONFIG_PATH
    if not config_path.exists():
        return SchedulerConfig()

    try:
        with config_path.open("rb") as config_file:
            raw_config = tomllib.load(config_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        logger.warning("Could not load scheduler config at %s: %s", config_path, error)
        return SchedulerConfig()

    discovery_config = raw_config.get("discovery_schedule", {})
    digest_config = raw_config.get("digest_schedule", {})

    return SchedulerConfig(
        discovery=DiscoveryScheduleConfig(
            hour=_bounded_int(
                _read_dict_value(discovery_config, "hour"),
                setting_name="discovery_schedule.hour",
                config_path=config_path,
                default=7,
                minimum=0,
                maximum=23,
            ),
            minute=_bounded_int(
                _read_dict_value(discovery_config, "minute"),
                setting_name="discovery_schedule.minute",
                config_path=config_path,
                default=0,
                minimum=0,
                maximum=59,
            ),
        ),
        digest=DigestScheduleConfig(
            day_of_week=_normalized_string(
                _read_dict_value(digest_config, "day_of_week"),
                setting_name="digest_schedule.day_of_week",
                config_path=config_path,
                default="mon",
            ),
            hour=_bounded_int(
                _read_dict_value(digest_config, "hour"),
                setting_name="digest_schedule.hour",
                config_path=config_path,
                default=8,
                minimum=0,
                maximum=23,
            ),
            minute=_bounded_int(
                _read_dict_value(digest_config, "minute"),
                setting_name="digest_schedule.minute",
                config_path=config_path,
                default=0,
                minimum=0,
                maximum=59,
            ),
            lookback_days=_bounded_int(
                _read_dict_value(digest_config, "lookback_days"),
                setting_name="digest_schedule.lookback_days",
                config_path=config_path,
                default=7,
                minimum=1,
                maximum=365,
            ),
            slack_timeout_seconds=_bounded_int(
                _read_dict_value(digest_config, "slack_timeout_seconds"),
                setting_name="digest_schedule.slack_timeout_seconds",
                config_path=config_path,
                default=30,
                minimum=1,
                maximum=120,
            ),
        ),
    )


def _read_dict_value(container: object, key: str) -> object | None:
    if isinstance(container, dict):
        return container.get(key)
    return None


def _normalized_string(
    value: object,
    *,
    setting_name: str,
    config_path: Path,
    default: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        if value is not None:
            logger.warning("Invalid %s in %s; using default %s", setting_name, config_path, default)
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
