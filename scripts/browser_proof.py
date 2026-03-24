"""Capture render-level browser proof for key public and admin surfaces."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_PATH = PROJECT_ROOT / "outputs" / "directory_dataset.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "browser_proof" / "m28"


def build_parser() -> argparse.ArgumentParser:
    """Return the CLI parser for browser proof capture."""
    parser = argparse.ArgumentParser(description="Capture headless browser proof for M28 surfaces.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--dataset-path", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--timeout-ms", type=int, default=15000)
    parser.add_argument(
        "--no-start-server",
        dest="start_server",
        action="store_false",
        help="Assume the preview server is already running.",
    )
    parser.set_defaults(start_server=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the browser-proof workflow."""
    args = build_parser().parse_args(argv)
    dataset_path = Path(args.dataset_path)
    output_dir = Path(args.output_dir)
    base_url = f"http://{args.host}:{args.port}"

    if args.start_server:
        ensure_preview_server(args.host, args.port)
    elif not port_is_open(args.host, args.port):
        raise RuntimeError(f"Preview server is not reachable at {base_url}")

    vendor_slug = load_first_vendor_slug(dataset_path)
    results = capture_browser_proof(
        build_surface_specs(base_url, vendor_slug),
        output_dir=output_dir,
        timeout_ms=args.timeout_ms,
    )
    manifest_path = write_manifest(output_dir, base_url=base_url, vendor_slug=vendor_slug, results=results)

    failed = [result for result in results if not result["success"]]
    print(f"Browser proof manifest: {manifest_path}")
    for result in results:
        status = "ok" if result["success"] else "failed"
        print(f"- {result['surface']} [{status}] -> {result['url']}")
    return 1 if failed else 0


def build_surface_specs(base_url: str, vendor_slug: str) -> list[dict[str, str]]:
    """Return the surface definitions used for proof capture."""
    return [
        {
            "surface": "landing",
            "url": f"{base_url}/landing.html",
            "ready_selector": "#vendor-results .vendor-card-link",
            "ready_js": (
                "() => { const status = document.querySelector('#directory-status'); "
                "return Boolean(status && !status.textContent.includes('Loading')); }"
            ),
            "text_snippet": "The Customer Success Technology Directory",
        },
        {
            "surface": "vendor",
            "url": f"{base_url}/vendor.html?vendor={vendor_slug}",
            "ready_selector": "#vendor-profile h1",
            "ready_js": (
                "() => { const heading = document.querySelector('#vendor-profile h1'); "
                "return Boolean(heading && heading.textContent.trim() && heading.textContent !== 'Profile unavailable'); }"
            ),
            "text_snippet": "Vendor profile",
        },
        {
            "surface": "admin",
            "url": f"{base_url}/admin.html",
            "ready_selector": "#vendors-body tr",
            "ready_js": (
                "() => { const rows = document.querySelectorAll('#vendors-body tr'); "
                "const metrics = document.querySelector('#lead-capture-metrics'); "
                "return rows.length > 0 && metrics && !metrics.textContent.includes('Loading'); }"
            ),
            "text_snippet": "Pipeline admin dashboard",
        },
    ]


def capture_browser_proof(
    surface_specs: list[dict[str, str]],
    *,
    output_dir: Path,
    timeout_ms: int,
) -> list[dict[str, Any]]:
    """Open each surface, assert rendered content, and save proof artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                executable_path=str(resolve_chromium_executable()),
            )
        except Exception as error:  # pragma: no cover - runtime dependency path
            raise RuntimeError(humanize_browser_launch_error(error)) from error
        context = browser.new_context(viewport={"width": 1440, "height": 1080})
        try:
            for spec in surface_specs:
                results.append(capture_surface(context, spec, output_dir=output_dir, timeout_ms=timeout_ms))
        finally:
            context.close()
            browser.close()

    return results


def capture_surface(context, spec: dict[str, str], *, output_dir: Path, timeout_ms: int) -> dict[str, Any]:
    """Capture one surface and return its assertion/artifact result."""
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    surface = spec["surface"]
    screenshot_path = output_dir / f"{surface}.png"
    dom_path = output_dir / f"{surface}.dom.html"
    text_path = output_dir / f"{surface}.txt"

    result: dict[str, Any] = {
        "surface": surface,
        "url": spec["url"],
        "success": False,
        "title": "",
        "screenshot_path": str(screenshot_path.relative_to(PROJECT_ROOT)),
        "dom_path": str(dom_path.relative_to(PROJECT_ROOT)),
        "text_path": str(text_path.relative_to(PROJECT_ROOT)),
        "errors": errors,
    }
    try:
        page.goto(spec["url"], wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_selector(spec["ready_selector"], timeout=timeout_ms)
        page.wait_for_function(spec["ready_js"], timeout=timeout_ms)
        page.wait_for_timeout(500)

        dom_path.write_text(page.content(), encoding="utf-8")
        text_path.write_text(page.locator("body").inner_text(timeout=timeout_ms), encoding="utf-8")
        page.screenshot(path=str(screenshot_path), full_page=True)

        result["title"] = page.title()
        result["text_assertion"] = assert_text_contains(text_path, spec["text_snippet"])
        result["success"] = result["text_assertion"]["success"] and not errors
        if not result["success"] and errors:
            result["error"] = "pageerror during render"
        elif not result["success"]:
            result["error"] = result["text_assertion"]["error"]
    except PlaywrightTimeoutError as error:
        result["error"] = f"timeout: {error}"
    except Exception as error:  # pragma: no cover - defensive runtime path
        result["error"] = str(error)
    finally:
        page.close()
    return result


def assert_text_contains(text_path: Path, snippet: str) -> dict[str, Any]:
    """Return a simple visible-text assertion result."""
    text = text_path.read_text(encoding="utf-8")
    if snippet.lower() in text.lower():
        return {"success": True, "snippet": snippet}
    return {"success": False, "snippet": snippet, "error": f"visible text did not contain {snippet!r}"}


def humanize_browser_launch_error(error: Exception) -> str:
    """Return a clearer operator-facing browser dependency error."""
    message = str(error)
    if "error while loading shared libraries" in message or "libnspr4.so" in message:
        return (
            "Chromium could not launch because required OS libraries are missing. "
            "An operator must install the Playwright/Chromium system dependencies, for example with "
            "`sudo .venv/bin/python -m playwright install-deps chromium`."
        )
    return message


def write_manifest(
    output_dir: Path,
    *,
    base_url: str,
    vendor_slug: str,
    results: list[dict[str, Any]],
) -> Path:
    """Write the browser-proof manifest."""
    manifest = {
        "base_url": base_url,
        "vendor_slug": vendor_slug,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": results,
    }
    manifest_path = output_dir / "proof_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def resolve_chromium_executable() -> Path:
    """Return the preferred Chromium executable for browser proof runs."""
    candidates = sorted(
        (Path.home() / ".cache" / "ms-playwright").glob("chromium-*/chrome-linux64/chrome"),
        reverse=True,
    )
    if candidates:
        return candidates[0]
    raise RuntimeError(
        "No Playwright Chromium executable was found. Run `.venv/bin/python -m playwright install chromium` first."
    )


def load_first_vendor_slug(dataset_path: Path) -> str:
    """Return the slug for the first vendor in the exported directory dataset."""
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"Directory dataset is empty or invalid at {dataset_path}")
    first_vendor = payload[0]
    if not isinstance(first_vendor, dict):
        raise RuntimeError(f"Directory dataset is invalid at {dataset_path}")
    return vendor_slug(first_vendor)


def vendor_slug(vendor: dict[str, Any]) -> str:
    """Match the client-side vendor slug implementation."""
    base = str(vendor.get("vendor_name") or vendor.get("website") or "vendor")
    return "-".join(part for part in "".join(char.lower() if char.isalnum() else "-" for char in base).split("-") if part)


def ensure_preview_server(host: str, port: int) -> None:
    """Start the local preview server when it is not already reachable."""
    if port_is_open(host, port):
        return

    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "services.admin.admin_api",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    for _ in range(40):
        if port_is_open(host, port):
            return
        time.sleep(0.25)
    raise RuntimeError(f"Preview server did not become reachable at http://{host}:{port}")


def port_is_open(host: str, port: int) -> bool:
    """Return True when the target TCP port is reachable."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


if __name__ == "__main__":
    raise SystemExit(main())
