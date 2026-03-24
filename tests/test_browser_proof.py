"""Tests for browser proof helpers."""

import json

from scripts import browser_proof


def test_vendor_slug_matches_client_side_shape():
    slug = browser_proof.vendor_slug({"vendor_name": "Example Corp AI"})

    assert slug == "example-corp-ai"


def test_load_first_vendor_slug_uses_directory_dataset(tmp_path):
    dataset_path = tmp_path / "directory_dataset.json"
    dataset_path.write_text(
        json.dumps(
            [
                {"vendor_name": "Alpha Labs", "website": "https://alpha.example.com"},
                {"vendor_name": "Bravo", "website": "https://bravo.example.com"},
            ]
        ),
        encoding="utf-8",
    )

    slug = browser_proof.load_first_vendor_slug(dataset_path)

    assert slug == "alpha-labs"


def test_build_surface_specs_includes_public_and_admin_surfaces():
    specs = browser_proof.build_surface_specs("http://127.0.0.1:8787", "alpha-labs")

    assert [spec["surface"] for spec in specs] == ["landing", "vendor", "admin"]
    assert specs[1]["url"].endswith("/vendor.html?vendor=alpha-labs")


def test_resolve_chromium_executable_prefers_cached_browser(tmp_path, monkeypatch):
    cache_root = tmp_path / ".cache" / "ms-playwright" / "chromium-1208" / "chrome-linux64"
    cache_root.mkdir(parents=True)
    executable = cache_root / "chrome"
    executable.write_text("", encoding="utf-8")
    monkeypatch.setattr(browser_proof.Path, "home", lambda: tmp_path)

    result = browser_proof.resolve_chromium_executable()

    assert result == executable


def test_write_manifest_persists_results(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_proof, "PROJECT_ROOT", tmp_path)
    output_dir = tmp_path / "outputs" / "browser_proof" / "m28"
    output_dir.mkdir(parents=True)

    manifest_path = browser_proof.write_manifest(
        output_dir,
        base_url="http://127.0.0.1:8787",
        vendor_slug="alpha-labs",
        results=[{"surface": "landing", "success": True}],
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["base_url"] == "http://127.0.0.1:8787"
    assert payload["vendor_slug"] == "alpha-labs"
    assert payload["results"] == [{"surface": "landing", "success": True}]


def test_humanize_browser_launch_error_surfaces_operator_action():
    message = browser_proof.humanize_browser_launch_error(
        RuntimeError("chrome-headless-shell: error while loading shared libraries: libnspr4.so")
    )

    assert "required OS libraries are missing" in message
    assert "playwright install-deps chromium" in message


def test_assert_text_contains_is_case_insensitive(tmp_path):
    text_path = tmp_path / "vendor.txt"
    text_path.write_text("VENDOR PROFILE", encoding="utf-8")

    result = browser_proof.assert_text_contains(text_path, "Vendor profile")

    assert result == {"success": True, "snippet": "Vendor profile"}
