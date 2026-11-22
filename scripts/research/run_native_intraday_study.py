"""Submit research through QuantDinger's native application routes.

Uses the existing user's private library, factor-research persistence and
strategy-evolution job queue. Does not create live deployments.
"""
from inspect import unwrap
from pathlib import Path
import json
from flask import Flask, g
from app.routes.script_source_routes import create_script_source
from app.routes.backtest_center import run_factor_research
from app.routes.strategy_evolution import run_strategy_evolution
from app.services.script_source import get_script_source_service

OUT=Path('/tmp/native_research_20261028')
OUT.mkdir(exist_ok=True)
app=Flask('native_research_driver')

def post(handler,path,payload):
    with app.test_request_context(path,method='POST',json=payload):
        g.user_id=1
        response=app.make_response(unwrap(handler)())
        result=response.get_json()
        if response.status_code>=400 or result.get('code')!=1:
            raise RuntimeError(json.dumps({'status':response.status_code,'body':result},default=str))
        return result['data']


def source(name,code):
    existing=next((s for s in get_script_source_service().list_sources(1) if s['name']==name),None)
    if existing:
        assert existing['code'].strip()==code.strip(), 'Existing research source changed; do not overwrite'
        return existing
    return post(create_script_source,'/api/strategies/script-sources/create',{'name':name,'code':code,'description':'Native factor/evolution study 2026-10-28. Research only; see study outputs.','metadata':{'research_candidate':True,'study':'native_research_20261028'},'status':'draft','visibility':'private'})

symbols=['AAPL','MSFT','NVDA','AMD','AVGO','AMZN','META','GOOGL','INTC','QCOM']
factor_code='''"""US Liquid Tech 15m Factor Research
Static present-day research universe. Cross-sectional diagnostics only; no orders.
"""
def initialize(context):
    context.set_universe(SYMBOLS)
    context.subscribe(frequency="15m", fields=["open","high","low","close","volume"])
    context.set_warmup(80)

def on_rebalance(context, panel):
    pass
'''.replace('SYMBOLS',repr(['USStock:'+s for s in symbols]))
factor_source=source('US Liquid Tech 15m Factor Research',factor_code)
trade_source=source('NVDA 15m Morning Reversion - Native Research',Path('/tmp/nvda_15m_morning_reversion.py').read_text())
previous_ids=json.loads((OUT/'ids.json').read_text()) if (OUT/'ids.json').exists() else {}
ids={**previous_ids,'factor_source_id':factor_source['id'],'trade_source_id':trade_source['id'],'factor_run_ids':[]}
(OUT/'ids.json').write_text(json.dumps(ids,indent=2))
print('SOURCES',ids,flush=True)
plan={'frequency':'15m','factor_universe':symbols,'factor_dates':['2025-09-01','2025-12-31'],'evolution_dates':['2025-09-01','2025-12-31'],'external_test_dates':['2026-01-01','2026-10-27'],'data_window_revision':'Two-year minute-history request failed before any result. Shortened study to Sep-Dec 2025 after a successful NVDA data-availability check; shorter sample must be disclosed.','note':'2026 daily results were previously observed; this is outside the new parameter search but is not wholly unseen market history. Native cross-sectional factor holding periods can cross sessions; they are diagnostics, not the same-day execution strategy.','commission':.0005,'slippage':.0005,'candidate_acceptance':'Positive external net return and positive doubled-cost return; zero overnight closed trades and no terminal open positions. Report native blind/OOS and robustness regardless of acceptance.'}
(OUT/'plan.json').write_text(json.dumps(plan,indent=2))
for factor,params,label in [('rsi',{'period':2},'rsi2'),('rsi',{'period':4},'rsi4'),('momentum',{'period':20},'momentum20')]:
    payload={'sourceId':factor_source['id'],'factorId':factor,'factorParams':params,'startDate':'2025-09-01','endDate':'2025-12-31','groups':2,'holdingPeriod':4,'commission':.0005,'slippage':.0005,'neutralizeIndustry':False}
    cache=OUT/f'factor_{label}.json'
    if cache.exists():
        result=json.loads(cache.read_text())
    else:
        print('FACTOR_START',label,flush=True)
        result=post(run_factor_research,'/api/backtest/factor-research',payload)
        cache.write_text(json.dumps(result,default=str))
    ids['factor_run_ids'].append(result['runId'])
    print('FACTOR_RESULT',label,{k:result.get(k) for k in ['runId','rankIc','icir','coverage','netLongShortReturn','sampleDiagnostics']},flush=True)
    (OUT/'ids.json').write_text(json.dumps(ids,indent=2))

payload={'sourceId':trade_source['id'],'startDate':'2025-09-01','endDate':'2025-12-31','initialCapital':10000,'commission':.0005,'slippage':.0005,'leverageEnabled':False,'parameterSpace':[{'name':'rsi_period','min':2,'max':4,'step':2},{'name':'entry_rsi','min':10,'max':20,'step':10},{'name':'exit_period','min':3,'max':5,'step':2}], 'config':{'method':'grid','trials':8,'folds':4,'trainRatio':.7,'blindRatio':.2,'embargoBars':1,'seed':42,'autoPrune':False,'monteCarloPaths':100,'blockSize':5,'costMultipliers':[1,2],'topCandidates':3}}
(OUT/'evolution_request.json').write_text(json.dumps(payload,indent=2))
if 'evolution_job_id' not in ids:
    receipt=post(run_strategy_evolution,'/api/strategy-evolution/run',payload)
    ids['evolution_job_id']=receipt['jobId']
    (OUT/'ids.json').write_text(json.dumps(ids,indent=2))
    print('EVOLUTION_SUBMITTED',receipt,flush=True)
