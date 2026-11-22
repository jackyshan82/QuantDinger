# @param rsi_period int 14 Wilder RSI period
# @param rsi_oversold float 35 RSI bullish vote below this level
# @param rsi_overbought float 65 RSI bearish vote above this level
# @param macd_fast int 12 MACD fast EMA period
# @param macd_slow int 26 MACD slow EMA period
# @param macd_signal int 9 MACD signal EMA period
# @param trend_period int 20 Trend SMA period
# @param min_confirmations int 2 Required directional votes out of three
# @param volume_period int 20 Prior volume average period
# @param volume_multiplier float 0.8 Minimum relative volume
# @param use_volume_filter bool true Require volume confirmation
# @param atr_period int 14 Wilder ATR period
# @param atr_min_pct float 0.0 Minimum ATR percent
# @param atr_max_pct float 5.0 Maximum ATR percent
# @param use_atr_filter bool true Require ATR within bounds

my_indicator_name = "US Stock Composite Buy Sell"
my_indicator_description = "RSI, standard MACD and SMA vote on direction; volume and ATR filter events. Two votes required by default. Signals use the preceding closed bar and appear once when a condition becomes true."

df = df.copy()
rsi_period = max(2, int(params.get("rsi_period", 14)))
rsi_oversold = float(params.get("rsi_oversold", 35))
rsi_overbought = float(params.get("rsi_overbought", 65))
macd_fast = max(2, int(params.get("macd_fast", 12)))
macd_slow = max(macd_fast + 1, int(params.get("macd_slow", 26)))
macd_signal = max(2, int(params.get("macd_signal", 9)))
trend_period = max(2, int(params.get("trend_period", 20)))
min_confirmations = min(3, max(1, int(params.get("min_confirmations", 2))))
volume_period = max(2, int(params.get("volume_period", 20)))
volume_multiplier = max(0.0, float(params.get("volume_multiplier", 0.8)))
use_volume_filter = bool(params.get("use_volume_filter", True))
atr_period = max(2, int(params.get("atr_period", 14)))
atr_min_pct = max(0.0, float(params.get("atr_min_pct", 0.0)))
atr_max_pct = max(atr_min_pct, float(params.get("atr_max_pct", 5.0)))
use_atr_filter = bool(params.get("use_atr_filter", True))
if not 0 < rsi_oversold < 50 < rsi_overbought < 100:
    raise ValueError("Require 0 < rsi_oversold < 50 < rsi_overbought < 100")

close = pd.to_numeric(df["close"], errors="coerce")
high = pd.to_numeric(df["high"], errors="coerce")
low = pd.to_numeric(df["low"], errors="coerce")
volume = pd.to_numeric(df["volume"], errors="coerce")

def wilder(series, period):
    seed = series.rolling(period, min_periods=period).mean()
    ready = seed.notna().cummax()
    first = ready & ~ready.shift(1, fill_value=False)
    values = series.where(ready).where(~first, seed)
    return values.ewm(alpha=1.0 / period, adjust=False, ignore_na=True).mean().where(ready)

delta = close.diff()
gain = wilder(delta.clip(lower=0), rsi_period)
loss = wilder(-delta.clip(upper=0), rsi_period)
rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
rsi = rsi.mask((loss == 0) & (gain > 0), 100.0)
rsi = rsi.mask((gain == 0) & (loss > 0), 0.0)
rsi = rsi.mask((gain == 0) & (loss == 0), 50.0)
macd = close.ewm(span=macd_fast, adjust=False, min_periods=macd_fast).mean() - close.ewm(span=macd_slow, adjust=False, min_periods=macd_slow).mean()
macd_line = macd.ewm(span=macd_signal, adjust=False, min_periods=macd_signal).mean()
histogram = macd - macd_line
trend = close.rolling(trend_period, min_periods=trend_period).mean()
prior_volume = volume.shift(1).rolling(volume_period, min_periods=volume_period).mean()
true_range = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
atr = wilder(true_range, atr_period)
atr_pct = 100 * atr / close.where(close > 0)

# RSI contributes a reversal vote at extremes, or a momentum vote near the middle.
# MACD and trend can confirm each other without waiting for an extreme RSI.
rsi_bull = (rsi <= rsi_oversold) | ((rsi > 50) & (rsi < rsi_overbought))
rsi_bear = (rsi >= rsi_overbought) | ((rsi < 50) & (rsi > rsi_oversold))
buy_score = rsi_bull.astype(int) + (histogram > 0).astype(int) + (close > trend).astype(int)
sell_score = rsi_bear.astype(int) + (histogram < 0).astype(int) + (close < trend).astype(int)
valid = np.isfinite(close) & np.isfinite(high) & np.isfinite(low) & (close > 0) & (high >= low) & rsi.notna() & histogram.notna() & trend.notna()
volume_ok = (volume > 0) & (prior_volume > 0) & (volume >= prior_volume * volume_multiplier)
atr_ok = np.isfinite(atr_pct) & (atr_pct >= atr_min_pct) & (atr_pct <= atr_max_pct)
eligible = valid & (volume_ok | (not use_volume_filter)) & (atr_ok | (not use_atr_filter))
buy_condition = eligible & (buy_score >= min_confirmations) & (buy_score > sell_score)
sell_condition = eligible & (sell_score >= min_confirmations) & (sell_score > buy_score)

def confirmed_edge(condition):
    current = condition.fillna(False).astype(bool)
    return (current & ~current.shift(1, fill_value=False)).shift(1, fill_value=False)

def points(series):
    return [float(value) if pd.notna(value) and np.isfinite(value) else None for value in series]

# Mark the next bar using only the preceding bar's price and ATR.
offset = pd.concat([atr * 0.2, close.abs() * 0.001], axis=1).max(axis=1)
buy_marks = points((low - offset).shift(1).where(confirmed_edge(buy_condition)))
sell_marks = points((high + offset).shift(1).where(confirmed_edge(sell_condition)))
output = {
    "name": my_indicator_name,
    "plots": [
        {"name": "Trend SMA (confirmed)", "type": "line", "data": points(trend.shift(1)), "color": "#F59E0B", "overlay": True},
        {"name": "RSI (confirmed)", "type": "line", "data": points(rsi.shift(1)), "color": "#6366F1", "overlay": False},
    ],
    "signals": [
        {"type": "buy", "text": "Buy", "color": "#22C55E", "data": buy_marks, "overlay": True, "renderMode": "events"},
        {"type": "sell", "text": "Sell", "color": "#EF4444", "data": sell_marks, "overlay": True, "renderMode": "events"},
    ],
    "layers": [],
}
