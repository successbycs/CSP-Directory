# Lead Capture — User Guide & Architecture

**Status:** Live at vendors.successbycs.com
**Last updated:** 2026-03-26

---

## How to use it (operator instructions)

### Viewing leads

1. Start the admin panel on your laptop: `python3 -m services.admin.admin_api`
2. Open `http://127.0.0.1:8787`
3. Go to the **Lead capture** section
4. Every form submission appears here with name, email, company, intent, and full attribution context

### What the visitor sees

When any CTA button is clicked on the live site, a modal opens with:
- **Name** — free text
- **Work email** — required, validated
- **Company** — free text
- **What do you want?** — dropdown: The market map / A shortlist brief / An advisory intro
- **Notes** — optional, what are they evaluating right now?

Visitor submits → row lands in Supabase → visible immediately in `/admin/leads`.

### Updating live vendor data

1. Run the enrichment pipeline on your laptop
2. Open the admin panel → **Enriched vendors** section → click **Publish**
3. This writes the updated dataset to `docs/website/data/directory_dataset.json`
4. `git add docs/website/data/directory_dataset.json && git push`
5. Vercel auto-deploys within ~30 seconds — vendors.successbycs.com is updated

### Following up on a lead

In the admin panel leads table, use the follow-up status dropdown to mark leads as:
`new` → `in_progress` → `contacted` → `qualified` → `closed`

High-priority leads (shortlist / advisory intent) are automatically flagged with `follow_up_priority: high`.

---

## What it does (technical)

---

## The flow end-to-end

```
Visitor clicks a CTA button (e.g. "Get the 2026 market map")
  ↓
lead-magnet.js opens a modal form
  Fields: name, work email, company, intent (dropdown)
  Hidden: CTA context, vendor context, UTM params, entry page
  ↓
Visitor submits form → lead-magnet.js POSTs JSON to /api/lead-capture
  ↓
Vercel routes the request to api/lead-capture.py (serverless function)
  ↓
Function validates payload (name, email, company, intent all required)
  ↓
Function derives:
  - intent_category: "service" (shortlist/advisory/audit) or "content" (market-map)
  - follow_up_priority: "high" for service, "normal" for content
  - recommended_handoff_channel: "calendar_or_email" or "email_nurture"
  ↓
Function writes row to Supabase table: lead_captures
  ↓
Browser receives {ok: true} → modal shows success message
  ↓
Lead visible in admin panel → /admin/leads
```

---

## What is a serverless function?

A serverless function is a single file of code that runs on-demand in the cloud — no server to manage, no always-on process. Vercel hosts `api/lead-capture.py` and runs it only when a request arrives. You pay per invocation (essentially free at this volume). It starts in milliseconds and stops when the request is done.

The alternative would be a running server (like the Python admin API on Docker). For the lead capture use case, serverless is better because:
- It runs 24/7 without needing your laptop on
- No infrastructure to maintain
- Scales automatically if traffic spikes
- Free on Vercel's hobby/pro tier at this volume

---

## What gets stored per lead

| Field | Source | Example |
|---|---|---|
| `lead_name` | Form input | "Chris Sparshott" |
| `lead_email` | Form input | "chris@successbycs.com" |
| `company_name` | Form input | "SuccessByCS" |
| `lead_intent` | Form dropdown | "shortlist" |
| `intent_category` | Derived | "service" |
| `follow_up_priority` | Derived | "high" |
| `cta_surface` | Button attribute | "hero", "directory-banner", "footer-cta" |
| `cta_label` | Button attribute | "Get the 2026 market map" |
| `vendor_name` | Vendor page context | "Gainsight" (if from a vendor page) |
| `utm_source` | URL param | "linkedin" |
| `recommended_next_step` | Derived | "Offer a consultation..." |
| `follow_up_status` | Default | "new" |
| `follow_up_owner` | Default | "fractional-head-of-cs" |

---

## The CTA surfaces

The landing page has buttons in four places, each tagged with context so you know where the lead came from:

| Surface | Buttons | Intent options triggered |
|---|---|---|
| `hero` | "Get the 2026 market map" | market-map |
| `lead-magnet` section | "Unlock the market map", "Get the shortlist brief" | market-map, shortlist |
| `directory-banner` | "Request shortlist brief", "Talk to SuccessByCS" | shortlist, advisory |
| `footer-cta` | "Get the market map", "Request advisory intro" | market-map, advisory |

---

## Infrastructure

| Component | Where it runs | Purpose |
|---|---|---|
| `api/lead-capture.py` | Vercel serverless | Accepts POST, validates, writes to Supabase |
| `lead-magnet.js` | Browser (static JS) | Modal UI, form submit, success/error state |
| `lead_captures` table | Supabase | Persistent storage |
| Admin panel `/admin/leads` | Docker (local) | Review and follow-up queue |

---

## Credentials required

Set as environment variables in the Vercel project settings (not in code):
- `SUPABASE_URL` — the Supabase project URL
- `SUPABASE_KEY` — the server-side key used by the Vercel function to write to `lead_captures`

---

## Updating live data

The vendor directory data (`directory_dataset.json`) is a static file committed to the repo. To update what visitors see:

1. Run the enrichment pipeline on the Docker laptop
2. Click **Publish** in the admin panel (POST /admin/publish)
   - This writes `outputs/directory_dataset.json` AND `docs/website/data/directory_dataset.json`
3. `git add docs/website/data/directory_dataset.json && git push`
4. Vercel auto-deploys within ~30 seconds
