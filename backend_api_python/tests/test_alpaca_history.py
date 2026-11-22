from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.services import alpaca_history as history
from app.services.backtest_cache import KlineCache
from app.services.backtest_limits import backtest_range_policy_metadata, validate_backtest_range
from app.services.strategy_v2.service import StrategyV2BacktestService


def bar(time, close=101):
    return {"t": time, "o": 100, "h": 102, "l": 99, "c": close, "v": 10}


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("US_STOCK_BACKTEST_PROVIDER", "alpaca")
    monkeypatch.setenv("ALPACA_BACKTEST_FEED", "iex")
    monkeypatch.setenv("CACHE_ENABLED", "false")
    monkeypatch.setattr(history, "_cache", KlineCache())
    credentials = MagicMock(return_value=(11, {"api_key": "test-key", "secret_key": "test-secret"}))
    monkeypatch.setattr(history, "_owned_credentials", credentials)
    session = MagicMock()
    session.__enter__.return_value = session
    monkeypatch.setattr(history.requests, "Session", lambda: session)
    return session, credentials


def response(rows, token=None, status=200):
    return SimpleNamespace(status_code=status, json=lambda: {"bars": {"MSFT": rows}, "next_page_token": token})


def load(user=7, timeframe="1m"):
    return history.load_alpaca_frame(user, "MSFT", timeframe,
                                    datetime(2025, 1, 2), datetime(2025, 1, 3, 23, 59))


def test_all_pages_are_loaded_sorted_and_deduplicated(provider):
    session, _ = provider
    session.get.side_effect = [response([bar("2025-01-02T14:31:00Z")], "next"),
                               response([bar("2025-01-02T14:30:00Z"), bar("2025-01-02T14:31:00Z", 102)])]
    frame = load()
    assert list(frame.close) == [101, 102]
    assert frame.index.tz is None
    assert frame.attrs == {"provider": "alpaca", "feed": "iex", "adjustment": "all"}
    assert session.get.call_count == 2
    assert session.get.call_args.kwargs["params"]["page_token"] == "next"
    assert session.get.call_args.args == ("https://data.alpaca.markets/v2/stocks/bars",)


def test_cache_is_isolated_by_user_account_and_feed(provider, monkeypatch):
    session, credentials = provider
    session.get.return_value = response([bar("2025-01-02T14:30:00Z")])
    load(); load()
    assert session.get.call_count == 1
    load(user=8)
    assert session.get.call_count == 2
    credentials.return_value = (22, {"api_key": "test-key", "secret_key": "test-secret"})
    load()
    assert session.get.call_count == 3
    monkeypatch.setenv("ALPACA_BACKTEST_FEED", "sip")
    load()
    assert session.get.call_count == 4
    # Ownership is checked even on cache hits.
    credentials.side_effect = ValueError("brokerAccounts.accountUnavailable")
    with pytest.raises(ValueError, match="accountUnavailable"):
        load()


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_provider_errors_do_not_fallback_or_expose_credentials(provider, status):
    session, _ = provider
    session.get.return_value = response([], status=status)
    with pytest.raises(ValueError, match=f"HTTP {status}") as caught:
        load()
    assert "test-secret" not in str(caught.value)
    assert session.get.call_count == 1


def test_repeated_pagination_token_fails_without_partial_cache(provider):
    session, _ = provider
    session.get.return_value = response([bar("2025-01-02T14:30:00Z")], "same")
    with pytest.raises(ValueError, match="pagination"):
        load()
    assert session.get.call_count == 2


def test_daily_bar_is_visible_after_session_close(provider):
    session, _ = provider
    session.get.return_value = response([bar("2025-01-02T05:00:00Z")])
    frame = history.load_alpaca_frame(7, "MSFT", "1d", datetime(2025, 1, 2), datetime(2025, 1, 2, 23, 59))
    assert len(frame) == 1


def test_range_policy_changes_only_us_stocks(provider, monkeypatch):
    args = dict(symbol="MSFT", timeframe="1m", start_date=datetime(2025, 1, 1), end_date=datetime(2025, 3, 1))
    assert validate_backtest_range(market="USStock", **args) is None
    assert validate_backtest_range(market="Crypto", **args)["max_days"] == 30
    monkeypatch.setenv("US_STOCK_BACKTEST_PROVIDER", "yfinance")
    assert validate_backtest_range(market="USStock", **args)["max_days"] == 30


def test_alpaca_form_limit_includes_equity_session_warmup(provider):
    metadata = backtest_range_policy_metadata(markets=["USStock"], timeframe="1m", warmup_bars=260)
    assert metadata["maxDays"] == 180
    assert metadata["warmupDays"] == 7
    assert metadata["maxSelectedDays"] == 173


def test_default_service_routes_owned_us_history_to_alpaca(provider, monkeypatch):
    loader = MagicMock(return_value=pd.DataFrame({"close": [100]}))
    monkeypatch.setattr(history, "load_alpaca_frame", loader)
    service = StrategyV2BacktestService(repository=object(), universe_service=object(), snapshot_store=object())
    member = {"market": "USStock", "symbol": "MSFT", "key": "USStock:MSFT", "_data_user_id": 7}
    frames, skipped = service.fetch_frequency_frames([member], ("1m",), {"1m": datetime(2025, 1, 1)}, datetime(2025, 3, 1))
    assert not skipped
    assert "USStock:MSFT" in frames["1m"]
    assert loader.call_args.args[0] == 7


def test_credential_lookup_is_owned_and_rejects_ambiguous_accounts(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = [{"id": 11}, {"id": 22}]
    connection = MagicMock()
    connection.cursor.return_value = cursor

    @contextmanager
    def database():
        yield connection

    monkeypatch.setattr(history, "get_db_connection", database)
    with pytest.raises(ValueError, match="accountSelectionRequired"):
        history._owned_credentials(7)
    sql, args = cursor.execute.call_args.args
    assert "user_id = %s" in sql and "exchange_id = 'alpaca'" in sql
    assert args == (7,)
    cursor.fetchall.return_value = []
    with pytest.raises(ValueError, match="accountUnavailable"):
        history._owned_credentials(8)


def test_account_error_is_not_hidden_as_empty_market_data(provider):
    _, credentials = provider
    credentials.side_effect = history.AlpacaHistoryError("brokerAccounts.accountUnavailable")
    service = StrategyV2BacktestService(repository=object(), universe_service=object(), snapshot_store=object())
    member = {"market": "USStock", "symbol": "MSFT", "key": "USStock:MSFT", "_data_user_id": 7}
    with pytest.raises(history.AlpacaHistoryError, match="accountUnavailable"):
        service.fetch_frequency_frames([member], ("1m",), {"1m": datetime(2025, 1, 1)}, datetime(2025, 3, 1))


def test_live_candles_are_current_but_research_keeps_delay(provider, monkeypatch):
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 9, 15, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(history, "datetime", FixedClock)
    session, _ = provider
    session.get.return_value = response([
        bar("2026-11-09T14:30:00Z"), bar("2026-11-09T14:59:00Z"),
        bar("2026-11-09T15:00:00Z"),
    ])
    start, end = datetime(2026, 11, 9), datetime(2026, 11, 9, 15, tzinfo=timezone.utc)
    historical = history.load_alpaca_frame(7, "MSFT", "1m", start, end)
    assert str(historical.index[-1]) == "2026-11-09 14:30:00"
    assert session.get.call_args.kwargs["params"]["end"].startswith("2026-11-09T14:45:00")
    live = history.load_alpaca_frame(7, "MSFT", "1m", start, end, live=True)
    assert str(live.index[-1]) == "2026-11-09 14:59:00"
    assert session.get.call_args.kwargs["params"]["end"].startswith("2026-11-09T15:00:00")
    assert session.get.call_args.kwargs["timeout"] == (3, 8)


def test_transport_failure_retries_without_returning_partial_history(provider, monkeypatch):
    session, _ = provider
    monkeypatch.setattr(history.time, "sleep", lambda *_: None)
    session.get.side_effect = [
        response([bar("2025-01-02T14:30:00Z")], "next"),
        history.requests.ReadTimeout("sensitive-provider-detail"),
        response([bar("2025-01-02T14:31:00Z")]),
    ]
    frame = load()
    assert len(frame) == 2
    assert session.get.call_count == 3


def test_persistent_transport_failure_is_bounded_and_sanitized(provider, monkeypatch):
    session, _ = provider
    monkeypatch.setattr(history.time, "sleep", lambda *_: None)
    session.get.side_effect = history.requests.ConnectionError("sensitive-provider-detail")
    with pytest.raises(history.AlpacaHistoryError, match="ConnectionError") as caught:
        load()
    assert session.get.call_count == 2
    assert "sensitive-provider-detail" not in str(caught.value)
    assert "test-secret" not in str(caught.value)


def test_live_service_forwards_current_data_flag(provider, monkeypatch):
    loader = MagicMock(return_value=pd.DataFrame({"close": [100]}))
    monkeypatch.setattr(history, "load_alpaca_frame", loader)
    service = StrategyV2BacktestService(repository=object(), universe_service=object(), snapshot_store=object())
    service._fetch_member_frame(
        {"market": "USStock", "symbol": "MSFT", "_data_user_id": 7, "_live_market_data": True},
        "1m", datetime(2026, 11, 9), datetime(2026, 11, 9, 15),
    )
    assert loader.call_args.kwargs["live"] is True


def test_live_bundle_marks_stocks_without_mutating_universe():
    from app.services.strategy_runtime.timeframes import load_live_frequency_frames

    candidate = {"market": "USStock", "symbol": "MSFT", "key": "USStock:MSFT", "_data_user_id": 7}
    frame = pd.DataFrame({"close": [100]})
    fetch = MagicMock(return_value=({"1m": {"USStock:MSFT": frame}}, []))
    service = SimpleNamespace(fetch_frequency_frames=fetch)
    manifest = SimpleNamespace(warmup_bars=20, frequencies=("1m",), driving_frequency="1m", fundamental_dependencies=())
    load_live_frequency_frames(service=service, candidates=[candidate], manifest=manifest, end_date=datetime(2026, 11, 9, 15))
    supplied = fetch.call_args.args[0][0]
    assert supplied["_live_market_data"] is True
    assert supplied["_data_user_id"] == 7
    assert "_live_market_data" not in candidate


@pytest.mark.parametrize("failure", ["connection", 429, 503])
def test_live_alpaca_outage_reaches_runtime_data_path_and_recovers(provider, monkeypatch, failure):
    from app.data_sources.errors import MarketDataUnavailableError
    from app.services.strategy_runtime.timeframes import load_live_frequency_frames

    session, _ = provider
    monkeypatch.setattr(history.time, "sleep", lambda *_: None)
    if failure == "connection":
        session.get.side_effect = history.requests.ConnectionError("sensitive-provider-detail")
    else:
        session.get.return_value = response([], status=failure)
    service = StrategyV2BacktestService(repository=object(), universe_service=object(), snapshot_store=object())
    candidate = {"market": "USStock", "symbol": "MSFT", "key": "USStock:MSFT", "_data_user_id": 7}
    manifest = SimpleNamespace(warmup_bars=20, frequencies=("1m",), driving_frequency="1m", fundamental_dependencies=())

    def fetch():
        return load_live_frequency_frames(service=service, candidates=[candidate], manifest=manifest,
                                          end_date=datetime(2025, 1, 3, 23, 59))

    with pytest.raises(MarketDataUnavailableError) as caught:
        fetch()
    detail = caught.value.failure
    assert detail.code == ("rate_limited" if failure == 429 else "exchange_unavailable")
    assert detail.retryable is True
    assert (detail.exchange_id, detail.symbol, detail.timeframe) == ("alpaca", "MSFT", "1m")
    assert "sensitive-provider-detail" not in str(detail.as_dict())
    assert "test-secret" not in str(detail.as_dict())
    assert session.get.call_count == (2 if failure == "connection" else 1)
    # A later cycle must fetch again and receive real bars, not cached failure
    # or an empty/stale bundle masquerading as successful market data.
    session.get.side_effect = None
    session.get.return_value = response([bar("2025-01-02T14:30:00Z")])
    assert not fetch()["1m"]["USStock:MSFT"].empty


@pytest.mark.parametrize("status", [401, 403])
def test_live_auth_failures_still_fail_explicitly(provider, status):
    session, _ = provider
    session.get.return_value = response([], status=status)
    with pytest.raises(history.AlpacaHistoryError, match=f"HTTP {status}"):
        history.load_alpaca_frame(7, "MSFT", "1m", datetime(2025, 1, 2),
                                  datetime(2025, 1, 3, 23, 59), live=True)
