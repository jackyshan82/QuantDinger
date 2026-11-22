---
name: quantdinger-research
description: Use QuantDinger's native factor research, strategy evolution and backtests to investigate trading rules, save research records, resume prior research, or coordinate an authorized Orca research team. Applies inside the QuantDinger repository or with an authorized QuantDinger connection; excludes generic investment advice and unrelated repository maintenance.
---

# QuantDinger Research

## Start in the right project

Locate the repository root using `git rev-parse --show-toplevel`. Read its
[AGENTS.md](../../../AGENTS.md), which remains the canonical repository policy.
Do not duplicate its coding, architecture or trading safety rules here.

For resumed research, read the dated
[research handoff](../../../docs/agent/RESEARCH_HANDOFF.md), then verify current
backend records. Historical IDs, account ownership, results and runtime status
can change. A handoff describes past authorization; it does not grant new access
or permission to deploy or trade.

For strategy code, use the current
[Strategy API V2 guide](../../../docs/trading/STRATEGY_DEV_GUIDE.md).
Read [native workflows](references/native-workflows.md) when accessing the app.

For authorized research delegation, follow the repository's
[Orca delegation rules](../../../AGENTS.md#agent-delegation-in-orca).
Load the installed Orca skills and their runtime-matched guides before launch;
research helpers must have actual Orca registration, not model-native subagent
identities. Keep task boundaries and result provenance in the research report.

## Supervised team roles

When the user requests a supervised research team, the coordinator reads
[team workflow](references/team-workflow.md). Dispatched workers read only
their assigned role reference and study inputs:

| Assigned role | Reference |
| --- | --- |
| Universe and factor researcher | [Universe selection](references/universe-selection.md), then [factor research](references/factor-researcher.md) |
| Strategy developer | [Strategy development](references/strategy-developer.md) |
| Independent validator | [Independent validation](references/independent-validator.md) |

One shared skill supplies the project workflow; Orca's `orchestration` skill
supplies actual worker lifecycle. A role reference is not a new agent process
or authorization to spawn one. Ordinary single-agent studies need no team.

## Use the application's research workflow

Prefer the project's factor-research, strategy-evolution and backtest services
and persist their ordinary result/job records. Do not quietly substitute an
ad hoc search script when the user asks to use the application's features.
Use existing authorized connections; do not print credentials or make the user
re-enter an already working connection.

Use the Agent Gateway/MCP for supported business operations, following
[Agent API access](../../../AGENTS.md#agent-api-access). Load the existing private
connection with `python scripts/with-agent-env.py <command> ...` and verify
`/api/agent/v1/whoami`; never send the token value to a worker. Consult the current
OpenAPI before choosing a fallback for factor-study or evolution capabilities
that are not exposed. State the gap and keep any native fallback within existing
authorization.

- Resolve the intended market, instrument, frequency, direction, holding horizon
  and costs from the request and existing source manifest. A daily source is not
  an intraday source; changing frequency requires new validation.
- For a stock pool, accept a pre-study [selection packet](references/universe-selection.md)
  before factor submissions. Record parent membership, past-only filtering,
  exclusions and the native saved pool ID; do not pick symbols from final returns.
- Use factor research for cross-sectional diagnostics across a suitable universe.
  Distinguish factor ranks and hypothetical long/short spreads from an executable
  single-instrument strategy. Native factor holding periods can cross sessions.
- Declare meaningful signal parameters and bounded ranges before evolution.
  Inspect the generated parameter space; searching only position size does not
  test signal parameters. Keep related-parameter constraints valid.
- Define search, validation and final-test periods before inspecting returns.
  Use native walk-forward/blind and cost-stress outputs. Record every tested
  configuration, failed study and data-availability revision. A previously
  inspected market interval is not wholly unseen just because a new study uses it.
- Freeze parameters before the final native backtest. Verify source ID, compiled
  code hash, manifest and effective parameters, rather than relying on the title
  or the currently selected UI tab.
- For same-day strategies, reconstruct positions from all executions in the
  exchange timezone and inspect end holdings; confirm no overnight positions.
  Bar labels can denote opens although handlers see completed closes. Account
  for next-bar fills, DST, early closes and missing/deferred fills.
- Retain native rejection, blind loss, limited sample and cost-stress failures.
  A highest-ranked candidate can still lose money. Compare positive results with
  an equivalent buy-and-hold baseline and state data/execution limitations.

## Finish with durable evidence

Report the strategy source ID, factor run IDs, evolution job ID, backtest IDs,
effective parameters, dates, net return, drawdown and acceptance/rejection.
Keep a readable report and supporting outputs in a dated `artifacts/` directory.
Link the relevant results from the handoff when continuing this local study.
Persist a new snapshot rather than overwriting unrelated strategies or history.

Saving or testing research does not authorize live deployment. State what was
actually run and whether any work remains; do not promise profitability.
