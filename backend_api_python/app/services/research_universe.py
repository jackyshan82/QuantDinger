"""Auditable pre-study stock-universe selection using native universe/history services."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
import hashlib
import json
import math
from typing import Callable

import pandas as pd

from app.services.universe import get_universe_service, member_content_hash, normalize_members


_DURATIONS = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60}


@dataclass(frozen=True)
class SelectionPolicy:
    frequency: str = '15m'
    lookback_days: int = 60
    min_sessions: int = 20
    min_median_session_bars: float = 20
    min_price: float = 0
    min_median_session_notional: float = 0
    max_stale_days: int = 7
    max_candidates: int | None = None
    min_candidates: int = 3

    def __post_init__(self):
        if self.frequency not in _DURATIONS:
            raise ValueError('researchUniverse.unsupportedFrequency')
        for value in [self.lookback_days, self.min_sessions, self.max_stale_days, self.min_candidates]:
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError('researchUniverse.invalidPolicy')
        for value in [self.min_median_session_bars, self.min_price, self.min_median_session_notional]:
            if not math.isfinite(value) or value < 0:
                raise ValueError('researchUniverse.invalidPolicy')
        if self.max_candidates is not None and (
            isinstance(self.max_candidates, bool) or not isinstance(self.max_candidates, int)
            or self.max_candidates < self.min_candidates
        ):
            raise ValueError('researchUniverse.invalidCandidateLimit')


def _utc_boundary(day: date) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(day, time.min), tz='America/New_York').tz_convert('UTC')


def _fingerprint(report: dict) -> str:
    payload = {key: value for key, value in report.items() if key not in {'selection_hash', 'saved_universe'}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False, default=str).encode()).hexdigest()


class ResearchUniverseService:
    def __init__(self, *, universe_service=None, frame_loader: Callable | None = None):
        self.universes = universe_service or get_universe_service()
        self.frame_loader = frame_loader

    def _load(self, member, frequency, start, end):
        if self.frame_loader:
            return self.frame_loader(member, frequency, start, end)
        from app.services.strategy_v2 import StrategyV2BacktestService
        return StrategyV2BacktestService()._fetch_member_frame(member, frequency, start, end)

    def prepare(self, *, user_id: int, universe_id: int, selection_as_of: date,
                research_start: date, policy: SelectionPolicy, plan_only: bool = False) -> dict:
        if user_id <= 0 or research_start <= selection_as_of:
            raise ValueError('researchUniverse.selectionMustPrecedeResearch')
        if selection_as_of >= pd.Timestamp.now(tz='America/New_York').date():
            raise ValueError('researchUniverse.completedSelectionDateRequired')
        universe = self.universes.get_universe(user_id, universe_id)
        if universe['market'] != 'USStock':
            raise ValueError('researchUniverse.usStocksOnly')
        if universe['universe_type'] == 'watchlist' or universe.get('source') == 'symbol_master':
            raise ValueError('researchUniverse.currentOnlyMembershipUnsupported')
        history_from = str(universe.get('history_from') or '')[:10]
        if history_from and selection_as_of < date.fromisoformat(history_from):
            raise ValueError('researchUniverse.membershipHistoryUnavailable')
        members = self.universes.resolve_members(user_id, universe_id, as_of=selection_as_of)
        if not members:
            raise ValueError('researchUniverse.emptyParentUniverse')
        if any(m['market'] != 'USStock' for m in members):
            raise ValueError('researchUniverse.usStocksOnly')
        members = sorted(members, key=lambda m: (m['symbol'], m.get('instrument_id') or ''))
        start_day = selection_as_of - timedelta(days=policy.lookback_days - 1)
        start, cutoff = _utc_boundary(start_day), _utc_boundary(selection_as_of + timedelta(days=1))
        metadata = universe.get('metadata') or {}
        assumed = metadata.get('history_mode') == 'fixed_current_constituents' or bool(metadata.get('snapshot_only'))
        if assumed and metadata.get('snapshot_as_of') and selection_as_of < date.fromisoformat(str(metadata['snapshot_as_of'])[:10]):
            raise ValueError('researchUniverse.assumedCurrentMembersLeakFuture')
        warnings = [
            'Selection is a fixed cohort for research beginning after selection_as_of, not dynamic historical membership.',
            'Session bar counts cover observed sessions only; they do not prove exchange-calendar completeness.',
            'Session notional is sum(close * volume) on the configured feed and adjusted series; it is not consolidated market turnover.',
            'Provider historical adjustments may incorporate later corporate actions; cutoff bars alone do not prove fully point-in-time prices.',
        ]
        if assumed or universe['universe_type'] == 'manual':
            warnings.append('Membership provenance is fixed/manual, not independently verified historical index membership.')
        report = {
            'schema_version': 1, 'user_id': user_id, 'parent_universe_id': universe_id,
            'parent_universe_code': universe['code'], 'parent_content_hash': member_content_hash(members),
            'parent_history_metadata': metadata, 'selection_as_of': selection_as_of.isoformat(),
            'research_start': research_start.isoformat(), 'lookback_start': start_day.isoformat(),
            'data_end_exclusive_utc': cutoff.isoformat(), 'policy': asdict(policy),
            'parent_member_count': len(members), 'warnings': warnings,
            'status': 'plan_only' if plan_only else 'incomplete', 'rows': [], 'selected_members': [],
        }
        if plan_only:
            report['parent_members'] = members
            report['selection_hash'] = _fingerprint(report)
            return report
        for member in members:
            owned = {**member, '_data_user_id': user_id}
            row = {'member': member, 'included': False, 'reasons': [], 'metrics': {}}
            try:
                frame = self._load(owned, policy.frequency, start.tz_localize(None).to_pydatetime(),
                                   (cutoff - pd.Timedelta(microseconds=1)).tz_localize(None).to_pydatetime())
                row['data_source'] = {key: str(getattr(frame, 'attrs', {}).get(key) or '') for key in ['provider', 'feed', 'adjustment']}
                row['metrics'], row['reasons'] = self._metrics(frame, start, cutoff, selection_as_of, policy)
            except Exception as exc:
                # Provider exceptions can carry URLs or account details; keep only the class.
                row['reasons'] = ['data_unavailable']
                row['error_type'] = type(exc).__name__
            report['rows'].append(row)
        eligible = [row for row in report['rows'] if not row['reasons']]
        eligible.sort(key=lambda row: (-row['metrics']['median_session_notional'], row['member']['symbol']))
        for index, row in enumerate(eligible):
            row['eligibility_rank'] = index + 1
            if policy.max_candidates is not None and index >= policy.max_candidates:
                row['reasons'].append('outside_candidate_limit')
            else:
                row['included'] = True
                report['selected_members'].append(row['member'])
        report['selected_count'] = len(report['selected_members'])
        if any('data_unavailable' in row['reasons'] for row in report['rows']):
            report['status'] = 'incomplete'
        elif report['selected_count'] < policy.min_candidates:
            report['status'] = 'insufficient_candidates'
        else:
            report['status'] = 'ready'
        report['selection_hash'] = _fingerprint(report)
        return report

    @staticmethod
    def _metrics(frame, start, cutoff, as_of, policy):
        if frame is None or frame.empty:
            return {}, ['no_data']
        if not set(['open', 'high', 'low', 'close', 'volume']).issubset(frame.columns):
            return {}, ['invalid_ohlcv']
        work = frame[['open', 'high', 'low', 'close', 'volume']].copy()
        index = pd.DatetimeIndex(work.index)
        if index.hasnans or index.has_duplicates:
            return {}, ['invalid_timestamps']
        work.index = index.tz_localize('UTC') if index.tz is None else index.tz_convert('UTC')
        duration = pd.Timedelta(minutes=_DURATIONS[policy.frequency])
        work = work.loc[(work.index >= start) & (work.index + duration <= cutoff)].sort_index()
        local = work.index.tz_convert('America/New_York')
        minutes = local.hour * 60 + local.minute
        work = work.loc[(minutes >= 570) & (minutes + _DURATIONS[policy.frequency] <= 960)]
        if work.empty:
            return {}, ['no_regular_session_data']
        work = work.apply(pd.to_numeric, errors='coerce')
        finite = work.map(lambda value: pd.notna(value) and math.isfinite(value)).all(axis=None)
        valid = ((work[['open', 'high', 'low', 'close']] > 0).all(axis=1)
                 & (work['volume'] >= 0)
                 & (work['high'] >= work[['open', 'close', 'low']].max(axis=1))
                 & (work['low'] <= work[['open', 'close', 'high']].min(axis=1)))
        if not finite or not valid.all():
            return {}, ['invalid_ohlcv']
        dates = work.index.tz_convert('America/New_York').date
        counts = work.groupby(dates).size()
        notional = (work['close'] * work['volume']).groupby(dates).sum()
        if not notional.map(lambda value: math.isfinite(value)).all():
            return {}, ['invalid_notional']
        last_date = work.index[-1].tz_convert('America/New_York').date()
        values = {'bars': len(work), 'sessions': len(counts),
                  'median_session_bars': float(counts.median()),
                  'median_session_notional': float(notional.median()),
                  'last_close': float(work['close'].iloc[-1]), 'last_session': last_date.isoformat(),
                  'stale_calendar_days': (as_of - last_date).days,
                  'observed_start_utc': work.index[0].isoformat(),
                  'observed_end_utc': work.index[-1].isoformat(),
                  'bars_hash': hashlib.sha256(work.to_csv(float_format='%.12g').encode()).hexdigest()}
        reasons = []
        for failed, code in [
            (values['sessions'] < policy.min_sessions, 'too_few_sessions'),
            (values['median_session_bars'] < policy.min_median_session_bars, 'too_few_session_bars'),
            (values['last_close'] < policy.min_price, 'price_below_minimum'),
            (values['median_session_notional'] < policy.min_median_session_notional, 'notional_below_minimum'),
            (values['stale_calendar_days'] > policy.max_stale_days, 'stale_history'),
        ]:
            if failed: reasons.append(code)
        return values, reasons

    def persist(self, *, user_id: int, report: dict, name: str) -> dict:
        if report.get('user_id') != user_id or report.get('selection_hash') != _fingerprint(report):
            raise ValueError('researchUniverse.invalidSelectionPacket')
        if report['status'] != 'ready':
            raise ValueError('researchUniverse.selectionNotReady')
        # Revalidate native ownership and membership before freezing a durable pool.
        snapshot = self.universes.create_snapshot(user_id, report['parent_universe_id'], as_of=report['selection_as_of'])
        if snapshot['content_hash'] != report['parent_content_hash']:
            raise ValueError('researchUniverse.parentChanged')
        metadata = {'research_selection_hash': report['selection_hash'],
                    'parent_universe_id': report['parent_universe_id'],
                    'parent_snapshot_id': snapshot['snapshot_id'],
                    'selection_as_of': report['selection_as_of'],
                    'not_valid_before': report['research_start'], 'policy': report['policy'],
                    'membership_interpretation': 'fixed_pre_study_cohort'}
        expected_members = normalize_members(report['selected_members'], default_market='USStock')
        for existing in self.universes.list_universes(user_id):
            if existing.get('user_id') == user_id and (existing.get('metadata') or {}).get('research_selection_hash') == report['selection_hash']:
                current = self.universes.resolve_members(user_id, existing['id'])
                if member_content_hash(current) != member_content_hash(expected_members):
                    raise ValueError('researchUniverse.savedSelectionChanged')
                return existing
        return self.universes.create_manual(user_id, {'name': name, 'market': 'USStock',
                    'members': expected_members, 'metadata': metadata})
