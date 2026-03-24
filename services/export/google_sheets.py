"""Google Sheets export service.

This module provides functions to export vendor intelligence to Google Sheets format.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path
from typing import Any

from services.config.load_config import DEFAULT_GOOGLE_SHEETS_COLUMNS, load_pipeline_config
from services.extraction.vendor_intel import VendorIntelligence

logger = logging.getLogger(__name__)
GOOGLE_SHEETS_COLUMNS = list(DEFAULT_GOOGLE_SHEETS_COLUMNS)
RUN_REVIEW_COLUMNS = [
    "run_id",
    "started_at",
    "completed_at",
    "queries_executed",
    "candidate_count",
    "queued_count",
    "enriched_count",
    "dropped_count",
    "run_status",
    "error_summary",
]
CANDIDATE_REVIEW_COLUMNS = [
    "run_id",
    "candidate_domain",
    "candidate_title",
    "source_query",
    "source_rank",
    "candidate_status",
    "drop_reason",
    "discovered_at",
]
VENDOR_REVIEW_COLUMNS = [
    "run_id",
    "vendor_name",
    "website",
    "source",
    "lifecycle_stages",
    "directory_category",
    "directory_fit",
    "include_in_directory",
    "confidence",
    "pricing_summary",
    "soc2",
    "free_trial",
    "founded",
    "mission_summary",
    "use_case_summary",
    "evidence_url_count",
    "last_updated",
]


def vendor_intelligence_to_sheet_row(
    vendor_intel: VendorIntelligence,
) -> dict[str, str]:
    """Convert a VendorIntelligence object into a flat Google Sheets row dictionary.

    Args:
        vendor_intel: The VendorIntelligence object to convert.

    Returns:
        A dictionary representing a row for Google Sheets.
    """
    return {
        "vendor_name": vendor_intel.vendor_name,
        "website": vendor_intel.website,
        "source": vendor_intel.source,
        "mission": vendor_intel.mission,
        "usp": vendor_intel.usp,
        "icp": "|".join(vendor_intel.icp),
        "use_cases": "|".join(vendor_intel.use_cases),
        "lifecycle_stages": "|".join(vendor_intel.lifecycle_stages),
        "pricing": "|".join(vendor_intel.pricing),
        "free_trial": _stringify_boolean(vendor_intel.free_trial),
        "soc2": _stringify_boolean(vendor_intel.soc2),
        "founded": vendor_intel.founded,
        "case_studies": "|".join(vendor_intel.case_studies),
        "customers": "|".join(vendor_intel.customers),
        "value_statements": "|".join(vendor_intel.value_statements),
        "confidence": vendor_intel.confidence,
        "evidence_urls": "|".join(vendor_intel.evidence_urls),
        "directory_fit": vendor_intel.directory_fit,
        "directory_category": vendor_intel.directory_category,
        "include_in_directory": _stringify_boolean(vendor_intel.include_in_directory),
    }


def write_rows_to_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    """Write Google Sheets-ready rows to a CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = _google_sheets_columns()

    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def append_rows_to_google_sheet(rows: list[dict[str, str]]) -> None:
    """Append Google Sheets-ready rows to the vendors sheet when configured."""
    append_rows_to_google_sheet_tab(rows)


def append_rows_to_google_sheet_tab(
    rows: list[dict[str, object]],
    *,
    worksheet_name: str | None = None,
    columns: list[str] | tuple[str, ...] | None = None,
) -> None:
    """Append rows to a specific Google Sheets tab using deterministic column order."""
    if not rows:
        return

    sheet_id = os.getenv("GOOGLE_SHEETS_ID")
    if not sheet_id:
        logger.warning("GOOGLE_SHEETS_ID is not set, skipping Google Sheets output")
        return

    credentials_info = _load_google_sheets_credentials_info()
    if credentials_info is None:
        logger.warning("Google Sheets credentials are unavailable, skipping Google Sheets output")
        return

    service = _build_google_sheets_service(credentials_info)
    target_columns = list(columns or _google_sheets_columns())
    worksheet_name = worksheet_name or _get_google_worksheet_name()
    _ensure_google_sheet_headers(service, sheet_id, worksheet_name, target_columns)
    values = [_row_to_ordered_values(row, target_columns) for row in rows]
    (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=sheet_id,
            range=f"{worksheet_name}!A:{_sheet_column_letter(len(target_columns))}",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        )
        .execute()
    )
    logger.info("Appended %s row(s) to Google Sheets worksheet %s", len(rows), worksheet_name)


def publish_ops_review_export(
    *,
    run_record: dict[str, object],
    candidate_records: list[dict[str, object]],
    enrichment_results: list[dict[str, object]],
) -> None:
    """Publish review-friendly runs, candidates, and vendors tabs to Google Sheets."""
    sheets_config = load_pipeline_config().google_sheets
    if not sheets_config.ops_review_enabled:
        return

    append_rows_to_google_sheet_tab(
        [run_record_to_review_row(run_record)],
        worksheet_name=sheets_config.runs_worksheet_name,
        columns=RUN_REVIEW_COLUMNS,
    )
    append_rows_to_google_sheet_tab(
        candidate_records_to_review_rows(candidate_records, run_record=run_record),
        worksheet_name=sheets_config.candidates_worksheet_name,
        columns=CANDIDATE_REVIEW_COLUMNS,
    )
    append_rows_to_google_sheet_tab(
        enrichment_results_to_review_rows(enrichment_results, run_record=run_record),
        worksheet_name=sheets_config.vendors_worksheet_name,
        columns=VENDOR_REVIEW_COLUMNS,
    )


def run_record_to_review_row(run_record: dict[str, object]) -> dict[str, object]:
    """Return one compact operator-facing review row for a pipeline run."""
    return {
        "run_id": run_record.get("run_id", ""),
        "started_at": run_record.get("started_at", ""),
        "completed_at": run_record.get("completed_at", ""),
        "queries_executed": run_record.get("queries_executed") or run_record.get("query", ""),
        "candidate_count": run_record.get("candidate_count", ""),
        "queued_count": run_record.get("queued_count", ""),
        "enriched_count": run_record.get("enriched_count", ""),
        "dropped_count": run_record.get("dropped_count", ""),
        "run_status": run_record.get("run_status", ""),
        "error_summary": run_record.get("error_summary", ""),
    }


def candidate_records_to_review_rows(
    candidate_records: list[dict[str, object]],
    *,
    run_record: dict[str, object],
) -> list[dict[str, object]]:
    """Return review-friendly candidate rows for one pipeline run."""
    run_id = str(run_record.get("run_id", "")).strip()
    rows: list[dict[str, object]] = []
    for candidate_record in candidate_records:
        rows.append(
            {
                "run_id": run_id,
                "candidate_domain": candidate_record.get("candidate_domain", ""),
                "candidate_title": candidate_record.get("candidate_title", ""),
                "source_query": candidate_record.get("source_query", ""),
                "source_rank": candidate_record.get("source_rank", ""),
                "candidate_status": candidate_record.get("candidate_status", ""),
                "drop_reason": candidate_record.get("drop_reason", ""),
                "discovered_at": candidate_record.get("discovered_at", ""),
            }
        )
    return rows


def enrichment_results_to_review_rows(
    enrichment_results: list[dict[str, object]],
    *,
    run_record: dict[str, object],
) -> list[dict[str, object]]:
    """Return review-friendly vendor rows for one pipeline run."""
    run_id = str(run_record.get("run_id", "")).strip()
    rows: list[dict[str, object]] = []
    for enrichment_result in enrichment_results:
        profile = enrichment_result.get("profile")
        if not isinstance(profile, VendorIntelligence):
            continue
        rows.append(
            {
                "run_id": run_id,
                "vendor_name": profile.vendor_name,
                "website": profile.website,
                "source": profile.source,
                "lifecycle_stages": ", ".join(profile.lifecycle_stages),
                "directory_category": profile.directory_category,
                "directory_fit": profile.directory_fit,
                "include_in_directory": _stringify_boolean(profile.include_in_directory),
                "confidence": profile.confidence,
                "pricing_summary": ", ".join(profile.pricing[:3]),
                "soc2": _stringify_boolean(profile.soc2),
                "free_trial": _stringify_boolean(profile.free_trial),
                "founded": profile.founded,
                "mission_summary": _summary_text(profile.mission),
                "use_case_summary": ", ".join(profile.use_cases[:3]),
                "evidence_url_count": len(profile.evidence_urls),
                "last_updated": enrichment_result.get("completed_at", ""),
            }
        )
    return rows


def _load_google_sheets_credentials_info() -> dict[str, Any] | None:
    """Load Google Sheets service account credentials from env vars."""
    credentials_json = (
        os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
        or os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    )

    if credentials_json:
        try:
            return json.loads(credentials_json)
        except json.JSONDecodeError as error:
            logger.warning("Could not parse GOOGLE_SHEETS_CREDENTIALS_JSON: %s", error)
            return None

    return None


def _build_google_sheets_service(credentials_info: dict[str, Any]):
    """Build a Google Sheets API service using service account credentials."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _get_google_worksheet_name() -> str:
    """Return the configured worksheet name for vendor rows."""
    worksheet_name = (
        os.getenv("GOOGLE_SHEETS_WORKSHEET")
        or os.getenv("GOOGLE_SHEETS_TAB")
        or load_pipeline_config().google_sheets.worksheet_name
    )
    return worksheet_name.strip() or load_pipeline_config().google_sheets.worksheet_name


def _ensure_google_sheet_headers(service, sheet_id: str, worksheet_name: str, columns: list[str]) -> None:
    """Ensure the target worksheet starts with the expected header row."""
    header_range = f"{worksheet_name}!A1:{_sheet_column_letter(len(columns))}1"
    response = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=header_range)
        .execute()
    )
    existing_values = response.get("values", [])
    existing_header = existing_values[0] if existing_values else []

    if existing_header == columns:
        return

    if _row_has_any_value(existing_header):
        worksheet_id = _get_google_worksheet_id(service, sheet_id, worksheet_name)
        (
            service.spreadsheets()
            .batchUpdate(
                spreadsheetId=sheet_id,
                body={
                    "requests": [
                        {
                            "insertDimension": {
                                "range": {
                                    "sheetId": worksheet_id,
                                    "dimension": "ROWS",
                                    "startIndex": 0,
                                    "endIndex": 1,
                                },
                                "inheritFromBefore": False,
                            }
                        }
                    ]
                },
            )
            .execute()
        )
        logger.warning(
            "Inserted a header row at the top of Google Sheets worksheet %s because the first row did not match the expected columns",
            worksheet_name,
        )
    else:
        logger.info("Initializing Google Sheets header row in worksheet %s", worksheet_name)

    (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=sheet_id,
            range=header_range,
            valueInputOption="RAW",
            body={"values": [columns]},
        )
        .execute()
    )


def _get_google_worksheet_id(service, sheet_id: str, worksheet_name: str) -> int:
    """Return the numeric worksheet ID for a named tab."""
    metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    for sheet in metadata.get("sheets", []):
        properties = sheet.get("properties", {})
        if properties.get("title") == worksheet_name:
            return int(properties["sheetId"])

    raise ValueError(f"Worksheet {worksheet_name!r} was not found in the configured Google Sheet")


def _row_to_ordered_values(row: dict[str, object], columns: list[str]) -> list[str]:
    """Convert a row dictionary into deterministic Google Sheets column order."""
    return [_stringify_cell(row.get(column, "")) for column in columns]


def _stringify_boolean(value: bool | None) -> str:
    """Return a Google Sheets-friendly string for a boolean value."""
    if value is None:
        return ""
    return "TRUE" if value else "FALSE"


def _sheet_column_letter(column_number: int) -> str:
    """Return a 1-based Google Sheets column letter."""
    letters: list[str] = []
    current_number = column_number

    while current_number > 0:
        current_number, remainder = divmod(current_number - 1, 26)
        letters.append(chr(65 + remainder))

    return "".join(reversed(letters))


def _stringify_cell(value: object) -> str:
    """Return a string cell value for Google Sheets."""
    if value is None:
        return ""
    return str(value)


def _row_has_any_value(row: list[object]) -> bool:
    """Return True when any non-empty cell exists in the row."""
    return any(str(cell).strip() for cell in row)


def _google_sheets_columns() -> list[str]:
    """Return the configured Google Sheets column order."""
    return list(load_pipeline_config().google_sheets.columns)


def _summary_text(text: str, *, max_chars: int = 120) -> str:
    """Return one readable summary string for operator review."""
    cleaned = " ".join(text.split()).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."
