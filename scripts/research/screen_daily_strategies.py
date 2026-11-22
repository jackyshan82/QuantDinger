"""Bounded, chronological strategy screen using the existing simulation engine.

Run inside the backend container. Credentials remain in the backend; output is
price history, generated strategy sources and reproducible research results.
"""
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time

import pandas as pd
from app.services.alpaca_history import load_alpaca_frame
from app.services.strategy_v2 import StrategyV2BacktestRunner, compile_strategy_v2

OUT = Path('/tmp/strategy_research_20261028')
OUT.mkdir(exist_ok=True)
SYMBOLS = ['NVDA', 'SPY', 'QQQ']
RULES = ['trend_100', 'dual_20_100', 'breakout_55_20', 'rsi2_reversion', 'rsi2_trend_reversion']
PERIODS = {'train': ('2021-07-01', '2022-12-31'), 'validation': ('2023-01-01', '2024-12-31'), 'holdout': ('2025-01-01', '2026-10-27')}
PLAN = {'symbols': SYMBOLS, 'rules': RULES, 'periods': PERIODS, 'commission': .0005, 'slippage': .0005, 'target_pct': .95,
        'provider':'alpaca', 'feed':'iex', 'adjustment':'all',
        'data_availability_revision':'Before observing returns, training start moved from 2018 to 2021-07-01 because IEX history is sparse before 2020-07-27. Earlier isolated observations excluded.',
        'selection':'At least 5 train and 3 validation closed trades; positive net return in both; train max drawdown <= 40%, validation <= 30%. Rank by the lesser of train/validation net-return-to-drawdown ratios. Holdout never used for ranking. No post-holdout tuning.',
        'holdout_acceptance':'Positive net return, drawdown <= 30%, >= 3 closed trades; positive at doubled commission/slippage. Historical research only.'}
(OUT/'plan.json').write_text(json.dumps(PLAN, indent=2))


def source(symbol, rule):
    return f'''"""{symbol} Daily {rule}
Long-only, completed daily bars; queued orders fill next bar open.
Rule selected on training/validation periods, with a separate final holdout.
"""
# @param target_pct float 0.95 Maximum long portfolio weight

def initialize(context):
    g.symbol = "USStock:{symbol}"
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
    sma20 = float(close.tail(20).mean())
    sma100 = float(close.tail(100).mean())
    sma200 = float(close.tail(200).mean())
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    up = float(gain.iloc[-1])
    down = float(loss.iloc[-1])
    rsi2 = 50.0 if up == 0 and down == 0 else (100.0 if down == 0 else 100 - 100 / (1 + up / down))
    rule = "{rule}"
    entry = False
    exit_signal = False
    if rule == "trend_100":
        entry = price > sma100
        exit_signal = price <= sma100
    elif rule == "dual_20_100":
        entry = sma20 > sma100
        exit_signal = sma20 <= sma100
    elif rule == "breakout_55_20":
        entry = price > float(bars["high"].iloc[:-1].tail(55).max())
        exit_signal = price < float(bars["low"].iloc[:-1].tail(20).min())
    elif rule == "rsi2_reversion":
        entry = rsi2 < 10
        exit_signal = price > sma5
    elif rule == "rsi2_trend_reversion":
        entry = price > sma200 and rsi2 < 10
        exit_signal = price > sma5 or price < sma200
    elif rule == "buy_hold":
        entry = True
    position = get_position(g.symbol)
    target = min(0.95, max(0.0, float(context.params.get("target_pct", 0.95))))
    if position.amount <= 0 and entry and target > 0:
        order_target_percent(g.symbol, target, reason="{rule}_entry")
    elif position.amount > 0 and exit_signal:
        order_target_percent(g.symbol, 0.0, reason="{rule}_exit")
'''


def fetch(symbol):
    path = OUT/f'{symbol}_1d.csv'
    if path.exists():
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
    else:
        frame = load_alpaca_frame(1, symbol, '1d', datetime(2016,1,1), datetime(2026,10,27,23,59,59))
        frame.to_csv(path)
    assert frame.index.is_monotonic_increasing and frame.index.is_unique
    assert ((frame['high'] >= frame[['open','close','low']].max(axis=1)) & (frame['low'] <= frame[['open','close','high']].min(axis=1))).all()
    frame = frame.loc[frame.index >= '2020-07-27']
    assert len(frame) > 1500 and frame.index[-1] >= pd.Timestamp('2026-10-26')
    print('DATA',symbol,len(frame),str(frame.index[0]),str(frame.index[-1]),flush=True)
    return symbol,frame


def simulate(symbol, rule, frame, period, cost=.0005, detail=False):
    start,end = PERIODS[period]
    visible = frame.loc[frame.index <= pd.Timestamp(end)+pd.Timedelta(days=1)-pd.Timedelta(seconds=1)]
    runner = StrategyV2BacktestRunner(code=source(symbol,rule), frames={f'USStock:{symbol}':visible}, initial_capital=10000,commission=cost,slippage=cost)
    result = runner.run(start_date=start, end_date=end+' 23:59:59')
    summary = {k:result.get(k) for k in ['totalReturn','maxDrawdown','totalTrades','totalExecutions','winRate','sharpeRatio','totalCommission','finalEquity','resultStatus']}
    summary['maxDrawdown'] = abs(float(summary['maxDrawdown']))
    summary['bars'] = len(visible.loc[visible.index >= start])
    if detail:
        (OUT/f'{symbol}_{rule}_{period}_result.json').write_text(json.dumps(result,default=str))
    return summary


def main():
    frames=dict(ThreadPoolExecutor(max_workers=3).map(fetch,SYMBOLS))
    rows=[]
    cache = json.loads((OUT/'screen.json').read_text()) if (OUT/'screen.json').exists() else []
    fingerprint = hashlib.sha256(json.dumps(PLAN, sort_keys=True).encode() + b''.join(hashlib.sha256((OUT/f'{symbol}_1d.csv').read_bytes()).digest() for symbol in SYMBOLS)).hexdigest()
    cache_metadata = OUT/'screen_cache_metadata.json'
    prior_fingerprint = json.loads(cache_metadata.read_text()).get('fingerprint') if cache_metadata.exists() else None
    cached = {(r['symbol'], r['rule']): r for r in cache if r.get('research_fingerprint') == fingerprint} if prior_fingerprint == fingerprint else {}
    cache_metadata.write_text(json.dumps({'fingerprint': fingerprint, 'plan': PLAN}, indent=2))
    for symbol in SYMBOLS:
        for rule in RULES+['buy_hold']:
            row={'symbol':symbol,'rule':rule,'research_fingerprint':fingerprint}
            for period in ['train','validation']:
                row[period]=cached[(symbol,rule)][period] if (symbol,rule) in cached else simulate(symbol,rule,frames[symbol],period)
                row[period]['maxDrawdown'] = abs(float(row[period]['maxDrawdown']))
            train,val=row['train'],row['validation']
            row['eligible']=(rule!='buy_hold' and train['totalTrades']>=5 and val['totalTrades']>=3 and train['totalReturn']>0 and val['totalReturn']>0 and train['maxDrawdown']<=40 and val['maxDrawdown']<=30)
            row['score']=min(train['totalReturn']/max(train['maxDrawdown'],1),val['totalReturn']/max(val['maxDrawdown'],1)) if row['eligible'] else None
            rows.append(row)
            (OUT/'screen.json').write_text(json.dumps(rows,indent=2))
            print('SCREEN',symbol,rule,json.dumps(row),flush=True)
    eligible=sorted([r for r in rows if r['eligible']],key=lambda r:r['score'],reverse=True)
    if not eligible:
        (OUT/'conclusion.json').write_text(json.dumps({'accepted':False,'reason':'No candidate passed predeclared train/validation criteria.'},indent=2))
        print('NO_ELIGIBLE_CANDIDATE',flush=True)
        return
    selected=dict(eligible[0])
    symbol,rule=selected['symbol'],selected['rule']
    # Freeze selection before reading any holdout strategy results.
    (OUT/'selected_before_holdout.json').write_text(json.dumps(selected,indent=2))
    (OUT/'selected_strategy.py').write_text(source(symbol,rule))
    selected['code_hash']=hashlib.sha256(source(symbol,rule).encode()).hexdigest()
    selected['holdout']=simulate(symbol,rule,frames[symbol],'holdout',detail=True)
    selected['holdout_double_cost']=simulate(symbol,rule,frames[symbol],'holdout',cost=.001,detail=False)
    selected['buy_hold_holdout']=simulate(symbol,'buy_hold',frames[symbol],'holdout',detail=True)
    h=selected['holdout']
    selected['accepted']=h['totalReturn']>0 and h['maxDrawdown']<=30 and h['totalTrades']>=3 and selected['holdout_double_cost']['totalReturn']>0
    (OUT/'conclusion.json').write_text(json.dumps(selected,indent=2))
    print('CONCLUSION',json.dumps(selected),flush=True)

if __name__ == '__main__':
    main()
