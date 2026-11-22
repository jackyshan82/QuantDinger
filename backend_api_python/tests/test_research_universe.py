from copy import deepcopy
from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.services.research_universe import ResearchUniverseService, SelectionPolicy
from app.services.universe import member_content_hash


AS_OF = date(2025, 11, 7)
START = date(2025, 11, 10)


def member(symbol):
    return {'market':'USStock', 'symbol':symbol, 'instrument_id':'USStock:'+symbol}


def bars(volume=1000):
    # The range crosses the US DST transition; sessions are always 09:30 New York.
    frames=[]
    for day in ['2025-10-31','2025-11-03','2025-11-07']:
        index=pd.date_range(day+' 09:30',periods=26,freq='15min',tz='America/New_York').tz_convert('UTC').tz_localize(None)
        frames.append(pd.DataFrame({'open':10.,'high':11.,'low':9.,'close':10.,'volume':volume},index=index))
    return pd.concat(frames)


@pytest.fixture
def native():
    service=MagicMock()
    service.get_universe.return_value={'id':5,'code':'nasdaq100','market':'USStock',
        'universe_type':'index','source':'public_snapshot','history_from':'2023-01-01','metadata':{}}
    service.resolve_members.return_value=[member('AAA'),member('BBB'),member('CCC')]
    service.create_snapshot.return_value={'snapshot_id':'native-snapshot',
        'content_hash':member_content_hash(service.resolve_members.return_value)}
    service.list_universes.return_value=[]
    service.create_manual.return_value={'id':60}
    return service


@pytest.fixture
def policy():
    return SelectionPolicy(min_sessions=3,min_median_session_bars=26,min_candidates=2)


def prepare(native,policy,loader,**kwargs):
    return ResearchUniverseService(universe_service=native,frame_loader=loader).prepare(
        user_id=7,universe_id=5,selection_as_of=AS_OF,research_start=START,policy=policy,**kwargs)


def test_membership_and_data_loader_remain_tenant_scoped(native,policy):
    loader=MagicMock(return_value=bars())
    result=prepare(native,policy,loader)
    native.get_universe.assert_called_once_with(7,5)
    native.resolve_members.assert_called_once_with(7,5,as_of=AS_OF)
    assert result['status']=='ready' and result['selected_count']==3
    for call in loader.call_args_list:
        assert call.args[0]['_data_user_id']==7
        assert call.args[3] < pd.Timestamp('2025-11-08 05:00').to_pydatetime()
    assert all(row['metrics']['median_session_bars']==26 for row in result['rows'])


def test_future_and_extended_hours_prices_cannot_change_selection(native,policy):
    original=bars()
    extra=pd.DataFrame({'open':1000.,'high':1001.,'low':999.,'close':1000.,'volume':1e12},
        index=pd.to_datetime(['2025-11-07 22:00','2025-11-10 14:30']))
    a=prepare(native,policy,lambda *_:original)
    b=prepare(native,policy,lambda *_:pd.concat([original,extra]))
    assert a==b


def test_rank_cap_is_deterministic_and_records_exclusions(native,policy):
    policy=SelectionPolicy(min_sessions=3,min_median_session_bars=26,min_candidates=2,max_candidates=2)
    result=prepare(native,policy,lambda m,*_:bars({'AAA':100,'BBB':200,'CCC':300}[m['symbol']]))
    assert [m['symbol'] for m in result['selected_members']]==['CCC','BBB']
    assert result['rows'][0]['reasons']==['outside_candidate_limit']
    assert result['rows'][0]['included'] is False


def test_provider_failure_is_not_silently_used_to_choose_remaining_winners(native,policy):
    def load(m,*_):
        if m['symbol']=='BBB': raise RuntimeError('secret-provider-details')
        return bars()
    result=prepare(native,policy,load)
    assert result['status']=='incomplete'
    assert result['rows'][1]['reasons']==['data_unavailable']
    assert 'secret-provider-details' not in str(result)
    with pytest.raises(ValueError,match='selectionNotReady'):
        ResearchUniverseService(universe_service=native).persist(user_id=7,report=result,name='Research')
    native.create_manual.assert_not_called()


def test_assumed_current_members_cannot_be_projected_back_in_time(native,policy):
    native.get_universe.return_value['metadata']={'history_mode':'fixed_current_constituents','snapshot_as_of':'2026-10-27'}
    with pytest.raises(ValueError,match='assumedCurrentMembersLeakFuture'):
        prepare(native,policy,MagicMock())


def test_selection_date_precedes_research_and_history_coverage(native,policy):
    service=ResearchUniverseService(universe_service=native)
    with pytest.raises(ValueError,match='selectionMustPrecedeResearch'):
        service.prepare(user_id=7,universe_id=5,selection_as_of=AS_OF,research_start=AS_OF,policy=policy)
    native.get_universe.return_value['history_from']='2026-01-01'
    with pytest.raises(ValueError,match='membershipHistoryUnavailable'):
        prepare(native,policy,MagicMock())


def test_empty_duplicate_and_stale_data_are_excluded(native,policy):
    def load(m,*_):
        frame=bars()
        if m['symbol']=='AAA':return frame.iloc[:0]
        if m['symbol']=='BBB':return pd.concat([frame,frame.iloc[:1]])
        return frame.loc[frame.index<'2025-11-01']
    result=prepare(native,policy,load)
    assert result['status']=='insufficient_candidates'
    assert result['rows'][0]['reasons']==['no_data']
    assert result['rows'][1]['reasons']==['invalid_timestamps']
    assert 'too_few_sessions' in result['rows'][2]['reasons']


def test_plan_only_does_not_fetch_prices_or_write_snapshots(native,policy):
    loader=MagicMock()
    result=prepare(native,policy,loader,plan_only=True)
    assert result['status']=='plan_only' and len(result['parent_members'])==3
    loader.assert_not_called()
    native.create_snapshot.assert_not_called()


def test_persist_checks_tenant_packet_and_parent_snapshot(native,policy):
    result=prepare(native,policy,lambda *_:bars())
    service=ResearchUniverseService(universe_service=native)
    with pytest.raises(ValueError,match='invalidSelectionPacket'):
        service.persist(user_id=8,report=result,name='Research')
    modified=deepcopy(result);modified['selected_members']=[]
    with pytest.raises(ValueError,match='invalidSelectionPacket'):
        service.persist(user_id=7,report=modified,name='Research')
    native.create_snapshot.return_value['content_hash']='changed'
    with pytest.raises(ValueError,match='parentChanged'):
        service.persist(user_id=7,report=result,name='Research')
    native.create_manual.assert_not_called()


def test_persist_uses_native_service_and_reuses_unchanged_saved_selection(native,policy):
    result=prepare(native,policy,lambda *_:bars())
    service=ResearchUniverseService(universe_service=native)
    assert service.persist(user_id=7,report=result,name='Research')['id']==60
    payload=native.create_manual.call_args.args[1]
    assert payload['metadata']['not_valid_before']==START.isoformat()
    assert payload['metadata']['parent_snapshot_id']=='native-snapshot'
    native.create_manual.reset_mock()
    native.resolve_members.return_value=payload['members']
    native.list_universes.return_value=[{'id':60,'user_id':7,'metadata':payload['metadata']}]
    assert service.persist(user_id=7,report=result,name='Research')['id']==60
    native.create_manual.assert_not_called()
    native.resolve_members.return_value=[member('OTHER')]
    with pytest.raises(ValueError,match='savedSelectionChanged'):
        service.persist(user_id=7,report=result,name='Research')


def test_snapshot_only_metadata_also_blocks_backdated_selection(native,policy):
    native.get_universe.return_value['metadata']={'snapshot_only':True,'snapshot_as_of':'2026-10-28'}
    loader=MagicMock()
    with pytest.raises(ValueError,match='assumedCurrentMembersLeakFuture'):
        prepare(native,policy,loader,plan_only=True)
    loader.assert_not_called()


def test_declared_price_and_notional_filters_keep_all_reasons(native):
    policy=SelectionPolicy(min_sessions=3,min_median_session_bars=26,min_candidates=2,
        min_price=11,min_median_session_notional=1_000_000)
    result=prepare(native,policy,lambda *_:bars())
    assert result['status']=='insufficient_candidates'
    assert all(row['reasons']==['price_below_minimum','notional_below_minimum'] for row in result['rows'])


def test_saved_pool_identity_is_normalized_before_idempotent_reuse(native,policy):
    for m in native.resolve_members.return_value:
        m['instrument_id']=''
    native.create_snapshot.return_value['content_hash']=member_content_hash(native.resolve_members.return_value)
    result=prepare(native,policy,lambda *_:bars())
    service=ResearchUniverseService(universe_service=native)
    service.persist(user_id=7,report=result,name='Research')
    payload=native.create_manual.call_args.args[1]
    native.resolve_members.return_value=payload['members']
    native.list_universes.return_value=[{'id':60,'user_id':7,'metadata':payload['metadata']}]
    native.create_manual.reset_mock()
    assert service.persist(user_id=7,report=result,name='Research')['id']==60
    native.create_manual.assert_not_called()
