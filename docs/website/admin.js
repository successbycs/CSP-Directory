const API_FALLBACK_BASE = "http://127.0.0.1:8787";
const DEFAULT_PIPELINE_CONTROLS = [
  {
    pipeline_id: "full_pipeline",
    name: "Full Discovery + Enrichment",
    description:
      "Includes Apify Google Search discovery -> Apify/web crawl enrichment (configured depth/page limits) -> deterministic + optional LLM extraction -> persistence + export.",
  },
  {
    pipeline_id: "weekly_discovery_job",
    name: "Weekly Discovery Job",
    description:
      "Discovery-only runner: Apify Google Search using configured query set and candidate limits.",
  },
  {
    pipeline_id: "weekly_digest_job",
    name: "Weekly Digest Job",
    description: "Digest/report runner: builds weekly lifecycle summary outputs.",
  },
  {
    pipeline_id: "g2_rapidapi_enrichment",
    name: "G2 RapidAPI Enrichment",
    description:
      "Targeted enrichment runner: G2 RapidAPI enrichment over included vendors.",
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
  searchVisibility: {
    metrics: {},
    role_query_rankings: [],
    vendor_visibility_summary: [],
  },
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
    searchVisibility: "",
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
    const [candidates, vendors, leads, runs, searchVisibility, enrichmentMetrics, pipelineRunners, pipelines] = await Promise.all([
      fetchJson("/admin/candidates"),
      fetchJson("/admin/vendors"),
      fetchJson("/admin/leads"),
      fetchJson("/admin/runs"),
      fetchJson("/admin/search-visibility"),
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
    state.searchVisibility = {
      metrics: searchVisibility.metrics || {},
      role_query_rankings: searchVisibility.role_query_rankings || [],
      vendor_visibility_summary: searchVisibility.vendor_visibility_summary || [],
    };
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
    state.errors.searchVisibility = formatApiError(searchVisibility);
    state.errors.enrichmentMetrics = formatApiError(enrichmentMetrics);
    state.errors.pipelineRunners = formatApiError(pipelineRunners);
    state.errors.pipelines = formatApiError(pipelines);

    populateVendorCategoryFilter();
    renderCandidates();
    renderVendors();
    renderLeads();
    renderRuns();
    renderSearchVisibility();
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
    const vendorName = vendor.name || vendor.vendor_name || "";
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

function renderSearchVisibility() {
  const summaryBody = document.getElementById("search-visibility-summary-body");
  const rankingsBody = document.getElementById("search-visibility-rankings-body");
  const metricsNode = document.getElementById("search-visibility-metrics");
  if (!summaryBody || !rankingsBody || !metricsNode) {
    return;
  }
  if (state.errors.searchVisibility) {
    metricsNode.textContent = state.errors.searchVisibility;
    summaryBody.innerHTML = `<tr><td colspan="6" class="message">${escapeHtml(state.errors.searchVisibility)}</td></tr>`;
    rankingsBody.innerHTML = `<tr><td colspan="7" class="message">${escapeHtml(state.errors.searchVisibility)}</td></tr>`;
    return;
  }

  const metrics = state.searchVisibility.metrics || {};
  metricsNode.textContent = `${metrics.query_count || 0} queries, ${metrics.ranking_count || 0} rankings, ${metrics.vendor_count || 0} surfaced vendors.`;

  const summaryRows = (state.searchVisibility.vendor_visibility_summary || []).slice(0, 10);
  summaryBody.innerHTML = summaryRows.map((row) => `
    <tr>
      <td>${escapeHtml(row.surfaced_vendor_name || "")}</td>
      <td>${escapeHtml(String(row.appearances ?? ""))}</td>
      <td>${escapeHtml(String(row.best_rank ?? ""))}</td>
      <td>${escapeHtml(String(row.average_visibility_score ?? ""))}</td>
      <td>${escapeHtml(formatList(row.buyer_roles))}</td>
      <td>${escapeHtml(formatList(row.search_channels))}</td>
    </tr>
  `).join("") || '<tr><td colspan="6" class="message">No vendor visibility summary rows found.</td></tr>';

  const rankingRows = (state.searchVisibility.role_query_rankings || []).slice(0, 12);
  rankingsBody.innerHTML = rankingRows.map((row) => `
    <tr>
      <td>${escapeHtml(row.run_timestamp || "")}</td>
      <td>${escapeHtml(row.buyer_role || "")}</td>
      <td>${escapeHtml(row.search_channel_label || "")}</td>
      <td>${escapeHtml(row.query_text || "")}</td>
      <td>${escapeHtml(String(row.observed_rank ?? ""))}</td>
      <td>${escapeHtml(row.surfaced_vendor_name || "")}</td>
      <td>${escapeHtml(String(row.visibility_score ?? ""))}</td>
    </tr>
  `).join("") || '<tr><td colspan="7" class="message">No role-by-query ranking rows found.</td></tr>';
}

function renderFailureState(message) {
  const candidatesBody = document.getElementById("candidates-body");
  const vendorsBody = document.getElementById("vendors-body");
  const leadsBody = document.getElementById("leads-body");
  const runsBody = document.getElementById("runs-body");
  const searchVisibilitySummaryBody = document.getElementById("search-visibility-summary-body");
  const searchVisibilityRankingsBody = document.getElementById("search-visibility-rankings-body");
  const searchVisibilityMetrics = document.getElementById("search-visibility-metrics");
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
  if (searchVisibilitySummaryBody) {
    searchVisibilitySummaryBody.innerHTML = `<tr><td colspan="6" class="message">${escapeHtml(message)}</td></tr>`;
  }
  if (searchVisibilityRankingsBody) {
    searchVisibilityRankingsBody.innerHTML = `<tr><td colspan="7" class="message">${escapeHtml(message)}</td></tr>`;
  }
  if (searchVisibilityMetrics) {
    searchVisibilityMetrics.textContent = message;
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

function renderPipelines() {
  const body = document.getElementById("pipelines-body");
  const metricsNode = document.getElementById("pipeline-control-metrics");
  if (!body || !metricsNode) {
    return;
  }
  const rows = state.pipelines.length ? state.pipelines : normalizePipelineItems([]);
  const running = rows.filter((pipeline) => pipeline.status === "running").length;
  metricsNode.textContent = state.errors.pipelines
    ? `${rows.length} pipeline controls configured. ${state.errors.pipelines} Showing default controls.`
    : `${rows.length} pipeline controls configured, ${running} running. Times shown in NZ (Pacific/Auckland).`;

  body.innerHTML = rows.map((pipeline) => {
    const status = String(pipeline.status || "idle");
    const statusClass = status === "running" ? "is-warning" : status === "failed" ? "is-danger" : "is-neutral";
    const progress = String(pipeline.progress || "").trim();
    const progressText = progress || (state.errors.pipelines ? "Pipeline endpoint unavailable on this backend instance." : "No log output yet.");
    return `
      <tr>
        <td>
          <div class="cell-stack">
            <strong>${escapeHtml(pipeline.name || pipeline.pipeline_id || "")}</strong>
            <span>${escapeHtml(pipeline.description || "")}</span>
            <span><code>${escapeHtml(pipeline.pipeline_id || "")}</code></span>
          </div>
        </td>
        <td><span class="status-pill ${statusClass}">${escapeHtml(status)}</span></td>
        <td>${escapeHtml(formatNzDateTime(pipeline.last_triggered_at || ""))}</td>
        <td>${escapeHtml(formatNzDateTime(pipeline.last_finished_at || ""))}</td>
        <td>
          <div class="actions">
            <button class="action-button action-primary" data-pipeline-action="run" data-pipeline-id="${escapeAttribute(pipeline.pipeline_id || "")}" ${status === "running" ? "disabled" : ""}>Run</button>
            <button class="action-button action-secondary" data-pipeline-action="refresh">Refresh</button>
          </div>
        </td>
        <td><pre class="pipeline-progress">${escapeHtml(progressText)}</pre></td>
      </tr>
    `;
  }).join("") || '<tr><td colspan="6" class="message">No pipeline controls found.</td></tr>';
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
  if (!button) {
    return;
  }
  const action = button.dataset.pipelineAction;
  if (action === "refresh") {
    await refreshPipelines();
    return;
  }
  if (action !== "run") {
    return;
  }
  const pipelineId = button.dataset.pipelineId;
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

// Start polling on page load
document.addEventListener('DOMContentLoaded', () => {
  refreshPipelineLog();
  _logPollInterval = setInterval(refreshPipelineLog, 3000);
});
