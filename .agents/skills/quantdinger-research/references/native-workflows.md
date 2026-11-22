# Native workflow locations

Paths below are relative to the QuantDinger repository root. Read only the
implementation needed for the current operation; contracts can change.

## Access

- Follow `AGENTS.md#agent-api-access`: load the private local connection through
  `python scripts/with-agent-env.py <command> ...`, verify `/api/agent/v1/whoami`,
  and use Gateway/MCP operations wherever the current contract supports them.
- External agents: start at `docs/agent/README.md`,
  `docs/agent/AGENT_QUICKSTART.md`, `docs/agent/MCP_SETUP.md` and
  `mcp_server/README.md`. Verify current tools and scopes before using them.
- Agent Gateway `/api/agent/v1` uses its own scoped Agent Token. Human Web APIs
  use normal application authentication. Do not interchange those credentials.
- Check `docs/agent/agent-openapi.json` and available MCP capabilities: factor
  catalog access does not imply native factor-study/evolution submission exists
  through the Gateway. Do not invent unavailable tools or endpoints.
- If a required feature has no exposed connector, an operator-authorized local
  backend service invocation can use the same application services and result
  persistence. Disclose that route. Do not bypass authentication on a remote
  service or assume a tenant from an old example.
- For a local installation, first discover services with
  `docker ps --format '{{.Names}}\t{{.Status}}'`. Read-only container inspection
  may work when Compose cannot read a protected `.env`; do not dump that file
  or container environment to work around it.

## Source library and compilation

- Agent HTTP: `/api/agent/v1/strategy-sources`, `/compile`, and version routes.
- Human HTTP fallback: `/api/strategies/script-sources` and its create/update/compile routes.
- Code: `backend_api_python/app/routes/script_source_routes.py`;
  `app/services/script_source.py`;
  `app/services/strategy_v2/contract.py`.
- Save with canonical V2 manifest metadata and version history through the
  application. Match source-owned symbol/frequency with the user's intent.

## Factor research

- HTTP: `POST /api/backtest/factor-research`;
  `GET /api/backtest/factor-research/history` and `/get`.
- Route: `app/routes/backtest_center.py:run_factor_research`.
- Service: `StrategyV2BacktestService.research_factor` or
  `.research_universe_factor`; persistence: `FactorResearchRepository`.
- Requests take `sourceId` for a portfolio source or an authorized `universeId`,
  `factorId`, `factorParams`, dates, groups, holding period and costs.
  Source mode requires a portfolio strategy, with at least three usable symbols.
- Look up IDs and parameter names in the actual catalog; do not infer them from
  labels. Inspect coverage, sample diagnostics, IC direction, group results and
  net costs. Factor-return fractions and backtest percentage metrics use
  different units; inspect the schema before formatting.

## Strategy evolution

- HTTP: `GET /api/strategy-evolution/parameter-space?sourceId=...`;
  `POST /estimate`, `POST /run`, `GET /jobs/<job_id>` under that prefix.
- Route: `app/routes/strategy_evolution.py`.
- Service: `app/services/strategy_evolution/service.py`;
  parameter contracts: `parameter_space.py`, `models.py`, `constraints.py`.
- The job persists in `qd_agent_jobs` with kind `strategy_evolution`. Poll its
  existing receipt rather than resubmitting on timeout. Inspect grid size,
  effective ranges, folds, blind usage, stress results and `recommended`.
- Check current units: the native summary's OOS and blind returns are percentage
  values, whereas some factor research returns are fractions.

## Backtests and restart checks

- Agent HTTP: `POST /api/agent/v1/backtest/run`, then `/api/agent/v1/jobs/<job_id>`.
- Human HTTP fallback: `/api/backtest/jobs`, `/jobs/<job_id>`, `/history`, `/get`; synchronous
  `POST /api/backtest/run` is also available in the current implementation.
- Services: `StrategyV2BacktestService`, `StrategyBacktestRepository`.
- Durable records: `qd_script_sources`, `qd_script_source_versions`,
  `qd_factor_research_runs`, `qd_agent_jobs`, `qd_backtest_runs`.
- Scope every source/job/history query to the verified user. Select only needed
  fields; request JSON and stored source code can contain sensitive context.
- Result history may be compacted. Before an execution audit, verify the returned
  execution count equals `totalExecutions` or fetch the complete execution ledger.
- The web UI may share loading state across tabs. Verify the backend job's actual
  kind/status instead of interpreting a spinner as proof of a second task.

The dated scripts in `scripts/research/` are local study drivers, not general
installers or portable account tools. They contain study-specific user IDs,
paths, parameters and dates. Read them and existing receipts before any reuse;
re-running verification may create additional backtests or consume credits.
