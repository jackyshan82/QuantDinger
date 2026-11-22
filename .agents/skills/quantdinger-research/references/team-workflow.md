# Supervised research team

Use this workflow when the user requests supervised division of research work.
The coordinator loads the installed `orchestration` skill and its version-matched
kernel, coordinator-loop reference, and any placement reference required by the
current host. Those guides, not this file, own launch and lifecycle commands.
Do not create workers just to explain or prepare this plan.

## Study contract before paid or mutating work

Create a new dated study directory with a unique suffix; never reuse an earlier
study directory as a fresh experiment. Record the following in `study.json` or
an equivalent readable plan:

- Authorized tenant and connection route, without credentials.
- Market, symbols or universe, frequency, direction, same-day/overnight policy.
- Parent pool, selection cutoff before research, eligibility/ranking policy,
  expected selection packet and acceptance gate before factor submissions.
- Capital, commission, slippage, risk limits and evaluation objective.
- Data provenance and availability; search, validation and final-test dates;
  which intervals/results were already inspected.
- Finite factor list and parameter combinations, job/resource limits, and
  declared accept/reject conditions including sample sufficiency.
- Benchmark, cost-stress conditions and who may submit which native job.
- Per-role file ownership and the exact report paths each Task must produce.

Infer choices already fixed by the user's request; clarify only consequential
unresolved choices before dependent work. A favorable return alone is not an
acceptance rule. State how net profitability, drawdown, activity, benchmark
comparison and validation failures will affect the decision. Example thresholds
are study inputs, not universal defaults imposed by this skill.

## Roles and permissions

| Role | Scope | Outputs under the study directory | Boundary |
| --- | --- | --- | --- |
| Coordinator | Contract, Orca lifecycle, gates, receipts, final conclusion | `study.json`, `receipts.json`, `report.html` | Does not rewrite a rejected result or spend beyond the agreed study |
| Universe/factor researcher | Native parent-pool selection, then factor studies | `universe/selection.json`, saved pool ID, `factor/report.md`, `factor/records.json` | No final-return-based symbol selection, trading-source edits or final-test inspection |
| Strategy developer | Owned candidate source, compilation, native development evolution | `strategy/`, `strategy/frozen_candidate.json` | No final-test selection or validation-report edits |
| Independent validator | Predeclared protocol, frozen-source verification, native final backtests | `validation/protocol.md`, `validation/report.md`, `validation/records.json` | No candidate edits or parameter selection |

The strategy developer owns a source under `study/strategy/`; publish a stable
example into `examples/strategies/` only if it is part of the agreed deliverable.
Use native application services for saved sources, factor results, evolution
jobs and backtest history. Do not directly rewrite database result rows.

## Ready waves

1. Launch the first independent wave through Orca: universe/factor research, strategy
   scaffold preparation, and validation-protocol preparation. The universe/factor
   researcher first delivers a scope packet under `universe/`; the coordinator
   accepts it before native factor submissions. The scaffold worker does not
   start parameter search before the factor evidence and
   protocol are accepted. The protocol worker does not inspect final returns.
2. After factor and protocol deliveries, the coordinator decides whether there
   is a defensible hypothesis. Route a new implementation/evolution Task to the
   developer with the accepted packets. Native evolution uses development dates
   only. Factor ranks are diagnostics and need not mechanically establish a
   single-symbol time-series entry rule; record that limitation explicitly.
3. Accept a frozen packet from the developer: source ID, source version/code
   hash, manifest, effective parameters, accepted cohort hash/native pool ID,
   factor/evolution IDs, dates and known
   failures. Then dispatch final validation to the independent validator.
4. The validator reproduces source/hash/parameters and executes the predeclared
   external backtest and cost stress. The coordinator synthesizes pass, reject
   or inconclusive, links native records, and updates the dated handoff.

Encode real dependencies in Orca Tasks. A role is not a continuously running
process: release a settled worker with no immediate ready follow-up. If the
same proven agent has ready work, reuse it through a new Dispatch exactly as
the Orca guide specifies. Do not leave idle workers alive merely to preserve
three visible panes. Do not change model or effort unless requested.

## Dispatch contract

### Research team display names

Use concise English names that identify the study and responsibility. For this
project, prefer `<symbol or study> | <role>` for visible agent terminals:
`SKHY | Research Lead`, `SKHY | Factor Research`,
`SKHY | Strategy Development`, and `SKHY | Backtest Validation`.
Task titles should also identify the deliverable, such as
`SKHY | Factor Research | RSI and momentum`.

A task title and a terminal title are separate Orca fields. Set the task title
at creation, then use the runtime guide's supported terminal commands to set
both the tab and pane title for a verified terminal worker handle. Confirm the
names through terminal metadata; a role written only in a prompt does not name
the visible agent. Shared tabs require care because a tab rename affects every
pane in that tab. For workers without a terminal, use the display fields the
runtime actually exposes and report any unsupported rename rather than editing
Orca's internal state. Historical task status/result fields are not rename APIs.

Each Task includes Target, Change, Constraints, Ownership and Observable
acceptance, plus these concrete inputs:

```text
Use the quantdinger-research skill and its <role> reference.
Study directory: <absolute directory>
Plan: <absolute study.json>
Inputs: <accepted artifact paths and relevant native record IDs>
Owned outputs: <exact paths>; everything else is read-only.
Allowed native submissions: <factor studies / development evolution /
  frozen final backtests / none>, within the plan's job budget.
Acceptance: <reproducible artifacts, checks and native receipts>.
Follow the live Orca Task/Dispatch preamble for questions, mail and completion.
```

Track returned Run/Task/Dispatch IDs and native job/run IDs separately in
`receipts.json`. A CLI timeout does not authorize a duplicate submission; inspect
the existing receipt. Only the assigned role submits its stage's jobs. Begin
with at most one heavy native study at a time; parallelism is initially for
analysis/scaffolding/protocol work, not duplicate data fetches and backtests.

## Independence and failed candidates

Give the validator rules and frozen inputs, not an instruction to confirm that
it is profitable. The validator must not alter source, thresholds, dates or
costs to obtain a pass. A technical defect goes back to the developer through a
new Task, produces a new source/hash, and requires new validation accounting.
After final-test returns have been viewed, the interval remains inspected;
fixing code does not make it a fresh blind interval.

Roles in one checkout and database are cooperative boundaries, not a secure
sandbox that hides holdout files. If enforced secrecy is required, arrange
separate data access and filesystem isolation before claiming it. Record a
rejection or insufficient evidence as a successful research outcome when the
protocol was executed correctly. Worker completion and strategy profitability
are different statuses. No research Task authorizes live deployment.
