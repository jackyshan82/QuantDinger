# Supervised research team

[中文](RESEARCH_TEAM_CN.md) · [Shared research skill](../../.agents/skills/quantdinger-research/SKILL.md)

Use one coordinator and three roles, with actual workers created through Orca.
The reusable project skill explains the research workflow; Orca's installed
`orchestration` skill owns Run/Task/Dispatch registration and lifecycle.

| Role | Main work | Deliverable |
| --- | --- | --- |
| Universe/factor researcher | Past-only native parent-pool selection, factor diagnostics and costs | Selection packet/native pool ID, factor report and research IDs |
| Strategy developer | V2 source, parameter ranges and native evolution | Frozen source hash, parameters and evolution receipt |
| Independent validator | Protocol, execution checks and native final tests | Reproducible acceptance/rejection and backtest IDs |
| Coordinator | Research contract, readiness gates, resource budget and synthesis | Study plan, Orca/native receipts and final report |

## Execution order

1. Fix the target market, timeframe, direction, data periods, costs, finite search
   budget and acceptance criteria before results. Reuse decisions already made
   by the user; clarify only material missing choices.
2. Start the independent preparation wave: universe/factor studies, source scaffolding,
   and validation-protocol preparation. Only the factor role submits heavy
   native research jobs in this wave, after the coordinator accepts its
   [universe selection packet](../trading/RESEARCH_UNIVERSE.md).
3. After the factor evidence and protocol are accepted, the developer implements
   the hypothesis and runs native evolution on development dates. Deliver source
   ID/version/hash, manifest and exact parameter overrides as a frozen packet.
4. The validator checks that frozen packet and runs native external backtests,
   benchmark comparison and cost stress, without changing source or parameters.
5. The coordinator accepts the evidence, reports pass/reject/inconclusive,
   settles Orca resources and updates the handoff. No live trading is implied.

This is three roles, not three processes left permanently running. Reuse a
settled worker only for an immediately ready follow-up; otherwise release it
according to the runtime-matched Orca guide. Later phases may launch a fresh
worker for the same role.

## Practical boundaries

- Begin with one heavy native study at a time, because data APIs, database
  pools and CPU are shared. Parallel agents initially prepare different work
  products; they must not duplicate the same parameter search.
- Each role owns a separate subdirectory in a new dated study directory under
  `artifacts/`. The developer owns the candidate source; the validator's copy is
  read-only by task agreement. All native actions use the verified tenant.
- Use application services and ordinary stored research/job/backtest records.
  Track Orca IDs separately from QuantDinger IDs. Resume existing receipts after
  timeouts rather than starting a duplicate worker or study.
- The validator writes acceptance criteria before final outcomes and never
  selects parameters. Bug fixes go back to the developer through a new Task.
  Previously observed periods remain observed after a fix.
- Shared-workspace role boundaries do not technically hide holdout data. Do not
  claim enforced information isolation without actual access separation.
- A strategy rejection is a useful research result. Worker execution can succeed
  while the strategy fails profitability or robustness checks.

Detailed dispatch contracts and per-role instructions live in the skill's
[team workflow](../../.agents/skills/quantdinger-research/references/team-workflow.md).
Read the current Orca guide before launch; examples in documentation are not a
substitute for a verified runtime receipt.

## Invocation

A user can request:

> Use quantdinger-research and Orca orchestration to research NVDA intraday
> strategies. Delegate native factor research, strategy development and independent
> validation, freeze the evaluation plan before testing, and report all native
> records and rejected candidates. Do not start live trading.

This document prepares the workflow. It does not itself create a Run or launch
workers, and it does not imply that a profitable strategy has been found.
