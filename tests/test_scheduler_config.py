"""Tests for repo-level scheduler configuration."""

from pathlib import Path

from services.pipeline.scheduler_config import load_scheduler_config


def test_load_scheduler_config_reads_cron_and_digest_settings(tmp_path: Path):
    config_path = tmp_path / "scheduler.toml"
    config_path.write_text(
        """
[discovery_schedule]
hour = 6
minute = 30

[digest_schedule]
day_of_week = "fri"
hour = 9
minute = 15
lookback_days = 14
slack_timeout_seconds = 45
""".strip(),
        encoding="utf-8",
    )

    result = load_scheduler_config(config_path)

    assert result.discovery.hour == 6
    assert result.discovery.minute == 30
    assert result.digest.day_of_week == "fri"
    assert result.digest.hour == 9
    assert result.digest.minute == 15
    assert result.digest.lookback_days == 14
    assert result.digest.slack_timeout_seconds == 45
