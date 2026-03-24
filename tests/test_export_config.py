"""Tests for repo-level export configuration."""

from pathlib import Path

from services.export.export_config import load_export_config


def test_load_export_config_reads_worksheet_and_columns(tmp_path: Path):
    config_path = tmp_path / "export.toml"
    config_path.write_text(
        """
[google_sheets]
worksheet_name = "directory_vendors"
columns = ["vendor_name", "website", "confidence"]
""".strip(),
        encoding="utf-8",
    )

    result = load_export_config(config_path)

    assert result.google_worksheet_name == "directory_vendors"
    assert result.google_sheets_columns == ("vendor_name", "website", "confidence")
