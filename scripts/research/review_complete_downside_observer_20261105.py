"""Independent original-Fraction winner audit; no search or account mutation."""
from pathlib import Path
from fractions import Fraction as F
from hashlib import sha256
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from math import prod
import json,gzip,sys,time
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from backtest.research_exact_fraction_json import loads,dumps
from scripts.audit_capped_training_frontier import validate_binding,capped,evaluate


def main():
 start=time.monotonic();out=ROOT/'tmp/downside_observer_complete_first_month_20261105_v2';report={'status':'FAIL','scope':'RETAINED_WINNER_ARITHMETIC_NOT_GLOBAL_OPTIMALITY'};pins={}
 def read(name,encoded=False):
  path=ROOT/name;raw=path.read_bytes();pins[name]=sha256(raw).hexdigest()
  return loads(raw) if encoded else json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)
 try:
  prefix=out.relative_to(ROOT).as_posix()+'/'
  summary=read(prefix+'summary.json',True)
  assert summary['status']=='SEARCH_FINISHED_COST_SAMPLE' and summary['observer_complete'] is True, 'RUN_NOT_COMPLETE'
  assert summary['post_run_source_verification']['status']=='PASS'
  side=read(prefix+'sidecar.json',True);search=read(prefix+'search_result.json',True)
  raw=read('tmp/recent_continuous_baseline_20261026_v7/2020-12-31.selection.json')['raw_selection'];args=validate_binding(raw)
  assert search==raw['search_result'] and summary['saved_original_result_equal'] and summary['difference_count']==0
  assert summary['source_hashes']==side['source_hashes']
  for n,h in summary['source_hashes'].items():assert sha256((ROOT/n).read_bytes()).hexdigest()==h,('PIN_CHANGED',n)
  assert side['binding']['search_arguments']==args and side['binding']['decision_date']=='2020-12-31'
  coverage=side['coverage'];assert coverage==summary['coverage']
  assert coverage['risk_evaluated']==coverage['capped_unique'] and coverage['over_holdings_limit']==0 and coverage['risk_evaluated']<=summary['risk_budget']
  assert summary['domain_size']==side['max_holdings']==len(args['prices'])==102
  counts=side['phase_counts'];extra=search['continuous_comparison']['exact_evaluations']
  assert counts['base']==search['objective_evaluations'] and counts['comparison']==extra['saved_unique']+extra['new_unique']
  assert sum(counts.values())==summary['hook_calls']
  assert sum(side['passed_by_actual_k'].values())==coverage['risk_pass_positive']+coverage['risk_pass_cash']
  assert side['complete'] and side['search_hook_counts_verified'] and not side['source_authenticated'] and not side['search_coverage_verified']
  training=read('tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json')
  window=next(o['window'] for o in training['windows'] if o['window']['decision_cutoff']=='2020-12-31')
  dates=window['training_dates'];assert len(dates)==253 and dates==sorted(set(dates)) and dates[-1]==args['decision_date']
  assert args['scenario_dates']==dates[21::21] and len(args['training_scenarios'])==12
  candidates={c['security_id']:c for c in window['candidates'] if c.get('security_id')};returns={}
  for sid in args['prices']:
   prices=list(map(F,candidates[sid]['training_close']));assert len(prices)==253 and all(p>0 for p in prices)
   assert all(prices[(i+1)*21]/prices[i*21]==F(args['training_scenarios'][i][sid]) for i in range(12))
   returns[sid]=[b/a-1 for a,b in zip(prices,prices[1:])]
  qprices={}
  for name in ('tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin'):
   body=read(name)['chart']['result'][0]
   for stamp,close in zip(body['timestamp'],body['indicators']['quote'][0]['close']):
    if close is None:continue
    d=datetime.fromtimestamp(stamp,tz=timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat();v=F(str(close))
    assert d not in qprices or qprices[d]==v;qprices[d]=v
  qreturns=[qprices[b]/qprices[a]-1 for a,b in zip(dates,dates[1:])]
  exact_d=lambda row:sum((min(x,F(0))**2 for x in row),F(0))/len(row)
  reference=exact_d(qreturns);checked=[]
  for k,record in [('0',side['cash']),*side['eligible_best_by_k'].items()]:
   q=record['target_quantities'];assert str(len(q))==k and len(q)==record['actual_k']
   assert capped(q,args)==q and capped(dict(record['raw_signature']),args)==q
   score=evaluate(q,args)
   assert score['product']==record['exact_product'] and score['notional']==record['notional'] and score['residual_cash']==record['residual_cash']
   weights={s:n*F(args['prices'][s])/F(args['entered_cash']) for s,n in q.items()}
   values=[sum((w*returns[s][i] for s,w in weights.items()),F(0)) for i in range(252)]
   downside=exact_d(values);assert downside<=reference,('D_GATE_FAILED',k)
   low,high=map(F,record['downside_interval']);assert low<=downside<=high
   checked.append(dict(k=int(k),daily_values_checked=252,exact_downside_le_qqq=True))
  report.update(status='PASS',winners_checked=len(checked),checks=checked,coverage=coverage,
                search_result_matches_saved=True,full_hook_counts_reconciled=True,
                limitation='Checks retained winners and aggregate coverage; does not independently prove each winner dominates all observed candidates because full candidate ledger is not persisted.')
 except Exception as error:report.update(error=repr(error))
 report.update(elapsed_seconds=time.monotonic()-start,review_input_hashes=pins,review_script_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
 (out/'independent_review.json').write_text(dumps(report),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k not in ('checks','review_input_hashes')},default=str))

if __name__=='__main__':main()
