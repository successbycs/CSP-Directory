"""Export role-based search visibility reporting artifacts."""

from __future__ import annotations

import json
from collections import defaultdict
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any

from services.persistence import search_visibility_store
from services.persistence import supabase_client

if TYPE_CHECKING:
    from supabase import Client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEARCH_VISIBILITY_REPORT_PATH = PROJECT_ROOT / "outputs" / "search_visibility_report.json"
DEFAULT_SEARCH_VISIBILITY_HTML_PATH = PROJECT_ROOT / "outputs" / "search_visibility_report.html"


def export_search_visibility_artifacts(
    *,
    report_output_path: Path | None = None,
    html_output_path: Path | None = None,
    client: "Client | None" = None,
    fallback_query_rows: list[dict[str, Any]] | None = None,
    fallback_result_rows: list[dict[str, Any]] | None = None,
    prefer_fallback_rows: bool = False,
) -> dict[str, Any]:
    """Write JSON and HTML role-based search visibility reports."""
    report = build_search_visibility_report(
        client=client,
        fallback_query_rows=fallback_query_rows,
        fallback_result_rows=fallback_result_rows,
        prefer_fallback_rows=prefer_fallback_rows,
    )
    report_output_path = report_output_path or DEFAULT_SEARCH_VISIBILITY_REPORT_PATH
    html_output_path = html_output_path or DEFAULT_SEARCH_VISIBILITY_HTML_PATH
    write_search_visibility_report(report, report_output_path)
    write_search_visibility_html(report, html_output_path)
    return report


def build_search_visibility_report(
    client: "Client | None" = None,
    *,
    fallback_query_rows: list[dict[str, Any]] | None = None,
    fallback_result_rows: list[dict[str, Any]] | None = None,
    prefer_fallback_rows: bool = False,
) -> dict[str, Any]:
    """Return a reporting-friendly role-search visibility snapshot."""
    query_rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []

    if not prefer_fallback_rows and (client is not None or supabase_client.is_configured()):
        try:
            query_rows = search_visibility_store.list_buyer_search_queries(limit=1000, client=client)
            result_rows = search_visibility_store.list_buyer_search_results(limit=5000, client=client)
        except Exception as error:
            if not _is_unavailable(error):
                raise

    if not query_rows and fallback_query_rows:
        query_rows = list(fallback_query_rows)
    if not result_rows and fallback_result_rows:
        result_rows = list(fallback_result_rows)

    rankings = _build_role_query_rankings(query_rows=query_rows, result_rows=result_rows)
    summary = _build_vendor_visibility_summary(rankings)
    return {
        "metrics": {
            "query_count": len(query_rows),
            "ranking_count": len(rankings),
            "vendor_count": len(summary),
        },
        "role_query_rankings": rankings,
        "vendor_visibility_summary": summary,
    }


def write_search_visibility_report(report: dict[str, Any], output_path: Path) -> None:
    """Write the JSON report to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def write_search_visibility_html(report: dict[str, Any], output_path: Path) -> None:
    """Write a self-contained HTML review report for search visibility."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_search_visibility_html(report), encoding="utf-8")


def _build_role_query_rankings(
    *,
    query_rows: list[dict[str, Any]],
    result_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    query_lookup = {
        str(row.get("query_signature") or "").strip(): row
        for row in query_rows
        if str(row.get("query_signature") or "").strip()
    }

    rankings: list[dict[str, Any]] = []
    for result_row in result_rows:
        query_signature = str(result_row.get("query_signature") or "").strip()
        query_row = query_lookup.get(query_signature, {})
        search_channel = str(result_row.get("search_channel") or "").strip().lower()
        search_provider = str(result_row.get("search_provider") or "").strip().lower()
        rankings.append(
            {
                "query_signature": query_signature,
                "source_vendor_name": _string_value(query_row.get("source_vendor_name")),
                "source_vendor_website": _string_value(query_row.get("source_vendor_website")),
                "buyer_role": _string_value(result_row.get("buyer_role") or query_row.get("buyer_role")),
                "search_channel": search_channel,
                "search_provider": search_provider,
                "search_channel_label": search_visibility_store.format_search_channel_label(
                    search_channel,
                    search_provider,
                ),
                "query_text": _string_value(result_row.get("query_text") or query_row.get("query_text")),
                "observed_rank": _int_value(result_row.get("observed_rank")),
                "surfaced_vendor_name": _string_value(result_row.get("surfaced_vendor_name")),
                "surfaced_vendor_website": _string_value(result_row.get("surfaced_vendor_website")),
                "source_url": _string_value(result_row.get("source_url")),
                "response_reference": _string_value(result_row.get("response_reference")),
                "visibility_score": _float_value(result_row.get("visibility_score")),
                "run_timestamp": _string_value(result_row.get("run_timestamp")),
            }
        )

    rankings = sorted(rankings, key=lambda row: row["observed_rank"] if row["observed_rank"] is not None else 10**9)
    rankings = sorted(rankings, key=lambda row: row["query_text"].lower())
    rankings = sorted(rankings, key=lambda row: row["search_channel_label"].lower())
    rankings = sorted(rankings, key=lambda row: row["buyer_role"].lower())
    rankings = sorted(rankings, key=lambda row: row["run_timestamp"], reverse=True)
    return rankings


def _build_vendor_visibility_summary(rankings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    role_sets: dict[tuple[str, str], set[str]] = defaultdict(set)
    channel_sets: dict[tuple[str, str], set[str]] = defaultdict(set)

    for ranking in rankings:
        vendor_name = ranking["surfaced_vendor_name"]
        vendor_website = ranking["surfaced_vendor_website"]
        key = (vendor_name.lower(), vendor_website.lower())
        if key not in grouped:
            grouped[key] = {
                "surfaced_vendor_name": vendor_name,
                "surfaced_vendor_website": vendor_website,
                "appearances": 0,
                "best_rank": None,
                "average_rank": 0.0,
                "average_visibility_score": 0.0,
                "latest_run_timestamp": "",
            }

        entry = grouped[key]
        entry["appearances"] += 1
        observed_rank = ranking["observed_rank"]
        visibility_score = ranking["visibility_score"] or 0.0
        if observed_rank is not None:
            entry["average_rank"] += float(observed_rank)
            if entry["best_rank"] is None or observed_rank < entry["best_rank"]:
                entry["best_rank"] = observed_rank
        entry["average_visibility_score"] += visibility_score
        entry["latest_run_timestamp"] = max(entry["latest_run_timestamp"], ranking["run_timestamp"])

        if ranking["buyer_role"]:
            role_sets[key].add(ranking["buyer_role"])
        if ranking["search_channel_label"]:
            channel_sets[key].add(ranking["search_channel_label"])

    summary_rows: list[dict[str, Any]] = []
    for key, entry in grouped.items():
        appearances = entry["appearances"] or 1
        average_rank = entry["average_rank"] / appearances if entry["average_rank"] else 0.0
        average_visibility_score = entry["average_visibility_score"] / appearances
        summary_rows.append(
            {
                **entry,
                "buyer_roles": sorted(role_sets[key]),
                "search_channels": sorted(channel_sets[key]),
                "average_rank": round(average_rank, 2) if average_rank else None,
                "average_visibility_score": round(average_visibility_score, 2),
            }
        )

    summary_rows = sorted(summary_rows, key=lambda row: row["surfaced_vendor_name"].lower())
    summary_rows = sorted(
        summary_rows,
        key=lambda row: (
            -(row["average_visibility_score"] or 0.0),
            row["best_rank"] if row["best_rank"] is not None else 10**9,
        ),
    )
    summary_rows = sorted(summary_rows, key=lambda row: row["appearances"], reverse=True)
    return summary_rows


def _render_search_visibility_html(report: dict[str, Any]) -> str:
    summary_rows = list(report.get("vendor_visibility_summary") or [])
    ranking_rows = list(report.get("role_query_rankings") or [])
    metrics = report.get("metrics") or {}
    summary_table = "".join(
        """
        <tr>
          <td>{vendor_name}</td>
          <td>{vendor_website}</td>
          <td>{appearances}</td>
          <td>{best_rank}</td>
          <td>{average_rank}</td>
          <td>{average_visibility_score}</td>
          <td>{buyer_roles}</td>
          <td>{search_channels}</td>
        </tr>
        """.format(
            vendor_name=escape(str(row.get("surfaced_vendor_name") or "")),
            vendor_website=escape(str(row.get("surfaced_vendor_website") or "")),
            appearances=escape(str(row.get("appearances") or 0)),
            best_rank=escape(str(row.get("best_rank") or "")),
            average_rank=escape(str(row.get("average_rank") or "")),
            average_visibility_score=escape(str(row.get("average_visibility_score") or "")),
            buyer_roles=escape(", ".join(row.get("buyer_roles") or [])),
            search_channels=escape(", ".join(row.get("search_channels") or [])),
        )
        for row in summary_rows
    )
    ranking_table = "".join(
        """
        <tr>
          <td>{run_timestamp}</td>
          <td>{buyer_role}</td>
          <td>{search_channel}</td>
          <td>{query_text}</td>
          <td>{observed_rank}</td>
          <td>{surfaced_vendor_name}</td>
          <td>{surfaced_vendor_website}</td>
          <td>{visibility_score}</td>
        </tr>
        """.format(
            run_timestamp=escape(str(row.get("run_timestamp") or "")),
            buyer_role=escape(str(row.get("buyer_role") or "")),
            search_channel=escape(str(row.get("search_channel_label") or "")),
            query_text=escape(str(row.get("query_text") or "")),
            observed_rank=escape(str(row.get("observed_rank") or "")),
            surfaced_vendor_name=escape(str(row.get("surfaced_vendor_name") or "")),
            surfaced_vendor_website=escape(str(row.get("surfaced_vendor_website") or "")),
            visibility_score=escape(str(row.get("visibility_score") or "")),
        )
        for row in ranking_rows
    )

    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Search Visibility Report | SuccessByCS</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f1e8;
      --panel: #fffaf2;
      --ink: #1e1a15;
      --muted: #6b6258;
      --line: #d8cebf;
      --accent: #0c5b6a;
      --accent-soft: #d9edf1;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Manrope", Arial, sans-serif;
      background: linear-gradient(180deg, #faf6ef 0%, var(--bg) 100%);
      color: var(--ink);
    }}
    main {{ max-width: 1240px; margin: 0 auto; padding: 32px 20px 56px; }}
    .hero, .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 20px; }}
    .hero {{ padding: 24px; margin-bottom: 24px; }}
    .panel {{ padding: 20px; margin-bottom: 20px; }}
    .eyebrow {{ margin: 0 0 10px; text-transform: uppercase; letter-spacing: 0.12em; font-size: 12px; color: var(--muted); }}
    h1, h2 {{ margin: 0 0 10px; }}
    p {{ margin: 0; line-height: 1.5; }}
    .metric-grid {{ display: grid; gap: 12px; grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: 18px; }}
    .metric {{ background: #fff; border: 1px solid var(--line); border-radius: 16px; padding: 16px; }}
    .metric strong {{ display: block; font-size: 28px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--line); vertical-align: top; font-size: 14px; }}
    th {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); background: #fcf8f1; }}
    tr:last-child td {{ border-bottom: none; }}
    .empty {{ color: var(--muted); font-style: italic; }}
    @media (max-width: 900px) {{
      .metric-grid {{ grid-template-columns: 1fr; }}
      table, thead, tbody, tr, th, td {{ display: block; }}
      thead {{ display: none; }}
      td {{ border-bottom: none; padding: 6px 0; }}
      tr {{ border-bottom: 1px solid var(--line); padding: 10px 0; }}
      td::before {{
        content: attr(data-label);
        display: block;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
      }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <p class="eyebrow">Operator review output</p>
      <h1>Search visibility report</h1>
      <p>Review how vendors surface across buyer-role search prompts and compare aggregate visibility by vendor.</p>
      <div class="metric-grid">
        <div class="metric">
          <span class="eyebrow">Queries</span>
          <strong>{query_count}</strong>
          <p>Persisted buyer-role prompts available for review.</p>
        </div>
        <div class="metric">
          <span class="eyebrow">Rankings</span>
          <strong>{ranking_count}</strong>
          <p>Observed ranked search results.</p>
        </div>
        <div class="metric">
          <span class="eyebrow">Vendors</span>
          <strong>{vendor_count}</strong>
          <p>Distinct surfaced vendors in the current report.</p>
        </div>
      </div>
    </section>

    <section class="panel">
      <p class="eyebrow">Vendor-centric view</p>
      <h2>Vendor visibility summary</h2>
      {summary_markup}
    </section>

    <section class="panel">
      <p class="eyebrow">Query-centric view</p>
      <h2>Role-by-query rankings</h2>
      {ranking_markup}
    </section>
  </main>
</body>
</html>
""".format(
        query_count=escape(str(metrics.get("query_count") or 0)),
        ranking_count=escape(str(metrics.get("ranking_count") or 0)),
        vendor_count=escape(str(metrics.get("vendor_count") or 0)),
        summary_markup=(
            f"<table><thead><tr><th>vendor</th><th>website</th><th>appearances</th><th>best rank</th><th>average rank</th><th>average score</th><th>buyer roles</th><th>channels</th></tr></thead><tbody>{summary_table}</tbody></table>"
            if summary_rows
            else '<p class="empty">No vendor visibility summary rows are available.</p>'
        ),
        ranking_markup=(
            f"<table><thead><tr><th>run</th><th>buyer role</th><th>channel</th><th>query</th><th>rank</th><th>vendor</th><th>website</th><th>score</th></tr></thead><tbody>{ranking_table}</tbody></table>"
            if ranking_rows
            else '<p class="empty">No role-by-query ranking rows are available.</p>'
        ),
    )


def _is_unavailable(error: Exception) -> bool:
    return (
        search_visibility_store.is_search_visibility_store_unavailable_error(error)
        or supabase_client.is_persistence_unavailable_error(error)
    )


def _string_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _int_value(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _float_value(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None
