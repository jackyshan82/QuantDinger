"""NVDA 15m Morning Reversion - Native Research
Long-only research candidate with regular-session RSI pullback entries.
Enter only 10:00-11:00 New York; request flat from 12:00 using next-bar fills.
The conservative noon exit also precedes normal 13:00 early closes.
No guarantee of fills when bars or market liquidity are missing; inspect overnight audits.
"""
# @param rsi_period int 2 RSI calculation period range=2:4:2
# @param entry_rsi float 10 RSI oversold entry threshold range=10:20:10
# @param exit_period int 3 Exit SMA lookback range=3:5:2
# @param target_pct float 0.95 Maximum long portfolio weight


def initialize(context):
    g.symbol = "USStock:NVDA"
    context.set_universe([g.symbol])
    context.subscribe(frequency="15m", fields=["open", "high", "low", "close", "volume"])
    context.set_warmup(80)
    context.set_benchmark(g.symbol)


def handle_data(context, data):
    timestamp = pd.Timestamp(context.current_dt)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    local_time = timestamp.tz_convert("America/New_York")
    minute = local_time.hour * 60 + local_time.minute
    position = get_position(g.symbol)
    # On liquid regular-session data this queues an exit at 12:15, well before
    # both full-day and half-day closes. The backtest must audit same-day fills.
    if position.amount > 0 and minute >= 720:
        order_target_percent(g.symbol, 0.0, reason="intraday_noon_exit")
        return
    if minute < 570 or minute >= 960:
        return

    bars = get_history(400, "15m", ["open", "high", "low", "close", "volume"], g.symbol)
    local_index = bars.index.tz_localize("UTC").tz_convert("America/New_York")
    minute_index = local_index.hour * 60 + local_index.minute
    bars = bars.loc[(minute_index >= 570) & (minute_index < 960)]
    period = max(2, int(context.params.get("rsi_period", 2)))
    threshold = float(context.params.get("entry_rsi", 10))
    exit_period = max(2, int(context.params.get("exit_period", 3)))
    if len(bars) < max(period * 5, exit_period) + 2:
        return
    close = bars["close"]
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1.0 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1.0 / period, adjust=False).mean()
    up = float(gain.iloc[-1])
    down = float(loss.iloc[-1])
    rsi = 50.0 if up == 0 and down == 0 else (100.0 if down == 0 else 100 - 100 / (1 + up / down))
    average = float(close.tail(exit_period).mean())
    target = min(0.95, max(0.0, float(context.params.get("target_pct", 0.95))))
    if position.amount > 0 and float(close.iloc[-1]) > average:
        order_target_percent(g.symbol, 0.0, reason="intraday_reversion_exit")
    elif position.amount <= 0 and 600 <= minute < 660 and rsi < threshold and target > 0:
        order_target_percent(g.symbol, target, reason="intraday_rsi_entry")
