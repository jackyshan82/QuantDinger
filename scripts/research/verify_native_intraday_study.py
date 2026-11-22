"""Run native external backtests and audit the same-day execution requirement."""
from pathlib import Path
from inspect import unwrap
import json
from collections import Counter
import pandas as pd
from flask import Flask, g
from app.routes.backtest_center import run_strategy_backtest
from app.utils.agent_jobs import get_job

out=Path('/tmp/native_research_20261028')
ids=json.loads((out/'ids.json').read_text())
job=get_job(ids['evolution_job_id'],user_id=1)
assert job['status']=='succeeded', (job['status'],job.get('error'))
evolution=job['result']
if isinstance(evolution,str): evolution=json.loads(evolution)
(out/'evolution_result.json').write_text(json.dumps(evolution,default=str))
params=evolution['bestParams']
app=Flask('native_intraday_verification')
summary={'evolution_summary':evolution['summary'],'best_params':params,'factor_run_ids':ids['factor_run_ids']}
for label,cost in [('base',.0005),('double_cost',.001)]:
    payload={'sourceId':ids['trade_source_id'],'startDate':'2026-01-01','endDate':'2026-10-27','initialCapital':10000,'commission':cost,'slippage':cost,'params':params,'persist':True}
    print('NATIVE_BACKTEST_START',label,flush=True)
    with app.test_request_context('/api/backtest/run',method='POST',json=payload):
        g.user_id=1
        response=app.make_response(unwrap(run_strategy_backtest)())
        body=response.get_json()
        assert response.status_code==200 and body['code']==1,body
        result=body['data']
    (out/f'external_{label}.json').write_text(json.dumps(result,default=str))
    executions=result['executions']
    assert len(executions)==result['totalExecutions'], 'Audit requires full executions, not sampled history'
    open_quantity=0.0
    open_date=None
    overnight=[]
    times=[]
    for item in executions:
        timestamp=pd.Timestamp(item['time'])
        if timestamp.tzinfo is None: timestamp=timestamp.tz_localize('UTC')
        local=timestamp.tz_convert('America/New_York')
        date=str(local.date())
        quantity=float(item['quantity'])
        if item['side']=='buy':
            if open_quantity>0 and open_date!=date:overnight.append({'type':'buy_after_overnight','time':str(local)})
            if open_quantity==0:open_date=date
            open_quantity+=quantity
        else:
            if open_date!=date:overnight.append({'type':'overnight_exit','entry_date':open_date,'exit':str(local)})
            open_quantity-=quantity
            if abs(open_quantity)<1e-8:open_quantity=0.0;open_date=None
        times.append({'side':item['side'],'time':str(local),'reason':item.get('reason')})
    assert not result.get('positions'), 'Terminal position remains open'
    assert open_quantity==0, 'Execution reconstruction ends with open shares'
    assert not overnight, overnight
    metrics={k:result.get(k) for k in ['runId','totalReturn','maxDrawdown','totalTrades','totalExecutions','totalCommission','finalEquity','resultStatus']}
    metrics.update({'overnight_execution_violations':len(overnight),'terminal_quantity':open_quantity,'execution_reasons':dict(Counter(e.get('reason') for e in executions)),'first_executions':times[:4]})
    summary[label]=metrics
    ids['external_'+label+'_run_id']=result['runId']
    (out/'ids.json').write_text(json.dumps(ids,indent=2))
    (out/'verification.json').write_text(json.dumps(summary,indent=2))
    print('NATIVE_BACKTEST_RESULT',label,json.dumps(metrics),flush=True)
summary['passed']=bool(evolution['summary']['recommended'] and summary['base']['totalReturn']>0 and summary['double_cost']['totalReturn']>0)
(out/'verification.json').write_text(json.dumps(summary,indent=2))
print('FINAL_ACCEPTANCE',summary['passed'],flush=True)
