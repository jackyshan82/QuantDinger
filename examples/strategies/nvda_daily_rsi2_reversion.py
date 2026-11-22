"""NVDA Daily RSI2 Reversion - Research
Long-only, completed daily bars; queued orders fill next bar open.
Rule selected on training/validation periods, with a separate final holdout.
"""
# @param target_pct float 0.95 Maximum long portfolio weight

def initialize(context):
    g.symbol = "USStock:NVDA"
    context.set_universe([g.symbol])
    context.subscribe(frequency="1d", fields=["open", "high", "low", "close", "volume"])
    context.set_warmup(250)
    context.set_benchmark(g.symbol)

def handle_data(context, data):
    bars = get_history(260, "1d", ["open", "high", "low", "close", "volume"], g.symbol)
    if len(bars) < 201:
        return
    close = bars["close"]
    price = float(close.iloc[-1])
    sma5 = float(close.tail(5).mean())
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    up = float(gain.iloc[-1])
    down = float(loss.iloc[-1])
    rsi2 = 50.0 if up == 0 and down == 0 else (100.0 if down == 0 else 100 - 100 / (1 + up / down))
    entry = rsi2 < 10
    exit_signal = price > sma5
    position = get_position(g.symbol)
    target = min(0.95, max(0.0, float(context.params.get("target_pct", 0.95))))
    if position.amount <= 0 and entry and target > 0:
        order_target_percent(g.symbol, target, reason="rsi2_reversion_entry")
    elif position.amount > 0 and exit_signal:
        order_target_percent(g.symbol, 0.0, reason="rsi2_reversion_exit")
