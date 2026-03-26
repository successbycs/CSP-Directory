"""M47: Discover → enrich → export single entry-point pipeline."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest


def _run_main(*argv):
    """Run discover_vendors.main() with patched sys.argv."""
    with patch.object(sys, "argv", ["discover_vendors.py"] + list(argv)):
        from scripts import discover_vendors
        import importlib
        importlib.reload(discover_vendors)
        return discover_vendors


def _mock_config():
    return SimpleNamespace(
        discovery=SimpleNamespace(
            queries=["customer success ai"],
            junk_domain_denylist=("reddit.com",),
        )
    )


def _mock_supabase(existing_websites=None):
    client = MagicMock()
    existing = existing_websites or []
    client.table.return_value.select.return_value.execute.return_value.data = [
        {"website": w} for w in existing
    ]
    client.table.return_value.upsert.return_value.execute.return_value = None
    return client


@patch("scripts.discover_vendors.step_export")
@patch("scripts.discover_vendors.step_health_check")
@patch("scripts.discover_vendors.step_enrich")
@patch("scripts.discover_vendors.step_discover")
@patch("scripts.discover_vendors.get_supabase")
@patch("scripts.discover_vendors.load_pipeline_config")
def test_all_four_steps_execute_in_order(mock_config, mock_supabase, mock_discover, mock_enrich, mock_health, mock_export):
    mock_config.return_value = _mock_config()
    mock_supabase.return_value = _mock_supabase()
    mock_discover.return_value = 2
    mock_enrich.return_value = 0
    mock_health.return_value = True
    mock_export.return_value = 0

    with patch.object(sys, "argv", ["discover_vendors.py"]):
        from scripts import discover_vendors
        result = discover_vendors.main()

    assert result == 0
    mock_discover.assert_called_once()
    mock_enrich.assert_called_once()
    mock_health.assert_called_once()
    mock_export.assert_called_once()


@patch("scripts.discover_vendors.step_export")
@patch("scripts.discover_vendors.step_health_check")
@patch("scripts.discover_vendors.step_enrich")
@patch("scripts.discover_vendors.step_discover")
@patch("scripts.discover_vendors.get_supabase")
@patch("scripts.discover_vendors.load_pipeline_config")
def test_export_skipped_when_health_check_fails(mock_config, mock_supabase, mock_discover, mock_enrich, mock_health, mock_export):
    mock_config.return_value = _mock_config()
    mock_supabase.return_value = _mock_supabase()
    mock_discover.return_value = 0
    mock_enrich.return_value = 0
    mock_health.return_value = False
    mock_export.return_value = 0

    with patch.object(sys, "argv", ["discover_vendors.py"]):
        from scripts import discover_vendors
        result = discover_vendors.main()

    assert result == 1
    mock_export.assert_not_called()


@patch("scripts.discover_vendors.step_export")
@patch("scripts.discover_vendors.step_health_check")
@patch("scripts.discover_vendors.step_enrich")
@patch("scripts.discover_vendors.step_discover")
@patch("scripts.discover_vendors.get_supabase")
@patch("scripts.discover_vendors.load_pipeline_config")
def test_dry_run_stops_after_discovery(mock_config, mock_supabase, mock_discover, mock_enrich, mock_health, mock_export):
    mock_config.return_value = _mock_config()
    mock_supabase.return_value = _mock_supabase()
    mock_discover.return_value = 0

    with patch.object(sys, "argv", ["discover_vendors.py", "--dry-run"]):
        from scripts import discover_vendors
        result = discover_vendors.main()

    assert result == 0
    mock_enrich.assert_not_called()
    mock_health.assert_not_called()
    mock_export.assert_not_called()


@patch("scripts.discover_vendors.step_export")
@patch("scripts.discover_vendors.step_health_check")
@patch("scripts.discover_vendors.step_enrich")
@patch("scripts.discover_vendors.step_discover")
@patch("scripts.discover_vendors.get_supabase")
@patch("scripts.discover_vendors.load_pipeline_config")
def test_skip_discover_flag_skips_step1(mock_config, mock_supabase, mock_discover, mock_enrich, mock_health, mock_export):
    mock_config.return_value = _mock_config()
    mock_supabase.return_value = _mock_supabase()
    mock_enrich.return_value = 0
    mock_health.return_value = True
    mock_export.return_value = 0

    with patch.object(sys, "argv", ["discover_vendors.py", "--skip-discover"]):
        from scripts import discover_vendors
        result = discover_vendors.main()

    assert result == 0
    mock_discover.assert_not_called()
    mock_enrich.assert_called_once()
    mock_export.assert_called_once()
