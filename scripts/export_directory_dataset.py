"""CLI for exporting the public directory dataset from Supabase."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.export.directory_dataset import DEFAULT_DIRECTORY_DATASET_PATH, export_directory_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export the public directory dataset from Supabase.")
    parser.add_argument(
        "--out",
        default=str(DEFAULT_DIRECTORY_DATASET_PATH),
        help="Output path for the directory JSON dataset.",
    )
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    load_dotenv(PROJECT_ROOT / ".env")
    args = build_parser().parse_args()
    output_path = Path(args.out)
    dataset = export_directory_dataset(output_path=output_path)
    logging.info("Exported %s vendor records to %s", len(dataset), output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
