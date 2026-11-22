"""Build an auditable research cohort from a native stock universe.

Execute from backend_api_python. No database writes unless --save-name is given.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.research_universe import ResearchUniverseService, SelectionPolicy


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user-id', type=int, required=True)
    parser.add_argument('--universe-id', type=int, required=True)
    parser.add_argument('--as-of', type=date.fromisoformat, required=True)
    parser.add_argument('--research-start', type=date.fromisoformat, required=True)
    parser.add_argument('--frequency', default='15m', choices=['1m', '5m', '15m', '30m', '1h'])
    parser.add_argument('--lookback-days', type=int, default=60)
    parser.add_argument('--min-sessions', type=int, default=20)
    parser.add_argument('--min-session-bars', type=float, default=20)
    parser.add_argument('--min-price', type=float, default=0)
    parser.add_argument('--min-session-notional', type=float, default=0)
    parser.add_argument('--max-stale-days', type=int, default=7)
    parser.add_argument('--max-candidates', type=int)
    parser.add_argument('--min-candidates', type=int, default=3)
    parser.add_argument('--plan-only', action='store_true', help='Resolve native membership without fetching prices or saving a pool')
    parser.add_argument('--save-name', help='Save a ready selection as a private native manual universe')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.plan_only and args.save_name:
        parser.error('--plan-only cannot save a selected pool')
    if args.output.exists():
        parser.error('Output already exists; use a new study path instead of overwriting evidence')
    policy = SelectionPolicy(frequency=args.frequency, lookback_days=args.lookback_days,
        min_sessions=args.min_sessions, min_median_session_bars=args.min_session_bars,
        min_price=args.min_price, min_median_session_notional=args.min_session_notional,
        max_stale_days=args.max_stale_days, max_candidates=args.max_candidates,
        min_candidates=args.min_candidates)
    service = ResearchUniverseService()
    report = service.prepare(user_id=args.user_id, universe_id=args.universe_id,
        selection_as_of=args.as_of, research_start=args.research_start, policy=policy,
        plan_only=args.plan_only)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Keep the evidence even if native persistence later fails.
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False, default=str)+'\n')
    if args.save_name:
        report['saved_universe'] = service.persist(user_id=args.user_id, report=report, name=args.save_name)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False, default=str)+'\n')
    print(json.dumps({'status':report['status'],'parent_members':report['parent_member_count'],
        'selected_count':report.get('selected_count'), 'selection_hash':report['selection_hash'],
        'saved_universe_id':(report.get('saved_universe') or {}).get('id'), 'report':str(args.output)},ensure_ascii=False))
    return 0 if report['status'] in {'ready','plan_only'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
