# Preparing a research universe

[中文](RESEARCH_UNIVERSE_CN.md)

The backend helper combines existing native stock universes, tenant-scoped
historical data and private manual-universe persistence. It establishes the
candidate range before factor research; it does not select stocks by future
strategy returns, run evolution, place orders or add a frontend screener page.

## Inputs and results

Choose a native parent pool (for example Nasdaq 100), a completed selection date,
a later research start, a lookback, frequency and eligibility rules. The service
resolves members at the selection date and evaluates only completed bars in the
lookback, restricted to New York normal-session hours with DST conversion.

Available filters are minimum observed sessions, median bars per session, latest
price, median session notional and maximum stale calendar days. Optional candidate
limits rank eligible symbols by median session notional with deterministic symbol
tie-breaking. Price/notional minima default to zero (disabled). Defaults are
research examples, not universally adequate liquidity or risk requirements.

The output JSON includes every member, metrics, reasons for exclusion, provider
attributes, bar hashes, parent membership hash, dates, policy, selected members
and an overall selection hash. It is `ready` only if the complete scan has no
provider failures and enough candidates remain. Data failures make it `incomplete`;
valid data with too few eligible symbols yields `insufficient_candidates`.

## Commands

Run from `backend_api_python` using an authorized user and a visible native pool.
Inspect `python scripts/prepare_research_universe.py --help` for options.

```bash
python scripts/prepare_research_universe.py \
  --user-id USER_ID --universe-id POOL_ID \
  --as-of 2025-08-29 --research-start 2025-09-01 \
  --plan-only --output /tmp/new-study/universe/plan.json
```

Then scan, for example, 60 calendar days of 15-minute bars with at least 20
observed sessions, a median of 20 normal-session bars, and a 20-symbol resource cap:

```bash
python scripts/prepare_research_universe.py \
  --user-id USER_ID --universe-id POOL_ID \
  --as-of 2025-08-29 --research-start 2025-09-01 \
  --frequency 15m --lookback-days 60 \
  --min-sessions 20 --min-session-bars 20 --max-candidates 20 \
  --output /tmp/new-study/universe/selection.json
```

Replace example dates and IDs with the study contract; these dates are not fresh
blind data in this workspace. The default is read-only. Add `--save-name NAME` to
the scan to save a ready result through native services. It snapshots/rechecks
parent membership and creates a private manual universe with selection provenance.
An unchanged existing selection is reused; altered saved membership is rejected.
Existing output evidence is not overwritten.

A caller with an already prepared packet can use
`ResearchUniverseService.persist(user_id=..., report=..., name=...)` without
repeating the price scan. Both entrypoints enforce the same packet hash,
readiness and tenant checks. No new schema or HTTP contract is introduced.

## Interpretation and limits

- This is a fixed cohort for research starting after the selection date. It is
  not a rolling selection/rebalance engine. The saved pool's `not_valid_before`
  metadata documents scope; it is not enforced throughout all other app APIs.
- Known current-constituent snapshots cannot be projected into earlier dates.
  Manual pools are labeled fixed; current watchlists/symbol-master lists are
  unsupported for historical membership selection.
- Date-based native membership does not independently prove complete historical
  index accuracy. Inspect the parent's provenance and limitations.
- Session counts measure observed sessions. Missing entire sessions, exchange
  holidays and early closes are not fully assessed against an exchange calendar.
- Notional is `sum(close * volume)` on the configured feed. IEX is not consolidated
  market turnover; adjusted histories can incorporate later corporate actions.
  Excluding future bar timestamps alone does not make every price adjustment
  point-in-time. Preserve these limitations in research reports.
- A full scan may make many data requests. Run one heavy study at a time and
  retain failed-request evidence rather than silently replacing unavailable data.

The universe/factor researcher delivers the selection packet and native pool ID
before factor submissions; the coordinator accepts the scope, and independent
validation checks it with the frozen candidate. See the
[team workflow](../agent/RESEARCH_TEAM.md).
