from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.data_providers import alpaca_research as provider
from app.professional_report.builder import build_professional_report
from app.professional_report.providers import provider_configuration_status
from app.professional_report.snapshot import build_evidence_snapshot
from app.services.alpaca_search import AlpacaNewsProvider
from app.services.fast_analysis import FastAnalysisService
from app.services.market_data_collector import MarketDataCollector


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ALPACA_REPORT_FEED", "iex")
    monkeypatch.setenv("ALPACA_OPTIONS_FEED", "indicative")
    monkeypatch.setattr(provider, "_owned_credentials", lambda user: (user * 10, {"api_key": "test", "secret_key": "secret", "paper": True}))
    monkeypatch.setattr(provider, "_now", lambda: datetime(2026, 10, 28, 1, tzinfo=timezone.utc))
    return provider.AlpacaResearch(7)


def test_cache_partition_and_no_cross_user_credentials(client, monkeypatch):
    cache, requests = {}, []
    monkeypatch.setattr(provider, "get_cached", lambda key, ttl: cache.get(key))
    monkeypatch.setattr(provider, "set_cached", lambda key, payload, ttl: cache.update({key: payload}))
    session = MagicMock()
    session.__enter__.return_value = session
    session.get.side_effect = lambda url, **kwargs: (requests.append((url, kwargs)) or
                                                   SimpleNamespace(status_code=200, json=lambda: {"dailyBar": {"c": 100}}))
    monkeypatch.setattr(provider.requests, "Session", lambda: session)
    first = client.snapshot("MSFT")
    first["dailyBar"]["c"] = 0
    assert client.snapshot("MSFT")["dailyBar"]["c"] == 100
    assert len(requests) == 1
    provider.AlpacaResearch(8).snapshot("MSFT")
    assert len(requests) == 2
    client.feed = "sip"
    client.snapshot("MSFT")
    assert len(requests) == 3
    assert all(kwargs["allow_redirects"] is False for _, kwargs in requests)
    assert session.trust_env is False


def test_news_pages_filter_unrelated_future_and_duplicates(client, monkeypatch):
    row = {"id": 1, "headline": "Microsoft update", "summary": "news", "symbols": ["MSFT"],
           "created_at": "2026-10-27T20:00:00Z", "url": "https://example.com/news", "source": "benzinga"}
    pages = iter([{"news": [dict(row, symbols=["AAPL"]), dict(row, created_at="2030-01-01T00:00:00Z")], "next_page_token": "next"},
                  {"news": [row, row], "next_page_token": None}])
    monkeypatch.setattr(client, "request", lambda *_a, **_k: next(pages))
    news = client.news("MSFT", limit=2)
    assert len(news) == 1
    assert news[0]["source"] == "alpaca_benzinga" and news[0]["datetime"] == row["created_at"]


def test_market_and_news_requests_send_rfc3339_seconds(client, monkeypatch):
    requests = []
    monkeypatch.setattr(client, "request", lambda path, params, **_kwargs: (requests.append(params.copy()) or {}))
    client.news("MSFT")
    client.bars("MSFT", "1D")
    for params in requests:
        assert params["end"].endswith(":00+00:00")


def test_snapshot_has_real_timestamp_and_unknown_fields_are_not_zero(client, monkeypatch):
    monkeypatch.setattr(client, "snapshot", lambda _: {"latestTrade": {"p": 105, "t": "2026-10-27T20:00:00Z"},
                                                      "prevDailyBar": {"c": 100}, "latestQuote": {"bp": 104}})
    price = client.price("MSFT")
    assert price["change"] == 5 and price["changePercent"] == pytest.approx(5)
    assert price["high"] is None and price["as_of"] == "2026-10-27T20:00:00Z"
    assert price["source"] == "alpaca_iex"


def test_indicative_options_keep_scope_and_do_not_invent_oi(client, monkeypatch):
    snapshots = {"MSFT261030C00100000": {"latestQuote": {"bp": 1, "ap": 2, "t": "2026-10-27T20:00:00Z"},
                                       "impliedVolatility": .25, "greeks": {"delta": .5}},
                 "MSFT261030P00100000": {"latestQuote": {"bp": 2, "ap": 3, "t": "2026-10-27T20:00:00Z"}},
                 "AAPL261030C00100000": {"impliedVolatility": .9, "latestQuote": {"t": "2026-10-27T20:00:00Z"}}}
    monkeypatch.setattr(client, "request", lambda *_a, **_k: {"snapshots": snapshots})
    result = client.options("MSFT", 100)
    assert result["nearest_atm_implied_volatility_pct"] == 25
    assert result["sample_contract_count"] == 2
    assert "indicative_prices_not_opra" in result["quality_flags"]
    assert "call_open_interest" not in result and "put_call_volume_ratio" not in result


def test_report_normalization_retains_source_and_indicative_caveat():
    now = datetime.now(timezone.utc).isoformat()
    payload = {"market": "USStock", "symbol": "MSFT", "collected_at": now,
               "price": {"price": 100, "source": "alpaca_iex", "as_of": now},
               "kline": [{"time": now, "open": 99, "high": 101, "low": 98, "close": 100, "volume": 10, "source": "alpaca_iex"}],
               "options": {"source": "alpaca_indicative", "feed": "indicative", "expiry": "2026-10-30",
                           "as_of": now, "nearest_atm_implied_volatility_pct": 25,
                           "quality_flags": ["indicative_prices_not_opra"]},
               "corporate_actions": [{"source": "alpaca_corporate_actions", "action_type": "cash_dividends", "as_of": now}],
               "news": [{"headline": "Microsoft MSFT update", "source": "alpaca_benzinga", "datetime": now, "url": "https://example.com/news"}],
               "_meta": {"alpaca_provider_status": {"account_configured": True}}}
    snapshot = build_evidence_snapshot(payload)
    option = next(x for x in snapshot["observations"] if x["metric"] == "options.snapshot")
    assert option["source"] == "alpaca_indicative"
    assert "indicative_prices_not_opra" in option["quality_flags"]
    report = build_professional_report(payload, {"market": "USStock", "language": "zh-CN"})
    alpaca = next(row for row in report["provider_options"]["community"] if row["key"] == "alpaca")
    assert alpaca["configured"] is True


def test_news_provider_is_symbol_scoped_and_web_queries_are_not_redirected(client, monkeypatch):
    monkeypatch.setattr("app.services.alpaca_search.AlpacaResearch", lambda _: client)
    monkeypatch.setattr(client, "news", lambda symbol, **_: [{"headline": symbol + " update", "summary": "news", "url": "https://example.com",
                                                             "source": "alpaca_benzinga", "datetime": "2026-10-27T20:00:00Z"}])
    search = AlpacaNewsProvider(7)
    assert search.search_symbol("MSFT").results[0].title == "MSFT update"
    assert search.search("$MSFT news").success
    assert not search.search("$MSFT 2016 annual revenue").success
    assert not search.search("US inflation latest news").success


def test_collector_and_fast_analysis_forward_owner_without_mutable_global_state(monkeypatch):
    service = FastAnalysisService.__new__(FastAnalysisService)
    service.data_collector = SimpleNamespace(collect_all=MagicMock(return_value={}))
    service._collect_market_data("USStock", "MSFT", user_id=7)
    assert service.data_collector.collect_all.call_args.kwargs["user_id"] == 7
    monkeypatch.setattr("app.data_providers.alpaca_research.account_available", lambda user: user == 7)
    assert provider_configuration_status("alpaca", user_id=7)["configured"]
    assert not provider_configuration_status("alpaca", user_id=8)["configured"]
    assert not provider_configuration_status("alpaca")["configured"]


def test_collector_falls_back_for_missing_account_without_hiding_other_sources(monkeypatch):
    collector = MarketDataCollector.__new__(MarketDataCollector)
    collector.kline_service = SimpleNamespace(get_realtime_price=lambda *_a, **_k: {"price": 100, "source": "public"})
    monkeypatch.setattr("app.data_providers.alpaca_research.AlpacaResearch", lambda _: (_ for _ in ()).throw(ValueError("no account")))
    assert collector._get_price("USStock", "MSFT", user_id=8)["source"] == "public"


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_optional_provider_errors_are_explicit_and_redacted(client, monkeypatch, status):
    monkeypatch.setattr(provider, "get_cached", lambda *_: None)
    session = MagicMock()
    session.__enter__.return_value = session
    session.get.return_value.status_code = status
    monkeypatch.setattr(provider.requests, "Session", lambda: session)
    with pytest.raises(ValueError, match=f"alpacaResearch.httpError:{status}") as error:
        client.snapshot("MSFT")
    assert "secret" not in str(error.value)
