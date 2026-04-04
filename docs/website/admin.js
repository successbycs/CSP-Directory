const API_FALLBACK_BASE = "http://127.0.0.1:8787";
const DEFAULT_PIPELINE_CONTROLS = [
  // ── Discovery ──────────────────────────────────────────────────────────────
  {
    pipeline_id: "full_pipeline",
    name: "Full Discovery + Enrichment",
    group: "discovery",
    description:
      "Runs discover → enrich → export using configured query set. Includes Apify Google Search, web crawl, LLM extraction, and persistence.",
  },
  {
    pipeline_id: "weekly_discovery_job",
    name: "Weekly Discovery Job",
    group: "discovery",
    description:
      "Discovery-only: Apify Google Search using configured query set and candidate limits.",
  },
  {
    pipeline_id: "google_discovery",
    name: "Step 1 — Google Discovery",
    group: "discovery",
    description:
      "Discovers new vendor candidates via Apify Google Search → n8n workflow → filters review/directory sites → upserts candidates.",
  },
  {
    pipeline_id: "weekly_digest_job",
    name: "Weekly Digest",
    group: "discovery",
    description: "Builds weekly lifecycle digest and summary outputs.",
  },
  // ── Enrichment ─────────────────────────────────────────────────────────────
  {
    pipeline_id: "full_enrichment_cycle",
    name: "⚡ Full Enrichment Cycle",
    group: "enrichment",
    description:
      "Runs all enrichment sources in sequence: site crawl (tiered) → LLM extraction → Datagma firmographic → LinkedIn → G2 → pricing. Use for backfill or full vendor refresh.",
  },
  {
    pipeline_id: "site_crawl_enrichment",
    name: "Step 2 — Site Crawl (Tiered)",
    group: "enrichment",
    description:
      "Re-crawls vendor homepages: Tier 1 (free HTTP) → Tier 2 (Apify RAG ~$0.001/page) → Tier 3 (Apify WCC + proxy ~$0.004/page). Requires N8N_CRAWL_TIER1/2/3_WEBHOOK.",
  },
  {
    pipeline_id: "tier3_batch_crawl",
    name: "Step 3 — Tier 3 Batch Crawl",
    group: "enrichment",
    description:
      "Triggers csp-crawl-tier3-wcc for all directory vendors without sufficient pages. Apify WCC, async, ~$0.004/page. Skips vendors with 20+ pages already.",
  },
  {
    pipeline_id: "embed_vendor_pages",
    name: "Step 4 — Embed Vendor Pages",
    group: "enrichment",
    description:
      "Chunks vendor_pages text and embeds with nomic-embed-text (local Ollama). Stores in vendor_page_embeddings for RAG retrieval. Skips already-embedded vendors.",
  },
  {
    pipeline_id: "firmographic_enrichment",
    name: "Step 5 — Firmographic Enrichment",
    group: "enrichment",
    description:
      "Single domain call via Datagma (RapidAPI) returns founded, hq_address, funding_stage, total_funding, ceo_name, company_size, revenue. Requires RAPIDAPI_KEY + Datagma subscription.",
  },
  {
    pipeline_id: "g2_rapidapi_enrichment",
    name: "Step 7 — G2 RapidAPI Enrichment",
    group: "enrichment",
    description:
      "G2 product data via RapidAPI G2 Data API. Fills g2_url, g2_rating, g2_review_count, g2_categories. Currently 20/119 vendors covered — run to fill remaining 99.",
  },
  {
    pipeline_id: "trustpilot_enrichment",
    name: "Step 8 — Trustpilot Enrichment",
    group: "enrichment",
    description:
      "Scrapes Trustpilot review pages for all include_in_directory vendors. Fills trustpilot_rating and trustpilot_review_count. Triggered via n8n csp-trustpilot-enrichment workflow.",
  },
  {
    pipeline_id: "feature_depth_enrichment",
    name: "Step 9 — Feature Depth Enrichment",
    group: "enrichment",
    description:
      "Crawls vendor help/docs site and runs LLM feature taxonomy extraction across 6 dimensions. Computes category-relative feature_depth_score (0–100) and feature_signals list. Triggered via n8n csp-feature-depth-enrichment workflow.",
  },
  {
    pipeline_id: "ops_llm_enrichment_batch",
    name: "Step 10 — Batch LLM Enrichment (GPT-4o)",
    group: "enrichment",
    description:
      "Runs full crawl → embed → GPT-4o extraction pipeline for every vendor not yet enriched. Saves progress after each vendor — safe to interrupt and resume. ~$0.05–0.10 per vendor.",
  },
  {
    pipeline_id: "ops_ai_summary",
    name: "Step 11 — AI Summary (GPT-4o mini)",
    group: "enrichment",
    description:
      "Generate a 400-word vendor summary using GPT-4o mini from live web fetch + stored pages. Stored in ai_summary column and exported to directory dataset. Skips vendors that already have a summary.",
  },
  {
    pipeline_id: "ops_export_dataset",
    name: "Step 12 — Export Dataset to Vercel",
    group: "enrichment",
    description:
      "Pull latest vendor data from Supabase and write docs/website/data/directory_dataset.json. Run after any enrichment to publish changes to the live directory.",
  },
];
const DEFAULT_PIPELINE_RUNNERS = [
  {
    step_order: 1,
    phase: "discovery",
    runner: "Apify Google Search",
    details: "Runs configured query set and collects candidate domains/snippets.",
    config: {
      source_engine: "google_search",
      actor_id: "apify/google-search-scraper",
      query_count: 22,
      max_pages_per_query: 1,
      results_per_page: 10,
      max_candidate_domains_per_run: 100,
    },
  },
  {
    step_order: 2,
    phase: "enrichment",
    runner: "Homepage fetch",
    details: "Fetches each queued vendor homepage before deeper exploration.",
    config: {
      request_timeout_seconds: 10,
      external_fetch_backend: "apify",
      external_fetch_actor_id: "apify/website-content-crawler",
      external_fetch_max_pages: 1,
    },
  },
  {
    step_order: 3,
    phase: "enrichment",
    runner: "Apify/Web crawl",
    details: "Explores high-signal pages and crawl depth limits per vendor.",
    config: {
      discovery_mode: "auto",
      max_crawl_depth: 3,
      max_non_homepage_pages: 100,
      max_pages_total: 100,
    },
  },
  {
    step_order: 4,
    phase: "enrichment",
    runner: "Deterministic extraction",
    details: "Rule-based extraction from fetched pages.",
    config: {},
  },
  {
    step_order: 5,
    phase: "enrichment",
    runner: "LLM extraction",
    details: "Optional semantic extraction and enrichment merge.",
    config: {
      enabled: true,
      model: "gpt-4o-mini",
    },
  },
];

const state = {
  apiBase: "",
  candidates: [],
  vendors: [],
  leads: {
    metrics: {},
    items: [],
  },
  runs: [],
  enrichmentMetrics: {
    metrics: {},
    pipeline_counts: {},
  },
  pipelineRunners: [],
  pipelines: [],
  errors: {
    candidates: "",
    vendors: "",
    leads: "",
    runs: "",
    enrichmentMetrics: "",
    pipelineRunners: "",
    pipelines: "",
  },
};

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("candidate-search")?.addEventListener("input", renderCandidates);
  document.getElementById("candidate-status-filter")?.addEventListener("change", renderCandidates);
  document.getElementById("vendor-search")?.addEventListener("input", renderVendors);
  document.getElementById("vendor-category-filter")?.addEventListener("change", renderVendors);
  document.getElementById("lead-search")?.addEventListener("input", renderLeads);
  document.getElementById("lead-status-filter")?.addEventListener("change", renderLeads);
  document.getElementById("pipelines-body")?.addEventListener("click", handlePipelineTableClick);
  loadDashboard();
});

async function loadDashboard() {
  try {
    state.apiBase = await detectApiBase();
    const [candidates, vendors, leads, runs, enrichmentMetrics, pipelineRunners, pipelines] = await Promise.all([
      fetchJson("/admin/candidates"),
      fetchJson("/admin/vendors"),
      fetchJson("/admin/leads"),
      fetchJson("/admin/runs"),
      fetchJson("/admin/enrichment-metrics").catch(() => ({metrics: {}, pipeline_counts: {}, error: "enrichment_metrics_unavailable"})),
      fetchJson("/admin/pipeline-runners").catch(() => ({items: [], error: "pipeline_runners_unavailable"})),
      fetchJson("/admin/pipelines").catch(() => ({items: [], error: "pipelines_unavailable"})),
    ]);

    state.candidates = sortCandidates(candidates.items || []);
    state.vendors = vendors.items || [];
    state.leads = {
      metrics: leads.metrics || {},
      items: leads.items || [],
    };
    state.runs = runs.items || [];
    state.enrichmentMetrics = {
      metrics: enrichmentMetrics.metrics || {},
      pipeline_counts: enrichmentMetrics.pipeline_counts || {},
    };
    state.pipelineRunners = normalizePipelineRunners(pipelineRunners.items);
    state.pipelines = normalizePipelineItems(pipelines.items);
    state.errors.candidates = formatApiError(candidates);
    state.errors.vendors = formatApiError(vendors);
    state.errors.leads = formatApiError(leads);
    state.errors.runs = formatApiError(runs);
    state.errors.enrichmentMetrics = formatApiError(enrichmentMetrics);
    state.errors.pipelineRunners = formatApiError(pipelineRunners);
    state.errors.pipelines = formatApiError(pipelines);

    populateVendorCategoryFilter();
    renderCandidates();
    renderVendors();
    renderLeads();
    renderRuns();
    renderEnrichmentMetrics();
    renderPipelineRunners();
    renderPipelines();
    startPipelinePolling();
  } catch (error) {
    renderFailureState(`Admin API unavailable: ${error.message}`);
  }
}

async function detectApiBase() {
  if (await hasJsonAdminEndpoint("")) {
    return "";
  }
  if (await hasJsonAdminEndpoint(API_FALLBACK_BASE)) {
    return API_FALLBACK_BASE;
  }
  return API_FALLBACK_BASE;
}

async function hasJsonAdminEndpoint(base) {
  try {
    const response = await fetch(`${base}/admin/candidates`);
    if (!response.ok) {
      return false;
    }
    const contentType = String(response.headers.get("content-type") || "").toLowerCase();
    if (!contentType.includes("application/json")) {
      return false;
    }
    const payload = await response.json();
    return !!payload && Array.isArray(payload.items);
  } catch (error) {
    return false;
  }
}

async function fetchJson(path, options = {}) {
  const response = await fetch(`${state.apiBase}${path}`, options);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function sortCandidates(candidates) {
  return [...candidates].sort((left, right) => String(right.discovered_at || "").localeCompare(String(left.discovered_at || "")));
}

function populateVendorCategoryFilter() {
  const filter = document.getElementById("vendor-category-filter");
  if (!filter) {
    return;
  }
  filter.querySelectorAll("option:not([value=''])").forEach((option) => option.remove());
  const categories = Array.from(new Set(state.vendors.map((vendor) => vendor.directory_category).filter(Boolean))).sort();
  categories.forEach((category) => filter.appendChild(new Option(category, category)));
}

function renderCandidates() {
  const body = document.getElementById("candidates-body");
  if (!body) {
    return;
  }
  if (state.errors.candidates) {
    body.innerHTML = `<tr><td colspan="5" class="message">${escapeHtml(state.errors.candidates)}</td></tr>`;
    return;
  }
  const searchValue = document.getElementById("candidate-search")?.value.trim().toLowerCase() || "";
  const statusValue = document.getElementById("candidate-status-filter")?.value || "";

  const rows = state.candidates.filter((candidate) => {
    const matchesSearch = !searchValue || String(candidate.candidate_domain || "").toLowerCase().includes(searchValue);
    const matchesStatus = !statusValue || candidate.candidate_status === statusValue;
    return matchesSearch && matchesStatus;
  });

  body.innerHTML = rows.map((candidate) => {
    const statusClass = candidate.candidate_status === "filtered_out" ? "is-danger" : candidate.candidate_status === "failed" ? "is-warning" : "";
    const rowClass = candidate.candidate_status === "filtered_out" ? "is-filtered-out" : "";
    return `
      <tr class="${rowClass}">
        <td>${escapeHtml(candidate.candidate_domain || "")}</td>
        <td>${escapeHtml(candidate.source_query || "")}</td>
        <td><span class="status-pill ${statusClass}">${escapeHtml(candidate.candidate_status || "")}</span></td>
        <td>${escapeHtml(formatNzDateTime(candidate.discovered_at || ""))}</td>
        <td>${escapeHtml(candidate.drop_reason || "")}</td>
      </tr>
    `;
  }).join("") || '<tr><td colspan="5" class="message">No discovery candidates found.</td></tr>';
}

function renderVendors() {
  const body = document.getElementById("vendors-body");
  if (!body) {
    return;
  }
  if (state.errors.vendors) {
    body.innerHTML = `<tr><td colspan="7" class="message">${escapeHtml(state.errors.vendors)}</td></tr>`;
    return;
  }
  const searchValue = document.getElementById("vendor-search")?.value.trim().toLowerCase() || "";
  const categoryValue = document.getElementById("vendor-category-filter")?.value || "";

  const rows = state.vendors.filter((vendor) => {
    const matchesSearch = !searchValue || String(vendor.name || vendor.vendor_name || "").toLowerCase().includes(searchValue);
    const matchesCategory = !categoryValue || vendor.directory_category === categoryValue;
    return matchesSearch && matchesCategory;
  });

  body.innerHTML = rows.map((vendor) => {
    const includeValue = vendor.include_in_directory === true;
    const rowClass = includeValue ? "" : "is-excluded";
    const vendorName = vendor.name || vendor.vendor_name || vendor.website || "";
    const productSummary = summarizeProductNames(vendor.products);
    return `
      <tr class="${rowClass}">
        <td>
          <div class="cell-stack">
            <a href="${escapeAttribute(vendor.website || "#")}" target="_blank" rel="noreferrer">${escapeHtml(vendorName)}</a>
            ${productSummary ? `<span>Products: ${escapeHtml(productSummary)}</span>` : ""}
          </div>
        </td>
        <td>${escapeHtml(formatList(vendor.lifecycle_stages))}</td>
        <td>${escapeHtml(formatIntegrationSummary(vendor) || "Not mapped")}</td>
        <td>${escapeHtml(vendor.directory_category || "")}</td>
        <td>${formatVendorDecision(vendor)}</td>
        <td>${escapeHtml(includeValue ? "true" : "false")}</td>
        <td>
          <div class="actions">
            <button class="action-button ${includeValue ? 'action-active' : 'action-secondary'}" data-action="include" data-vendor="${escapeAttribute(vendor.website || vendorName)}">Include</button>
            <button class="action-button ${!includeValue ? 'action-active' : 'action-secondary'}" data-action="exclude" data-vendor="${escapeAttribute(vendor.website || vendorName)}">Exclude</button>
            <button class="action-button action-secondary" data-action="rerun-enrichment" data-vendor="${escapeAttribute(vendor.website || vendorName)}">Rerun Enrichment</button>
            <button class="action-button action-secondary" data-action="show-record" data-vendor-index="${escapeAttribute(String(rows.indexOf(vendor)))}">See full record</button>
            <button class="action-button action-secondary" data-action="view-raw" data-vendor-index="${escapeAttribute(String(rows.indexOf(vendor)))}">View record</button>
          </div>
        </td>
      </tr>
    `;
  }).join("") || '<tr><td colspan="7" class="message">No enriched vendors found.</td></tr>';

  body.querySelectorAll("[data-action]").forEach((button) => {
    if (button.dataset.action === "show-record") {
      button.addEventListener("click", (event) => {
        const index = parseInt(event.currentTarget.dataset.vendorIndex, 10);
        showVendorModal(rows[index]);
      });
    } else if (button.dataset.action === "view-raw") {
      button.addEventListener("click", (event) => {
        const index = parseInt(event.currentTarget.dataset.vendorIndex, 10);
        showRawRecordModal(rows[index]);
      });
    } else {
      button.addEventListener("click", handleVendorAction);
    }
  });
}

function renderLeads() {
  const body = document.getElementById("leads-body");
  const metricsNode = document.getElementById("lead-capture-metrics");
  if (!body || !metricsNode) {
    return;
  }
  if (state.errors.leads) {
    metricsNode.textContent = state.errors.leads;
    body.innerHTML = `<tr><td colspan="7" class="message">${escapeHtml(state.errors.leads)}</td></tr>`;
    return;
  }

  const searchValue = document.getElementById("lead-search")?.value.trim().toLowerCase() || "";
  const statusValue = document.getElementById("lead-status-filter")?.value || "";
  const rows = (state.leads.items || []).filter((lead) => {
    const searchableText = [
      lead.lead_name,
      lead.lead_email,
      lead.company_name,
      lead.vendor_name,
      lead.entry_page,
    ].join(" ").toLowerCase();
    const matchesSearch = !searchValue || searchableText.includes(searchValue);
    const matchesStatus = !statusValue || lead.follow_up_status === statusValue;
    return matchesSearch && matchesStatus;
  });

  const metrics = state.leads.metrics || {};
  metricsNode.textContent =
    `${metrics.lead_count || 0} captured leads, ${metrics.service_lead_count || 0} service-intent, ` +
    `${metrics.qualified_lead_count || 0} qualified.`;

  body.innerHTML = rows.map((lead) => `
    <tr>
      <td>${escapeHtml(formatNzDateTime(lead.created_at || ""))}</td>
      <td>${formatLeadIdentity(lead)}</td>
      <td>${formatLeadIntent(lead)}</td>
      <td>${formatLeadSource(lead)}</td>
      <td>${formatLeadAttribution(lead)}</td>
      <td>${formatLeadFollowUp(lead)}</td>
      <td><span class="status-pill">n8n Discord and email sent</span></td>
    </tr>
  `).join("") || '<tr><td colspan="7" class="message">No captured leads found.</td></tr>';
}

function renderRuns() {
  const body = document.getElementById("runs-body");
  if (!body) {
    return;
  }
  if (state.errors.runs) {
    body.innerHTML = `<tr><td colspan="6" class="message">${escapeHtml(state.errors.runs)}</td></tr>`;
    return;
  }
  body.innerHTML = state.runs.map((run) => `
    <tr>
      <td>${escapeHtml(run.run_id || "")}</td>
      <td>${escapeHtml(formatNzDateTime(run.started_at || run.start_time || ""))}</td>
      <td>${formatRunQuery(run)}</td>
      <td>${escapeHtml(String(run.candidate_count ?? run.candidates_found ?? ""))}</td>
      <td>${escapeHtml(String(run.enriched_count ?? run.vendors_enriched ?? ""))}</td>
      <td>${escapeHtml(String(run.dropped_count ?? run.vendors_dropped ?? ""))}</td>
    </tr>
  `).join("") || '<tr><td colspan="6" class="message">No pipeline run snapshots found.</td></tr>';
}

function formatNzDateTime(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString("en-NZ", {
    timeZone: "Pacific/Auckland",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatRunQuery(run) {
  const queryText = String(run.query || run.queries_executed || "").trim();
  const pipelineLabel = String(run.pipeline_name || run.pipeline || "").trim() || "Apify Google search";
  return `
    <div class="cell-stack">
      <span>${escapeHtml(queryText)}</span>
      <span>Pipeline: ${escapeHtml(pipelineLabel)}</span>
    </div>
  `;
}

function renderFailureState(message) {
  const candidatesBody = document.getElementById("candidates-body");
  const vendorsBody = document.getElementById("vendors-body");
  const leadsBody = document.getElementById("leads-body");
  const runsBody = document.getElementById("runs-body");
  const leadCaptureMetrics = document.getElementById("lead-capture-metrics");
  const enrichmentMetrics = document.getElementById("enrichment-metrics");
  const pipelineControlMetrics = document.getElementById("pipeline-control-metrics");
  const pipelinesBody = document.getElementById("pipelines-body");
  if (candidatesBody) {
    candidatesBody.innerHTML = `<tr><td colspan="5" class="message">${escapeHtml(message)}</td></tr>`;
  }
  if (vendorsBody) {
    vendorsBody.innerHTML = `<tr><td colspan="6" class="message">${escapeHtml(message)}</td></tr>`;
  }
  if (leadsBody) {
    leadsBody.innerHTML = `<tr><td colspan="7" class="message">${escapeHtml(message)}</td></tr>`;
  }
  if (runsBody) {
    runsBody.innerHTML = `<tr><td colspan="6" class="message">${escapeHtml(message)}</td></tr>`;
  }
  if (leadCaptureMetrics) {
    leadCaptureMetrics.textContent = message;
  }
  if (enrichmentMetrics) {
    enrichmentMetrics.textContent = message;
  }
  if (pipelineControlMetrics) {
    pipelineControlMetrics.textContent = message;
  }
  if (pipelinesBody) {
    pipelinesBody.innerHTML = `<tr><td colspan="6" class="message">${escapeHtml(message)}</td></tr>`;
  }
}

function formatApiError(payload) {
  if (!payload || !payload.error) {
    return "";
  }
  const detail = payload.detail ? ` ${payload.detail}` : "";
  return `Data unavailable: ${payload.error}.${detail}`.trim();
}

async function handleVendorAction(event) {
  const button = event.currentTarget;
  const action = button.dataset.action;
  const vendor = button.dataset.vendor;
  if (!action || !vendor) {
    return;
  }

  const originalText = button.textContent;
  button.disabled = true;
  button.classList.add("action-active");
  button.textContent = originalText + "…";
  try {
    await fetchJson(`/admin/vendor/${action}`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({vendor}),
    });
    const vendors = await fetchJson("/admin/vendors");
    state.vendors = vendors.items || [];
    renderVendors();
  } catch (error) {
    button.disabled = false;
    button.classList.remove("action-active");
    button.textContent = originalText;
    window.alert(`Admin action failed: ${error.message}`);
  }
}

async function handleLeadFollowUpAction(event) {
  const button = event.currentTarget;
  const leadId = button.dataset.leadId;
  const followUpStatus = button.dataset.leadAction;
  if (!leadId || !followUpStatus) {
    return;
  }

  const originalText = button.textContent;
  button.disabled = true;
  button.classList.add("action-active");
  button.textContent = originalText + "…";
  try {
    await fetchJson("/admin/lead/follow-up", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({lead_id: leadId, follow_up_status: followUpStatus}),
    });
    const leads = await fetchJson("/admin/leads");
    state.leads = {
      metrics: leads.metrics || {},
      items: leads.items || [],
    };
    renderLeads();
  } catch (error) {
    button.disabled = false;
    button.classList.remove("action-active");
    button.textContent = originalText;
    window.alert(`Lead follow-up update failed: ${error.message}`);
  }
}

function formatLeadIdentity(lead) {
  return `
    <div class="cell-stack">
      <strong>${escapeHtml(lead.lead_name || "")}</strong>
      <span>${escapeHtml(lead.lead_email || "")}</span>
      <span>${escapeHtml(lead.company_name || "")}</span>
    </div>
  `;
}

function summarizeProductNames(products) {
  if (!Array.isArray(products)) {
    return "";
  }
  return products
    .map((product) => String(product?.name || "").trim())
    .filter(Boolean)
    .slice(0, 3)
    .join(", ");
}

function formatIntegrationSummary(vendor) {
  const taxonomy = Array.isArray(vendor.integration_taxonomy) ? vendor.integration_taxonomy : [];
  if (taxonomy.length) {
    return taxonomy
      .map((group) => {
        const category = integrationCategoryLabel(group?.category || "");
        const integrations = Array.isArray(group?.integrations)
          ? group.integrations.map((name) => String(name || "").trim()).filter(Boolean)
          : [];
        return integrations.length ? `${category}: ${integrations.join(", ")}` : category;
      })
      .join(" | ");
  }

  const categories = Array.isArray(vendor.integration_categories)
    ? vendor.integration_categories.map((value) => integrationCategoryLabel(value)).filter(Boolean)
    : [];
  const integrations = Array.isArray(vendor.integrations)
    ? vendor.integrations.map((value) => String(value || "").trim()).filter(Boolean)
    : [];
  const productCategories = collectProductIntegrationValues(vendor.products, "integration_categories")
    .map((value) => integrationCategoryLabel(value))
    .filter(Boolean);
  const productIntegrations = collectProductIntegrationValues(vendor.products, "integrations");
  const allCategories = Array.from(new Set([...categories, ...productCategories]));
  const allIntegrations = Array.from(new Set([...integrations, ...productIntegrations]));

  if (!allCategories.length && !allIntegrations.length) {
    return "";
  }
  if (!allCategories.length) {
    return allIntegrations.join(", ");
  }
  if (!allIntegrations.length) {
    return allCategories.join(", ");
  }
  return `${allCategories.join(", ")}: ${allIntegrations.join(", ")}`;
}

function integrationCategoryLabel(category) {
  const labels = {
    crm: "CRM",
    csp: "CSP",
    pm: "PM",
    workflow: "Workflow",
    "email/calendar": "Email/Calendar",
    communication: "Communication",
    support: "Support",
    warehouse: "Warehouse",
    other: "Other",
  };
  return labels[String(category || "").trim().toLowerCase()] || String(category || "").trim();
}

function collectProductIntegrationValues(products, fieldName) {
  if (!Array.isArray(products)) {
    return [];
  }
  return Array.from(
    new Set(
      products.flatMap((product) =>
        Array.isArray(product?.[fieldName])
          ? product[fieldName].map((value) => String(value || "").trim()).filter(Boolean)
          : []
      )
    )
  );
}

function formatVendorDecision(vendor) {
  const reasoning = Array.isArray(vendor.directory_reasoning) ? vendor.directory_reasoning.slice(0, 2).join(" | ") : "";
  const autoFit = vendor.llm_directory_fit || vendor.directory_fit || "";
  const autoCategory = vendor.llm_directory_category || vendor.directory_category || "";
  const autoInclude =
    vendor.llm_include_in_directory === true
      ? "true"
      : vendor.llm_include_in_directory === false
        ? "false"
        : "";
  return `
    <div class="cell-stack">
      <span>${escapeHtml(vendor.directory_fit || "")} · ${escapeHtml(vendor.directory_decision_source || "auto")}</span>
      <span>Auto: ${escapeHtml(autoFit)} / ${escapeHtml(autoCategory)} / ${escapeHtml(autoInclude)}</span>
      <span>${escapeHtml(reasoning || "Reasoning not captured.")}</span>
    </div>
  `;
}

function renderEnrichmentMetrics() {
  const node = document.getElementById("enrichment-metrics");
  if (!node) {
    return;
  }
  if (state.errors.enrichmentMetrics) {
    node.textContent = state.errors.enrichmentMetrics;
    return;
  }
  const metrics = state.enrichmentMetrics.metrics || {};
  const pipelineCounts = state.enrichmentMetrics.pipeline_counts || {};
  const topPipelines = Object.entries(pipelineCounts)
    .slice(0, 3)
    .map(([name, count]) => `${name}: ${count}`)
    .join(", ");
  const latest = metrics.latest_enriched_at || "n/a";
  node.textContent =
    `${metrics.total_enrichment_events || 0} enrichment events across ${metrics.vendors_with_enrichment || 0} vendors. ` +
    `Latest: ${latest}.` +
    (topPipelines ? ` Top pipelines: ${topPipelines}.` : "");
}

// IDs shown as batch cards (top-level, no vendor needed)
const BATCH_PIPELINE_IDS = [
  "full_pipeline",
  "google_discovery",
  "site_crawl_enrichment",
  "tier3_batch_crawl",
  "embed_vendor_pages",
  "firmographic_enrichment",
  "g2_rapidapi_enrichment",
  "trustpilot_enrichment",
  "feature_depth_enrichment",
  "ops_llm_enrichment_batch",
  "ops_ai_summary",
  "ops_export_dataset",
];

const BATCH_PIPELINE_SOURCES = {
  full_pipeline:            { label: "Full cycle",     cls: "source-tier" },
  google_discovery:         { label: "Apify · Google", cls: "source-tier" },
  tier3_batch_crawl:        { label: "Apify WCC · async", cls: "source-tier" },
  embed_vendor_pages:       { label: "Ollama · local",    cls: "source-merge" },
  g2_rapidapi_enrichment:   { label: "RapidAPI · G2",  cls: "source-g2" },
  firmographic_enrichment:  { label: "RapidAPI · Datagma", cls: "source-datagma" },
  trustpilot_enrichment:    { label: "Trustpilot · HTTP",   cls: "source-g2" },
  feature_depth_enrichment: { label: "Help crawl · GPT-4o mini", cls: "source-llm" },
  site_crawl_enrichment:    { label: "Apify · Crawl",  cls: "source-tier" },
  ops_llm_enrichment_batch: { label: "GPT-4o",         cls: "source-llm" },
  ops_ai_summary:           { label: "GPT-4o mini",    cls: "source-llm" },
  ops_export_dataset:       { label: "Supabase → JSON",cls: "source-merge" },
};

function renderPipelines() {
  const grid = document.getElementById("ops-batch-grid");
  const metricsNode = document.getElementById("pipeline-control-metrics");
  const rows = state.pipelines.length ? state.pipelines : normalizePipelineItems([]);
  const running = rows.filter((p) => p.status === "running").length;

  if (metricsNode) {
    const msg = state.errors.pipelines
      ? `Showing default controls — backend unavailable.`
      : `${rows.length} pipelines · ${running} running · Times NZ`;
    metricsNode.firstChild && (metricsNode.childNodes[0].textContent = msg + " · ");
  }

  if (!grid) return;

  const batchRows = rows.filter((p) => BATCH_PIPELINE_IDS.includes(p.pipeline_id));

  grid.innerHTML = batchRows.map((p) => {
    const status   = String(p.status || "idle");
    const src      = BATCH_PIPELINE_SOURCES[p.pipeline_id] || { label: "", cls: "source-null" };
    const progress = String(p.progress || "").trim();
    const lastRun  = p.last_triggered_at ? formatNzDateTime(p.last_triggered_at) : "Never";
    const isRunning = status === "running";
    return `
      <div class="pipeline-batch-card ${progress ? 'has-progress' : ''}" data-pipeline-id="${escapeAttribute(p.pipeline_id)}">
        <div style="display:flex;align-items:flex-start;gap:8px;">
          <div style="flex:1">
            <div class="pbc-name">${escapeHtml(p.name || p.pipeline_id)}</div>
          </div>
          <span class="ops-step-source ${src.cls}" style="white-space:nowrap;flex-shrink:0">${escapeHtml(src.label)}</span>
        </div>
        <div class="pbc-desc">${escapeHtml(p.description || "")}</div>
        <div class="pbc-meta">
          <span class="pbc-status ${status}">${escapeHtml(status)}</span>
          <span class="pbc-time">Last run: ${escapeHtml(lastRun)}</span>
        </div>
        <div class="pbc-actions">
          <button class="action-button action-primary" data-pipeline-action="run" data-pipeline-id="${escapeAttribute(p.pipeline_id)}" ${isRunning ? "disabled" : ""}>
            ${isRunning ? "Running…" : "Run"}
          </button>
          <button class="action-button action-secondary" data-pipeline-action="refresh">Refresh</button>
          ${isRunning ? `<button class="action-button action-danger" data-pipeline-action="reset" data-pipeline-id="${escapeAttribute(p.pipeline_id)}">Reset</button>` : ""}
        </div>
        ${progress ? `<pre class="pbc-progress">${escapeHtml(progress)}</pre>` : ""}
      </div>
    `;
  }).join("") || '<p style="color:#6e7681;font-size:13px;">No batch pipelines found.</p>';

  // Keep hidden table body in sync for click handler
  const hiddenBody = document.getElementById("pipelines-body");
  if (hiddenBody) {
    hiddenBody.innerHTML = rows.map((p) =>
      `<tr data-pipeline-id="${escapeAttribute(p.pipeline_id)}"></tr>`
    ).join("");
  }
}

// Card click handler — delegate from the grid
document.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-pipeline-action]");
  if (!btn) return;
  const card = btn.closest(".pipeline-batch-card");
  if (!card) return; // let existing table handler deal with table clicks
  // Reuse the existing table click logic by dispatching a synthetic event
  handlePipelineActionButton(btn);
});

async function handlePipelineActionButton(button) {
  const action = button.dataset.pipelineAction;
  const pipelineId = button.dataset.pipelineId;
  if (!pipelineId && action !== "refresh") return;

  if (action === "refresh") { await refreshPipelines(); return; }

  if (action === "reset") {
    button.disabled = true;
    button.textContent = "Resetting…";
    try {
      await fetchJson("/admin/pipelines/reset", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({pipeline_id: pipelineId}),
      });
    } catch (e) { window.alert(`Reset failed: ${e.message}`); }
    await refreshPipelines();
    return;
  }

  if (action === "run") {
    button.disabled = true;
    button.textContent = "Running…";
    try {
      await fetchJson("/admin/pipelines/run", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({pipeline_id: pipelineId}),
      });
    } catch (e) { window.alert(`Run failed: ${e.message}`); }
    button.textContent = "Run";
    await refreshPipelines();
  }
}

function renderPipelineRunners() {
  const body = document.getElementById("pipeline-runners-body");
  if (!body) {
    return;
  }
  const rows = state.pipelineRunners.length ? state.pipelineRunners : normalizePipelineRunners([]);
  body.innerHTML = rows.map((row) => `
    <tr>
      <td>${escapeHtml(String(row.step_order || ""))}</td>
      <td>${escapeHtml(String(row.phase || ""))}</td>
      <td>${escapeHtml(String(row.runner || ""))}</td>
      <td>${escapeHtml(String(row.details || ""))}</td>
      <td>${escapeHtml(formatRunnerConfig(row.config))}</td>
    </tr>
  `).join("") || '<tr><td colspan="5" class="message">No pipeline runner metadata found.</td></tr>';
}

function formatRunnerConfig(config) {
  if (!config || typeof config !== "object") {
    return "n/a";
  }
  const parts = Object.entries(config).map(([key, value]) => `${key}: ${String(value)}`);
  return parts.length ? parts.join(" | ") : "n/a";
}

async function handlePipelineTableClick(event) {
  const button = event.target.closest("[data-pipeline-action]");
  if (!button) return;
  // Card clicks are handled by the delegated listener — skip here
  if (button.closest(".pipeline-batch-card")) return;
  const action = button.dataset.pipelineAction;
  if (action === "refresh") {
    await refreshPipelines();
    return;
  }
  const pipelineId = button.dataset.pipelineId;

  if (action === "reset") {
    if (!pipelineId) return;
    button.disabled = true;
    button.textContent = "Resetting…";
    try {
      await fetchJson("/admin/pipelines/reset", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({pipeline_id: pipelineId}),
      });
    } catch (error) {
      window.alert(`Pipeline reset failed: ${error.message}`);
    } finally {
      await refreshPipelines();
    }
    return;
  }

  if (action !== "run") {
    return;
  }
  if (!pipelineId) {
    return;
  }
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "Running…";
  try {
    await fetchJson("/admin/pipelines/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({pipeline_id: pipelineId}),
    });
  } catch (error) {
    window.alert(`Pipeline trigger failed: ${error.message}`);
  } finally {
    button.textContent = originalText;
    await refreshPipelines();
  }
}

async function refreshPipelines() {
  try {
    const payload = await fetchJson("/admin/pipelines");
    state.pipelines = normalizePipelineItems(payload.items);
    state.errors.pipelines = formatApiError(payload);
  } catch (error) {
    state.pipelines = normalizePipelineItems([]);
    state.errors.pipelines = `Pipeline controls unavailable: ${error.message}`;
  }
  renderPipelines();
}

function normalizePipelineItems(items) {
  const source = Array.isArray(items) ? items.filter((item) => item && typeof item === "object") : [];
  const byId = new Map(source.map((item) => [String(item.pipeline_id || ""), item]));
  return DEFAULT_PIPELINE_CONTROLS.map((base) => {
    const live = byId.get(base.pipeline_id) || {};
    return {
      ...base,
      ...live,
      pipeline_id: String(live.pipeline_id || base.pipeline_id),
      name: String(live.name || base.name),
      description: String(live.description || base.description),
      status: String(live.status || "idle"),
      last_triggered_at: String(live.last_triggered_at || ""),
      last_finished_at: String(live.last_finished_at || ""),
      progress: String(live.progress || ""),
      group: String(live.group || base.group || "other"),
    };
  });
}

function normalizePipelineRunners(items) {
  const source = Array.isArray(items) ? items.filter((item) => item && typeof item === "object") : [];
  if (!source.length) {
    return DEFAULT_PIPELINE_RUNNERS;
  }
  return source.map((item, index) => ({
    step_order: item.step_order ?? index + 1,
    phase: String(item.phase || ""),
    runner: String(item.runner || ""),
    details: String(item.details || ""),
    config: item.config && typeof item.config === "object" ? item.config : {},
  }));
}

function formatLeadIntent(lead) {
  return `
    <div class="cell-stack">
      <span class="status-pill ${lead.intent_category === "service" ? "" : "is-neutral"}">${escapeHtml(lead.lead_intent || "")}</span>
      <span>${escapeHtml(lead.intent_category || "")}</span>
      <span>Priority: ${escapeHtml(lead.follow_up_priority || "")}</span>
    </div>
  `;
}

function formatLeadSource(lead) {
  const sourceBits = [
    lead.entry_page ? `Page: ${lead.entry_page}` : "",
    lead.vendor_name ? `Vendor: ${lead.vendor_name}` : "",
    lead.vendor_category ? `Category: ${lead.vendor_category}` : "",
  ].filter(Boolean);
  return `<div class="cell-stack">${sourceBits.map((bit) => `<span>${escapeHtml(bit)}</span>`).join("")}</div>`;
}

function formatLeadAttribution(lead) {
  const attributionBits = [
    lead.cta_surface ? `Surface: ${lead.cta_surface}` : "",
    lead.cta_variant ? `Variant: ${lead.cta_variant}` : "",
    lead.utm_source ? `UTM source: ${lead.utm_source}` : "",
    lead.utm_campaign ? `Campaign: ${lead.utm_campaign}` : "",
  ].filter(Boolean);
  return `<div class="cell-stack">${attributionBits.map((bit) => `<span>${escapeHtml(bit)}</span>`).join("") || "<span>Direct / untagged</span>"}</div>`;
}

function formatLeadFollowUp(lead) {
  const statusClass =
    lead.follow_up_status === "qualified"
      ? ""
      : lead.follow_up_status === "closed"
        ? "is-danger"
        : lead.follow_up_status === "new"
          ? "is-neutral"
          : "is-warning";
  return `
    <div class="cell-stack">
      <span class="status-pill ${statusClass}">${escapeHtml(lead.follow_up_status || "")}</span>
      <span>Owner: ${escapeHtml(lead.follow_up_owner || "")}</span>
      <span>${escapeHtml(lead.recommended_next_step || "")}</span>
    </div>
  `;
}

function formatList(values) {
  return Array.isArray(values) ? values.join(", ") : String(values || "");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}

// ── Vendor record modal ───────────────────────────────────────

const VENDOR_FIELDS = [
  { key: "name", label: "Vendor name" },
  { key: "website", label: "Website" },
  { key: "last_enriched_at", label: "Last enriched at" },
  { key: "last_enriched_pipeline", label: "Last enriched pipeline" },
  { key: "enrichment_count", label: "Enrichment count" },
  { key: "enrichment_pipeline_counts", label: "Pipeline counts", wide: true },
  { key: "mission", label: "Mission / description", wide: true },
  { key: "usp", label: "USP", wide: true },
  { key: "icp", label: "ICP" },
  { key: "icp_buyer", label: "ICP buyer" },
  { key: "use_cases", label: "Use cases", wide: true },
  { key: "lifecycle_stages", label: "Lifecycle stages" },
  { key: "pricing", label: "Pricing" },
  { key: "free_trial", label: "Free trial" },
  { key: "soc2", label: "SOC 2" },
  { key: "founded", label: "Founded" },
  { key: "directory_fit", label: "Directory fit" },
  { key: "directory_category", label: "Directory category" },
  { key: "include_in_directory", label: "Include in directory" },
  { key: "directory_decision_source", label: "Decision source" },
  { key: "confidence", label: "Confidence" },
  { key: "directory_reasoning", label: "Directory reasoning", wide: true },
  { key: "value_statements", label: "Value statements", wide: true },
  { key: "case_studies", label: "Case studies", wide: true },
  { key: "customers", label: "Customers", wide: true },
  { key: "integrations", label: "Integrations", wide: true },
  { key: "evidence_urls", label: "Evidence URLs", wide: true },
  { key: "source", label: "Source" },
];

function formatFieldValue(value) {
  if (value === null || value === undefined || value === "") {
    return { text: "—", empty: true };
  }
  if (typeof value === "boolean") {
    return { text: String(value), empty: false };
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return { text: "—", empty: true };
    return { text: value.map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v))).join("\n"), empty: false };
  }
  if (typeof value === "object") {
    return { text: JSON.stringify(value, null, 2), empty: false };
  }
  return { text: String(value), empty: false };
}

function showVendorModal(vendor) {
  const modal = document.getElementById("vendor-record-modal");
  const title = document.getElementById("record-modal-title");
  const body = document.getElementById("record-modal-body");
  if (!modal || !title || !body) return;

  const vendorName = vendor.name || vendor.vendor_name || vendor.website || "Unknown vendor";
  title.textContent = vendorName;

  body.innerHTML = VENDOR_FIELDS.map(({ key, label, wide }) => {
    const { text, empty } = formatFieldValue(vendor[key]);
    return `
      <div class="record-field${wide ? " full-width" : ""}">
        <span class="record-field-label">${escapeHtml(label)}</span>
        <span class="record-field-value${empty ? " is-empty" : ""}">${escapeHtml(text)}</span>
      </div>
    `;
  }).join("");

  modal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function hideVendorModal() {
  const modal = document.getElementById("vendor-record-modal");
  if (modal) modal.classList.add("hidden");
  document.body.style.overflow = "";
}

function showRawRecordModal(vendor) {
  let modal = document.getElementById("raw-record-modal");
  if (!modal) {
    document.body.insertAdjacentHTML("beforeend", `
      <div class="record-modal hidden" id="raw-record-modal">
        <div class="record-modal-backdrop" id="raw-record-modal-backdrop"></div>
        <div class="record-modal-panel" style="width:fit-content;min-width:340px;max-width:min(860px,95vw);max-height:80vh;overflow-y:auto" role="dialog" aria-modal="true">
          <div class="record-modal-header">
            <h2 class="record-modal-title" id="raw-record-title"></h2>
            <button class="record-modal-close" id="raw-record-close" type="button" aria-label="Close">✕</button>
          </div>
          <div id="raw-record-body"></div>
        </div>
      </div>
    `);
    document.getElementById("raw-record-close").addEventListener("click", hideRawRecordModal);
    document.getElementById("raw-record-modal-backdrop").addEventListener("click", hideRawRecordModal);
    modal = document.getElementById("raw-record-modal");
  }

  const vendorName = vendor.name || vendor.vendor_name || vendor.website || "Unknown vendor";
  document.getElementById("raw-record-title").textContent = vendorName + " — raw record";
  document.getElementById("raw-record-body").innerHTML =
    `<pre style="margin:0;padding:14px 16px;background:#fff;color:#1d2522;border-radius:12px;font-size:0.78rem;line-height:1.6;white-space:pre-wrap;word-break:break-all">${escapeHtml(JSON.stringify(vendor, null, 2))}</pre>`;

  modal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function hideRawRecordModal() {
  const modal = document.getElementById("raw-record-modal");
  if (modal) modal.classList.add("hidden");
  document.body.style.overflow = "";
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("vendor-record-modal")?.querySelector(".record-modal-close")?.addEventListener("click", hideVendorModal);
  document.getElementById("vendor-record-modal")?.querySelector(".record-modal-backdrop")?.addEventListener("click", hideVendorModal);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { hideVendorModal(); hideRawRecordModal(); }
  });

  const publishBtn = document.getElementById("publish-btn");
  const publishStatus = document.getElementById("publish-status");
  if (publishBtn) {
    publishBtn.addEventListener("click", async () => {
      publishBtn.disabled = true;
      publishStatus.textContent = "Publishing…";
      try {
        const base = state.apiBase || API_FALLBACK_BASE;
        const res = await fetch(`${base}/admin/publish`, { method: "POST" });
        const data = await res.json();
        if (data.ok) {
          publishStatus.textContent = `Published ${data.vendor_count} vendors.`;
        } else {
          publishStatus.textContent = `Error: ${data.error}`;
        }
      } catch (err) {
        publishStatus.textContent = `Failed: ${err.message}`;
      } finally {
        publishBtn.disabled = false;
      }
    });
  }
});

// ---- Pipeline Log Panel (M-OPS1) ----
let _logPollInterval = null;
let _pipelinePollInterval = null;

async function refreshPipelineLog() {
  const container = document.getElementById('pipeline-log-entries');
  const status    = document.getElementById('log-refresh-status');
  if (!container) return;
  try {
    const base = (window.state && window.state.apiBase) || API_FALLBACK_BASE;
    const res  = await fetch(`${base}/admin/pipeline-log`);
    const data = await res.json();
    if (!data.ok || !Array.isArray(data.entries)) return;
    container.innerHTML = data.entries.map(entry => {
      const ts       = entry.timestamp ? entry.timestamp.substring(0, 19).replace('T', ' ') : '';
      const phase    = entry.phase    ? `<span style="color:#58a6ff">[${escHtml(entry.phase)}]</span> ` : '';
      const ms       = entry.milestone ? `<span style="color:#d2a8ff">${escHtml(entry.milestone)}</span> ` : '';
      const action   = entry.action   ? `<span style="color:#79c0ff">${escHtml(entry.action)}</span> ` : '';
      const msg      = entry.message  ? `<span style="color:#c9d1d9">${escHtml(entry.message)}</span>` : '';
      const ok       = entry.success === false ? '<span style="color:#ff7b72"> ✗</span>' : (entry.success === true ? '<span style="color:#56d364"> ✓</span>' : '');
      return `<div style="padding:2px 0;border-bottom:1px solid #21262d"><span style="color:#6e7681">${ts}</span> ${phase}${ms}${action}${msg}${ok}</div>`;
    }).join('') || '<span style="color:#888">No log entries found.</span>';
    status.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    status.textContent = `Error: ${err.message}`;
  }
}

function escHtml(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function startPipelinePolling() {
  if (_pipelinePollInterval) {
    clearInterval(_pipelinePollInterval);
  }
  _pipelinePollInterval = setInterval(() => {
    refreshPipelines();
  }, 5000);
}

// ── M76 Enrichment Workbench ───────────────────────────────────────────────

let _opsVendor = '';

function opsSetVendor() {
  const input = document.getElementById('ops-vendor-input');
  const status = document.getElementById('ops-vendor-status');
  const raw = (input ? input.value : '').trim();
  if (!raw) { if (status) status.textContent = 'Enter a vendor website URL.'; return; }
  _opsVendor = raw;
  if (status) status.textContent = `Vendor set: ${raw}`;
  opsCheckStep5Guard();
  opsLoadFieldCoverage();
}

async function opsCheckStep5Guard() {
  const btn = document.getElementById('ops-step5-btn');
  const guard = document.getElementById('ops-step5-guard');
  const countEl = document.getElementById('ops-step2-pages-count');
  if (!_opsVendor) return;
  try {
    const base = (window.state && window.state.apiBase) || API_FALLBACK_BASE;
    const res = await fetch(`${base}/admin/ops/field-coverage?vendor_website=${encodeURIComponent(_opsVendor)}&check=vendor_pages_count`);
    const data = await res.json();
    const count = data.vendor_pages_count || 0;
    if (countEl) countEl.textContent = `vendor_pages rows for this vendor: ${count}`;
    const insufficient = count < 10;
    if (guard) guard.style.display = insufficient ? 'block' : 'none';
    if (guard && insufficient) guard.textContent = `Run Step 2 (Tier Crawl) first — vendor_pages has ${count} rows for this vendor.`;
    if (btn) btn.disabled = insufficient;
  } catch (_) {}
}

async function opsRunStep(btn) {
  const pipelineId = btn.dataset.opsRun;
  if (!pipelineId) return;
  if (!_opsVendor) { alert('Set a vendor website first.'); return; }
  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = 'Running…';
  try {
    await fetchJson('/admin/pipelines/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({pipeline_id: pipelineId, vendor_website: _opsVendor}),
    });
    const stepEl = btn.closest('.ops-step-card');
    const statusEl = stepEl ? stepEl.querySelector('.ops-step-status') : null;
    if (statusEl) statusEl.textContent = 'Triggered — check Pipeline Log below';
    if (pipelineId === 'ops_crawl_llm' || pipelineId === 'ops_crawl_tier1' ||
        pipelineId === 'ops_crawl_tier2' || pipelineId === 'ops_crawl_tier3') {
      setTimeout(opsCheckStep5Guard, 5000);
    }
    if (pipelineId === 'ops_merge') {
      setTimeout(opsLoadFieldCoverage, 8000);
    }
  } catch (err) {
    alert(`Step trigger failed: ${err.message}`);
  } finally {
    btn.textContent = orig;
    btn.disabled = false;
  }
}

async function opsRunBatch(btn) {
  const limitInput = document.getElementById('ops-step7-limit');
  const limit = limitInput ? parseInt(limitInput.value, 10) || 0 : 0;
  const statusEl = document.getElementById('ops-step7-status');
  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = 'Starting…';
  if (statusEl) statusEl.textContent = '';
  try {
    const body = {pipeline_id: 'ops_llm_enrichment_batch'};
    if (limit > 0) body.limit = limit;
    await fetchJson('/admin/pipelines/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    if (statusEl) statusEl.textContent = `Batch triggered (limit: ${limit || 'all'}) — monitor Pipeline Log below`;
  } catch (err) {
    alert(`Batch enrichment failed: ${err.message}`);
  } finally {
    btn.textContent = orig;
    btn.disabled = false;
  }
}

async function opsRunN8nEnrichment(webhookPath, statusId, btn) {
  const statusEl = document.getElementById(statusId);
  if (!_opsVendor) {
    if (statusEl) statusEl.textContent = 'Set a vendor first';
    return;
  }
  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = 'Running…';
  if (statusEl) statusEl.textContent = 'Triggering n8n…';
  try {
    const resp = await fetch(`https://successbycs.app.n8n.cloud/webhook/${webhookPath}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({vendors: [{website: _opsVendor}]}),
    });
    const result = await resp.json().catch(() => ({}));
    if (statusEl) statusEl.textContent = resp.ok ? 'Triggered — check Supabase for results' : `Error: ${result.message || resp.status}`;
  } catch (e) {
    if (statusEl) statusEl.textContent = `Failed: ${e.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

async function opsExportPublish(btn) {
  const statusEl = document.getElementById('ops-step10-status');
  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = 'Publishing…';
  if (statusEl) statusEl.textContent = '';
  try {
    const base = (window.state && window.state.apiBase) || API_FALLBACK_BASE;
    const res = await fetch(`${base}/admin/publish`, { method: 'POST' });
    const data = await res.json();
    if (statusEl) statusEl.textContent = data.ok ? `Published ${data.vendor_count} vendors.` : `Error: ${data.error}`;
  } catch (err) {
    if (statusEl) statusEl.textContent = `Failed: ${err.message}`;
  } finally {
    btn.textContent = orig;
    btn.disabled = false;
  }
}

async function opsRunCrawlStep() {
  const tierSelect = document.getElementById('ops-step2-tier');
  const maxPagesInput = document.getElementById('ops-step2-maxpages');
  const pipelineId = tierSelect ? tierSelect.value : 'ops_crawl_tier3';
  const maxPages = maxPagesInput ? parseInt(maxPagesInput.value, 10) || 100 : 100;
  if (!_opsVendor) { alert('Set a vendor website first.'); return; }
  try {
    await fetchJson('/admin/pipelines/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({pipeline_id: pipelineId, vendor_website: _opsVendor, max_pages: maxPages}),
    });
    const statusEl = document.getElementById('ops-step2-status');
    if (statusEl) statusEl.textContent = `Triggered ${pipelineId} (max_pages=${maxPages}) — check Pipeline Log`;
    setTimeout(opsCheckStep5Guard, 8000);
  } catch (err) {
    alert(`Crawl step trigger failed: ${err.message}`);
  }
}

async function opsLoadFieldCoverage() {
  const container = document.getElementById('ops-field-coverage');
  if (!container || !_opsVendor) return;
  try {
    const base = (window.state && window.state.apiBase) || API_FALLBACK_BASE;
    const res = await fetch(`${base}/admin/ops/field-coverage?vendor_website=${encodeURIComponent(_opsVendor)}`);
    const data = await res.json();
    if (!data.ok || !data.coverage) { container.innerHTML = ''; return; }

    const sfm = data.source_field_map || {};
    const sourceClass = {tier1:'source-tier',tier2:'source-tier',tier3:'source-tier',datagma:'source-datagma',g2:'source-g2',llm:'source-llm'};

    const rows = Object.entries(sfm).map(([field, src]) => {
      const cls = sourceClass[src] || 'source-null';
      return `<tr><td>${escHtml(field)}</td><td><span class="ops-step-source ${cls}">${escHtml(src)}</span></td></tr>`;
    }).join('');

    container.innerHTML = rows ? `
      <p style="font-size:12px;font-weight:600;color:#8b949e;margin:0 0 6px 0;">Field coverage after last merge</p>
      <table class="ops-coverage-table">
        <thead><tr><th>field</th><th>source</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>` : '';
  } catch (_) {}
}

// Start polling on page load
document.addEventListener('DOMContentLoaded', () => {
  refreshPipelineLog();
  _logPollInterval = setInterval(refreshPipelineLog, 3000);
});
