# QuantDinger Repository Instructions

This is the canonical instruction file for coding agents working in this repository. Keep tool-specific entrypoints thin and do not duplicate these rules elsewhere.

## Repository map

- `backend_api_python/`: Flask API, services, trading runtime, migrations, and backend tests.
- `mcp_server/`: the tenant-scoped MCP client/server package backed by QuantDinger APIs.
- `docs/`: product, architecture, deployment, API, Agent Gateway, and trading documentation.
- `docker-compose*.yml` and `scripts/`: deployment topology and lifecycle tooling.
- Frontend source is maintained outside this repository. The prebuilt frontend image is configured by the `frontend` service in `docker-compose.yml`.

## Read by task

Read only the documentation relevant to the change:

- Agent Gateway or MCP: [Agent documentation](docs/agent/README.md), [Agent OpenAPI](docs/agent/agent-openapi.json), and [MCP package documentation](mcp_server/README.md).
- Strategy API, backtests, or trading behavior: [Strategy development guide](docs/trading/STRATEGY_DEV_GUIDE.md) and [live-trading safety](docs/trading/LIVE_TRADING_SAFETY.md).
- Continuing local strategy research: [project research skill](.agents/skills/quantdinger-research/SKILL.md) and the dated [research handoff](docs/agent/RESEARCH_HANDOFF.md); verify current records before reusing historical IDs or results.
- Runtime ownership, concurrency, Kafka, workers, or durable state: [architecture index](docs/architecture/README.md) and the task-specific document it links.
- HTTP contracts: [API conventions](docs/architecture/API_CONVENTIONS.md) and the applicable OpenAPI document.
- Installation or operations: the root [README](README.md) and the applicable guide under `docs/deployment/`.

## Agent API access

- For QuantDinger business operations, use the Agent Gateway at `/api/agent/v1` or its MCP wrapper. Read [Agent documentation](docs/agent/README.md), [quickstart](docs/agent/AGENT_QUICKSTART.md), and the [OpenAPI contract](docs/agent/agent-openapi.json) before calling it.
- The operator-authorized local connection is stored outside Git at `~/.config/quantdinger/agent.env` (mode `0600`). Use `python scripts/with-agent-env.py <command> ...` to load it into a child process without displaying the token. The same WSL user can reuse this connection across project agents and worktrees. See the quickstart's local connection example.
- At the start of a new connection, call `GET /api/agent/v1/whoami` and verify the actual tenant, scopes, allowlists, paper-only setting, and order limits. Token access does not grant new trading authorization. Do not assume a historical user ID or token capability.
- Use the Gateway for supported strategy/source operations, backtests, runtime/account observations, and orders. Keep mutations idempotent and preserve confirmations and live-trading safeguards. If the required feature is absent from the contract, disclose the gap and use only an already-authorized native fallback; do not silently bypass the Gateway with SQL or `docker exec`.
- Direct container/database access is for necessary infrastructure diagnosis, repairs, and explicitly authorized capability gaps. Never copy the token into repository files, prompts, worker messages, shell arguments, logs, screenshots, or reports. Give workers the documentation and private configuration path, not the credential value.

## Agent delegation in Orca

- When delegation is authorized for this project, use Orca-managed agents so their ownership and lifecycle are visible in Orca's dashboard. Do not substitute model-native subagent tools or ad hoc CLI agent processes for Orca workers.
- Load the installed `orca-cli` and, for supervised work, `orchestration` skills. Resolve the session's CLI as those skills specify, then load its version-matched guide with `skills get`; do not copy a stale launch recipe or use Linux's unrelated screen-reader `orca` executable.
- For supervised helpers, use the documented Run/Task/Dispatch workflow and `orchestration worker-start`; track the returned IDs, process completion messages, and settle/release workers according to that guide. Prefer the current checkout unless isolation is needed; do not assume uncommitted files exist in a new worktree.
- For a full ownership handoff or a standalone new agent without supervision, use `orca-cli`'s `agent launch` or `worktree create --agent` flow instead of creating supervised tracking state. Verify prompt delivery and report the returned handle.
- If Orca cannot confirm startup or lifecycle state, report the actual receipt or blocker. Do not silently fall back to an invisible subagent, invent registration, or repeat an uncertain launch as a new worker.

## Architecture and contract invariants

- Preserve the process ownership documented in the architecture index. Do not move persistent trading loops into the HTTP backend or let evaluator processes submit exchange orders directly.
- PostgreSQL is the durable source of truth. Kafka transports versioned events; Redis cache data is evictable, while the jobs Redis has a separate durability role. Do not silently substitute one for another.
- Keep tenant isolation, idempotency, leases, fencing, and audit behavior intact when changing distributed or trading workflows.
- `/api/agent/v1` is the Agent Gateway boundary. Update `docs/agent/agent-openapi.json` and its alignment tests whenever that HTTP contract changes.
- MCP capabilities must retain the same authentication, scopes, idempotency, limits, and live-trading safeguards as the backing API.

## Safety and repository hygiene

- Never commit real secrets, production `.env` files, API keys, or database passwords. Use `.env.example` and placeholders.
- Do not weaken live-trading safeguards or bypass explicit authorization and human review unless the user requests and scopes that change.
- Do not add upgrade-time data rewrites for one-off local cleanup. Use an explicit, reviewed migration only when shipped user data must change.
- Preserve unrelated working-tree changes.
- Use English for source-code comments. Keep user-facing application copy in the existing localization system rather than hardcoding it in source files.
- Keep machine-readable contracts and identifiers in English. When a human guide has English and `_CN` editions, update both when the change affects both audiences.

## Verification

- Run focused backend tests from `backend_api_python/` with `python -m pytest tests/<test_file>.py -q`.
- Agent contract coverage lives in `backend_api_python/tests/test_ai_agent_contract_alignment.py` and related `test_agent_*.py` files.
- MCP tests live in `mcp_server/tests/`.
- Validate Compose changes with `docker compose config --quiet` before exercising the affected services.
- Match verification depth to risk; trading, migrations, tenancy, and distributed ownership require targeted regression tests.
