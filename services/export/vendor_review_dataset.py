"""Export a slim vendor review dataset and HTML report for operators."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any

from services.extraction.vendor_intel import (
    VendorIntelligence,
    normalize_case_study_details,
    normalize_external_enrichment_records,
    normalize_icp_buyer_profiles,
    normalize_integration_taxonomy,
    summarize_external_enrichment,
    summarize_icp_buyer_profiles,
    summarize_integration_taxonomy,
)
from services.persistence import supabase_client

if TYPE_CHECKING:
    from supabase import Client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VENDOR_REVIEW_DATASET_PATH = PROJECT_ROOT / "outputs" / "vendor_review_dataset.json"
DEFAULT_VENDOR_REVIEW_HTML_PATH = PROJECT_ROOT / "outputs" / "vendor_review.html"


def export_vendor_review_artifacts(
    *,
    dataset_output_path: Path | None = None,
    html_output_path: Path | None = None,
    client: "Client | None" = None,
    fallback_profiles: list[VendorIntelligence] | None = None,
    prefer_fallback_profiles: bool = False,
) -> list[dict[str, Any]]:
    """Write a slim JSON dataset plus a self-contained HTML review report."""
    dataset = build_vendor_review_dataset(
        client=client,
        fallback_profiles=fallback_profiles,
        prefer_fallback_profiles=prefer_fallback_profiles,
    )
    dataset_output_path = dataset_output_path or DEFAULT_VENDOR_REVIEW_DATASET_PATH
    html_output_path = html_output_path or DEFAULT_VENDOR_REVIEW_HTML_PATH
    write_vendor_review_dataset(dataset, dataset_output_path)
    write_vendor_review_html(dataset, html_output_path)
    return dataset


def build_vendor_review_dataset(
    client: "Client | None" = None,
    *,
    fallback_profiles: list[VendorIntelligence] | None = None,
    prefer_fallback_profiles: bool = False,
) -> list[dict[str, Any]]:
    """Return a review-friendly vendor subset from Supabase or current-run profiles."""
    rows: list[dict[str, Any]]
    if prefer_fallback_profiles:
        rows = []
    elif client is not None or supabase_client.is_configured():
        try:
            rows = supabase_client.list_vendor_profiles(limit=500, client=client)
        except Exception:
            rows = []
    else:
        rows = []

    if not rows and fallback_profiles:
        rows = [_profile_to_vendor_row(profile) for profile in fallback_profiles]

    dataset = [_normalize_vendor_row(row) for row in rows]
    return sorted(dataset, key=lambda item: item["vendor_name"].lower())


def write_vendor_review_dataset(dataset: list[dict[str, Any]], output_path: Path) -> None:
    """Write the JSON review dataset to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")


def write_vendor_review_html(dataset: list[dict[str, Any]], output_path: Path) -> None:
    """Write a self-contained HTML report for quick visual review."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_vendor_review_html(dataset), encoding="utf-8")


def _normalize_vendor_row(row: dict[str, Any]) -> dict[str, Any]:
    mission = _string_value(row.get("mission"))
    usp = _string_value(row.get("usp"))
    pricing = _list_value(row.get("pricing"))
    source_urls = _list_value(row.get("source_urls") or row.get("evidence_urls"))
    lifecycle_stages = _list_value(row.get("lifecycle_stages"))
    icp_buyer = normalize_icp_buyer_profiles(row.get("icp_buyer"))
    case_study_details = normalize_case_study_details(row.get("case_study_details"))
    external_enrichment = normalize_external_enrichment_records(row.get("external_enrichment"))
    products = _list_of_dicts(row.get("products"))
    product_integration_categories = _collect_product_integration_values(products, field_name="integration_categories")
    product_integrations = _collect_product_integration_values(products, field_name="integrations")
    integration_taxonomy = normalize_integration_taxonomy(
        row.get("integration_taxonomy"),
        integrations=[*_list_value(row.get("integrations")), *product_integrations],
        categories=[*_list_value(row.get("integration_categories")), *product_integration_categories],
    )

    return {
        "vendor_name": _string_value(row.get("name") or row.get("vendor_name")),
        "website": _string_value(row.get("website")),
        "source": _string_value(row.get("source")),
        "mission_summary": _summary_text(mission or usp),
        "products": products,
        "product_count": len(products),
        "product_summary": _product_summary(products),
        "integration_taxonomy": integration_taxonomy,
        "integration_summary": summarize_integration_taxonomy(integration_taxonomy),
        "external_enrichment": external_enrichment,
        "external_enrichment_summary": summarize_external_enrichment(external_enrichment),
        "icp_buyer": icp_buyer,
        "icp_buyer_summary": summarize_icp_buyer_profiles(icp_buyer),
        "use_case_summary": ", ".join(_list_value(row.get("use_cases"))[:3]),
        "pricing_summary": ", ".join(pricing[:3]),
        "lifecycle_stages": lifecycle_stages,
        "directory_category": _string_value(row.get("directory_category")),
        "directory_fit": _string_value(row.get("directory_fit")),
        "include_in_directory": _bool_value(row.get("include_in_directory")),
        "llm_directory_category": _string_value(row.get("llm_directory_category")),
        "llm_directory_fit": _string_value(row.get("llm_directory_fit")),
        "llm_include_in_directory": _bool_value(row.get("llm_include_in_directory")),
        "directory_decision_source": _string_value(row.get("directory_decision_source")) or "auto",
        "directory_reasoning": _list_value(row.get("directory_reasoning")),
        "confidence": _string_value(row.get("confidence")),
        "free_trial": _bool_value(row.get("free_trial")),
        "soc2": _bool_value(row.get("soc2")),
        "founded": _string_value(row.get("founded")),
        "case_study_details": case_study_details,
        "case_study_count": len(case_study_details),
        "evidence_url_count": len(source_urls),
        "last_updated": _string_value(row.get("last_updated")),
    }


def _profile_to_vendor_row(profile: VendorIntelligence) -> dict[str, Any]:
    return {
        "name": profile.vendor_name,
        "website": profile.website,
        "source": profile.source,
        "mission": profile.mission,
        "products": profile.products,
        "usp": profile.usp,
        "icp_buyer": profile.icp_buyer,
        "use_cases": profile.use_cases,
        "pricing": profile.pricing,
        "lifecycle_stages": profile.lifecycle_stages,
        "integration_categories": profile.integration_categories,
        "integrations": profile.integrations,
        "integration_taxonomy": profile.integration_taxonomy,
        "external_enrichment": profile.external_enrichment,
        "directory_category": profile.directory_category,
        "directory_fit": profile.directory_fit,
        "include_in_directory": profile.include_in_directory,
        "llm_directory_category": profile.llm_directory_category,
        "llm_directory_fit": profile.llm_directory_fit,
        "llm_include_in_directory": profile.llm_include_in_directory,
        "directory_decision_source": profile.directory_decision_source,
        "directory_reasoning": profile.directory_reasoning,
        "confidence": profile.confidence,
        "free_trial": profile.free_trial,
        "soc2": profile.soc2,
        "founded": profile.founded,
        "case_studies": profile.case_studies,
        "case_study_details": profile.case_study_details,
        "evidence_urls": profile.evidence_urls,
        "last_updated": "",
    }


def _render_vendor_review_html(dataset: list[dict[str, Any]]) -> str:
    payload = json.dumps(dataset)
    total_vendors = len(dataset)
    included_count = sum(1 for vendor in dataset if vendor.get("include_in_directory") is True)
    high_fit_count = sum(1 for vendor in dataset if vendor.get("directory_fit") == "high")

    template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Vendor Review Report | SuccessByCS</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f3efe6;
      --panel: #fffaf1;
      --ink: #1f1b16;
      --muted: #6d655b;
      --line: #d7cdbf;
      --accent: #145a4a;
      --accent-soft: #d9efe8;
      --warn: #8b5e1a;
      --warn-soft: #f8ead1;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Manrope", Arial, sans-serif;
      background: linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
      color: var(--ink);
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 56px; }}
    .hero {{
      display: grid;
      gap: 16px;
      grid-template-columns: 2fr 1fr;
      align-items: start;
      margin-bottom: 28px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 20px;
      box-shadow: 0 18px 40px rgba(31, 27, 22, 0.06);
    }}
    h1, h2 {{ margin: 0 0 8px; }}
    p {{ margin: 0; line-height: 1.55; }}
    .eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 10px;
    }}
    .metric-grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }}
    .metric strong {{ display: block; font-size: 28px; margin-bottom: 4px; }}
    .toolbar {{
      display: grid;
      gap: 12px;
      grid-template-columns: 2fr 1fr 1fr;
      margin-bottom: 16px;
    }}
    input, select {{
      width: 100%;
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fff;
      font: inherit;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #fff;
      border-radius: 16px;
      overflow: hidden;
    }}
    th, td {{
      text-align: left;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      background: #fbf7f0;
    }}
    tr:last-child td {{ border-bottom: none; }}
    .pill {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      background: var(--accent-soft);
      color: var(--accent);
    }}
    .pill-warn {{
      background: var(--warn-soft);
      color: var(--warn);
    }}
    .case-study + .case-study {{
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px dashed var(--line);
    }}
    .muted {{ color: var(--muted); }}
    .empty {{
      padding: 28px;
      text-align: center;
      color: var(--muted);
      background: #fff;
      border: 1px dashed var(--line);
      border-radius: 16px;
    }}
    a {{ color: var(--accent); }}
    @media (max-width: 900px) {{
      .hero, .metric-grid, .toolbar {{ grid-template-columns: 1fr; }}
      table, thead, tbody, tr, th, td {{ display: block; }}
      thead {{ display: none; }}
      tr {{
        border-bottom: 1px solid var(--line);
        padding: 10px 0;
      }}
      td {{
        border-bottom: none;
        padding: 6px 0;
      }}
      td::before {{
        content: attr(data-label);
        display: block;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
        margin-bottom: 2px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <article class="panel">
        <p class="eyebrow">Visual review output</p>
        <h1>Vendor review report</h1>
        <p>This report is generated by the pipeline run so operators can quickly inspect the vendor subset synced from Supabase or the current run fallback without opening a raw Google Sheet dump.</p>
      </article>
      <aside class="panel metric-grid">
        <div class="metric">
          <span class="eyebrow">Vendors</span>
          <strong>__TOTAL_VENDORS__</strong>
          <p class="muted">Rows available for review.</p>
        </div>
        <div class="metric">
          <span class="eyebrow">Included</span>
          <strong>__INCLUDED_COUNT__</strong>
          <p class="muted">Marked for directory inclusion.</p>
        </div>
        <div class="metric">
          <span class="eyebrow">High fit</span>
          <strong>__HIGH_FIT_COUNT__</strong>
          <p class="muted">High-fit vendors in the current review set.</p>
        </div>
      </aside>
    </section>

    <section class="panel">
      <div class="toolbar">
        <input id="search" type="search" placeholder="Search vendor name or website">
        <select id="include-filter">
          <option value="">All inclusion states</option>
          <option value="true">Included</option>
          <option value="false">Excluded</option>
        </select>
        <select id="category-filter">
          <option value="">All categories</option>
        </select>
      </div>
      <div id="table-container"></div>
    </section>
  </main>

  <script id="vendor-review-data" type="application/json">__PAYLOAD__</script>
  <script>
    const dataset = JSON.parse(document.getElementById("vendor-review-data").textContent);
    const tableContainer = document.getElementById("table-container");
    const searchInput = document.getElementById("search");
    const includeFilter = document.getElementById("include-filter");
    const categoryFilter = document.getElementById("category-filter");

    function populateCategoryFilter() {{
      const categories = Array.from(new Set(dataset.map((vendor) => vendor.directory_category).filter(Boolean))).sort();
      categories.forEach((category) => categoryFilter.appendChild(new Option(category, category)));
    }}

    function render() {{
      const searchValue = searchInput.value.trim().toLowerCase();
      const includeValue = includeFilter.value;
      const categoryValue = categoryFilter.value;

      const rows = dataset.filter((vendor) => {{
        const matchesSearch = !searchValue
          || String(vendor.vendor_name || "").toLowerCase().includes(searchValue)
          || String(vendor.website || "").toLowerCase().includes(searchValue);
        const matchesInclude = !includeValue || String(vendor.include_in_directory) === includeValue;
        const matchesCategory = !categoryValue || vendor.directory_category === categoryValue;
        return matchesSearch && matchesInclude && matchesCategory;
      }});

      if (!rows.length) {{
        tableContainer.innerHTML = '<div class="empty">No vendors match the current filters.</div>';
        return;
      }}

      tableContainer.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Vendor</th>
              <th>Lifecycle</th>
              <th>Category</th>
              <th>Fit</th>
              <th>Include</th>
              <th>Case Studies</th>
              <th>Summary</th>
              <th>Pricing</th>
              <th>Signals</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((vendor) => `
              <tr>
                <td data-label="Vendor">
                  <strong>${escapeHtml(vendor.vendor_name || "")}</strong><br>
                  <a href="${escapeAttribute(vendor.website || "#")}" target="_blank" rel="noreferrer">${escapeHtml(vendor.website || "")}</a>
                  ${vendor.product_summary ? `<br><span class="muted">Products: ${escapeHtml(vendor.product_summary)}</span>` : ""}
                  ${vendor.integration_summary ? `<br><span class="muted">Integrations: ${escapeHtml(vendor.integration_summary)}</span>` : ""}
                </td>
                <td data-label="Lifecycle">${escapeHtml((vendor.lifecycle_stages || []).join(", ") || "Not mapped")}</td>
                <td data-label="Category">${escapeHtml(vendor.directory_category || "uncategorized")}</td>
                <td data-label="Fit"><span class="pill ${vendor.directory_fit === "low" ? "pill-warn" : ""}">${escapeHtml(vendor.directory_fit || "unscored")}</span></td>
                <td data-label="Include">${escapeHtml(vendor.include_in_directory === true ? "true" : vendor.include_in_directory === false ? "false" : "")}</td>
                <td data-label="Case Studies">${formatCaseStudies(vendor.case_study_details || [])}</td>
                <td data-label="Summary">${escapeHtml(vendor.mission_summary || "No summary captured.")}</td>
                <td data-label="Pricing">${escapeHtml(vendor.pricing_summary || "No pricing captured.")}</td>
                <td data-label="Signals">
                  Decision source: ${escapeHtml(vendor.directory_decision_source || "auto")}<br>
                  Auto decision: ${escapeHtml(formatAutoDecision(vendor))}<br>
                  Reasoning: ${escapeHtml((vendor.directory_reasoning || []).slice(0, 2).join(" | ") || "Not captured")}<br>
                  Confidence: ${escapeHtml(vendor.confidence || "n/a")}<br>
                  Free trial: ${escapeHtml(formatBoolean(vendor.free_trial))}<br>
                  SOC2: ${escapeHtml(formatBoolean(vendor.soc2))}<br>
                  Integrations: ${escapeHtml(vendor.integration_summary || "Not mapped")}<br>
                  External enrichment: ${escapeHtml(vendor.external_enrichment_summary || "Not staged")}<br>
                  Case studies: ${escapeHtml(String(vendor.case_study_count || 0))}<br>
                  Product count: ${escapeHtml(String(vendor.product_count || 0))}<br>
                  Evidence URLs: ${escapeHtml(String(vendor.evidence_url_count || 0))}
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
    }}

    function formatBoolean(value) {{
      if (value === true) return "Yes";
      if (value === false) return "No";
      return "Unknown";
    }}

    function formatCaseStudies(items) {{
      if (!items.length) {{
        return '<span class="muted">No structured case studies.</span>';
      }}
      return items.map((item) => `
        <div class="case-study">
          <strong>${escapeHtml(item.client || item.title || "Case study")}</strong><br>
          ${escapeHtml(item.use_case || "Use case not captured")}<br>
          ${escapeHtml(item.value_realized || "")}
          ${item.metric ? `<br><span class="muted">Metric: ${escapeHtml(item.metric)}</span>` : ""}
        </div>
      `).join("");
    }}

    function formatAutoDecision(vendor) {{
      const fit = vendor.llm_directory_fit || vendor.directory_fit || "unscored";
      const category = vendor.llm_directory_category || vendor.directory_category || "uncategorized";
      const include = vendor.llm_include_in_directory;
      return `${fit} / ${category} / ${include === true ? "true" : include === false ? "false" : ""}`;
    }}

    function escapeHtml(value) {{
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }}

    function escapeAttribute(value) {{
      return escapeHtml(value);
    }}

    populateCategoryFilter();
    render();
    searchInput.addEventListener("input", render);
    includeFilter.addEventListener("change", render);
    categoryFilter.addEventListener("change", render);
  </script>
</body>
</html>
"""
    return (
        template
        .replace("__TOTAL_VENDORS__", str(total_vendors))
        .replace("__INCLUDED_COUNT__", str(included_count))
        .replace("__HIGH_FIT_COUNT__", str(high_fit_count))
        .replace("__PAYLOAD__", escape(payload))
        .replace("{{", "{")
        .replace("}}", "}")
    )


def _string_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _list_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        separators_normalized = value.replace("\n", "|").replace(",", "|")
        return [segment.strip() for segment in separators_normalized.split("|") if segment.strip()]
    return []


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _summary_text(text: str, *, max_chars: int = 140) -> str:
    cleaned = " ".join(text.split()).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."


def _product_summary(products: list[dict[str, Any]]) -> str:
    product_names = [str(product.get("name") or "").strip() for product in products]
    cleaned_names = [name for name in product_names if name]
    return ", ".join(cleaned_names[:3])


def _collect_product_integration_values(products: list[dict[str, Any]], *, field_name: str) -> list[str]:
    values: list[str] = []
    for product in products:
        for value in _list_value(product.get(field_name)):
            if value and value not in values:
                values.append(value)
    return values
