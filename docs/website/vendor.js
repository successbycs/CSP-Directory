const DATASET_URL = "./data/directory_dataset.json";

document.addEventListener("DOMContentLoaded", () => {
  loadVendorProfile();
});

async function loadVendorProfile() {
  const container = document.getElementById("vendor-profile");
  const vendorKey = decodeURIComponent(new URLSearchParams(window.location.search).get("vendor") || "").trim();

  if (!vendorKey) {
    renderNotFound(container, "No vendor identifier was provided.");
    return;
  }

  try {
    const response = await fetch(DATASET_URL);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const dataset = await response.json();
    const vendors = Array.isArray(dataset) ? dataset : [];
    const vendor = resolveVendor(vendors, vendorKey);

    if (!vendor) {
      renderNotFound(container, "Vendor not found in the current directory dataset.");
      return;
    }

    renderVendor(container, vendor);
  } catch (error) {
    renderNotFound(container, "Directory dataset could not be loaded.");
  }
}

function resolveVendor(vendors, vendorKey) {
  const normalizedKey = normalizeValue(vendorKey);
  return vendors.find((vendor) => {
    const website = String(vendor.website || "");
    const name = String(vendor.vendor_name || "");
    return [
      normalizeValue(vendorSlug(vendor)),
      normalizeValue(name),
      normalizeValue(website),
      normalizeValue(stripProtocol(website)),
    ].includes(normalizedKey);
  });
}

function renderVendor(container, vendor) {
  const vendorName = vendor.vendor_name || "Unknown vendor";
  const website = vendor.website || "";
  const websiteLabel = stripProtocol(website) || "Website unavailable";
  const category = formatCategory(vendor.directory_category);
  const fit = formatText(vendor.directory_fit);
  const confidence = formatText(vendor.confidence);
  const mission = vendor.mission || "Mission not captured for this vendor yet.";
  const usp = vendor.usp || "No differentiated positioning captured yet.";
  const pricing = formatList(vendor.pricing);
  const stageCount = Array.isArray(vendor.lifecycle_stages) ? vendor.lifecycle_stages.length : 0;
  const useCaseCount = Array.isArray(vendor.use_cases) ? vendor.use_cases.length : 0;
  const evidenceCount = Array.isArray(vendor.evidence_urls) ? vendor.evidence_urls.length : 0;
  const founded = formatText(vendor.founded);

  document.title = `${vendorName} | SuccessByCS Directory`;

  container.className = "profile";
  container.innerHTML = `
    <section class="hero">
      <div>
        <p class="eyebrow">Vendor profile</p>
        <h1>${escapeHtml(vendorName)}</h1>
        <p class="hero-sub">${escapeHtml(mission)}</p>
        <p class="hero-summary">
          ${escapeHtml(usp)} This profile pulls together the signals currently captured for
          this vendor so a buyer can move from a market-map view into a practical evaluation.
        </p>
        <div class="chip-row">
          ${renderChip(category)}
          ${renderChip(`Fit: ${fit}`)}
          ${renderChip(`Confidence: ${confidence}`)}
          ${renderChip(founded === "Not captured" ? "Founded not captured" : `Founded ${founded}`)}
          ${renderChip(vendor.free_trial === true ? "Free trial" : "No free-trial signal")}
          ${renderChip(vendor.soc2 === true ? "SOC 2 signal" : "No SOC 2 signal")}
        </div>
        <div class="hero-actions">
          ${website ? `<a class="button button-primary" href="${escapeAttribute(website)}" target="_blank" rel="noreferrer">Visit website</a>` : ""}
          <a class="button button-secondary" href="./browse.html">Back to browse</a>
        </div>
      </div>
      <aside class="hero-side">
        <section class="hero-card">
          <p class="eyebrow">Snapshot</p>
          <h3>${escapeHtml(websiteLabel)}</h3>
          <p>
            ${escapeHtml(category)} vendor with ${stageCount} lifecycle stage${stageCount === 1 ? "" : "s"},
            ${useCaseCount} use case${useCaseCount === 1 ? "" : "s"}, and ${evidenceCount}
            evidence source${evidenceCount === 1 ? "" : "s"} currently captured.
          </p>
          <div class="tag-list">
            ${renderTags(vendor.lifecycle_stages)}
          </div>
        </section>
        <section class="note-card">
          <p class="eyebrow">Buyer action</p>
          <h3>Need a shortlist around ${escapeHtml(vendorName)}?</h3>
          <p>Capture vendor-specific context and route the next step into the SuccessByCS follow-up flow.</p>
          <div class="hero-actions">
            <button
              class="button button-primary"
              type="button"
              data-lead-magnet-trigger
              data-cta-surface="vendor-profile"
              data-cta-variant="shortlist-brief"
              data-cta-intent="shortlist"
              data-cta-label="Get shortlist brief"
              data-vendor-name="${escapeAttribute(vendorName)}"
              data-vendor-website="${escapeAttribute(website)}"
              data-vendor-category="${escapeAttribute(category)}"
            >
              Get shortlist brief
            </button>
            <button
              class="button button-secondary"
              type="button"
              data-lead-magnet-trigger
              data-cta-surface="vendor-profile"
              data-cta-variant="advisory-intro"
              data-cta-intent="advisory"
              data-cta-label="Talk to SuccessByCS"
              data-vendor-name="${escapeAttribute(vendorName)}"
              data-vendor-website="${escapeAttribute(website)}"
              data-vendor-category="${escapeAttribute(category)}"
            >
              Talk to SuccessByCS
            </button>
          </div>
        </section>
      </aside>
    </section>

    <section class="metric-grid">
      ${renderMetricCard("Lifecycle coverage", String(stageCount), formatList(vendor.lifecycle_stages) || "No stages captured")}
      ${renderMetricCard("Use cases", String(useCaseCount), formatList(vendor.use_cases) || "No use cases captured")}
      ${renderMetricCard("Pricing signals", pricing === "Not captured" ? "None" : String((vendor.pricing || []).length), pricing)}
      ${renderMetricCard("Evidence URLs", String(evidenceCount), evidenceCount ? "Sources linked below" : "No evidence URLs captured")}
    </section>

    <section class="content-grid">
      <div class="content-main">
        <section class="section-card">
          <div>
            <p class="eyebrow">Overview</p>
            <h2>What this vendor appears to do</h2>
          </div>
          <p class="section-copy">${escapeHtml(mission)}</p>
          <div class="detail-grid">
            ${renderDetailItem("Unique selling point", usp)}
            ${renderDetailItem("Category", category)}
            ${renderDetailItem("Directory fit", fit)}
            ${renderDetailItem("Confidence", confidence)}
          </div>
        </section>

        <section class="section-card">
          <div>
            <p class="eyebrow">Buyer fit</p>
            <h2>Who this looks relevant for</h2>
          </div>
          <div class="detail-grid">
            ${renderDetailItem("Ideal customer profile", formatList(vendor.icp))}
            ${renderDetailItem("Use cases", formatList(vendor.use_cases))}
            ${renderDetailItem("Lifecycle stages", formatList(vendor.lifecycle_stages))}
            ${renderDetailItem("Pricing", pricing)}
          </div>
        </section>

        ${renderStorySection("Case-study details", vendor.case_study_details, formatCaseStudy)}
        ${renderStorySection("Use-case detail objects", vendor.use_case_details, formatUseCaseDetail)}
        ${renderSimpleListSection("Value statements", vendor.value_statements)}
      </div>

      <aside class="content-side">
        <section class="section-card">
          <div>
            <p class="eyebrow">Operational signals</p>
            <h2>What we have on record</h2>
          </div>
          <div class="detail-grid">
            ${renderDetailItem("Website", websiteLabel)}
            ${renderDetailItem("Founded", founded)}
            ${renderDetailItem("Free trial", formatBoolean(vendor.free_trial))}
            ${renderDetailItem("SOC 2", formatBoolean(vendor.soc2))}
          </div>
        </section>

        <section class="section-card">
          <div>
            <p class="eyebrow">Evidence</p>
            <h2>Source links</h2>
          </div>
          ${renderEvidenceList(vendor.evidence_urls)}
        </section>
      </aside>
    </section>
  `;
}

function renderMetricCard(label, value, note) {
  return `
    <article class="metric-card">
      <p class="metric-label">${escapeHtml(label)}</p>
      <p class="metric-value">${escapeHtml(value)}</p>
      <p class="metric-note">${escapeHtml(note)}</p>
    </article>
  `;
}

function renderDetailItem(label, value) {
  return `
    <dl class="detail-item">
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(value || "Not captured")}</dd>
    </dl>
  `;
}

function renderSimpleListSection(title, items) {
  if (!Array.isArray(items) || !items.length) {
    return "";
  }

  return `
    <section class="section-card">
      <div>
        <p class="eyebrow">Signals</p>
        <h2>${escapeHtml(title)}</h2>
      </div>
      <ul class="list">
        ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
    </section>
  `;
}

function renderStorySection(title, items, formatter) {
  if (!Array.isArray(items) || !items.length) {
    return "";
  }

  return `
    <section class="section-card">
      <div>
        <p class="eyebrow">Structured detail</p>
        <h2>${escapeHtml(title)}</h2>
      </div>
      <div class="story-list">
        ${items.map((item) => formatter(item)).join("")}
      </div>
    </section>
  `;
}

function formatCaseStudy(item) {
  const title = item.title || item.client || "Case study";
  const highlights = [item.client, item.use_case, item.metric].filter(Boolean);
  return `
    <article class="story-card">
      <h3>${escapeHtml(title)}</h3>
      ${highlights.length ? `<div class="story-meta">${highlights.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}</div>` : ""}
      ${item.value_realized ? `<p>${escapeHtml(item.value_realized)}</p>` : ""}
      ${item.source_url ? `<a href="${escapeAttribute(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(item.source_url)}</a>` : ""}
    </article>
  `;
}

function formatUseCaseDetail(item) {
  const title = item.label || item.title || "Use case";
  return `
    <article class="story-card">
      <h3>${escapeHtml(title)}</h3>
      ${item.summary ? `<p>${escapeHtml(item.summary)}</p>` : ""}
      ${item.url ? `<a href="${escapeAttribute(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.url)}</a>` : ""}
    </article>
  `;
}

function renderEvidenceList(urls) {
  if (!Array.isArray(urls) || !urls.length) {
    return '<p class="section-copy">No evidence URLs captured for this vendor yet.</p>';
  }

  return `
    <ul class="evidence-list">
      ${urls.map((url) => `<li><a href="${escapeAttribute(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a></li>`).join("")}
    </ul>
  `;
}

function renderTags(values) {
  if (!Array.isArray(values) || !values.length) {
    return renderTag("No lifecycle mapping");
  }
  return values.map((value) => renderTag(value)).join("");
}

function renderTag(value) {
  return `<span class="tag">${escapeHtml(value)}</span>`;
}

function renderChip(value) {
  return `<span class="chip">${escapeHtml(value)}</span>`;
}

function renderNotFound(container, message) {
  container.className = "profile-state";
  container.innerHTML = `
    <p class="eyebrow">Vendor profile</p>
    <h2>Profile unavailable</h2>
    <p style="margin-top: 12px;">${escapeHtml(message)}</p>
  `;
}

function vendorSlug(vendor) {
  const base = vendor.vendor_name || vendor.website || "vendor";
  return normalizeValue(base)
    .replace(/^https?:\/\//, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function formatCategory(value) {
  const labels = {
    cs_core: "CS Core",
    cs_adjacent: "CS Adjacent",
    other: "Other",
  };
  return labels[value] || formatText(value);
}

function formatList(values) {
  return Array.isArray(values) && values.length ? values.join(", ") : "Not captured";
}

function formatBoolean(value) {
  if (value === true) {
    return "Yes";
  }
  if (value === false) {
    return "No";
  }
  return "Not captured";
}

function formatText(value) {
  const text = String(value || "").trim();
  return text || "Not captured";
}

function stripProtocol(value) {
  return String(value || "").replace(/^https?:\/\//, "").replace(/\/$/, "");
}

function normalizeValue(value) {
  return String(value || "").trim().toLowerCase();
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
