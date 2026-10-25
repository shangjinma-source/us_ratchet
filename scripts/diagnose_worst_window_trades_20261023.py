"""Exact mark/trade decomposition for the saved worst baseline window; offline."""
import json
from pathlib import Path
from hashlib import sha256
from fractions import Fraction as F
ROOT=Path(__file__).resolve().parents[1]
START,END='2025-02-14','2025-04-04'

def run():
 out=ROOT/'tmp/worst_window_trade_diagnosis_20261023_v1';out.mkdir(exist_ok=False)
 pins={};prior=json.loads((ROOT/'tmp/paired_decline_recovery_20261023_v1/report.json').read_bytes())
 def read(name,digest):
  raw=(ROOT/name).read_bytes()
  if sha256(raw).hexdigest()!=digest:raise ValueError('SOURCE_CHANGED:'+name)
  pins[name]=digest;return json.loads(raw)
 data=read('tmp/daily_verified_domain_experiment_20261016_v2/assembled.json','5bf4bb1b7b1394f85796fe08ed0a303db97dc8796becffaf97ba579826064bf2')
 results=[]
 for arm,name in [('baseline','tmp/fixed_monthly_entry_delay_20261023_v1/baseline_10bp.json'),('weak5','tmp/fixed_monthly_weak5_exit_20261023_v2/weak5_exit_10bp.json')]:
  saved=read(name,prior['source_hashes'][name]);rows=[r for r in saved['daily_ledger'] if START<=r['date']<=END]
  assert rows[0]['date']==START and rows[-1]['date']==END
  totals={};days=[];trades=[]
  def add(sid,kind,amount):
   totals.setdefault(sid,dict(mark=F(0),execution=F(0),fees=F(0)))[kind]+=amount
  for previous,current in zip(rows,rows[1:]):
   day=current['date'];mark=F(0);execution=F(0);fees=F(0)
   for sid,quantity in previous['shares'].items():
    if not quantity:continue
    part=quantity*(F(data['close_prices'][sid][day])-F(data['close_prices'][sid][previous['date']]))
    mark+=part;add(sid,'mark',part)
   for fill in saved['order_log']:
    if fill['date']!=day or fill['event']!='ASSUMED_NEXT_OPEN_FILLED':continue
    sid=fill['security_id'];signed=fill['quantity']*(1 if fill['side']=='BUY' else -1)
    part=signed*(F(data['close_prices'][sid][day])-F(fill['price']));fee=F(fill['fee'])
    execution+=part;fees+=fee;add(sid,'execution',part);add(sid,'fees',fee)
    trades.append(dict(date=day,ticker=data['metadata'][sid]['ticker'],security_id=sid,side=fill['side'],quantity=fill['quantity'],price=str(fill['price']),fee=str(fee),held_before=previous['shares'].get(sid,0),held_at_close=current['shares'].get(sid,0)))
   delta=F(current['equity'])-F(previous['equity']);residual=delta-mark-execution+fees
   if residual:raise ValueError('UNEXPLAINED_ACTION_OR_FLOW:'+arm+':'+day+':'+str(residual))
   days.append(dict(date=day,equity_change=str(delta),overnight_and_close_marks=str(mark),execution_vs_close=str(execution),fees=str(fees),residual='0'))
  contributions=[dict(ticker=data['metadata'][sid]['ticker'],security_id=sid,**{k:str(v) for k,v in values.items()},net=str(values['mark']+values['execution']-values['fees']),net_usd=float(values['mark']+values['execution']-values['fees'])) for sid,values in totals.items()]
  change=F(rows[-1]['equity'])-F(rows[0]['equity']);assert sum((F(r['net']) for r in contributions),F())==change
  results.append(dict(arm=arm,opening_equity=str(rows[0]['equity']),closing_equity=str(rows[-1]['equity']),equity_change=str(change),contributions=contributions,trades=trades,daily_reconciliation=days))
 for name,digest in pins.items():assert sha256((ROOT/name).read_bytes()).hexdigest()==digest
 report=dict(status='EXACT_SAVED_WINDOW_TRADE_RECONCILIATION',start=START,end=END,source_hashes=pins,arms=results,production_changed=False,economic_replays=0,limitations=['Retrospective conditional research window, not PIT/OOS or actual trades.','Different opening wealth; USD loss differences are descriptive, not pure causal effects.','Mark and execution components reconcile exactly but are not independent signal attribution.'])
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps([dict(arm=r['arm'],contributions=r['contributions']) for r in results],ensure_ascii=False))
if __name__=='__main__':run()
