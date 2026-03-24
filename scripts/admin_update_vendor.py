"""Thin CLI for applying admin overrides to vendor directory fields."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.persistence import supabase_client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply manual admin overrides to a vendor record.")
    parser.add_argument("--vendor", required=True, help="Vendor website or vendor name lookup.")
    parser.add_argument("--include", choices=["true", "false"], help="Override include_in_directory.")
    parser.add_argument("--fit", choices=["high", "medium", "low"], help="Override directory_fit.")
    parser.add_argument(
        "--category",
        choices=["cs_core", "cs_adjacent", "support_only", "generic_cx", "infra"],
        help="Override directory_category.",
    )
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    load_dotenv(PROJECT_ROOT / ".env")
    args = build_parser().parse_args()

    updated_vendor = supabase_client.update_vendor_admin_fields(
        args.vendor,
        include_in_directory=_parse_optional_bool(args.include),
        directory_fit=args.fit,
        directory_category=args.category,
    )
    print(f"Updated vendor: {updated_vendor.get('name') or updated_vendor.get('website')}")
    return 0


def _parse_optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() == "true"


if __name__ == "__main__":
    raise SystemExit(main())
