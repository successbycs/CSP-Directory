"""Tests for the thin admin override script."""

from __future__ import annotations

import sys

from scripts import admin_update_vendor


def test_parse_optional_bool_handles_true_false():
    assert admin_update_vendor._parse_optional_bool("true") is True
    assert admin_update_vendor._parse_optional_bool("false") is False
    assert admin_update_vendor._parse_optional_bool(None) is None


def test_main_updates_vendor_and_prints_success(monkeypatch, capsys):
    monkeypatch.setattr(admin_update_vendor, "load_dotenv", lambda _path: None)
    monkeypatch.setattr(
        admin_update_vendor.supabase_client,
        "update_vendor_admin_fields",
        lambda vendor, **kwargs: {"name": "Gainsight", "website": "https://gainsight.com", **kwargs},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["admin_update_vendor.py", "--vendor", "gainsight", "--include", "false", "--fit", "high"],
    )

    result = admin_update_vendor.main()

    assert result == 0
    assert "Updated vendor: Gainsight" in capsys.readouterr().out
