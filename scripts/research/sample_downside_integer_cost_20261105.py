"""Single bounded arithmetic comparison; no search or account replay."""
from pathlib import Path
import sys,json,time
from fractions import Fraction as F
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from backtest.downside_daily_integer_candidate import ExactDailyReturnIntegers
from scripts.audit_capped_training_frontier import capped,validate_binding
from scripts.research.preflight_downside_frontier_20261105 import bounds,classify


def main():
 start=time.monotonic();out=ROOT/'tmp/downside_integer_cost_20261105';out.mkdir(exist_ok=False)
 def check():
  if time.monotonic()-start>=300:raise TimeoutError('FIXED_300_SECONDS')
 pins={}
 def read(name):
  check();b=(ROOT/name).read_bytes();pins[name]=sha256(b).hexdigest();return json.loads(b)
 result=dict(scope='FIRST_64_UNIQUE_CAP_SAVED_BEST_BY_K_NUMERIC_K_ORDER_NOT_PRIOR_64_SEARCH_OBSERVATIONS',search_calls=0,economic_runs=0)
 try:
  prior=read('tmp/downside_observer_cost_first_month_20261105/summary.json')
  for n,h in prior['source_hashes'].items():
   check();assert sha256((ROOT/n).read_bytes()).hexdigest()==h,n
  raw=read('tmp/recent_continuous_baseline_20261026_v7/2020-12-31.selection.json')['raw_selection'];args=validate_binding(raw)
  training=read('tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json');window=next(x['window'] for x in training['windows'] if x['window']['decision_cutoff']=='2020-12-31')
  candidates={c['security_id']:c for c in window['candidates'] if c.get('security_id')};returns={}
  for s in args['prices']:
   p=list(map(F,candidates[s]['training_close']));returns[s]=[b/a-1 for a,b in zip(p,p[1:])]
  baskets=[];seen=set()
  for k,record in sorted(raw['search_result']['best_by_k'].items(),key=lambda item:int(item[0])):
   q=capped(record['quantities'],args);signature=tuple(sorted(q.items()))
   if signature not in seen:seen.add(signature);baskets.append(q)
   if len(baskets)==64:break
  check();t=time.monotonic();helper=ExactDailyReturnIntegers(prices=args['prices'],equity=args['entered_cash'],stock_returns=returns);construction=time.monotonic()-t;check()
  timings={'original':[],'integer':[]};equal=0
  for round_index,order in enumerate((('original','integer'),('integer','original'))):
   buffers={}
   for mode in order:
    began=time.monotonic();values=[]
    for q in baskets:
     check()
     if mode=='integer':v=helper.portfolio_returns(q)
     else:
      weights={s:n*F(args['prices'][s])/F(args['entered_cash']) for s,n in q.items()}
      v=[sum((weights[s]*returns[s][i] for s in weights),F(0)) for i in range(252)]
     values.append(v)
    timings[mode].append(time.monotonic()-began);buffers[mode]=values
   for a,b in zip(buffers['original'],buffers['integer']):
    check();assert a==b;equal+=len(a)
  # Shared downstream arithmetic is unchanged; verify strict result for every sample.
  reference=[F('-0.01')]*252;reference_bounds=bounds(reference)
  # Synthetic reference isolates computational equality, not actual QQQ risk eligibility.
  downstream_start=time.monotonic()
  for a,b in zip(buffers['original'],buffers['integer']):
   check();assert classify(a,reference,reference_bounds)==classify(b,reference,reference_bounds)
  result.update(status='PASS',baskets=baskets,basket_count=len(baskets),compared_daily_fractions=equal,construction_seconds=construction,
                timings=timings,diagnostics=helper.diagnostics,downstream_equality_seconds=time.monotonic()-downstream_start,
                downstream_reference_scope='SYNTHETIC_MINUS_1_PERCENT_FOR_EQUALITY_ONLY_NOT_QQQ_SCREEN')
 except Exception as e:result.update(status='FAILED',error=repr(e))
 for n in ('backtest/downside_daily_integer_candidate.py','scripts/research/sample_downside_integer_cost_20261105.py'):
  pins[n]=sha256((ROOT/n).read_bytes()).hexdigest()
 result.update(elapsed_seconds=time.monotonic()-start,source_hashes=pins)
 (out/'result.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
 print(json.dumps({k:v for k,v in result.items() if k not in ('baskets','source_hashes')},default=str))

if __name__=='__main__':main()
