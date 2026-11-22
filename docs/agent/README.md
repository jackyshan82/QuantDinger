# Agent documentation (English)

This folder holds **agent-facing** material for coding assistants (Cursor, Claude Code, Codex, CLI bots, etc.).

| Document | Purpose |
|----------|---------|
| [MCP_SETUP.md](MCP_SETUP.md) | Wire Cursor / Claude Code / Codex / remote agents to a QuantDinger backend via the `quantdinger-mcp` MCP server (local stdio + remote HTTP) |
| [AGENT_QUICKSTART.md](AGENT_QUICKSTART.md) | Operator + integrator walkthrough: issue a token, call the Gateway, run paper trades |
| [cursor-mcp.example.json](cursor-mcp.example.json) | Minimal Cursor MCP configuration with replaceable endpoint and token placeholders |
| [agent-openapi.json](agent-openapi.json) | Machine-readable contract for `/api/agent/v1` (OpenAPI 3.0) |
| [../architecture/API_CONVENTIONS.md](../architecture/API_CONVENTIONS.md) | Shared HTTP conventions (envelopes, auth, Public/Internal tiers) |
| [../api/openapi.yaml](../api/openapi.yaml) | Human Web API spec (flask-smorest; migration in progress) |
| [Project research skill](../../.agents/skills/quantdinger-research/SKILL.md) | Repo-scoped native factor research, strategy evolution and backtest workflow |
| [RESEARCH_HANDOFF.md](RESEARCH_HANDOFF.md) | Dated local research state, record IDs, results and restart guidance; verify current database state |
| [RESEARCH_TEAM.md](RESEARCH_TEAM.md) | Orca-supervised factor, strategy-development and independent-validation roles |
| [Research universe preparation](../trading/RESEARCH_UNIVERSE.md) | Native parent-pool selection, evidence packets and private candidate pools |

**Language policy:** Machine-readable schemas, route names, scopes, environment variables, and tool identifiers remain in English as the canonical contract. Human setup guides are maintained in paired editions: [中文入口](README_CN.md) and this English entry.

For operator-authorized agents in this local WSL project, follow the [local connection example](AGENT_QUICKSTART.md#local-project-connection). The shared instructions and configuration path apply to Codex, Claude Code, Gemini CLI, and authorized Orca workers; the credential itself stays outside the repository. Existing agents must reread updated instructions at their next checkpoint.

Repository-level coding-agent instructions live in [`AGENTS.md`](../../AGENTS.md). Tool-specific entrypoints should load that file instead of duplicating repository rules under this documentation directory.
