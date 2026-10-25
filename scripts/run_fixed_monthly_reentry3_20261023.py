"""Offline fixed-monthly-path entry timing sensitivity; no optimizer or live mutation."""
from copy import deepcopy
from datetime import date,datetime,timezone
from fractions import Fraction as F
from hashlib import sha256
import argparse,json,socket,gzip
from backtest.current_quantity_v2_signal_history import build_signal_history_resolver
from backtest.partial_trend_exposure import partial_sma20_target
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

from backtest.confirmed_reentry_v1 import confirmed_reentry_target as persistent_weak_target

def advance_wait_only(row,shares,plans,day,resolver,monthly_anchor,events,close_prices):
 if row.get('action')!='WAIT_POST_ACTION_MARK' or row['status']!='READY' or row['orders']:raise ValueError('EXPLICIT_EMPTY_ACTION_WAIT_REQUIRED')
 affected={e[k] for e in events if e['date']==day for k in ('parent_sid','post_parent_sid','child_sid')}
 if not affected:raise ValueError('ACTION_WAIT_EVIDENCE_REQUIRED')
 target=row['target_shares'];domain={sid for sid,q in target.items() if q>0}|{sid for sid,q in shares.items() if q>0}
 if domain & affected:raise ValueError('ACTION_AFFECTED_SIGNAL_UNAVAILABLE')
 inputs=resolver(decision_date=day,target_quantities=target,monthly_decision_date=monthly_anchor,count=20)
 for sid,q in target.items():
  if q and F(inputs['histories'][sid]['closes'][-1]['close'])!=F(close_prices[sid][day]):raise ValueError('HISTORY_CURRENT_UNIT_MISMATCH')
 risk=partial_sma20_target(signal_date=day,**inputs)
 persistent_weak_target(risk['target_quantities'],shares,plans,True,risk['diagnostics'],target)
 return deepcopy(row),risk

def run(out):
 out.mkdir(exist_ok=False)
 def save(name,value):
  with (out/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2,ensure_ascii=False)
 design=dict(date='2026-10-23',scope='FIXED_SAVED_MONTHLY_QUANTITIES_WEAK5_REENTRY3',staging_rule='Five consecutive held selected OFF closes exit remaining half next open; preserve exited latch until three consecutive ON completed closes or removal; OFF resets confirmation count; no missing signal interpolation',arms=[True],costs=[['0','0'],['10','10']],execution='prior completed close signals; next-session market open; same-open sells fund buys as inherited research assumption',selection_calls=0,production_changed=False,limitations=['Fixed original monthly target path, not independently reoptimized account returns','Historical conditional nominal units, not PIT/OOS certified','No intraday low or limit fill assumed','No return guarantee; cash may miss rallies'])
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
  pre=json.loads((ROOT/'tmp/continuous_guided_half_exposure_20261016_v1/preflight.json').read_bytes())
  extra=[prepared['risk_history_snapshots'],'tmp/official_session_closes_20261016_v1/session_close_times.json']
  for name in extra:
   if sha256((ROOT/name).read_bytes()).hexdigest()!=pre['source_hashes'][name]:raise ValueError('SNAPSHOT_SOURCE_CHANGED')
  snapshots={r['decision_date']:r['snapshot'] for r in [json.loads(line) for line in gzip.decompress((ROOT/extra[0]).read_bytes()).splitlines()]}
  schedule=json.loads((ROOT/extra[1]).read_bytes());resolver=build_signal_history_resolver(session_dates=schedule['session_dates'],session_close_times=schedule,snapshots=snapshots)
  save('reconstruction_sources.json',{name:pre['source_hashes'][name] for name in extra})
  for fees,slip in design['costs']:
   for threshold in design['arms']:
    label='weak5_reentry3'
    deferred=[];plans={};reconstructed=[];anchor=[None]
    def provider(**kw):
     day=kw['decision_date'];row=deepcopy(mapping[day])
     if row.get('target_decision_date'):anchor[0]=row['target_decision_date']
     if row.get('action')=='WAIT_POST_ACTION_MARK':
      if threshold:
       unchanged,risk=advance_wait_only(row,kw['state']['shares'],plans,day,resolver,anchor[0],assembled['distribution_events'],assembled['close_prices'])
       reconstructed.append(dict(date=day,diagnostics=risk['diagnostics'],orders=unchanged['orders'],conditional_historical_reconstruction=True))
       return unchanged
      return row
     if row['status']!='READY':raise ValueError('MISSING_CONTIGUOUS_RISK_SIGNAL:'+day)
     risk=row['risk_overlay']
     if risk['signal_date']!=day:raise ValueError('SIGNAL_DATE_MISMATCH')
     desired,blocked=persistent_weak_target(row['target_shares'],kw['state']['shares'],plans,threshold,risk['diagnostics'],row['monthly_ceiling'])
     for sid in blocked:deferred.append(dict(date=day,security_id=sid,quantity=row['target_shares'][sid]-desired[sid],close=risk['diagnostics'][sid]['close'],sma20=risk['diagnostics'][sid]['sma20']))
     orders=[]
     for sid in sorted(set(desired)|set(kw['state']['shares'])):
      delta=desired.get(sid,0)-kw['state']['shares'].get(sid,0)
      if delta:orders.append(dict(id=label+':'+day+':'+sid,security_id=sid,side='BUY' if delta>0 else 'SELL',quantity=abs(delta),decision_date=day,active_date=kw['active_date'],decision_mark=str(assembled['close_prices'][sid][day])))
     return dict(row,orders=orders,target_shares=desired,reserved_cash='0',unreserved_cash=kw['state']['cash'])
    result=run_next_open_book(session_dates=dates,ohlc=prepared['ohlc'],initial_cash='20000',fee_bps=fees,slippage_bps=slip,order_provider=provider,events=assembled['actions'],cash_stock_merger_events=assembled['cash_stock_merger_events'],fractional_settlements=assembled['fractional_settlements'],price_source_references=assembled['price_source_references'],distribution_events=assembled['distribution_events'],distribution_fractional_cash_values=assembled['distribution_fractional_cash_values'],account_model=assembled.get('account_model'))
    if result['status']!='COMPLETE':raise ValueError(str(result['reason']))
    if not threshold and fees=='0' and result['daily_ledger']!=base['daily_ledger']:raise ValueError('BASELINE_LEDGER_REPLAY_MISMATCH')
    equity=[dict(date=dates[0],equity='20000')]+result['daily_ledger'];ending=F(equity[-1]['equity']);years=(date.fromisoformat(dates[-1])-date.fromisoformat(dates[0])).days/365.25
    summary=dict(arm=label,fee_bps=fees,slippage_bps=slip,begin=dates[0],end=dates[-1],ending_wealth=float(ending),annualized=float(ending/F(20000))**(1/years)-1,max_drawdown=float(F(drawdown_summary(equity)['maximum_close_drawdown'])),average_cash_fraction=sum(float(F(r['cash'])/F(r['equity'])) for r in result['daily_ledger'])/len(result['daily_ledger']),deferred_security_days=len(deferred),deferred_days=len({r['date'] for r in deferred}),calendar_years=calendar_year_metrics(opening_date=dates[0],opening_equity='20000',daily_ledger=result['daily_ledger'],expected_sessions=dates[1:],report_through=dates[-1]))
    summary.update(total_fees=float(F(result['fees'])),minimum_cash=min(float(F(r['cash'])) for r in result['daily_ledger']),worst_year_return=min(float(F(y['cumulative_return'])) for y in summary['calendar_years']['years']))
    summaries.append(summary);save(label+'_'+fees+'bp.json',dict(summary=summary,deferred=deferred,reconstructed_waits=reconstructed,daily_ledger=result['daily_ledger'],order_log=result['order_log']))
  # Comparators are reused from sealed saved results; no baseline rerun.
  references={}
  index_raw=(ROOT/'tmp/paired_decline_recovery_20261023_v1/report.json').read_bytes()
  if sha256(index_raw).hexdigest()!='f2b84a6e6e0b0e0e0811a0c04eb2ebc1eca92f34f5ddd193becee027874da11b':raise ValueError('COMPARATOR_INDEX_CHANGED')
  original_index=json.loads((ROOT/'tmp/saved_risk_recovery_comparison_20261023_v1/report.json').read_bytes())
  for row in summaries:
   for comparator in ('baseline','weak5_exit'):
    folder='entry_delay_20261023_v1' if comparator=='baseline' else 'weak5_exit_20261023_v2'
    name=f'tmp/fixed_monthly_{folder}/{comparator}_{row["fee_bps"]}bp.json'
    raw=(ROOT/name).read_bytes();digest=sha256(raw).hexdigest()
    if original_index['source_hashes'][name]!=digest:raise ValueError('COMPARATOR_CHANGED')
    references[name]=digest;reference=json.loads(raw)['summary']
    row['ending_wealth_difference_vs_'+comparator]=row['ending_wealth']-reference['ending_wealth']
  save('comparator_references.json',references)
  save('summary.json',summaries);save('receipt.json',dict(status='COMPLETE',source_hashes=SOURCES,code_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),baseline_rerun=False,rule_sha256=sha256((ROOT/'backtest/confirmed_reentry_v1.py').read_bytes()).hexdigest(),selection_calls=0,network_calls=0,production_changed=False,completed_at=datetime.now(timezone.utc).isoformat()));print(json.dumps(summaries,ensure_ascii=False))
 except BaseException as error:
  save('failed.json',dict(error=str(error)));raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
 with patch.object(socket.socket,'connect',side_effect=AssertionError('OFFLINE_ONLY')):run(Path(args.output))
