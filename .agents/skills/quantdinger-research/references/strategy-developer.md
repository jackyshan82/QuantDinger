# Strategy developer

Read the shared skill, current Strategy API V2 guide, the study contract and the
accepted factor/protocol packets. Follow the live Orca preamble. Own only the
candidate source and strategy output paths assigned in the Task.
Use the accepted cohort and selection cutoff; a smaller instrument subset must
have a declared development-only rationale rather than final-test performance.

## Preparation Task

While research and validation protocol are being prepared, inspect the native
strategy contract, draft the source structure, identify meaningful parameters
and check source-owned symbol/frequency, direction and execution timing. Do not
run evolution or final backtests before their prerequisite packets are accepted.
Deliver a scaffold and parameter proposal, then settle this Task.

## Implementation/evolution Task

- Implement the accepted hypothesis with completed-bar decisions and executable
  trade rules, including required same-day exits and risk limits.
- Save/compile through native source-library services. Verify the actual manifest
  and parameter-space endpoint; periods, thresholds and exits must be searchable
  when the study optimizes them. Do not optimize only position size by accident.
- Run the native evolution job inside the declared development dates and budget.
  Preserve its walk-forward/blind outcomes, robustness grade and rejections.
- Do not inspect external final-test returns to pick parameters or change the
  hypothesis. A top-ranked result can still be unprofitable and must be reported.

## Freeze and deliver

Deliver `strategy/frozen_candidate.json` and a short research note containing:
source ID/version, compiled source code hash, the exact source file, manifest,
effective parameters, search/validation dates, costs, native evolution job ID,
factor IDs, cohort selection hash/native pool ID, selection rule, all known
failures and native recommendation.

The saved source defaults may differ from chosen run overrides: enumerate the
latter explicitly. Do not launch final validation or edit the validator's
reports. If the coordinator routes a technical fix back, create a new version
and packet and preserve the original evidence and inspected-period history.
