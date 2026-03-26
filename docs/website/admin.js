const API_FALLBACK_BASE = "http://127.0.0.1:8787";

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
  errors: {
    candidates: "",
    vendors: "",
    leads: "",
    runs: "",
    searchVisibility: "",
  },
};

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("candidate-search")?.addEventListener("input", renderCandidates);
  document.getElementById("candidate-status-filter")?.addEventListener("change", renderCandidates);
  document.getElementById("vendor-search")?.addEventListener("input", renderVendors);
  document.getElementById("vendor-category-filter")?.addEventListener("change", renderVendors);
  document.getElementById("lead-search")?.addEventListener("input", renderLeads);
  document.getElementById("lead-status-filter")?.addEventListener("change", renderLeads);
  loadDashboard();
});

async function loadDashboard() {
  try {
    state.apiBase = await detectApiBase();
    const [candidates, vendors, leads, runs, searchVisibility] = await Promise.all([
      fetchJson("/admin/candidates"),
      fetchJson("/admin/vendors"),
      fetchJson("/admin/leads"),
      fetchJson("/admin/runs"),
      fetchJson("/admin/search-visibility"),
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
    state.errors.candidates = formatApiError(candidates);
    state.errors.vendors = formatApiError(vendors);
    state.errors.leads = formatApiError(leads);
    state.errors.runs = formatApiError(runs);
    state.errors.searchVisibility = formatApiError(searchVisibility);

    populateVendorCategoryFilter();
    renderCandidates();
    renderVendors();
    renderLeads();
    renderRuns();
    renderSearchVisibility();
  } catch (error) {
    renderFailureState(`Admin API unavailable: ${error.message}`);
  }
}

async function detectApiBase() {
  try {
    const response = await fetch("/admin/candidates");
    if (response.ok) {
      return "";
    }
  } catch (error) {
    // fall through to local API fallback
  }
  return API_FALLBACK_BASE;
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
        <td>${escapeHtml(candidate.discovered_at || "")}</td>
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
      <td>${escapeHtml(lead.created_at || "")}</td>
      <td>${formatLeadIdentity(lead)}</td>
      <td>${formatLeadIntent(lead)}</td>
      <td>${formatLeadSource(lead)}</td>
      <td>${formatLeadAttribution(lead)}</td>
      <td>${formatLeadFollowUp(lead)}</td>
      <td>
        <div class="actions">
          <button class="action-button action-secondary" data-lead-action="in_progress" data-lead-id="${escapeAttribute(lead.lead_id || "")}">Start</button>
          <button class="action-button action-secondary" data-lead-action="contacted" data-lead-id="${escapeAttribute(lead.lead_id || "")}">Contacted</button>
          <button class="action-button action-primary" data-lead-action="qualified" data-lead-id="${escapeAttribute(lead.lead_id || "")}">Qualified</button>
        </div>
      </td>
    </tr>
  `).join("") || '<tr><td colspan="7" class="message">No captured leads found.</td></tr>';

  body.querySelectorAll("[data-lead-action]").forEach((button) => {
    button.addEventListener("click", handleLeadFollowUpAction);
  });
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
      <td>${escapeHtml(run.started_at || run.start_time || "")}</td>
      <td>${escapeHtml(run.query || run.queries_executed || "")}</td>
      <td>${escapeHtml(String(run.candidate_count ?? run.candidates_found ?? ""))}</td>
      <td>${escapeHtml(String(run.enriched_count ?? run.vendors_enriched ?? ""))}</td>
      <td>${escapeHtml(String(run.dropped_count ?? run.vendors_dropped ?? ""))}</td>
    </tr>
  `).join("") || '<tr><td colspan="6" class="message">No pipeline run snapshots found.</td></tr>';
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
