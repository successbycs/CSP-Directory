"""Small CLI runner for the MVP pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import socket
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.pipeline.run_mvp_pipeline import run_mvp_pipeline
from services.export.directory_dataset import DEFAULT_DIRECTORY_DATASET_PATH
from services.export.google_sheets import write_rows_to_csv
from services.export.search_visibility_report import (
    DEFAULT_SEARCH_VISIBILITY_HTML_PATH,
    DEFAULT_SEARCH_VISIBILITY_REPORT_PATH,
)
from services.export.vendor_review_dataset import (
    DEFAULT_VENDOR_REVIEW_DATASET_PATH,
    DEFAULT_VENDOR_REVIEW_HTML_PATH,
)

DEFAULT_CSV_OUTPUT = PROJECT_ROOT / "outputs" / "vendor_rows.csv"


def load_environment() -> None:
    """Load environment variables from the local .env file."""
    load_dotenv(PROJECT_ROOT / ".env")


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Run the MVP vendor intelligence pipeline for a search query.",
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Optional search query used for vendor discovery. Leave blank to use config/pipeline_config.json queries.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON output",
    )
    parser.add_argument(
        "--csv-out",
        default=str(DEFAULT_CSV_OUTPUT),
        help="CSV output path for Google Sheets-ready vendor rows",
    )
    parser.add_argument(
        "--preview-host",
        default="127.0.0.1",
        help="Host used for the local admin/static preview server",
    )
    parser.add_argument(
        "--preview-port",
        type=int,
        default=8787,
        help="Port used for the local admin/static preview server",
    )
    parser.add_argument(
        "--serve-preview",
        dest="serve_preview",
        action="store_true",
        help="Start the local preview server after the pipeline run",
    )
    parser.add_argument(
        "--no-serve-preview",
        dest="serve_preview",
        action="store_false",
        help="Skip starting the local preview server after the pipeline run",
    )
    parser.set_defaults(serve_preview=True)
    return parser


def main() -> int:
    """Run the CLI entrypoint."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    load_environment()
    args = build_parser().parse_args()
    rows = run_mvp_pipeline(args.query)
    csv_path = Path(args.csv_out)

    write_rows_to_csv(rows, csv_path)
    logging.info("Wrote %s vendor rows to %s", len(rows), csv_path)
    logging.info("Directory dataset: %s", DEFAULT_DIRECTORY_DATASET_PATH)
    logging.info("Vendor review dataset: %s", DEFAULT_VENDOR_REVIEW_DATASET_PATH)
    logging.info("Vendor review report: %s", DEFAULT_VENDOR_REVIEW_HTML_PATH)
    logging.info("Search visibility report: %s", DEFAULT_SEARCH_VISIBILITY_REPORT_PATH)
    logging.info("Search visibility HTML: %s", DEFAULT_SEARCH_VISIBILITY_HTML_PATH)

    if args.serve_preview:
        _ensure_preview_server(args.preview_host, args.preview_port)
        logging.info("Preview landing page: http://%s:%s/landing.html", args.preview_host, args.preview_port)
        logging.info("Preview admin page: http://%s:%s/admin.html", args.preview_host, args.preview_port)
        logging.info(
            "Preview vendor review report: http://%s:%s/outputs/vendor_review.html",
            args.preview_host,
            args.preview_port,
        )
        logging.info(
            "Preview search visibility report: http://%s:%s/outputs/search_visibility_report.html",
            args.preview_host,
            args.preview_port,
        )
    else:
        logging.info(
            "Preview server disabled. Open %s directly or run `.venv/bin/python -m services.admin.admin_api --host %s --port %s`.",
            DEFAULT_VENDOR_REVIEW_HTML_PATH,
            args.preview_host,
            args.preview_port,
        )

    if args.pretty:
        print(json.dumps(rows, indent=2))
    else:
        print(json.dumps(rows))

    return 0

def _ensure_preview_server(host: str, port: int) -> None:
    """Start the local admin/static preview server when it is not already running."""
    if _port_is_open(host, port):
        logging.info("Preview server already running at http://%s:%s", host, port)
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

    for _ in range(20):
        if _port_is_open(host, port):
            logging.info("Started preview server at http://%s:%s", host, port)
            return
        time.sleep(0.15)

    logging.warning("Preview server did not become reachable at http://%s:%s", host, port)


def _port_is_open(host: str, port: int) -> bool:
    """Return True when a TCP port is reachable."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


if __name__ == "__main__":
    raise SystemExit(main())
