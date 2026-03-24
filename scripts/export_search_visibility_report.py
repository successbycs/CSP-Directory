"""CLI for exporting role-based search visibility review artifacts."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.export.search_visibility_report import (
    DEFAULT_SEARCH_VISIBILITY_HTML_PATH,
    DEFAULT_SEARCH_VISIBILITY_REPORT_PATH,
    export_search_visibility_artifacts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export role-based search visibility JSON and HTML artifacts.")
    parser.add_argument(
        "--out",
        default=str(DEFAULT_SEARCH_VISIBILITY_REPORT_PATH),
        help="Output path for the search visibility JSON report.",
    )
    parser.add_argument(
        "--html-out",
        default=str(DEFAULT_SEARCH_VISIBILITY_HTML_PATH),
        help="Output path for the search visibility HTML report.",
    )
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    load_dotenv(PROJECT_ROOT / ".env")
    args = build_parser().parse_args()
    report = export_search_visibility_artifacts(
        report_output_path=Path(args.out),
        html_output_path=Path(args.html_out),
    )
    metrics = report.get("metrics") or {}
    logging.info(
        "Exported search visibility report with %s buyer-role prompts, %s ranked results, and %s surfaced vendors",
        metrics.get("query_count", 0),
        metrics.get("ranking_count", 0),
        metrics.get("vendor_count", 0),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
