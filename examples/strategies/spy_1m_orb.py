"""SPY 1m Opening Range Breakout (ORB)
Long-only intraday strategy on SPY using 1-minute completed bars.
Opening range = first N minutes of RTH (9:30 ET).
Entry: first bar close above OR high + buffer triggers a long.
Stop: OR low. Target: OR-width R-multiple above entry.
Optional prev-day trend filter: only enter when prev close > OR open.
One trade per session. Mandatory EOD flat before 15:50 ET.
Adapted from spagnola-analytics/intraday-strategies orb strategy.
"""
# @param or_minutes int 15 Opening range duration in minutes values=15,30
# @param breakout_buffer_ticks int 0 Extra ticks above OR high values=0,2,4
# @param tp_r float 2.0 Take-profit as multiple of OR-width risk values=1.0,1.5,2.0,3.0
# @param trend_filter bool false Only enter when prev-day close > RTH open values=true,false
# @param target_pct float 0.95 Maximum long portfolio weight values=0.5,0.75,0.95

import pandas as pd

PERSIST_RUNTIME_STATE = True

TICK = 0.01
RTH_OPEN_MINUTE = 570   # 09:30 ET
EOD_FLAT_MINUTE = 950   # 15:50 ET
NO_ENTRY_MINUTE = 900   # 15:00 ET — no new entries after this


def initialize(context):
    g.symbol = "USStock:SPY"
    g.day = ""
    g.or_high = 0.0
    g.or_low = 0.0
    g.or_complete = False
    g.attempted = False
    g.stop_price = 0.0
    g.tp_price = 0.0
    g.prev_day_close = 0.0
    context.set_universe([g.symbol])
    context.subscribe(frequency="1m", fields=["open", "high", "low", "close", "volume"])
    context.set_warmup(780)  # ~13 hours to cover prev-day close
    context.set_benchmark(g.symbol)
    context.set_metadata(
        direction_mode="long_only",
        timezone="America/New_York",
        bar_labels="UTC_open",
        execution="next_bar_open",
        required_session_exit="15:50 America/New_York",
    )


def _local_time(ts_utc):
    ts = pd.Timestamp(ts_utc)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    local = ts.tz_convert("America/New_York")
    return local.hour * 60 + local.minute, str(local.date()), local.weekday()


def handle_data(context, data):
    minute, today, weekday = _local_time(context.current_dt)

    if weekday >= 5 or minute < RTH_OPEN_MINUTE or minute >= EOD_FLAT_MINUTE + 10:
        return

    # --- Parameters ---
    or_minutes  = int(context.params.get("or_minutes", 15))
    buf_ticks   = int(context.params.get("breakout_buffer_ticks", 0))
    tp_r        = float(context.params.get("tp_r", 2.0))
    use_trend   = str(context.params.get("trend_filter", "false")).lower() == "true"
    target_pct  = float(context.params.get("target_pct", 0.95))

    # --- Load bars ---
    bars = get_history(780, "1m", ["open", "high", "low", "close", "volume"], g.symbol)
    if len(bars) < 2:
        return

    local_idx = pd.to_datetime(bars.index, utc=True).tz_convert("America/New_York")
    bar_dates = local_idx.normalize().strftime("%Y-%m-%d")
    bar_minutes = local_idx.hour * 60 + local_idx.minute

    # New session: reset state + capture prev-day close
    if g.day != today:
        position = get_position(g.symbol)
        if float(position.amount or 0.0) != 0.0:
            order_target_percent(g.symbol, 0.0, reason="overnight_safety_flat")
            return
        g.day = today
        g.or_high = 0.0
        g.or_low = 0.0
        g.or_complete = False
        g.attempted = False
        g.stop_price = 0.0
        g.tp_price = 0.0
        # Prev-day close: last bar of the previous calendar date
        prev_mask = bar_dates != today
        if prev_mask.any():
            g.prev_day_close = float(bars.loc[prev_mask, "close"].iloc[-1])

    # Today's RTH bars
    today_mask = (bar_dates == today) & (bar_minutes >= RTH_OPEN_MINUTE)
    today_bars = bars.loc[today_mask].copy()
    today_minutes = bar_minutes[today_mask].values
    if len(today_bars) < 2:
        return

    rth_open = float(today_bars["open"].iloc[0])

    # Build Opening Range from completed bars inside the OR window
    or_mask = today_minutes < (RTH_OPEN_MINUTE + or_minutes)
    or_bars = today_bars.loc[or_mask]
    after_or = today_bars.loc[~or_mask]

    if len(or_bars) > 0:
        g.or_high = float(or_bars["high"].max())
        g.or_low  = float(or_bars["low"].min())

    if len(after_or) > 0:
        g.or_complete = True

    if not g.or_complete or g.or_high <= g.or_low:
        return

    position = get_position(g.symbol)
    held = float(position.amount or 0.0) > 0.0

    # --- Mandatory EOD flat ---
    if minute >= EOD_FLAT_MINUTE:
        if held:
            order_target_percent(g.symbol, 0.0, reason="eod_mandatory_flat")
        return

    # --- Manage existing position ---
    if held:
        cur_low  = float(today_bars["low"].iloc[-1])
        cur_high = float(today_bars["high"].iloc[-1])
        if cur_low <= g.stop_price:
            order_target_percent(g.symbol, 0.0, reason="orb_stop_loss")
        elif cur_high >= g.tp_price:
            order_target_percent(g.symbol, 0.0, reason="orb_take_profit")
        return

    # --- Entry signal: one per session, before cutoff ---
    if g.attempted or minute >= NO_ENTRY_MINUTE:
        return

    # Trend filter: only enter when prev-day close > today's RTH open
    if use_trend and g.prev_day_close > 0.0:
        if g.prev_day_close <= rth_open:
            return

    # Use second-to-last completed bar close (no lookahead)
    prev_close = float(today_bars["close"].iloc[-2])
    breakout_level = g.or_high + buf_ticks * TICK

    if prev_close > breakout_level:
        or_width = g.or_high - g.or_low
        if or_width <= 0:
            return
        entry_approx = breakout_level
        sl_price = g.or_low
        tp_price = entry_approx + tp_r * or_width
        if entry_approx <= sl_price:
            return
        g.attempted = True
        g.stop_price = sl_price
        g.tp_price = tp_price
        order_target_percent(g.symbol, target_pct, reason="orb_breakout_long_entry")
