# Lead Magnet Strategy

The CSP Directory is the primary lead magnet for SuccessByCS. It is not just a vendor list — it is a tool for CS leaders evaluating their tech stack, which is the exact buyer profile for fractional CS leadership engagements.

## Access Model

The directory lives at `vendors.successbycs.com`. Access is gated behind an email submission — the user enters their email and the directory unlocks immediately (no "check your email" friction).

## Email Flow

### On submit
- Unlock the directory instantly
- Send a welcome email with a link back to the directory and a one-liner on the 8-stage CS lifecycle framework

### Weekly (on pipeline run)
- "What's new in AI CS tools this week" digest
- Short and scannable — 3-5 new or updated vendors with their lifecycle stage classification
- Keeps subscribers returning and keeps SuccessByCS top of mind

### New vendor alert
- Triggered when a notable new vendor is added to the directory
- Not every vendor — only ones worth highlighting
- Positions the directory as a live, maintained resource

### Nurture path (weeks 2-3+)
- After 2-3 weeks of digest engagement, a soft CTA
- "Working through a CS tech stack review? That's exactly what I help with."
- Bridges the directory lead into a fractional CS conversation

## Open Decisions

- **Email service** — Resend, SendGrid, Mailchimp, or ConvertKit. Decision needed before build.
- **Subdomain hosting** — vendors.successbycs.com. Depends on where successbycs.com is hosted.
- **Segmentation** — longer term, segment digest by CS lifecycle stage interest based on which vendors the user browses.

## Navigation

Add the directory as a project link under the "Autonomous Agents" nav item on successbycs.com.

## Pre-requisites Before Build

The lead magnet is only worth building once the directory data is accurate and trustworthy.

**Known issue:** The pipeline is not reliably enriching vendor fields in Supabase. The enrichment layer needs to be diagnosed and fixed before the public-facing directory is viable.

The human review pass (M35) will identify the specific gaps. Fix milestones will be defined from that review before any lead capture work begins.

## Build Order

1. Fix enrichment and data quality issues (AF-driven fix milestones after M35 review)
2. Validate vendor data manually
3. Build lead capture gate on vendors.successbycs.com
4. Wire email service for welcome and weekly digest
5. Add directory to successbycs.com navigation
6. Launch and monitor
