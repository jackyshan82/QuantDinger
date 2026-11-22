"""NVDA 5m TD9 Intraday Reversion - Research
Simplified nine-count setup, optional perfection and one-bar rebound confirmation.
Research only: frozen May-October 2026 calendar, regular sessions, next-bar orders.
This implements the nine-count hypothesis, not the full TD Sequential countdown.
"""

# @param perfected_only int 0 Require perfected buy setup range=0:1:1
# @param confirm_rebound int 0 Require immediate bullish confirmation range=0:1:1
# @param max_hold_bars int 6 Maximum completed bars held before exit request range=6:12:6


def initialize(context):
    g.symbol = "USStock:NVDA"
    context.set_universe([g.symbol])
    context.subscribe(frequency="5m", fields=["open", "high", "low", "close", "volume"])
    context.set_benchmark(g.symbol)
    context.set_metadata(direction_mode="long_only")
    context.set_warmup(20)
    g.session = ""
    g.rows = []
    g.down_count = 0
    g.up_count = 0
    g.bar_number = 0
    g.setup_bar = -1
    g.entry_bar = -1
    g.entry_attempts = 0
    g.was_in_position = False
    g.last_bar = ""
    # XNYS calendar has no early closes in the frozen May-October 2026 interval.
    # Refresh this published calendar before using this source for other dates.
    g.early_close_dates = []


def handle_data(context, data):
    timestamp = pd.Timestamp(context.current_dt)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    local = timestamp.tz_convert("America/New_York")
    session = local.strftime("%Y-%m-%d")
    minute = local.hour * 60 + local.minute
    position = get_position(g.symbol)
    flat_at = 765 if session in g.early_close_dates else 945
    entry_until = 720 if session in g.early_close_dates else 900
    if position.amount > 0 and minute >= flat_at:
        order_target_percent(g.symbol, 0.0, reason="td9_session_flat")
        return
    if minute < 570 or minute >= 960:
        return
    bar_key = str(timestamp)
    if bar_key == g.last_bar:
        return
    g.last_bar = bar_key
    if session != g.session:
        g.session = session
        g.rows = []
        g.down_count = 0
        g.up_count = 0
        g.bar_number = 0
        g.setup_bar = -1
        g.entry_bar = -1
        g.entry_attempts = 0
        g.was_in_position = False
        if position.amount > 0:
            order_target_percent(g.symbol, 0.0, reason="td9_overnight_recovery")
            return

    bars = get_history(1, "5m", ["open", "high", "low", "close", "volume"], g.symbol)
    if bars.empty:
        return
    last = bars.iloc[-1]
    row = [float(last["open"]), float(last["high"]), float(last["low"]), float(last["close"])]
    g.rows.append(row)
    g.rows = g.rows[-100:]
    g.bar_number += 1
    if len(g.rows) >= 5:
        reference = g.rows[-5][3]
        g.down_count = g.down_count + 1 if row[3] < reference else 0
        g.up_count = g.up_count + 1 if row[3] > reference else 0
    else:
        g.down_count = 0
        g.up_count = 0

    if position.amount > 0:
        if not g.was_in_position:
            g.entry_bar = g.bar_number
        g.was_in_position = True
        hold = max(1, int(context.params.get("max_hold_bars", 6)))
        if g.up_count == 9:
            order_target_percent(g.symbol, 0.0, reason="td9_opposite_setup_exit")
        elif g.bar_number - g.entry_bar >= hold:
            order_target_percent(g.symbol, 0.0, reason="td9_time_exit")
        return
    g.was_in_position = False
    g.entry_bar = -1
    if minute >= entry_until or g.entry_attempts >= 3:
        g.setup_bar = -1
        return

    confirmation = int(context.params.get("confirm_rebound", 0)) > 0
    entry = False
    if confirmation and g.setup_bar == g.bar_number - 1:
        entry = row[3] > row[0] and row[3] > g.rows[-2][3]
        g.setup_bar = -1
    if g.down_count == 9:
        perfected = min(g.rows[-2][2], g.rows[-1][2]) <= min(g.rows[-4][2], g.rows[-3][2])
        qualified = int(context.params.get("perfected_only", 0)) <= 0 or perfected
        if qualified:
            if confirmation:
                g.setup_bar = g.bar_number
            else:
                entry = True
    if entry:
        g.entry_attempts += 1
        order_target_percent(
            g.symbol,
            0.95,
            reason="td9_confirmed_entry" if confirmation else "td9_raw_entry",
            stop_loss_pct=0.01,
            take_profit_pct=0.015,
        )
