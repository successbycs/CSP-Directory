# Tools

This directory defines repo-owned tools that agents and controller workflows may use during autonomous development.

Rules:

- `tools/` is the registry and specification layer for project tools.
- Agents may use only tools declared in `tools/tool_registry.json` and exposed by the controller for the current milestone and role.
- Tool specs define allowed operations, role access, write permissions, and approval requirements.
- Direct repo-owned access is preferred.
- SQL and schema files outside `tools/` remain the source of truth for database structure.
- Do not store real credentials in `tools/`, tool specs, example configs, or helper scripts.
- Tool access must reference environment variables or other untracked local operator configuration for secrets.
- Example tool configuration should use placeholders only.

Current tools:

- `agent_cli` in `tools/agent_cli/`
- `supabase` in `tools/supabase/`
- `external_enrichment` in `tools/external_enrichment/`
- `n8n` in `tools/n8n/`
