"""Read-only drawdown episodes from sealed saved equity; no economic replay."""
import argparse, csv, json
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCES={
 'tmp/fixed_monthly_entry_delay_20261023_v1/baseline_10bp.json':'e9e0890190e86fe14112abd5752efa96acd2657f796cd746008bb74b9ba06172',
 'tmp/daily_verified_domain_experiment_20261016_v2/assembled.json':'5bf4bb1b7b1394f85796fe08ed0a303db97dc8796becffaf97ba579826064bf2'}
def episodes(rows):
 peak=rows[0]; trough=peak; start=0; result=[]
 for index,row in enumerate(rows[1:],1):
  if F(row['equity'])>=F(peak['equity']):
   if trough is not peak:result.append((peak,trough,row,index-start))
   peak=trough=row;start=index
  elif F(row['equity'])<F(trough['equity']):trough=row
 if trough is not peak:result.append((peak,trough,None,len(rows)-1-start))
 return result

def run(output):
 output.mkdir(exist_ok=False)
 values={}
 for name,digest in SOURCES.items():
  raw=(ROOT/name).read_bytes()
  if sha256(raw).hexdigest()!=digest:raise ValueError('SOURCE_CHANGED:'+name)
  values[name]=json.loads(raw)
 baseline,assembled=values.values()
 rows=[{'date':assembled['session_dates'][0],'equity':'20000','shares':{}}]+baseline['daily_ledger']
 if [r['date'] for r in rows]!=assembled['session_dates']:raise ValueError('SESSION_DOMAIN')
 results=[]
 for peak,trough,recovered,duration in episodes(rows):
  marks={sid:F(quantity)*F(assembled['close_prices'][sid][peak['date']]) for sid,quantity in peak['shares'].items() if quantity}
  largest=max(marks,key=marks.get) if marks else None
  results.append({'peak':peak['date'],'trough':trough['date'],'recovery':recovered['date'] if recovered else None,
   'drawdown':str(1-F(trough['equity'])/F(peak['equity'])),'drawdown_percent':float((1-F(trough['equity'])/F(peak['equity']))*100),
   'sessions_to_recovery_or_end':duration,'peak_equity':str(peak['equity']),'trough_equity':str(trough['equity']),
   'peak_largest_security':largest,'peak_largest_weight':float(marks[largest]/F(peak['equity'])) if largest else 0,
   'peak_stock_exposure':float(sum(marks.values(),F(0))/F(peak['equity']))})
 results.sort(key=lambda r:F(r['drawdown']),reverse=True)
 if abs(results[0]['drawdown_percent']/100-baseline['summary']['max_drawdown'])>1e-12:raise ValueError('MAX_DRAWDOWN_MISMATCH')
 # Hand-check episode recovery and equal-high behavior independently of real data.
 probe=[{'equity':str(x),'date':str(i)} for i,x in enumerate([100,90,95,100,110,88,99])]
 assert [(a['date'],b['date'],c['date'] if c else None,d) for a,b,c,d in episodes(probe)]==[('0','1','3',3),('4','5',None,2)]
 for name,digest in SOURCES.items():
  if sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('SOURCE_CHANGED_AFTER_READ')
 report={'status':'SAVED_EQUITY_EPISODES_VERIFIED','source_hashes':SOURCES,'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
 'fee_bps':10,'slippage_bps':10,'episode_count':len(results),'episodes':results,'economic_replays':0,'production_changed':False,
 'limitations':['Conditional fixed monthly quantities, not PIT/OOS or actual broker performance','Peak concentration is descriptive, not evidence a cap improves return','Recovered and unfinished episodes are distinguished; no artificial recovery date']}
 (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 with (output/'episodes.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(results[0]));writer.writeheader();writer.writerows(results)
 print(json.dumps({'episodes':len(results),'top5':results[:5]},ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);run(Path(p.parse_args().output))
