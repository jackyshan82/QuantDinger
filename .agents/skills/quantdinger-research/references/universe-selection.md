# Pre-study stock-universe selection

Use before factor research when the user has not fixed a single instrument.
The implementation is `backend_api_python/app/services/research_universe.py`;
the operator CLI is `backend_api_python/scripts/prepare_research_universe.py`.
It reuses native universe resolution, price history, snapshots and private manual
universe persistence. There is no new HTTP endpoint or frontend screener page.

## Freeze the selection contract

Record the parent native universe ID/code, selection date, research start,
lookback, frequency, eligibility filters and optional candidate cap before
viewing strategy returns. Verify the authorized tenant. The selection date must
precede the research start and be a completed New York calendar date.

Resolve parent members at the selection date. Do not back-project a known
current-constituent snapshot into earlier history. Current watchlists and symbol
master lists cannot supply historical membership through this helper. Manual or
fixed pools remain explicitly fixed universes, not verified historical indices.

Price/session filters and an optional liquidity ranking use only bars ending
before the selection cutoff. Use only normal-session bars, converted to New York
time with DST. The configured native provider and tenant's data account remain
in use. `sum(close * volume)` is a feed-specific session notional proxy, not
consolidated market turnover; adjusted historical prices may include later
corporate actions. Session counts do not prove exchange-calendar completeness.

## Run and inspect

From `backend_api_python`, first resolve membership without price reads/writes:

```bash
python scripts/prepare_research_universe.py \
  --user-id <authorized-user> --universe-id <native-pool-id> \
  --as-of <selection-date> --research-start <later-date> \
  --plan-only --output <new-study-path>/universe/plan.json
```

Then run selection with explicit study limits, for example:

```bash
python scripts/prepare_research_universe.py \
  --user-id <authorized-user> --universe-id <native-pool-id> \
  --as-of <selection-date> --research-start <later-date> \
  --frequency 15m --lookback-days 60 \
  --min-sessions 20 --min-session-bars 20 --max-candidates 20 \
  --output <new-study-path>/universe/selection.json
```

These are example research limits, not universally sufficient trading criteria.
`--min-price` and `--min-session-notional` default to zero (disabled); state any
nonzero thresholds in the plan. A candidate cap ranks eligible stocks by the
historical feed's median session notional, with symbol ordering to break ties.
It never ranks by final strategy return. The example 20-stock cap is a resource
limit, not an optimization target.

The packet contains every member's inclusion/exclusion reasons, metrics, input
bar hash, parent membership hash, dates, policy, warnings and a selection hash.
Statuses are `plan_only`, `ready`, `incomplete` or `insufficient_candidates`.
Provider exceptions make the whole scan incomplete; do not silently select only
the stocks whose requests happened to succeed. Fix/retry data with a new evidence
path, without changing thresholds in response to final strategy returns.

To persist a complete packet through the service, call
`ResearchUniverseService.persist(user_id=..., report=..., name=...)`.
Alternatively add `--save-name <private-pool-name>` to the original full-scan
command. The helper validates the hash and current parent snapshot, creates a
native private manual pool, and reuses an unchanged existing selection with the
same hash. It rejects cross-user, altered, changed-membership or incomplete
packets. CLI output files cannot be overwritten accidentally.

## Hand off the range

The universe/factor worker delivers `universe/selection.json` and its saved pool
ID before factor submissions. The coordinator accepts the scope; the developer
uses that cohort or an explicitly justified subset, not a symbol selected after
seeing final returns. The validator checks the membership hash and selection
cutoff alongside the frozen source.

The output pool is a fixed pre-study cohort. Its `not_valid_before` metadata is
provenance, not a platform-wide execution guard: callers must not use it for
research preceding that date. For rolling membership selection, generate dated
cohorts from past-only inputs and implement a proper dynamic-universe strategy;
this helper does not create rolling rebalances or guarantee profits.
