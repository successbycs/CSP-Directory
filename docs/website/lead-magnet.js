const LEAD_MAGNET_CAPTURE_VERSION = "m24a.v1";
const LEAD_MAGNET_STORAGE_KEY = "successbycs_lead_magnet_intake";
const LEAD_CAPTURE_API_URL = "/api/lead-capture";
const LEAD_CAPTURE_API_REMOTE = "https://successbycs.app.n8n.cloud/webhook/csp-lead-capture-intake";
const LEAD_CAPTURE_API_FALLBACK_BASE = "http://127.0.0.1:8787";
const LEAD_CAPTURE_API_PATH = "/api/lead-capture";

document.addEventListener("DOMContentLoaded", () => {
  ensureLeadMagnetModal();
  document.addEventListener("click", handleLeadMagnetClick);
  document.addEventListener("submit", handleLeadMagnetSubmit);
  document.addEventListener("keydown", handleLeadMagnetEscape);
});

function ensureLeadMagnetModal() {
  if (document.getElementById("lead-magnet-modal")) {
    return;
  }

  document.body.insertAdjacentHTML(
    "beforeend",
    `
      <div class="lead-magnet-backdrop is-hidden" id="lead-magnet-modal" aria-hidden="true">
        <div class="lead-magnet-dialog" role="dialog" aria-modal="true" aria-labelledby="lead-magnet-title">
          <button class="lead-magnet-close" type="button" data-lead-magnet-close aria-label="Close lead capture">
            Close
          </button>
          <div class="lead-magnet-copy">
            <p class="eyebrow">Lead magnet flow</p>
            <h2 id="lead-magnet-title">Save this research and unlock the next layer</h2>
            <p class="lead-magnet-supporting-copy" id="lead-magnet-context-copy">
              Capture the directory context now and route the right follow-up motion behind it.
            </p>
            <div class="lead-magnet-context" id="lead-magnet-context"></div>
          </div>
          <form class="lead-magnet-form" id="lead-magnet-form">
            <input type="hidden" name="capture_version" value="${LEAD_MAGNET_CAPTURE_VERSION}">
            <input type="hidden" name="entry_page" value="">
            <input type="hidden" name="entry_url" value="">
            <input type="hidden" name="cta_surface" value="">
            <input type="hidden" name="cta_variant" value="">
            <input type="hidden" name="cta_label" value="">
            <input type="hidden" name="vendor_name" value="">
            <input type="hidden" name="vendor_website" value="">
            <input type="hidden" name="vendor_category" value="">
            <input type="hidden" name="utm_source" value="">
            <input type="hidden" name="utm_medium" value="">
            <input type="hidden" name="utm_campaign" value="">
            <input type="hidden" name="utm_term" value="">
            <input type="hidden" name="utm_content" value="">
            <label class="control-group">
              <span>Name</span>
              <input name="name" type="text" placeholder="Your name" required>
            </label>
            <label class="control-group">
              <span>Work email</span>
              <input name="email" type="email" placeholder="you@company.com" required>
            </label>
            <label class="control-group">
              <span>Company</span>
              <input name="company" type="text" placeholder="Company name" required>
            </label>
            <label class="control-group">
              <span>What do you want?</span>
              <select name="intent" required>
                <option value="market-map">The market map</option>
                <option value="shortlist">A shortlist brief</option>
                <option value="advisory">An advisory intro</option>
              </select>
            </label>
            <label class="control-group">
              <span>Notes</span>
              <textarea name="notes" rows="4" placeholder="What are you evaluating right now?"></textarea>
            </label>
            <p class="lead-magnet-footnote" id="lead-magnet-form-note">
              The capture includes CTA context, vendor context, referrer, and available UTM attribution.
            </p>
            <div class="cta-actions">
              <button class="button button-primary" type="submit">Save research context</button>
              <button class="button button-secondary" type="button" data-lead-magnet-close>Cancel</button>
            </div>
          </form>
          <div class="lead-magnet-success is-hidden" id="lead-magnet-success">
            <p class="panel-label">Context saved</p>
            <h3>Lead capture is active</h3>
            <p class="lead-magnet-supporting-copy" id="lead-magnet-success-copy"></p>
            <div class="cta-actions">
              <button class="button button-primary" type="button" data-lead-magnet-close>Return to the directory</button>
            </div>
          </div>
        </div>
      </div>
    `,
  );
}

function handleLeadMagnetClick(event) {
  const trigger = event.target.closest("[data-lead-magnet-trigger]");
  if (trigger) {
    event.preventDefault();
    openLeadMagnet(trigger);
    return;
  }

  if (event.target.closest("[data-lead-magnet-close]")) {
    closeLeadMagnet("dismissed");
    return;
  }

  const backdrop = event.target.closest(".lead-magnet-backdrop");
  if (backdrop && event.target === backdrop) {
    closeLeadMagnet("backdrop");
  }
}

async function handleLeadMagnetSubmit(event) {
  const form = event.target.closest("#lead-magnet-form");
  if (!form) {
    return;
  }

  event.preventDefault();
  const formData = new FormData(form);
  const email = String(formData.get("email") || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    document.getElementById("lead-magnet-form-note").textContent = "Enter a valid work email to save the research context.";
    return;
  }

  const submitButton = form.querySelector("button[type='submit']");
  if (submitButton) {
    submitButton.disabled = true;
  }

  const payload = {
    capture_version: String(formData.get("capture_version") || LEAD_MAGNET_CAPTURE_VERSION),
    entry_page: String(formData.get("entry_page") || ""),
    entry_url: String(formData.get("entry_url") || ""),
    cta_surface: String(formData.get("cta_surface") || ""),
    cta_variant: String(formData.get("cta_variant") || ""),
    cta_label: String(formData.get("cta_label") || ""),
    vendor_name: String(formData.get("vendor_name") || ""),
    vendor_website: String(formData.get("vendor_website") || ""),
    vendor_category: String(formData.get("vendor_category") || ""),
    utm_source: String(formData.get("utm_source") || ""),
    utm_medium: String(formData.get("utm_medium") || ""),
    utm_campaign: String(formData.get("utm_campaign") || ""),
    utm_term: String(formData.get("utm_term") || ""),
    utm_content: String(formData.get("utm_content") || ""),
    name: String(formData.get("name") || "").trim(),
    email,
    company: String(formData.get("company") || "").trim(),
    intent: String(formData.get("intent") || "").trim(),
    notes: String(formData.get("notes") || "").trim(),
    referrer: document.referrer || "",
    captured_at: new Date().toISOString(),
  };

  try {
    const submission = await persistLeadMagnetPayload(payload);
    trackLeadMagnetEvent("lead_magnet_submit", {
      ...payload,
      storage_mode: submission.storageMode,
      follow_up_status: submission.lead.follow_up_status || "new",
    });

    document.getElementById("lead-magnet-form").classList.add("is-hidden");
    document.getElementById("lead-magnet-success").classList.remove("is-hidden");
    document.getElementById("lead-magnet-success-copy").textContent = buildSuccessMessage(payload, submission);
  } catch (error) {
    document.getElementById("lead-magnet-form-note").textContent = `Lead capture failed: ${error.message}`;
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
    }
  }
}

function handleLeadMagnetEscape(event) {
  if (event.key === "Escape") {
    closeLeadMagnet("escape");
  }
}

function openLeadMagnet(trigger) {
  const backdrop = document.getElementById("lead-magnet-modal");
  const form = document.getElementById("lead-magnet-form");
  const successPanel = document.getElementById("lead-magnet-success");
  const context = buildLeadMagnetContext(trigger);

  form.reset();
  successPanel.classList.add("is-hidden");
  form.classList.remove("is-hidden");
  form.elements.capture_version.value = LEAD_MAGNET_CAPTURE_VERSION;
  form.elements.entry_page.value = context.entry_page;
  form.elements.entry_url.value = context.entry_url;
  form.elements.cta_surface.value = context.cta_surface;
  form.elements.cta_variant.value = context.cta_variant;
  form.elements.cta_label.value = context.cta_label;
  form.elements.vendor_name.value = context.vendor_name;
  form.elements.vendor_website.value = context.vendor_website;
  form.elements.vendor_category.value = context.vendor_category;
  form.elements.utm_source.value = context.utm_source;
  form.elements.utm_medium.value = context.utm_medium;
  form.elements.utm_campaign.value = context.utm_campaign;
  form.elements.utm_term.value = context.utm_term;
  form.elements.utm_content.value = context.utm_content;
  form.elements.intent.value = context.intent;
  document.getElementById("lead-magnet-context-copy").textContent =
    context.vendor_name
      ? `Capture interest from ${context.vendor_name} and attach the vendor context to the follow-up queue.`
      : "Capture directory-level interest and route the right follow-up motion from the CTA source.";
  document.getElementById("lead-magnet-context").innerHTML = renderLeadMagnetContext(context);
  document.getElementById("lead-magnet-form-note").textContent =
    "The capture includes CTA context, vendor context, referrer, and available UTM attribution.";
  backdrop.classList.remove("is-hidden");
  backdrop.setAttribute("aria-hidden", "false");
  trackLeadMagnetEvent("lead_magnet_open", context);
  form.elements.name.focus();
}

function closeLeadMagnet(reason) {
  const backdrop = document.getElementById("lead-magnet-modal");
  if (!backdrop || backdrop.classList.contains("is-hidden")) {
    return;
  }
  backdrop.classList.add("is-hidden");
  backdrop.setAttribute("aria-hidden", "true");
  trackLeadMagnetEvent("lead_magnet_close", { reason });
}

function buildLeadMagnetContext(trigger) {
  const currentUrl = new URL(window.location.href);
  return {
    entry_page: window.location.pathname.split("/").pop() || "landing.html",
    entry_url: currentUrl.toString(),
    cta_surface: trigger.dataset.ctaSurface || "",
    cta_variant: trigger.dataset.ctaVariant || "",
    cta_label: trigger.dataset.ctaLabel || trigger.textContent.trim(),
    vendor_name: trigger.dataset.vendorName || "",
    vendor_website: trigger.dataset.vendorWebsite || "",
    vendor_category: trigger.dataset.vendorCategory || "",
    intent: trigger.dataset.ctaIntent || "market-map",
    utm_source: currentUrl.searchParams.get("utm_source") || "",
    utm_medium: currentUrl.searchParams.get("utm_medium") || "",
    utm_campaign: currentUrl.searchParams.get("utm_campaign") || "",
    utm_term: currentUrl.searchParams.get("utm_term") || "",
    utm_content: currentUrl.searchParams.get("utm_content") || "",
  };
}

function renderLeadMagnetContext(context) {
  const items = [
    context.entry_page ? `Entry page: ${escapeHtml(context.entry_page)}` : "",
    context.cta_surface ? `CTA surface: ${escapeHtml(context.cta_surface)}` : "",
    context.cta_variant ? `Variant: ${escapeHtml(context.cta_variant)}` : "",
    context.vendor_name ? `Vendor: ${escapeHtml(context.vendor_name)}` : "",
    context.vendor_category ? `Vendor category: ${escapeHtml(context.vendor_category)}` : "",
    context.utm_source ? `UTM source: ${escapeHtml(context.utm_source)}` : "",
    context.utm_campaign ? `UTM campaign: ${escapeHtml(context.utm_campaign)}` : "",
  ].filter(Boolean);

  return items.map((item) => `<span>${item}</span>`).join("");
}

async function persistLeadMagnetPayload(payload) {
  const endpoints = collectLeadCaptureEndpoints();
  let lastError = null;

  for (const endpoint of endpoints) {
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || result.ok === false) {
        throw new Error(result.error || `Request failed: ${response.status}`);
      }
      return {
        storageMode: "remote",
        lead: result.lead || payload,
      };
    } catch (error) {
      lastError = error;
    }
  }

  const storedEntries = readLeadMagnetEntries();
  storedEntries.push({...payload, storage_mode: "local_fallback"});
  window.localStorage.setItem(LEAD_MAGNET_STORAGE_KEY, JSON.stringify(storedEntries));
  return {
    storageMode: "local_fallback",
    lead: payload,
    error: lastError,
  };
}

function collectLeadCaptureEndpoints() {
  const endpoints = new Set([LEAD_CAPTURE_API_URL]);
  endpoints.add(LEAD_CAPTURE_API_REMOTE);
  endpoints.add(`${LEAD_CAPTURE_API_FALLBACK_BASE}${LEAD_CAPTURE_API_PATH}`);
  return Array.from(endpoints);
}

function buildSuccessMessage(payload, submission) {
  if (submission.storageMode === "local_fallback") {
    return `Saved ${payload.intent} intent locally with its attribution context because no lead-capture endpoint was reachable.`;
  }
  const followUpStatus = submission.lead.follow_up_status || "new";
  const nextStep = submission.lead.recommended_next_step || "Follow-up has been queued.";
  return `Saved ${payload.intent} intent from ${payload.entry_page || "the directory"} with CTA surface ${payload.cta_surface || "unknown"}. Status: ${followUpStatus}. ${nextStep}`;
}

function trackLeadMagnetEvent(eventName, payload) {
  const eventPayload = {
    event: eventName,
    capture_version: LEAD_MAGNET_CAPTURE_VERSION,
    ...payload,
  };
  window.successByCSLeadMagnetEvents = window.successByCSLeadMagnetEvents || [];
  window.successByCSLeadMagnetEvents.push(eventPayload);
  window.dataLayer = window.dataLayer || [];
  window.dataLayer.push(eventPayload);
  document.dispatchEvent(new CustomEvent("successbycs:lead-magnet", { detail: eventPayload }));
}

function readLeadMagnetEntries() {
  try {
    const rawValue = window.localStorage.getItem(LEAD_MAGNET_STORAGE_KEY);
    const parsedValue = rawValue ? JSON.parse(rawValue) : [];
    return Array.isArray(parsedValue) ? parsedValue : [];
  } catch (error) {
    return [];
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
