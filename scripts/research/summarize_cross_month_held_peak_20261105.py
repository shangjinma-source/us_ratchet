"""Completed-window arithmetic only; refuses incomplete books and changed inputs."""
from pathlib import Path
from fractions import Fraction as F
from datetime import date
from hashlib import sha256
import json
import argparse
ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_bytes())
def verify(pins):
 for name,digest in pins.items():assert sha256((ROOT/name).read_bytes()).hexdigest()==digest,name

def metrics(rows,start,fills):
 equity=[(start,F(20000))]+[(r['date'],F(r['equity'])) for r in rows]
 high=F(20000);hi_day=start;dd=F(0);peak=start;trough=start;peak_value=high
 for day,value in equity:
  if value>high:high=value;hi_day=day
  if 1-value/high>dd:dd=1-value/high;peak=hi_day;trough=day;peak_value=high
 recovery=next((day for day,v in equity if day>trough and v>=peak_value),None)
 years=(date.fromisoformat(equity[-1][0])-date.fromisoformat(start)).days/365.25
 annual={};previous=F(20000)
 for year in sorted({d[:4] for d,_ in equity[1:]}):
  day,end=[(d,v) for d,v in equity[1:] if d.startswith(year)][-1]
  annual[year]={'return_pct':float(end/previous-1)*100,'end_date':day};previous=end
 return dict(cagr_pct=((float(equity[-1][1]/20000))**(1/years)-1)*100,drawdown_pct=float(dd)*100,terminal=float(equity[-1][1]),fills=fills,annual=annual,peak=peak,trough=trough,recovery=recovery,peak_to_recovery_or_end_days=(date.fromisoformat(recovery or equity[-1][0])-date.fromisoformat(peak)).days,recovered=recovery is not None)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--window',choices=['2021_2023','2024_2026']);args=parser.parse_args()
 result=[];top=ROOT/'tmp/cross_month_held_peak_20261105';qqq=ROOT/'tmp/qqq_fair_hold_20261105';verify(read(qqq/'summary.json')['source_hashes'])
 for window,baseline in [('2021_2023','recent_continuous_baseline_20261026_v7'),('2024_2026','old_continuous_baseline_20261026_v9')]:
  if args.window and window!=args.window:continue
  folder=top/window;contract=read(folder/'contract.json');verify(contract['source_hashes']);book=read(folder/'book.json');document=read(ROOT/'tmp'/baseline/'execution_inputs.json');dates=document['assembled']['session_dates']
  assert book['status']=='COMPLETE',window+':incomplete'
  assert [r['date'] for r in book['daily_ledger']]==dates[1:],window+':sessions'
  summary=read(folder/'summary.json');assert summary['searches']['new']<=contract['maximum_new_searches']
  b=metrics(book['daily_ledger'],dates[0],sum(r.get('event')=='ASSUMED_NEXT_OPEN_FILLED' for r in book['order_log']))
  assert abs(b['drawdown_pct']-float(F(book['drawdown']['maximum_close_drawdown']))*100)<1e-9
  assert abs((b['terminal']/20000-1)-float(F(book['total_return'])))<1e-9
  q=read(qqq/(baseline+'.json'));assert [r['date'] for r in q['ledger']]==dates[1:]
  qm=metrics(q['ledger'],dates[0],1)
  result.append(dict(window=window,status='COMPLETE_ARITHMETIC_SOURCE_CHECK_PASS_NOT_INDEPENDENT_STRATEGY_REVIEW',candidate=b,qqq=qm,beats_both=b['cagr_pct']>qm['cagr_pct'] and b['drawdown_pct']<qm['drawdown_pct'],book_sha256=sha256((folder/'book.json').read_bytes()).hexdigest()))
 (top/('comparison_'+args.window+'.json' if args.window else 'comparison.json')).write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
