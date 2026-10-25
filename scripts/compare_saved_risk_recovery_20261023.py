"""Compare recovery burden across saved trials; no strategy replay or tuning."""
import csv,json
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from scripts.diagnose_saved_drawdown_episodes_20261023 import episodes
ROOT=Path(__file__).resolve().parents[1]
ARMS={
 'baseline':('entry_delay','baseline','原方案'),
 'delay10':('entry_delay','delay_11_10','高于均线10%暂缓买入'),
 'delay20':('entry_delay','delay_6_5','高于均线20%暂缓买入'),
 'staged3':('staged_entry','staged_3','分3日买入'),
 'staged5':('staged_entry','staged_5','分5日买入'),
 'weak5':('weak5_exit','weak5_exit','连续5日弱势退出')}

def metrics(ledger,begin):
 rows=[dict(date=begin,equity='20000')]+ledger
 peak=F(rows[0]['equity']);drawdowns=[];streak=longest=0
 for row in rows[1:]:
  equity=F(row['equity']);peak=max(peak,equity);dd=1-equity/peak;drawdowns.append(dd)
  streak=streak+1 if dd else 0;longest=max(longest,streak)
 parts=episodes(rows)
 recovered=[duration for _,_,end,duration in parts if end]
 return dict(max_drawdown_percent=float(max(drawdowns)*100),
  mean_underwater_depth_percent=float(sum(drawdowns,F())/len(drawdowns)*100),
  underwater_sessions=sum(d>0 for d in drawdowns),total_sessions=len(drawdowns),
  longest_consecutive_underwater_sessions=longest,
  longest_completed_peak_to_recovery_sessions=max(recovered,default=0),
  unfinished_peak_date=parts[-1][0]['date'] if parts and parts[-1][2] is None else None,
  unfinished_peak_to_end_sessions=parts[-1][3] if parts and parts[-1][2] is None else 0)

def run():
 output=ROOT/'tmp/saved_risk_recovery_comparison_20261023_v1';output.mkdir(exist_ok=False)
 pins={};results=[];dates=None
 def load(path):
  raw=(ROOT/path).read_bytes();pins[path]=sha256(raw).hexdigest();return json.loads(raw)
 index=load('tmp/risk_evidence_readonly_index_20261023_v1.json')
 for exp in index['experiments']:
  for path,digest in exp['references'].items():
   require=sha256((ROOT/path).read_bytes()).hexdigest()==digest
   if not require:raise ValueError('INDEX_SOURCE_CHANGED:'+path)
 probe=[dict(date=str(i),equity=str(x)) for i,x in enumerate([19000,20000,21000,18900,19950])]
 check=metrics(probe,'start')
 assert check['longest_consecutive_underwater_sessions']==2 and check['underwater_sessions']==3
 for cost in (0,10):
  for key,(experiment,arm,label) in ARMS.items():
   version='v2' if experiment=='weak5_exit' else 'v1'
   folder=f'tmp/fixed_monthly_{experiment}_20261023_{version}'
   result=load(f'{folder}/{arm}_{cost}bp.json')
   summary=next(r for r in load(f'{folder}/summary.json') if r['arm']==arm and str(r['fee_bps'])==str(cost))
   ledger=result['daily_ledger'];current_dates=[row['date'] for row in ledger]
   if dates is None:dates=current_dates
   assert dates==current_dates
   m=metrics(ledger,summary['begin'])
   assert abs(m['max_drawdown_percent']/100-summary['max_drawdown'])<1e-12
   assert abs(float(F(ledger[-1]['equity']))-summary['ending_wealth'])<1e-7
   results.append(dict(arm=key,name=label,fee_bps=cost,slippage_bps=cost,annualized_percent=100*summary['annualized'],ending_equity=summary['ending_wealth'],**m))
 for path,digest in pins.items():assert sha256((ROOT/path).read_bytes()).hexdigest()==digest
 report=dict(status='SAVED_RECOVERY_COMPARISON',source_hashes=pins,rows=results,economic_runs=0,
  limitations=['Same fixed monthly quantities; not PIT or independent OOS','No new strategy selected; does not prove preservation of future returns','Unfinished recovery is censored at 2026-10-13; not a predicted recovery date'])
 (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 with (output/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
  writer=csv.DictWriter(stream,fieldnames=list(results[0]));writer.writeheader();writer.writerows(results)
 print(json.dumps([r for r in results if r['fee_bps']==10],ensure_ascii=False))
if __name__=='__main__':run()
