"""SPY 1h First-Hour Momentum
Long-only intraday strategy on SPY using 1-hour completed bars.
Signal: enter long when first RTH hour (09:30-10:30) closes up strongly.
Exit:   take-profit at entry + tp_r * first-hour range, OR
        stop-loss at entry - sl_r * first-hour range, OR
        mandatory EOD flat at 15:00 ET.
One trade per session. Few trades, low commission drag.
Based on: first-hour strong momentum has ~72% intraday follow-through on SPY.
"""
# @param min_first_hour_pct float 0.30 Min first-hour gain to enter (percent) values=0.20,0.30,0.40
# @param tp_r float 1.5 Take-profit as multiple of first-hour range values=1.0,1.5,2.0
# @param sl_r float 0.8 Stop-loss as multiple of first-hour range values=0.5,0.8,1.0
# @param target_pct float 0.95 Maximum long portfolio weight values=0.75,0.95

import pandas as pd

PERSIST_RUNTIME_STATE = True

RTH_OPEN_MINUTE = 570   # 09:30 ET
EOD_FLAT_MINUTE = 900   # 15:00 ET


def initialize(context):
    g.symbol = "USStock:SPY"
    g.day = ""
    g.attempted = False
    g.stop_price  = 0.0
    g.tp_price    = 0.0
    context.set_universe([g.symbol])
    context.subscribe(frequency="1h", fields=["open", "high", "low", "close", "volume"])
    context.set_warmup(10)
    context.set_benchmark(g.symbol)
    context.set_metadata(
        direction_mode="long_only",
        timezone="America/New_York",
        bar_labels="UTC_open",
        execution="next_bar_open",
        required_session_exit="15:00 America/New_York",
    )


def _local_time(ts_utc):
    ts = pd.Timestamp(ts_utc)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    local = ts.tz_convert("America/New_York")
    return local.hour * 60 + local.minute, str(local.date()), local.weekday()


def handle_data(context, data):
    minute, today, weekday = _local_time(context.current_dt)

    if weekday >= 5 or minute < RTH_OPEN_MINUTE:
        return

    # New session: reset
    if g.day != today:
        position = get_position(g.symbol)
        if float(position.amount or 0.0) != 0.0:
            order_target_percent(g.symbol, 0.0, reason="overnight_safety_flat")
            return
        g.day = today
        g.attempted = False
        g.stop_price = 0.0
        g.tp_price   = 0.0

    # --- Parameters ---
    min_pct    = float(context.params.get("min_first_hour_pct", 0.30)) / 100.0
    tp_r       = float(context.params.get("tp_r", 1.5))
    sl_r       = float(context.params.get("sl_r", 0.8))
    target_pct = float(context.params.get("target_pct", 0.95))

    # --- Load hourly bars ---
    bars = get_history(20, "1h", ["open", "high", "low", "close", "volume"], g.symbol)
    if len(bars) < 2:
        return

    local_idx   = pd.to_datetime(bars.index, utc=True).tz_convert("America/New_York")
    bar_dates   = local_idx.normalize().strftime("%Y-%m-%d")
    bar_minutes = local_idx.hour * 60 + local_idx.minute

    position = get_position(g.symbol)
    held = float(position.amount or 0.0) > 0.0

    # --- Mandatory EOD flat ---
    if minute >= EOD_FLAT_MINUTE:
        if held:
            order_target_percent(g.symbol, 0.0, reason="eod_flat")
        return

    # --- Manage open position: fixed TP/SL based on first-hour range ---
    if held:
        cur_high = float(bars["high"].iloc[-1])
        cur_low  = float(bars["low"].iloc[-1])
        if cur_low <= g.stop_price:
            order_target_percent(g.symbol, 0.0, reason="range_stop_loss")
        elif cur_high >= g.tp_price:
            order_target_percent(g.symbol, 0.0, reason="range_take_profit")
        return

    # --- Entry: once per session, after first hour completes ---
    if g.attempted:
        return

    # bar_labels = UTC_open: the 09:30 ET bar has minute=570 in ET.
    # handle_data fires when a bar COMPLETES. The 09:30 bar (first RTH hour)
    # closes at 10:30 ET, so handle_data runs when current_dt labels the
    # 10:30 bar (minute=630). The completed 09:30 bar is bars.iloc[-2].
    # We look for it by scanning today's bars for minute==RTH_OPEN_MINUTE.
    today_rth = bars.loc[(bar_dates == today) & (bar_minutes >= RTH_OPEN_MINUTE)]
    if len(today_rth) < 2:
        # First hour not yet complete (only 1 bar visible today)
        return

    # The first completed RTH bar is today_rth.iloc[0] (label 09:30 = 570)
    first_bar   = today_rth.iloc[0]
    first_open  = float(first_bar["open"])
    first_close = float(first_bar["close"])
    first_high  = float(first_bar["high"])
    first_low   = float(first_bar["low"])

    if first_open <= 0:
        return

    first_ret   = (first_close - first_open) / first_open
    first_range = first_high - first_low

    # Only enter on strong up first hour with non-trivial range
    if first_ret < min_pct or first_range <= 0:
        return

    # Entry fills at the second RTH bar start; set TP/SL from first-hour range
    entry_approx  = first_close
    g.tp_price    = entry_approx + tp_r * first_range
    g.stop_price  = entry_approx - sl_r * first_range
    g.attempted   = True
    order_target_percent(g.symbol, target_pct, reason="first_hour_momentum_entry")
