"""Tests for repo-level LLM configuration."""

from pathlib import Path

from services.extraction.llm_config import load_llm_config


def test_load_llm_config_reads_runtime_limits(tmp_path: Path):
    config_path = tmp_path / "llm.toml"
    config_path.write_text(
        """
[openai]
enabled = false
model = "gpt-5"
request_timeout_seconds = 60
max_page_text_chars = 2200
max_site_text_chars = 9000
max_error_body_chars = 500
""".strip(),
        encoding="utf-8",
    )

    result = load_llm_config(config_path)

    assert result.enabled is False
    assert result.model == "gpt-5"
    assert result.request_timeout_seconds == 60
    assert result.max_page_text_chars == 2200
    assert result.max_site_text_chars == 9000
    assert result.max_error_body_chars == 500
