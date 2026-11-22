"""Tenant-scoped Alpaca price history for research, without trading API calls."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from app.data_sources.errors import MarketDataFailure, MarketDataUnavailableError
from app.services.backtest_cache import KlineCache
from app.utils.credential_crypto import decrypt_credential_blob
from app.utils.db import get_db_connection

class AlpacaHistoryError(ValueError):
    """A configured provider must fail explicitly rather than change data origin."""


_cache = KlineCache()
_TIMEFRAMES = {
    "1m": "1Min", "3m": "3Min", "5m": "5Min", "15m": "15Min",
    "30m": "30Min", "1h": "1Hour", "4h": "4Hour", "1d": "1Day", "1w": "1Week",
}


def stock_backtest_provider() -> str:
    provider = os.getenv("US_STOCK_BACKTEST_PROVIDER", "yfinance").strip().lower()
    if provider not in {"yfinance", "alpaca"}:
        raise AlpacaHistoryError("US_STOCK_BACKTEST_PROVIDER must be yfinance or alpaca")
    return provider


def _owned_credentials(user_id: int) -> tuple[int, dict]:
    if not user_id or int(user_id) <= 0:
        raise AlpacaHistoryError("brokerAccounts.accountUnavailable")
    with get_db_connection() as db:
        cur = db.cursor()
        try:
            cur.execute(
                "SELECT id, encrypted_config FROM qd_exchange_credentials "
                "WHERE user_id = %s AND exchange_id = 'alpaca' ORDER BY id",
                (int(user_id),),
            )
            rows = cur.fetchall() or []
        finally:
            cur.close()
    if not rows:
        raise AlpacaHistoryError("brokerAccounts.accountUnavailable")
    if len(rows) != 1:
        raise AlpacaHistoryError("brokerAccounts.accountSelectionRequired")
    try:
        config = json.loads(decrypt_credential_blob(rows[0]["encrypted_config"]))
        if not config.get("api_key") or not config.get("secret_key"):
            raise AlpacaHistoryError("missing credentials")
    except Exception:
        raise AlpacaHistoryError("brokerAccounts.accountUnavailable") from None
    return int(rows[0]["id"]), config


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def load_alpaca_frame(user_id: int, symbol: str, timeframe: str,
                      start_date: datetime, end_date: datetime, *, live: bool = False) -> pd.DataFrame:
    """Fetch every page; never substitute a different account, feed or provider."""
    frequency = str(timeframe).lower()
    if frequency not in _TIMEFRAMES:
        raise AlpacaHistoryError("strategyV2.unsupportedFrequency")
    feed = os.getenv("ALPACA_BACKTEST_FEED", "iex").strip().lower()
    if feed not in {"iex", "sip"}:
        raise AlpacaHistoryError("ALPACA_BACKTEST_FEED must be iex or sip")
    credential_id, config = _owned_credentials(user_id)
    start, end = _utc(start_date), _utc(end_date)
    # Historical research does not need the latest 15 minutes. Excluding them
    # also permits delayed SIP history with Basic market-data entitlements.
    delay = timedelta() if live else timedelta(minutes=15)
    end = min(end, datetime.now(timezone.utc) - delay)
    if start < datetime(2016, 1, 1, tzinfo=timezone.utc):
        raise AlpacaHistoryError("Alpaca historical stock data begins in 2016")
    if end <= start:
        raise AlpacaHistoryError("strategyV2.invalidDateRange")
    symbol = str(symbol).strip().upper().replace("/", ".")
    key = f"alpaca:v1:{int(user_id)}:{credential_id}:{feed}:all:{symbol}:{frequency}:{start.isoformat()}:{end.isoformat()}"
    if live:
        key = "live:" + key
    cached = _cache.get(key)
    if cached is not None:
        cached.attrs.update(provider="alpaca", feed=feed, adjustment="all")
        return cached
    params = {"symbols": symbol, "timeframe": _TIMEFRAMES[frequency],
              "start": start.isoformat(), "end": end.isoformat(), "limit": 10000,
              "feed": feed, "adjustment": "all", "sort": "asc"}
    rows, tokens = [], set()
    with requests.Session() as session:
        session.headers.update({"APCA-API-KEY-ID": config["api_key"],
                                "APCA-API-SECRET-KEY": config["secret_key"]})
        while True:
            for attempt in range(2):
                try:
                    response = session.get("https://data.alpaca.markets/v2/stocks/bars",
                                           params=params, timeout=(3, 8) if live else (10, 60))
                    break
                except requests.RequestException as exc:
                    if attempt == 1:
                        detail = "Alpaca historical data request failed (" + type(exc).__name__ + ")"
                        if live:
                            # Use the existing runtime data-outage path: skip
                            # evaluation without consuming strategy-error budget.
                            raise MarketDataUnavailableError(MarketDataFailure(
                                code="exchange_unavailable",
                                message="The Alpaca market-data service is temporarily unreachable.",
                                technical_detail=detail,
                                exchange_id="alpaca", market_type="spot",
                                symbol=symbol, timeframe=frequency, retryable=True,
                            )) from None
                        raise AlpacaHistoryError(
                            detail
                        ) from None
                    # Retrying a read is safe; never reuse this policy for orders.
                    time.sleep(0.25)
            if response.status_code != 200:
                # Do not include provider bodies or request headers in errors.
                if live and (response.status_code == 429 or 500 <= response.status_code <= 599):
                    limited = response.status_code == 429
                    raise MarketDataUnavailableError(MarketDataFailure(
                        code="rate_limited" if limited else "exchange_unavailable",
                        message="Alpaca market data is temporarily unavailable and will be retried.",
                        technical_detail=f"Alpaca historical data HTTP {response.status_code} (feed={feed})",
                        exchange_id="alpaca", market_type="spot",
                        symbol=symbol, timeframe=frequency, retryable=True,
                    ))
                raise AlpacaHistoryError(f"Alpaca historical data HTTP {response.status_code} (feed={feed})")
            payload = response.json()
            rows.extend((payload.get("bars") or {}).get(symbol) or [])
            token = payload.get("next_page_token")
            if not token:
                break
            if token in tokens:
                raise AlpacaHistoryError("Alpaca historical data pagination did not advance")
            tokens.add(token)
            params["page_token"] = token
    if not rows:
        raise AlpacaHistoryError("strategyV2.noMarketData")
    frame = pd.DataFrame(rows).rename(columns={"o": "open", "h": "high", "l": "low",
                                               "c": "close", "v": "volume"})
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop("t"), utc=True)).tz_convert(None)
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame[["open", "high", "low", "close", "volume"]].dropna()
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    frame = frame.loc[(frame.index >= pd.Timestamp(start).tz_convert(None)) &
                      (frame.index <= pd.Timestamp(end).tz_convert(None))]
    # Remove an open/incomplete bar, including daily and weekly candles.
    now = pd.Timestamp(end).tz_convert(None)
    duration = pd.Timedelta({"1d": "1D", "1w": "7D"}.get(frequency, frequency))
    if frequency == "1d":
        # Daily labels are midnight New York; the regular session closes at
        # 16:00 local time (early closes are conservatively excluded until 16:00).
        local_days = frame.index.tz_localize("UTC").tz_convert("America/New_York").normalize()
        closes = (local_days + pd.Timedelta(hours=16)).tz_convert("UTC").tz_localize(None)
        frame = frame.loc[closes <= now]
    else:
        frame = frame.loc[frame.index + duration <= now]
    if frame.empty:
        raise AlpacaHistoryError("strategyV2.noMarketData")
    frame.attrs.update(provider="alpaca", feed=feed, adjustment="all")
    _cache.put(key, frame, frequency)
    return frame.copy()
