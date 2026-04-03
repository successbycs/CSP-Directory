const DATASET_URL = "./data/directory_dataset.json";
const BOOK_TIME_URL = "https://meetings-ap1.hubspot.com/christopher-sparshott";

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
          ${renderChip(`Confidence: ${confidence}`)}
          ${renderChip(founded === "Not captured" ? "Founded not captured" : `Founded ${founded}`)}
          ${vendor.free_trial === true
            ? `<a href="#operational-signals" class="chip chip-link">Free trial ↓</a>`
            : renderChip("No free-trial signal")}
          ${renderChip(vendor.soc2 === true ? "SOC 2 signal" : "No SOC 2 signal")}
          ${vendor.g2_rating ? `<a href="${escapeAttribute(vendor.g2_url || 'https://g2.com')}" target="_blank" rel="noreferrer" class="chip chip-link">G2 ${vendor.g2_rating}★ (${vendor.g2_review_count} reviews) ↗</a>` : ""}
        </div>
        <div class="hero-actions">
          ${website ? `<a class="button button-primary" href="${escapeAttribute(website)}" target="_blank" rel="noreferrer">Visit website</a>` : ""}
          <a class="button button-secondary" href="./browse.html">Back to browse</a>
          <button class="button button-secondary" type="button" onclick="openFeedbackModal(${JSON.stringify(escapeHtml(vendorName))})">Suggest an edit</button>
        </div>
      </div>
      <aside class="hero-side">
        <section class="hero-card">
          <p class="eyebrow">Snapshot</p>
          <h3>${escapeHtml(websiteLabel)}</h3>
          <p>
            ${stageCount} lifecycle stage${stageCount === 1 ? "" : "s"},
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
            <a
              class="button button-primary"
              href="${escapeAttribute(BOOK_TIME_URL)}"
              target="_blank"
              rel="noreferrer"
            >
              Connect with Chris @ SuccessByCS
            </a>
          </div>
          <div style="display:flex;gap:16px;margin-top:14px;flex-wrap:wrap;">
            <a href="https://www.linkedin.com/in/chrissparshott/" target="_blank" rel="noreferrer"
               style="display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--text-muted);text-decoration:none;">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="#0a66c2"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
              LinkedIn
            </a>
            <a href="https://successbycs.com" target="_blank" rel="noreferrer"
               style="display:inline-flex;align-items:center;gap:7px;padding:5px 12px 5px 6px;background:#0d1a12;border-radius:20px;text-decoration:none;font-size:13px;font-weight:600;color:#fff;line-height:1;">
              <span style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;background:#22c55e;border-radius:50%;flex-shrink:0;">
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <rect x="2" y="2.5" width="2.2" height="5" rx="0.8" fill="#fff"/>
                  <rect x="5.8" y="2.5" width="2.2" height="5" rx="0.8" fill="#fff"/>
                </svg>
              </span>
              SuccessByCS
            </a>
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
        ${renderAiSummarySection(vendor.ai_summary)}
        <section class="section-card">
          <div>
            <p class="eyebrow">Buyer fit</p>
            <h2>Who this looks relevant for</h2>
          </div>
          <div class="detail-grid">
            ${renderDetailItem("Ideal customer profile", formatList(vendor.icp))}
            ${renderUseCaseLinks("Use cases", vendor.use_cases, vendor.use_case_details, vendor.website)}
            ${renderDetailItem("Lifecycle stages", formatList(vendor.lifecycle_stages))}
            ${renderPricingItem("Pricing", vendor.pricing)}
          </div>
        </section>

        ${renderStorySection("Case-study details", vendor.case_study_details, formatCaseStudy)}
        ${renderStorySection("Use-case detail objects", vendor.use_case_details, formatUseCaseDetail)}
        ${renderSimpleListSection("Value statements", vendor.value_statements)}
        ${renderBlogPostsSection(vendor.blog_posts)}
      </div>

      <aside class="content-side">
        <section class="section-card" id="operational-signals">
          <div>
            <p class="eyebrow">Operational signals</p>
            <h2>What we have on record</h2>
          </div>
          <div class="detail-grid">
            ${renderDetailItem("Website", websiteLabel)}
            ${renderDetailItem("Founded", founded)}
            ${renderDetailItem("Free trial", formatBoolean(vendor.free_trial))}
            ${renderDetailItem("SOC 2", formatBoolean(vendor.soc2))}
            ${vendor.g2_rating ? renderG2Item(vendor) : ""}
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

    <section class="section-card" style="margin-top:20px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;">
      <div>
        <p class="eyebrow">Improve this profile</p>
        <p style="font-size:14px;color:var(--text-mid);margin-top:4px;">Spotted something wrong or missing? Let us know — we review every submission.</p>
      </div>
      <button class="button button-secondary" type="button" onclick="openFeedbackModal(${JSON.stringify(escapeHtml(vendorName))})">Suggest an edit</button>
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

function renderUseCaseLinks(label, useCases, useCaseDetails, vendorWebsite) {
  if (!Array.isArray(useCases) || !useCases.length) {
    return renderDetailItem(label, null);
  }
  // Build a lookup from label (lowercased) → specific url from use_case_details
  const detailMap = {};
  if (Array.isArray(useCaseDetails)) {
    useCaseDetails.forEach(d => {
      const key = String(d.label || d.title || "").trim().toLowerCase();
      if (key && d.url) detailMap[key] = d.url;
    });
  }
  const links = useCases.map(u => {
    const detailUrl = detailMap[u.trim().toLowerCase()];
    const href = detailUrl || vendorWebsite || null;
    if (href) {
      return `<a href="${escapeAttribute(href)}" target="_blank" rel="noreferrer" class="use-case-link" title="See ${escapeHtml(u)} on vendor site">${escapeHtml(u)} ↗</a>`;
    }
    return `<span class="use-case-link">${escapeHtml(u)}</span>`;
  }).join('');
  return `
    <dl class="detail-item">
      <dt>${escapeHtml(label)}</dt>
      <dd class="use-case-links">${links}</dd>
    </dl>
  `;
}

const PRICING_LABELS = {
  '$':            'Price publicly listed on website',
  'per month':    'Monthly billing available',
  'per year':     'Annual billing available',
  'per seat':     'Per-seat pricing',
  'per user':     'Per-user pricing',
  'contact sales':'Custom pricing — contact sales',
};

function formatPricingHuman(pricingArray) {
  if (!Array.isArray(pricingArray) || !pricingArray.length) return 'Not captured';
  const lines = pricingArray.map(token => PRICING_LABELS[token.trim().toLowerCase()] || token);
  return lines.join(' · ');
}

function renderPricingItem(label, pricingArray) {
  const text = formatPricingHuman(pricingArray);
  return `
    <dl class="detail-item">
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(text)}</dd>
    </dl>
  `;
}

function renderBlogPostsSection(posts) {
  if (!Array.isArray(posts) || !posts.length) return "";
  const items = posts.slice(0, 6).map(p => {
    const url = escapeAttribute(p.source_url || "");
    const title = escapeHtml(p.title || "");
    const summary = escapeHtml((p.summary || "").slice(0, 160));
    return `
      <li style="padding:10px 0;border-bottom:1px solid var(--border);">
        <a href="${url}" target="_blank" rel="noreferrer"
           style="font-weight:600;color:var(--text-primary);text-decoration:none;font-size:14px;">${title} ↗</a>
        ${summary ? `<p style="margin:4px 0 0;font-size:13px;color:var(--text-muted);">${summary}</p>` : ""}
      </li>`;
  }).join("");
  return `
    <section class="section-card">
      <div>
        <p class="eyebrow">Content &amp; resources</p>
        <h2>From their blog</h2>
      </div>
      <ul class="list" style="list-style:none;padding:0;margin:0;">${items}</ul>
    </section>`;
}

function renderAiSummarySection(summary) {
  if (!summary || !summary.trim()) return "";
  const paragraphs = summary.trim().split(/\n+/).filter(Boolean)
    .map(p => `<p style="margin:0 0 14px 0;line-height:1.7;color:var(--text-body);">${escapeHtml(p)}</p>`)
    .join("");
  return `
    <section class="section-card">
      <div>
        <p class="eyebrow">AI overview</p>
        <h2>About this vendor</h2>
      </div>
      <div style="margin-top:12px;">${paragraphs}</div>
    </section>`;
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

function renderG2Item(vendor) {
  const stars = "★".repeat(Math.round(vendor.g2_rating)) + "☆".repeat(5 - Math.round(vendor.g2_rating));
  const cats = Array.isArray(vendor.g2_categories) && vendor.g2_categories.length
    ? vendor.g2_categories.join(", ")
    : "";
  const href = escapeAttribute(vendor.g2_url || "https://g2.com");
  return `
    <dl class="detail-item" style="grid-column: 1 / -1;">
      <dt>G2 Rating</dt>
      <dd>
        <a href="${href}" target="_blank" rel="noreferrer" style="color:var(--green-700);font-weight:700;text-decoration:none;">
          ${escapeHtml(String(vendor.g2_rating))} ${escapeHtml(stars)} &nbsp;·&nbsp; ${escapeHtml(String(vendor.g2_review_count))} reviews ↗
        </a>
        ${cats ? `<div style="margin-top:6px;font-size:12px;color:var(--text-muted)">${escapeHtml(cats)}</div>` : ""}
      </dd>
    </dl>
  `;
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

// ── Vendor feedback modal ─────────────────────────────────────────────────────

const FEEDBACK_WEBHOOK_URL = "https://successbycs.app.n8n.cloud/webhook/csp-vendor-feedback";

function openFeedbackModal(vendorName) {
  document.getElementById("feedback-vendor").value = vendorName;
  document.getElementById("feedback-type").value = "data_correction";
  document.getElementById("feedback-message").value = "";
  document.getElementById("feedback-email").value = "";
  const status = document.getElementById("feedback-status");
  status.className = "feedback-status";
  status.textContent = "";
  document.getElementById("feedback-submit").disabled = false;
  document.getElementById("feedback-overlay").classList.add("open");
  document.getElementById("feedback-message").focus();
}

function closeFeedbackModal() {
  document.getElementById("feedback-overlay").classList.remove("open");
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("feedback-cancel").addEventListener("click", closeFeedbackModal);
  document.getElementById("feedback-overlay").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeFeedbackModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeFeedbackModal();
  });
  document.getElementById("feedback-submit").addEventListener("click", submitFeedback);
});

async function submitFeedback() {
  const vendor = document.getElementById("feedback-vendor").value.trim();
  const type = document.getElementById("feedback-type").value;
  const message = document.getElementById("feedback-message").value.trim();
  const email = document.getElementById("feedback-email").value.trim();
  const status = document.getElementById("feedback-status");
  const btn = document.getElementById("feedback-submit");

  if (!message) {
    status.className = "feedback-status error";
    status.textContent = "Please describe your feedback before submitting.";
    return;
  }

  btn.disabled = true;
  status.className = "feedback-status";
  status.textContent = "";

  try {
    const resp = await fetch(FEEDBACK_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        vendor_name: vendor,
        feedback_type: type,
        message,
        submitter_email: email || null,
        source_url: window.location.href,
      }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    status.className = "feedback-status success";
    status.textContent = "Thanks — your feedback has been received and we'll review it shortly.";
    document.getElementById("feedback-message").value = "";
    document.getElementById("feedback-email").value = "";
  } catch (err) {
    status.className = "feedback-status error";
    status.textContent = "Something went wrong. Please try again or email chris@successbycs.com.";
    btn.disabled = false;
  }
}
