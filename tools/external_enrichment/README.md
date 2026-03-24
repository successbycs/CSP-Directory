# External Enrichment Tool

This directory declares staged third-party enrichment connectors for the autonomous system.

Rules:

- `M30` is registry-only. Connectors may be declared, reviewed, and represented in vendor records, but they are not live execution backends yet.
- Every external enrichment record must preserve:
  - `provider`
  - `source_id`
  - `source_type`
  - `status`
  - `source_url`
  - `captured_at`
  - `freshness_days`
  - `fields`
  - `notes`
- Vendor records store external provenance in `cs_vendors.external_enrichment`.
- Review/export surfaces may summarize staged external signals, but those summaries must remain clearly attributable to their declared provider.
- Any future live connector must add an explicit execution backend, approval model, and role-access update before the controller can use it directly.

Files:

- `tool_spec.json`: role access and safety boundary for the tool
- `connector_registry.json`: deferred connectors and allowed field scope for staged rollout
