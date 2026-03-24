"""Manual integration diagnostics for Supabase and Google Sheets."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.export import google_sheets
from services.persistence import supabase_client


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Check Supabase and Google Sheets integration configuration.",
    )
    parser.add_argument(
        "--write-supabase-test-row",
        action="store_true",
        help="Upsert a clearly marked diagnostic row into Supabase.",
    )
    parser.add_argument(
        "--write-google-test-row",
        action="store_true",
        help="Append a clearly marked diagnostic row to Google Sheets.",
    )
    return parser


def main() -> int:
    """Run manual integration diagnostics."""
    load_dotenv(PROJECT_ROOT / ".env")
    args = build_parser().parse_args()

    supabase_results = check_supabase(write_test_row=args.write_supabase_test_row)
    google_results = check_google_sheets(write_test_row=args.write_google_test_row)

    print_summary(supabase_results, google_results)
    return 0


def check_supabase(*, write_test_row: bool) -> dict[str, bool]:
    """Run Supabase diagnostics."""
    results = {
        "config_loaded": False,
        "read_worked": False,
        "write_worked": None,
    }

    config = supabase_client.get_supabase_config()
    results["config_loaded"] = config is not None
    if config is None:
        print("Supabase config loaded: no")
        print("Supabase read worked: no")
        print("Supabase write worked: no")
        return results

    print("Supabase config loaded: yes")

    try:
        client = supabase_client.get_supabase_client()
        response = client.table("cs_vendors").select("website", count="exact").limit(1).execute()
        row_count = response.count if response.count is not None else len(response.data or [])
        print(f"Supabase read worked: yes ({row_count} row(s) visible in cs_vendors)")
        results["read_worked"] = True
    except Exception as error:
        print(f"Supabase read worked: no ({error})")
        return results

    if not write_test_row:
        print("Supabase write worked: not run")
        return results

    try:
        diagnostic_row = {
            "name": "Diagnostic Test Vendor",
            "website": "https://diagnostic-test.example.com",
            "source": "diagnostic_script",
            "raw_description": "Diagnostic test row",
        }
        client.table("cs_vendors").upsert(diagnostic_row, on_conflict="website").execute()
        print("Supabase write worked: yes")
        results["write_worked"] = True
    except Exception as error:
        print(f"Supabase write worked: no ({error})")

    return results


def check_google_sheets(*, write_test_row: bool) -> dict[str, bool]:
    """Run Google Sheets diagnostics."""
    results = {
        "config_loaded": False,
        "append_worked": None,
    }

    sheet_id = os.getenv("GOOGLE_SHEETS_ID")
    credentials_info = google_sheets._load_google_sheets_credentials_info()

    results["config_loaded"] = bool(sheet_id) and credentials_info is not None
    if not results["config_loaded"]:
        print("Google Sheets config loaded: no")
        print("Google Sheets append worked: no")
        return results

    print("Google Sheets config loaded: yes")
    worksheet_name = google_sheets._get_google_worksheet_name()

    try:
        service = google_sheets._build_google_sheets_service(credentials_info)
        header_range = (
            f"{worksheet_name}!A1:"
            f"{google_sheets._sheet_column_letter(len(google_sheets.GOOGLE_SHEETS_COLUMNS))}1"
        )
        header_values = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=header_range,
        ).execute().get("values", [])
        print("Google Sheets read worked: yes")
        if header_values[:1] == [google_sheets.GOOGLE_SHEETS_COLUMNS]:
            print(f"Google Sheets header aligned: yes ({worksheet_name})")
        else:
            print(f"Google Sheets header aligned: no ({worksheet_name})")
    except Exception as error:
        print(f"Google Sheets read worked: no ({error})")
        print("Google Sheets append worked: no")
        return results

    if not write_test_row:
        print("Google Sheets append worked: not run")
        return results

    try:
        diagnostic_row = {
            "vendor_name": "Diagnostic Test Vendor",
            "website": "https://example.com",
            "use_cases": "diagnostic",
            "value_statements": "diagnostic",
            "customers": "",
            "pricing": "",
            "evidence_urls": "",
        }
        google_sheets.append_rows_to_google_sheet([diagnostic_row])
        print("Google Sheets append worked: yes")
        results["append_worked"] = True
    except Exception as error:
        print(f"Google Sheets append worked: no ({error})")

    return results


def print_summary(
    supabase_results: dict[str, bool | None],
    google_results: dict[str, bool | None],
) -> None:
    """Print a short summary block."""
    print("")
    print("Summary")
    print(f"Supabase config loaded: {'yes' if supabase_results['config_loaded'] else 'no'}")
    print(f"Supabase read worked: {'yes' if supabase_results['read_worked'] else 'no'}")
    print(f"Supabase write worked: {_format_optional_result(supabase_results['write_worked'])}")
    print(f"Google Sheets config loaded: {'yes' if google_results['config_loaded'] else 'no'}")
    print(f"Google Sheets append worked: {_format_optional_result(google_results['append_worked'])}")


def _format_optional_result(value: bool | None) -> str:
    """Return a readable status for yes/no/not run results."""
    if value is None:
        return "not run"
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
