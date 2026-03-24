const DATASET_URL = "../../outputs/directory_dataset.json";
const STAGE_ORDER = ["Sign", "Onboard", "Activate", "Adopt", "Support", "Expand", "Renew", "Advocate"];

const state = {
  dataset: [],
  filtered: [],
};

document.addEventListener("DOMContentLoaded", () => {
  loadDirectoryDataset();
  document.getElementById("search-input")?.addEventListener("input", applyFilters);
  document.getElementById("stage-filter")?.addEventListener("change", applyFilters);
  document.getElementById("category-filter")?.addEventListener("change", applyFilters);
  document.getElementById("free-trial-filter")?.addEventListener("change", applyFilters);
  document.getElementById("soc2-filter")?.addEventListener("change", applyFilters);
  document.getElementById("clear-filters")?.addEventListener("click", clearFilters);
});

async function loadDirectoryDataset() {
  const statusElement = document.getElementById("directory-status");
  try {
    const response = await fetch(DATASET_URL);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const dataset = await response.json();
    state.dataset = Array.isArray(dataset) ? dataset : [];
    populateFilterOptions(state.dataset);
    applyFilters();
  } catch (error) {
    renderEmptyState("Directory dataset not found yet. Run the export step, then reload this page.");
    if (statusElement) {
      statusElement.textContent = "Unable to load outputs/directory_dataset.json";
    }
  }
}

function populateFilterOptions(dataset) {
  const stageFilter = document.getElementById("stage-filter");
  const categoryFilter = document.getElementById("category-filter");
  if (!stageFilter || !categoryFilter) {
    return;
  }

  const stages = new Set();
  const categories = new Set();
  dataset.forEach((vendor) => {
    (vendor.lifecycle_stages || []).forEach((stage) => stages.add(stage));
    if (vendor.directory_category) {
      categories.add(vendor.directory_category);
    }
  });

  STAGE_ORDER.filter((stage) => stages.has(stage)).forEach((stage) => {
    stageFilter.appendChild(new Option(stage, stage));
  });
  Array.from(categories).sort().forEach((category) => {
    categoryFilter.appendChild(new Option(category, category));
  });
}

function applyFilters() {
  const searchValue = document.getElementById("search-input")?.value.trim().toLowerCase() || "";
  const stageValue = document.getElementById("stage-filter")?.value || "";
  const categoryValue = document.getElementById("category-filter")?.value || "";
  const freeTrialOnly = Boolean(document.getElementById("free-trial-filter")?.checked);
  const soc2Only = Boolean(document.getElementById("soc2-filter")?.checked);

  state.filtered = state.dataset.filter((vendor) => {
    const matchesSearch = !searchValue || (vendor.vendor_name || "").toLowerCase().includes(searchValue);
    const matchesStage = !stageValue || (vendor.lifecycle_stages || []).includes(stageValue);
    const matchesCategory = !categoryValue || vendor.directory_category === categoryValue;
    const matchesFreeTrial = !freeTrialOnly || vendor.free_trial === true;
    const matchesSoc2 = !soc2Only || vendor.soc2 === true;
    return matchesSearch && matchesStage && matchesCategory && matchesFreeTrial && matchesSoc2;
  });

  renderDirectory(state.filtered);
}

function clearFilters() {
  document.getElementById("search-input").value = "";
  document.getElementById("stage-filter").value = "";
  document.getElementById("category-filter").value = "";
  document.getElementById("free-trial-filter").checked = false;
  document.getElementById("soc2-filter").checked = false;
  applyFilters();
}

function renderDirectory(vendors) {
  const resultsElement = document.getElementById("vendor-results");
  const statusElement = document.getElementById("directory-status");
  if (!resultsElement || !statusElement) {
    return;
  }

  resultsElement.innerHTML = "";
  statusElement.textContent = `${vendors.length} vendor${vendors.length === 1 ? "" : "s"} shown`;

  if (!vendors.length) {
    renderEmptyState("No vendors match the current filters.");
    return;
  }

  vendors.forEach((vendor) => {
    const article = document.createElement("article");
    article.className = "vendor-card";

    const link = document.createElement("a");
    link.className = "vendor-card-link";
    link.href = `./vendor.html?vendor=${encodeURIComponent(vendorSlug(vendor))}`;

    const stageMarkup = (vendor.lifecycle_stages || []).map((stage) => `<span>${escapeHtml(stage)}</span>`).join("");
    const pricing = formatList(vendor.pricing) || "Pricing not captured";
    const summary = vendor.mission || vendor.usp || "Profile summary not captured yet.";
    const category = vendor.directory_category || "uncategorized";

    link.innerHTML = `
      <div class="vendor-card-top">
        <div>
          <h3 class="vendor-name">${escapeHtml(vendor.vendor_name || "Unknown vendor")}</h3>
          <p class="vendor-domain">${escapeHtml(formatDomain(vendor.website || ""))}</p>
        </div>
        <span class="signal-pill signal-pill-neutral">${escapeHtml(category)}</span>
      </div>
      <div class="stage-list">${stageMarkup || "<span>Unmapped</span>"}</div>
      <p class="vendor-summary">${escapeHtml(summary)}</p>
      <dl class="vendor-facts">
        <div><dt>Pricing</dt><dd>${escapeHtml(pricing)}</dd></div>
        <div><dt>Fit</dt><dd>${escapeHtml(vendor.directory_fit || "not scored")}</dd></div>
      </dl>
    `;

    article.appendChild(link);
    resultsElement.appendChild(article);
  });
}

function renderEmptyState(message) {
  const resultsElement = document.getElementById("vendor-results");
  if (!resultsElement) {
    return;
  }
  resultsElement.innerHTML = `
    <article class="vendor-card vendor-card-empty">
      <p class="vendor-use-case">${escapeHtml(message)}</p>
    </article>
  `;
}

function vendorSlug(vendor) {
  const base = vendor.vendor_name || vendor.website || "vendor";
  return base.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function formatDomain(website) {
  return website.replace(/^https?:\/\//, "");
}

function formatList(values) {
  return Array.isArray(values) ? values.join(", ") : "";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
