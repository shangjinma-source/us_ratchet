"""Offline fixed-monthly-path entry timing sensitivity; no optimizer or live mutation."""
from copy import deepcopy
from datetime import date,datetime,timezone
from fractions import Fraction as F
from hashlib import sha256
import argparse,json,socket
from pathlib import Path
from unittest.mock import patch
from backtest.current_quantity_v2_next_open_book import run_next_open_book
from backtest.current_quantity_v2_daily_next_open import drawdown_summary
from backtest.continuous_calendar_year_metrics import calendar_year_metrics
ROOT=Path(__file__).resolve().parents[1]
SOURCES={
 'tmp/continuous_guided_half_exposure_20261016_v1/outcome.json':'ff279e5925b4c07c0a717f97055cb698be5d330cbb79ae9b6ce22bdc10e079c7',
 'tmp/daily_verified_domain_experiment_20261016_v2/prepared.json':'83f30b31b941c5a406179ae2625395794d15a1a1e1a2427876ab307d2df19921',
 'tmp/daily_verified_domain_experiment_20261016_v2/assembled.json':'5bf4bb1b7b1394f85796fe08ed0a303db97dc8796becffaf97ba579826064bf2'}

def staged_target(target,shares,plans,days,monthly_anchor):
 if type(days)is not int or days not in (1,3,5):raise ValueError('PREDECLARED_DAYS_REQUIRED')
 result=dict(target);deferred=[]
 for sid in set(plans)-set(target):plans.pop(sid)
 for sid,q in target.items():
  held=shares.get(sid,0)
  if type(q)is not int or q<0 or type(held)is not int or held<0:raise ValueError('WHOLE_LONG_SHARES_REQUIRED')
  if q<=held:
   plans.pop(sid,None);continue
  key=(monthly_anchor,q)
  if sid not in plans or plans[sid]['key']!=key:plans[sid]=dict(key=key,remaining=days)
  remaining=plans[sid]['remaining'];gap=q-held
  addition=(gap+remaining-1)//remaining
  result[sid]=held+addition
  plans[sid]['remaining']=max(1,remaining-1)
  if result[sid]<q:deferred.append(sid)
 return result,deferred

def run(out):
 out.mkdir(exist_ok=False)
 def save(name,value):
  with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2,ensure_ascii=False)
 design=dict(date='2026-10-23',scope='FIXED_SAVED_MONTHLY_QUANTITIES_STAGED_BUYS_ONLY',staging_rule='Ceil remaining actual gap / remaining days; goal or monthly anchor changes restart schedule; reductions immediate; unfilled not credited',arms=[1,3,5],costs=[['0','0'],['10','10']],execution='prior completed close signals; next-session market open; same-open sells fund buys as inherited research assumption',selection_calls=0,production_changed=False,limitations=['Fixed original monthly target path, not independently reoptimized account returns','Historical conditional nominal units, not PIT/OOS certified','No intraday low or limit fill assumed','No return guarantee; cash may miss rallies'])
 save('design.json',design)
 try:
  values={}
  for name,digest in SOURCES.items():
   raw=(ROOT/name).read_bytes()
   if sha256(raw).hexdigest()!=digest:raise ValueError('SEALED_SOURCE_CHANGED:'+name)
   values[name]=json.loads(raw)
  base,prepared,assembled=[values[n] for n in SOURCES]
  dates=assembled['session_dates'];audit=base['provider_audit']
  if len(audit)!=len(dates)-1:raise ValueError('AUDIT_DOMAIN')
  mapping=dict(zip(dates[:-1],audit));summaries=[]
  for fees,slip in design['costs']:
   for threshold in design['arms']:
    label='baseline' if threshold==1 else 'staged_'+str(threshold)
    deferred=[];plans={}
    def provider(**kw):
     day=kw['decision_date'];row=deepcopy(mapping[day])
     if row['status']!='READY' or row.get('action')=='WAIT_POST_ACTION_MARK':return row
     risk=row['risk_overlay']
     if risk['signal_date']!=day:raise ValueError('SIGNAL_DATE_MISMATCH')
     desired,blocked=staged_target(row['target_shares'],kw['state']['shares'],plans,threshold,row['target_decision_date'])
     for sid in blocked:deferred.append(dict(date=day,security_id=sid,quantity=row['target_shares'][sid]-desired[sid],close=risk['diagnostics'][sid]['close'],sma20=risk['diagnostics'][sid]['sma20']))
     orders=[]
     for sid in sorted(set(desired)|set(kw['state']['shares'])):
      delta=desired.get(sid,0)-kw['state']['shares'].get(sid,0)
      if delta:orders.append(dict(id=label+':'+day+':'+sid,security_id=sid,side='BUY' if delta>0 else 'SELL',quantity=abs(delta),decision_date=day,active_date=kw['active_date'],decision_mark=str(assembled['close_prices'][sid][day])))
     return dict(row,orders=orders,target_shares=desired,reserved_cash='0',unreserved_cash=kw['state']['cash'])
    result=run_next_open_book(session_dates=dates,ohlc=prepared['ohlc'],initial_cash='20000',fee_bps=fees,slippage_bps=slip,order_provider=provider,events=assembled['actions'],cash_stock_merger_events=assembled['cash_stock_merger_events'],fractional_settlements=assembled['fractional_settlements'],price_source_references=assembled['price_source_references'],distribution_events=assembled['distribution_events'],distribution_fractional_cash_values=assembled['distribution_fractional_cash_values'],account_model=assembled.get('account_model'))
    if result['status']!='COMPLETE':raise ValueError(str(result['reason']))
    if threshold==1 and fees=='0' and result['daily_ledger']!=base['daily_ledger']:raise ValueError('BASELINE_LEDGER_REPLAY_MISMATCH')
    equity=[dict(date=dates[0],equity='20000')]+result['daily_ledger'];ending=F(equity[-1]['equity']);years=(date.fromisoformat(dates[-1])-date.fromisoformat(dates[0])).days/365.25
    summary=dict(arm=label,fee_bps=fees,slippage_bps=slip,begin=dates[0],end=dates[-1],ending_wealth=float(ending),annualized=float(ending/F(20000))**(1/years)-1,max_drawdown=float(F(drawdown_summary(equity)['maximum_close_drawdown'])),average_cash_fraction=sum(float(F(r['cash'])/F(r['equity'])) for r in result['daily_ledger'])/len(result['daily_ledger']),deferred_security_days=len(deferred),deferred_days=len({r['date'] for r in deferred}),calendar_years=calendar_year_metrics(opening_date=dates[0],opening_equity='20000',daily_ledger=result['daily_ledger'],expected_sessions=dates[1:],report_through=dates[-1]))
    summary.update(total_fees=float(F(result['fees'])),minimum_cash=min(float(F(r['cash'])) for r in result['daily_ledger']),worst_year_return=min(float(F(y['cumulative_return'])) for y in summary['calendar_years']['years']))
    summaries.append(summary);save(label+'_'+fees+'bp.json',dict(summary=summary,deferred=deferred,daily_ledger=result['daily_ledger'],order_log=result['order_log']))
  for row in summaries:
   reference=next(r for r in summaries if r['arm']=='baseline' and r['fee_bps']==row['fee_bps']);row['ending_wealth_difference_vs_baseline']=row['ending_wealth']-reference['ending_wealth']
  save('summary.json',summaries);save('receipt.json',dict(status='COMPLETE',source_hashes=SOURCES,code_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),baseline_daily_ledger_exact_replay=True,selection_calls=0,network_calls=0,production_changed=False,completed_at=datetime.now(timezone.utc).isoformat()));print(json.dumps(summaries,ensure_ascii=False))
 except BaseException as error:
  save('failed.json',dict(error=str(error)));raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
 with patch.object(socket.socket,'connect',side_effect=AssertionError('OFFLINE_ONLY')):run(Path(args.output))
