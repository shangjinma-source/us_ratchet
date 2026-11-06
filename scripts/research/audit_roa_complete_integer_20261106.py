"""Independent arithmetic audit of the frozen completed book; never reruns strategy."""
import json, hashlib
from pathlib import Path
from fractions import Fraction as F
from datetime import date
from backtest.research_exact_fraction_json import loads
ROOT=Path(__file__).resolve().parents[2]
def read(p):return loads((ROOT/p).read_text(encoding='utf8'))
def main():
 directory='tmp/roa_daily_account_20261106_v32/'
 b=read(directory+'book.json');freeze=read(directory+'freeze.json')
 assert b['status']=='COMPLETE'
 for p,h in freeze['source_hashes'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 q=json.loads((ROOT/'tmp/qqq_continuous_paid_reinvestment_20261106.json').read_bytes())['book']
 rows=b['daily_ledger'];dates=[r['date'] for r in rows];assert dates==[r['date'] for r in q['daily_ledger']];assert len(dates)==len(set(dates))==1399
 actions={}
 def action(day,old,new,multiple):actions.setdefault(day,[]).append((old,new,multiple))
 for day,sid,m in [('2021-07-20','research:security:nvda',4),('2023-08-22','research:security:cprt',2),('2024-06-10','security:0001045810:67066G104',10),('2024-09-12','security:0000723254:172908105',4),('2025-05-22','security:0000815556:311900104',2),('2025-06-10','security:0000898173:67103H107',15),('2025-11-17','security:0001065280:64110L106',10),('2026-06-12','security:0000319201:482480100',10)]:action(day,sid,sid,m)
 action('2024-10-03','security:0000707549:512807108','security:0000707549:512807306',10)
 aliases=json.loads((ROOT/'tmp/roa_integer_boundary_alias_review_20261106.json').read_bytes())
 for r in aliases['rows']:
  e=r['event'];action(e['date'],e['security_id'],e['new_security_id'],1)
 orders={}
 for o in b['order_log']:orders.setdefault(o['date'],[]).append(o)
 ev=b['dividend_ledger']['events'];payments={}
 for pay in b['dividend_ledger']['payments'].values():
  e=ev[pay['event_id']];assert pay['session_date']>=e['event']['payment_date'];payments.setdefault(pay['session_date'],[]).append(pay['event_id'])
 accrued={};seen=set();prior={};cash=F(20000);rec=F(0);previous=None
 bars={}
 for window in ['2021_2023','2024_2026']:
  doc=read('tmp/relative_strength_downside_20261106_'+window+'/execution_inputs.json')['document']
  for sid,bar in doc['ohlc'].items():bars.setdefault(sid,{}).update(bar)
 for r in rows:
  day=r['date'];shares=prior.copy()
  for key,item in ev.items():
   e=item['event']
   if e['ex_date']!=day:continue
   pair=(e['security_id'],day);assert pair not in seen;seen.add(pair)
   quantity=prior.get(e['security_id'],0);assert quantity==item['opening_quantity'],(day,e['security_id'])
   net=quantity*F(e['amount_per_share'])*(1-F(e['withholding_rate']));assert net==F(item['net']);rec+=net;accrued[key]=net
  for old,new,m in actions.get(day,[]):
   if old in shares:
    amount=shares.pop(old)*m;assert new not in shares;shares[new]=amount
  for o in orders.get(day,[]):
   delta=o['quantity']*(1 if o['side']=='BUY' else -1);shares[o['security_id']]=shares.get(o['security_id'],0)+delta
   cash-=delta*F(o['price'])+F(o['commission']);assert cash==F(o['cash_after'])
   assert cash>=0
  for key in payments.get(day,[]):cash+=accrued.pop(key);rec-=F(ev[key]['net'])
  shares={s:n for s,n in shares.items() if n}
  assert shares==r['shares'],day
  assert cash==F(r['cash']) and rec==F(r['dividend_receivable']) and F(r['merger_receivable'])==0,day
  nav=cash+rec+sum((n*F(bars[s][day]['close']) for s,n in shares.items()),F(0))
  assert nav==F(r['equity']),day
  assert len(shares)<=10 and all(type(n)is int and n>0 for n in shares.values())
  assert r['signal_date']<day
  if not r['risk_on']:assert not any(o['side']=='BUY' for o in orders.get(day,[]))
  if previous and previous['date'][:7]==day[:7]:assert not any(o['side']=='BUY' and o['security_id']in previous['stopped'] for o in orders.get(day,[]))
  prior=shares;previous=r
 def metrics(rows,shift=False,end=None):
  chosen=[r for r in rows if not end or r['date']<=end];peak=F(20000);dd=F(0)
  for r in chosen:
   v=F(r['equity'])+(F('6.40') if shift and r['date']=='2024-11-20' else 0);peak=max(peak,v);dd=max(dd,1-v/peak)
  terminal=F(chosen[-1]['equity']);years=(date.fromisoformat(chosen[-1]['date'])-date(2020,12,31)).days/365.25
  return {'cagr_pct':(float(terminal/F(20000))**(1/years)-1)*100,'maximum_drawdown_pct':float(dd*100),'terminal':str(terminal),'end':chosen[-1]['date']}
 out={'status':'INDEPENDENT_COMPLETE_ARITHMETIC_PASS','sessions':len(rows),'fills':len(b['order_log']),'source_pins':len(freeze['source_hashes']),'strategy':metrics(rows),'qqq':metrics(q['daily_ledger']),'amat_nov20_receivable_plus640':metrics(rows,True),'through_2025':{'strategy':metrics(rows,end='2025-12-31'),'qqq':metrics(q['daily_ledger'],end='2025-12-31')},'checks':['exact cash every fill and session','dividend opening quantity and unique SID/ex event, payment cash, receivable','integer share changes only exact reviewed splits and namespace aliases','every daily NAV equals cash plus receivable plus nominal close holdings','identical full QQQ calendar and causal signal dates','OFF no buys and same-month stopped no reentry'],'limitations':b['source_limitations']+['Gross zero withholding and zero commission with5bp; not HSBC tax result','Conditional universe and financial filed-date/revision assumptions do not become PIT-certified','Single full-sample candidate after research selection, not independent OOS certification']}
 (ROOT/'tmp/roa_complete_integer_independent_20261106.json').write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
