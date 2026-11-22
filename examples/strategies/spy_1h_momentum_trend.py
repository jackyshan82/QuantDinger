"""SPY 1h Momentum Trend
Long-only intraday strategy on SPY using 1-hour completed bars.
Entry: price closes above EMA-fast AND EMA-fast > EMA-slow (trend confirmed).
       Only enter during first half of session (before 13:00 ET).
Exit:  price closes below EMA-fast, OR mandatory EOD flat at 15:30 ET.
One position at a time; stop-loss at entry minus ATR multiple.
Low turnover to keep commission drag minimal.
"""
# @param ema_fast int 8 Fast EMA period values=5,8,13
# @param ema_slow int 21 Slow EMA period values=13,21,34
# @param atr_period int 14 ATR period for stop values=10,14
# @param atr_stop float 1.5 Stop distance in ATR multiples values=1.0,1.5,2.0
# @param target_pct float 0.95 Maximum long portfolio weight values=0.75,0.95

import pandas as pd

PERSIST_RUNTIME_STATE = True

RTH_OPEN_MINUTE = 570   # 09:30 ET
EOD_FLAT_MINUTE = 930   # 15:30 ET
NO_ENTRY_MINUTE = 780   # 13:00 ET — only enter in morning session


def initialize(context):
    g.symbol = "USStock:SPY"
    g.day = ""
    g.stop_price = 0.0
    context.set_universe([g.symbol])
    context.subscribe(frequency="1h", fields=["open", "high", "low", "close", "volume"])
    context.set_warmup(50)
    context.set_benchmark(g.symbol)
    context.set_metadata(
        direction_mode="long_only",
        timezone="America/New_York",
        bar_labels="UTC_open",
        execution="next_bar_open",
        required_session_exit="15:30 America/New_York",
    )


def _local_time(ts_utc):
    ts = pd.Timestamp(ts_utc)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    local = ts.tz_convert("America/New_York")
    return local.hour * 60 + local.minute, str(local.date()), local.weekday()


def _ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def _atr(bars, period):
    high = bars["high"]
    low = bars["low"]
    prev_close = bars["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def handle_data(context, data):
    minute, today, weekday = _local_time(context.current_dt)

    if weekday >= 5:
        return

    # New day: enforce no overnight, reset stop
    if g.day != today:
        position = get_position(g.symbol)
        if float(position.amount or 0.0) != 0.0:
            order_target_percent(g.symbol, 0.0, reason="overnight_safety_flat")
            return
        g.day = today
        g.stop_price = 0.0

    # --- Parameters ---
    fast   = int(context.params.get("ema_fast", 8))
    slow   = int(context.params.get("ema_slow", 21))
    atr_p  = int(context.params.get("atr_period", 14))
    atr_sl = float(context.params.get("atr_stop", 1.5))
    tgt    = float(context.params.get("target_pct", 0.95))

    # --- Load hourly bars ---
    bars = get_history(60, "1h", ["open", "high", "low", "close", "volume"], g.symbol)
    if len(bars) < slow + 2:
        return

    close = bars["close"]
    ema_f = _ema(close, fast)
    ema_s = _ema(close, slow)
    atr   = _atr(bars, atr_p)

    # All signals from the last fully completed bar (iloc[-2] relative to current)
    ef_prev = float(ema_f.iloc[-2])
    es_prev = float(ema_s.iloc[-2])
    cl_prev = float(close.iloc[-2])
    atr_val = float(atr.iloc[-2])

    trend_up   = ef_prev > es_prev
    price_above_ema = cl_prev > ef_prev

    position = get_position(g.symbol)
    held = float(position.amount or 0.0) > 0.0

    # --- EOD flat ---
    if minute >= EOD_FLAT_MINUTE:
        if held:
            order_target_percent(g.symbol, 0.0, reason="eod_flat")
        return

    # --- Manage open position ---
    if held:
        # Exit when price drops below fast EMA or stop is hit
        if cl_prev < ef_prev:
            order_target_percent(g.symbol, 0.0, reason="ema_exit")
        elif atr_val > 0 and cl_prev <= g.stop_price:
            order_target_percent(g.symbol, 0.0, reason="atr_stop")
        return

    # --- Entry: trend confirmed, morning session only ---
    if minute >= NO_ENTRY_MINUTE or minute < RTH_OPEN_MINUTE:
        return

    if trend_up and price_above_ema:
        g.stop_price = cl_prev - atr_sl * atr_val
        order_target_percent(g.symbol, tgt, reason="momentum_long_entry")
