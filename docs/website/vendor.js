const DATASET_URL = "../../outputs/directory_dataset.json";

document.addEventListener("DOMContentLoaded", () => {
  loadVendorProfile();
});

async function loadVendorProfile() {
  const container = document.getElementById("vendor-profile");
  const vendorKey = new URLSearchParams(window.location.search).get("vendor") || "";

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
    const vendor = vendors.find((item) => vendorSlug(item) === vendorKey);
    if (!vendor) {
      renderNotFound(container, "Vendor not found in the current directory dataset.");
      return;
    }
    renderVendor(container, vendor);
  } catch (error) {
    renderNotFound(container, "Directory dataset could not be loaded.");
  }
}

function renderVendor(container, vendor) {
  const mission = vendor.mission || "Mission not captured.";
  const usp = vendor.usp || "USP not captured.";
  const website = vendor.website || "";
  const vendorName = vendor.vendor_name || "this vendor";
  const category = vendor.directory_category || "Customer Success tooling";
  const stageSummary = formatList(vendor.lifecycle_stages) || "multiple lifecycle stages";

  container.innerHTML = `
    <header class="profile-header">
      <p class="eyebrow">Vendor profile</p>
      <h1>${escapeHtml(vendorName)}</h1>
      <p class="hero-subheadline">${escapeHtml(mission)}</p>
      <p class="profile-meta">${escapeHtml(category)} · fit ${escapeHtml(vendor.directory_fit || "not scored")}</p>
      <div class="hero-actions">
        <a class="button button-primary" href="${escapeAttribute(website)}" target="_blank" rel="noreferrer">Visit website</a>
        <a class="button button-secondary" href="./landing.html#directory">Back to directory</a>
      </div>
    </header>
    <div class="profile-panels">
      <section class="profile-panel">
        <div class="profile-grid">
          ${renderField("USP", usp)}
          ${renderField("Lifecycle stages", formatList(vendor.lifecycle_stages))}
          ${renderField("ICP", formatList(vendor.icp))}
          ${renderField("Use cases", formatList(vendor.use_cases))}
          ${renderField("Pricing", formatList(vendor.pricing))}
          ${renderField("Founded", vendor.founded || "Not captured")}
          ${renderField("Free trial", formatBoolean(vendor.free_trial))}
          ${renderField("SOC2", formatBoolean(vendor.soc2))}
          ${renderField("Case studies", formatList(vendor.case_studies))}
          ${renderField("Customers", formatList(vendor.customers))}
          ${renderField("Value statements", formatList(vendor.value_statements))}
          ${renderField("Confidence", vendor.confidence || "Not scored")}
        </div>
      </section>
      <aside class="profile-sidebar">
        <div class="profile-cta-card">
          <p class="panel-label">Convert research into action</p>
          <h3>Need a shortlist around ${escapeHtml(vendorName)}?</h3>
          <p class="profile-state">
            Use the SuccessByCS market map and shortlist brief flow to save context from this
            ${escapeHtml(category)} profile and move the evaluation forward.
          </p>
          <div class="profile-cta-points">
            <span>${escapeHtml(stageSummary)}</span>
            <span>${escapeHtml(category)}</span>
            <span>Vendor-specific research context</span>
          </div>
          <div class="cta-actions">
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
        </div>
        <p class="evidence-heading">Evidence URLs</p>
        ${renderEvidenceList(vendor.evidence_urls)}
      </aside>
    </div>
  `;
}

function renderField(label, value) {
  return `
    <dl class="profile-list">
      <div>
        <dt>${escapeHtml(label)}</dt>
        <dd>${escapeHtml(value || "Not captured")}</dd>
      </div>
    </dl>
  `;
}

function renderEvidenceList(urls) {
  if (!Array.isArray(urls) || !urls.length) {
    return '<p class="profile-state">No evidence URLs captured.</p>';
  }
  const items = urls
    .map((url) => `<li><a href="${escapeAttribute(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a></li>`)
    .join("");
  return `<ul class="evidence-list">${items}</ul>`;
}

function renderNotFound(container, message) {
  container.innerHTML = `
    <div class="empty-state">
      <p class="eyebrow">Vendor profile</p>
      <h1>Profile unavailable</h1>
      <p class="profile-state">${escapeHtml(message)}</p>
    </div>
  `;
}

function vendorSlug(vendor) {
  const base = vendor.vendor_name || vendor.website || "vendor";
  return base.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function formatList(values) {
  return Array.isArray(values) && values.length ? values.join(", ") : "";
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
