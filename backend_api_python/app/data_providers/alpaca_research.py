"""Owned Alpaca market evidence for reports and symbol-specific news searches."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

from app.data_providers import get_cached, set_cached
from app.services.alpaca_history import _owned_credentials


def account_available(user_id=None):
    if not user_id:
        return False
    try:
        _owned_credentials(int(user_id))
        return True
    except Exception:
        return False


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _now():
    return datetime.now(timezone.utc)


class AlpacaResearch:
    def __init__(self, user_id):
        self.user_id = int(user_id or 0)
        self.credential_id, self.config = _owned_credentials(self.user_id)
        self.feed = os.getenv("ALPACA_REPORT_FEED", "iex").strip().lower()
        self.options_feed = os.getenv("ALPACA_OPTIONS_FEED", "indicative").strip().lower()
        if self.feed not in {"iex", "sip"} or self.options_feed not in {"indicative", "opra"}:
            raise ValueError("alpacaResearch.invalidFeed")

    def request(self, path, params=None, ttl=60, trading=False):
        raw = json.dumps([self.user_id, self.credential_id, trading, path, params], sort_keys=True)
        key = "alpaca-research:v1:" + hashlib.sha256(raw.encode()).hexdigest()
        cached = get_cached(key, ttl)
        if cached is not None:
            return copy.deepcopy(cached)
        host = ("https://paper-api.alpaca.markets" if self.config.get("paper", True)
                else "https://api.alpaca.markets") if trading else "https://data.alpaca.markets"
        proxy = os.getenv("PROXY_URL", "").strip()
        with requests.Session() as session:
            session.trust_env = False
            session.headers.update({"APCA-API-KEY-ID": self.config["api_key"],
                                    "APCA-API-SECRET-KEY": self.config["secret_key"]})
            try:
                response = session.get(host + path, params=params, timeout=(3, 8), allow_redirects=False,
                                       proxies={"http": proxy, "https": proxy} if proxy else None)
            except requests.RequestException:
                raise ValueError("alpacaResearch.unavailable") from None
        if response.status_code != 200:
            raise ValueError(f"alpacaResearch.httpError:{response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise ValueError("alpacaResearch.invalidResponse") from None
        set_cached(key, payload, ttl)
        return copy.deepcopy(payload)

    @staticmethod
    def symbol(value):
        value = str(value).strip().upper().replace("/", ".")
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,19}", value):
            raise ValueError("alpacaResearch.invalidSymbol")
        return value

    def snapshot(self, symbol):
        symbol = self.symbol(symbol)
        return self.request(f"/v2/stocks/{quote(symbol, safe='')}/snapshot", {"feed": self.feed}, ttl=30)

    def price(self, symbol):
        row = self.snapshot(symbol)
        trade, daily, previous = row.get("latestTrade") or {}, row.get("dailyBar") or {}, row.get("prevDailyBar") or {}
        price, prior = _number(trade.get("p")), _number(previous.get("c"))
        if price is None or price <= 0:
            raise ValueError("alpacaResearch.priceUnavailable")
        return {"price": price, "previousClose": prior, "open": _number(daily.get("o")),
                "high": _number(daily.get("h")), "low": _number(daily.get("l")),
                "change": price - prior if prior else None,
                "changePercent": (price / prior - 1) * 100 if prior else None,
                "source": "alpaca_" + self.feed, "as_of": trade.get("t"), "feed": self.feed,
                "quality_flags": ["single_venue_iex"] if self.feed == "iex" else [],
                "latest_quote": row.get("latestQuote") or {}, "latest_trade": trade}

    def bars(self, symbol, timeframe, limit=60):
        symbol, frequency = self.symbol(symbol), str(timeframe).lower()
        frequencies = {"1m": ("1Min", 60), "3m": ("3Min", 180), "5m": ("5Min", 300),
                       "15m": ("15Min", 900), "30m": ("30Min", 1800), "1h": ("1Hour", 3600),
                       "4h": ("4Hour", 14400), "1d": ("1Day", 86400), "1w": ("1Week", 604800)}
        if frequency not in frequencies:
            raise ValueError("alpacaResearch.unsupportedTimeframe")
        interval, seconds = frequencies[frequency]
        end = _now() - (timedelta(minutes=15) if self.feed == "sip" else timedelta())
        days = max(7, math.ceil(limit * seconds / 86400 * 2.5))
        params = {"symbols": symbol, "timeframe": interval, "start": (end - timedelta(days=days)).isoformat(),
                  "end": end.replace(second=0, microsecond=0).isoformat(), "sort": "desc", "limit": min(10000, limit + 10),
                  "feed": self.feed, "adjustment": "all"}
        payload = self.request("/v2/stocks/bars", params)
        rows = (payload.get("bars") or {}).get(symbol) or []
        result = []
        for row in rows:
            stamp = datetime.fromisoformat(str(row["t"]).replace("Z", "+00:00"))
            if frequency == "1d":
                from zoneinfo import ZoneInfo
                local = stamp.astimezone(ZoneInfo("America/New_York"))
                closed = local.replace(hour=16, minute=0) <= end
            else:
                closed = stamp + timedelta(seconds=seconds) <= end
            if not closed:
                continue
            values = {long: _number(row.get(short)) for long, short in
                      (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"), ("volume", "v"))}
            if any(values[key] is None for key in ("open", "high", "low", "close")):
                continue
            result.append({"time": int(stamp.timestamp()), **values, "source": "alpaca_" + self.feed,
                           "quality_flags": ["single_venue_iex"] if self.feed == "iex" else []})
        return sorted(result, key=lambda row: row["time"])[-limit:]

    def news(self, symbol, limit=15, days=7):
        symbol = self.symbol(symbol)
        end = _now()
        params = {"symbols": symbol, "start": (end - timedelta(days=days)).date().isoformat(),
                  "end": end.replace(second=0, microsecond=0).isoformat(), "limit": min(50, max(1, limit)),
                  "sort": "desc", "include_content": "false"}
        result, tokens = [], set()
        for _ in range(3):
            payload = self.request("/v1beta1/news", params, ttl=300)
            for row in payload.get("news") or []:
                if symbol not in [str(item).upper() for item in row.get("symbols") or []]:
                    continue
                stamp = row.get("created_at")
                try:
                    observed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
                    observed = observed.replace(tzinfo=timezone.utc) if observed.tzinfo is None else observed
                except ValueError:
                    continue
                if observed > end:
                    continue
                if not row.get("headline") or not row.get("url"):
                    continue
                result.append({"id": row.get("id"), "headline": row["headline"],
                               "summary": str(row.get("summary") or "")[:600], "url": row["url"],
                               "datetime": stamp, "source": "alpaca_benzinga", "publisher": row.get("source"),
                               "symbols": row.get("symbols"), "asset_relevance": "direct"})
            token = payload.get("next_page_token")
            if len(result) >= limit or not token:
                break
            if token in tokens:
                raise ValueError("alpacaResearch.paginationDidNotAdvance")
            tokens.add(token)
            params["page_token"] = token
        unique = {row.get("id") or row["url"]: row for row in result}
        return sorted(unique.values(), key=lambda row: row["datetime"], reverse=True)[:limit]

    def options(self, symbol, spot=None):
        symbol = self.symbol(symbol)
        today = _now().date()
        params = {"feed": self.options_feed, "limit": 1000, "expiration_date_gte": today.isoformat(),
                  "expiration_date_lte": (today + timedelta(days=45)).isoformat()}
        if spot and spot > 0:
            params.update(strike_price_gte=round(spot * .8, 2), strike_price_lte=round(spot * 1.2, 2))
        snapshots, tokens, truncated = {}, set(), False
        for _ in range(3):
            payload = self.request(f"/v1beta1/options/snapshots/{quote(symbol, safe='')}", params, ttl=300)
            snapshots.update(payload.get("snapshots") or {})
            token = payload.get("next_page_token")
            if not token:
                break
            if token in tokens:
                raise ValueError("alpacaResearch.paginationDidNotAdvance")
            tokens.add(token)
            params["page_token"] = token
        else:
            truncated = bool(token)
        contracts = []
        for contract, row in snapshots.items():
            matched = re.fullmatch(r"(.+)(\d{6})([CP])(\d{8})", contract)
            if not matched:
                continue
            _, expiry, side, strike = matched.groups()
            if matched.group(1).replace(".", "") != symbol.replace(".", ""):
                continue
            q, t = row.get("latestQuote") or {}, row.get("latestTrade") or {}
            observed = q.get("t") or t.get("t")
            try:
                if not observed or datetime.fromisoformat(observed.replace("Z", "+00:00")) > _now():
                    continue
            except (ValueError, TypeError):
                continue
            iv = _number(row.get("impliedVolatility"))
            contracts.append({"symbol": contract, "expiry": datetime.strptime(expiry, "%y%m%d").date().isoformat(),
                              "type": "call" if side == "C" else "put", "strike": int(strike) / 1000,
                              "implied_volatility_pct": iv * 100 if iv is not None else None,
                              "greeks": {k: _number(v) for k, v in (row.get("greeks") or {}).items()},
                              "bid": _number(q.get("bp")), "ask": _number(q.get("ap")),
                              "last_trade": _number(t.get("p")), "as_of": q.get("t") or t.get("t")})
        if not contracts:
            return {}
        contracts.sort(key=lambda row: (row["expiry"], abs(row["strike"] - spot) if spot else row["strike"]))
        nearest = next((row for row in contracts if row["expiry"] == contracts[0]["expiry"] and row["implied_volatility_pct"] is not None), None)
        return {"source": "alpaca_" + self.options_feed, "feed": self.options_feed,
                "source_url": "https://data.alpaca.markets/v1beta1/options/snapshots/" + symbol,
                "scope": "bounded_near_term_chain_snapshot", "expiry": contracts[0]["expiry"],
                "sample_contract_count": len(contracts), "contracts": contracts[:24], "truncated": truncated,
                "nearest_atm_implied_volatility_pct": nearest["implied_volatility_pct"] if nearest else None,
                "as_of": max((row["as_of"] for row in contracts if row["as_of"]), default=None),
                "quality_flags": ["indicative_prices_not_opra"] if self.options_feed == "indicative" else []}

    def corporate_actions(self, symbol):
        symbol, today = self.symbol(symbol), _now().date()
        params = {"symbols": symbol, "start": (today - timedelta(days=365)).isoformat(),
                  "end": today.isoformat(), "sort": "desc", "limit": 1000}
        payload = self.request("/v1/corporate-actions", params, ttl=21600)
        result = []
        for kind, rows in (payload.get("corporate_actions") or {}).items():
            for row in rows:
                result.append({**row, "action_type": kind, "source": "alpaca_corporate_actions",
                               "as_of": row.get("process_date") or today.isoformat(),
                               "source_url": "https://data.alpaca.markets/v1/corporate-actions"})
        return result[:30]

    def security_profile(self, symbol):
        symbol = self.symbol(symbol)
        payload = self.request("/v2/assets/" + quote(symbol, safe=""), ttl=86400, trading=True)
        return {key: payload.get(key) for key in
                ("symbol", "name", "exchange", "class", "status", "tradable", "fractionable", "shortable")}
