"""SPY 1m VWAP Mean Reversion
Long-only intraday strategy on SPY using 1-minute completed bars.
Entry: price drops N ticks below session VWAP -> expect reversion up.
Exit: price returns to VWAP, or fixed stop, or mandatory EOD flat.
Adapted from spagnola-analytics/intraday-strategies vwap_mr strategy.
Same-day exit required; no overnight positions. At most one entry per session.
"""
# @param entry_ticks int 20 Ticks below VWAP to trigger entry values=10,15,20,25,30
# @param sl_ticks int 16 Fixed stop-loss in ticks values=8,12,16,20,24
# @param min_bars_from_open int 30 Skip first N bars after RTH start for VWAP stabilisation values=15,20,30
# @param target_pct float 0.95 Maximum long portfolio weight values=0.5,0.75,0.95

import pandas as pd

PERSIST_RUNTIME_STATE = True

TICK = 0.01           # SPY tick size $0.01
EOD_FLAT_MINUTE = 950  # 15:50 ET — mandatory flat
NO_ENTRY_MINUTE = 870  # 14:30 ET — no new entries after this
RTH_OPEN_MINUTE = 570  # 09:30 ET


def initialize(context):
    g.symbol = "USStock:SPY"
    g.day = ""
    g.attempted = False   # only one entry attempt per session
    g.stop_price = 0.0
    context.set_universe([g.symbol])
    context.subscribe(frequency="1m", fields=["open", "high", "low", "close", "volume"])
    context.set_warmup(60)
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

    # Outside RTH or weekend
    if weekday >= 5 or minute < RTH_OPEN_MINUTE or minute >= EOD_FLAT_MINUTE + 10:
        return

    # New session: reset state, verify no overnight position
    if g.day != today:
        position = get_position(g.symbol)
        if float(position.amount or 0.0) != 0.0:
            order_target_percent(g.symbol, 0.0, reason="overnight_safety_flat")
            return
        g.day = today
        g.attempted = False
        g.stop_price = 0.0

    # --- Parameters ---
    entry_ticks = int(context.params.get("entry_ticks", 20))
    sl_ticks    = int(context.params.get("sl_ticks", 16))
    min_bars    = int(context.params.get("min_bars_from_open", 30))
    target_pct  = float(context.params.get("target_pct", 0.95))

    # --- Load today's RTH bars ---
    bars = get_history(390, "1m", ["open", "high", "low", "close", "volume"], g.symbol)
    if len(bars) < 2:
        return

    local_idx = pd.to_datetime(bars.index, utc=True).tz_convert("America/New_York")
    today_mask = (
        (local_idx.normalize().strftime("%Y-%m-%d") == today)
        & ((local_idx.hour * 60 + local_idx.minute) >= RTH_OPEN_MINUTE)
    )
    today_bars = bars.loc[today_mask].copy()
    if len(today_bars) < 2:
        return

    # Session VWAP — cumulative from RTH open, no lookahead (use bars[:-1])
    tp  = (today_bars["high"] + today_bars["low"] + today_bars["close"]) / 3.0
    vol = today_bars["volume"].astype(float)
    cum_vol = vol.cumsum().where(vol.cumsum() > 0, other=float("nan"))
    vwap_series = (tp * vol).cumsum() / cum_vol

    # All signals use the second-to-last completed bar (prev bar, fully known)
    prev_close = float(today_bars["close"].iloc[-2])
    prev_vwap  = float(vwap_series.iloc[-2])
    cur_low    = float(today_bars["low"].iloc[-1])
    cur_high   = float(today_bars["high"].iloc[-1])
    cur_vwap   = float(vwap_series.iloc[-1])

    position = get_position(g.symbol)
    held = float(position.amount or 0.0) > 0.0

    # --- Mandatory EOD flat ---
    if minute >= EOD_FLAT_MINUTE:
        if held:
            order_target_percent(g.symbol, 0.0, reason="eod_mandatory_flat")
        return

    # --- Manage existing position ---
    if held:
        # Stop: low of current bar touches stop level
        if cur_low <= g.stop_price:
            order_target_percent(g.symbol, 0.0, reason="vwap_mr_stop_loss")
        # Take-profit: high of current bar reaches VWAP (dynamic target)
        elif cur_high >= cur_vwap:
            order_target_percent(g.symbol, 0.0, reason="vwap_mr_take_profit")
        return

    # --- Entry: one per session, after VWAP stabilises, before cutoff ---
    if g.attempted or minute >= NO_ENTRY_MINUTE or len(today_bars) <= min_bars:
        return

    dist_ticks = (prev_close - prev_vwap) / TICK
    if dist_ticks <= -entry_ticks:
        # Price far below VWAP — expect mean reversion up
        g.attempted = True
        g.stop_price = prev_close - sl_ticks * TICK
        order_target_percent(g.symbol, target_pct, reason="vwap_mr_long_entry")
