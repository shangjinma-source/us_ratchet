"""Strict complete-window account metrics; reuse existing calendar-year routine."""
import argparse,json
from pathlib import Path
from fractions import Fraction as F
from datetime import date
from hashlib import sha256
from backtest.continuous_calendar_year_metrics import calendar_year_metrics
from backtest.research_exact_fraction_json import loads
ROOT=Path(__file__).resolve().parents[2]
WINDOWS={'2021_2023':('recent_continuous_baseline_20261026_v7','2020-12-31','2023-12-29',753),'2024_2026':('old_continuous_baseline_20261026_v9','2023-12-29','2026-07-30',646)}
def read(path):
 text=Path(path).read_text(encoding='utf8');x=json.loads(text);return loads(text) if x.get('encoding')=='RESEARCH_EXACT_FRACTION_HEX_JSON_V1' else x

def summarize(book,*,anchor,expected_sessions):
 if book.get('status')!='COMPLETE' or book.get('reason') is not None:raise ValueError('COMPLETE_BOOK_REQUIRED')
 if F(str(book.get('external_flows',0)))!=0:raise ValueError('EXTERNAL_FLOW_UNSUPPORTED')
 rows=book['daily_ledger'];initial=F(str(book['initial_cash']))
 annual=calendar_year_metrics(opening_date=anchor,opening_equity=initial,daily_ledger=rows,expected_sessions=expected_sessions,report_through=expected_sessions[-1])
 peak=initial;peak_date=anchor;peak_index=0;worst=F(0);episodes=[];under=False
 for index,row in enumerate(rows,1):
  equity=F(str(row['equity']));day=row['date'];worst=max(worst,1-equity/peak)
  if equity>=peak:
   if under:episodes.append(dict(peak_date=peak_date,end_date=day,recovered=True,calendar_days=(date.fromisoformat(day)-date.fromisoformat(peak_date)).days,sessions=index-peak_index))
   peak=equity;peak_date=day;peak_index=index;under=False
  else:under=True
 if under:episodes.append(dict(peak_date=peak_date,end_date=rows[-1]['date'],recovered=False,calendar_days=(date.fromisoformat(rows[-1]['date'])-date.fromisoformat(peak_date)).days,sessions=len(rows)-peak_index))
 terminal=F(str(rows[-1]['equity']));elapsed=(date.fromisoformat(rows[-1]['date'])-date.fromisoformat(anchor)).days
 orders=[x for x in book['order_log'] if x.get('side') in ('BUY','SELL') and ('event' not in x or x['event']=='ASSUMED_NEXT_OPEN_FILLED')]
 return dict(status='COMPLETE_ON_EXPECTED_CALENDAR',anchor=anchor,first_close=rows[0]['date'],last_close=rows[-1]['date'],sessions=len(rows),initial_equity=str(initial),terminal_equity=str(terminal),total_return=str(terminal/initial-1),cagr=float(terminal/initial)**(365.25/elapsed)-1,daily_close_maximum_drawdown=str(worst),years=annual['years'],longest_underwater=max(episodes,key=lambda x:x['calendar_days']) if episodes else None,longest_completed_recovery=max((x for x in episodes if x['recovered']),key=lambda x:x['calendar_days'],default=None),fill_count=len(orders),buy_fill_count=sum(x['side']=='BUY' for x in orders),sell_fill_count=sum(x['side']=='SELL' for x in orders),limitations=['Daily close drawdown, not intraday or guaranteed loss bound.','Unrecovered underwater period is censored, not a completed recovery.','Fills are not round-trip trades. No external flows.','Annual rows retain source calendar coverage labels.'])

def compare(window,rsi_path=None,candidate_label='RSI2'):
 if candidate_label in ('V27','QQQ','QQQ_REINVESTED') or not candidate_label:raise ValueError('RESERVED_OR_EMPTY_CANDIDATE_LABEL')
 folder,anchor,end,count=WINDOWS[window];base=ROOT/'tmp'/folder;inputs=read(base/'execution_inputs.json');days=inputs['assembled']['session_dates'];expected=days[1:]
 if days[0]!=anchor or expected[-1]!=end or len(expected)!=count:raise ValueError('FROZEN_FULL_WINDOW_REQUIRED')
 result={};hashes={}
 for source,digest in read(ROOT/'tmp/qqq_fair_hold_20261105/summary.json')['source_hashes'].items():
  if sha256((ROOT/source).read_bytes()).hexdigest()!=digest:raise ValueError('QQQ_SOURCE_PIN_CHANGED')
  hashes[source]=digest
 for label,path in [('V27',base/'book.json'),('QQQ',ROOT/'tmp/qqq_fair_hold_20261105'/(folder+'.json'))]+([(candidate_label,Path(rsi_path))] if rsi_path else []):
  raw=path.read_bytes();hashes[str(path)]=sha256(raw).hexdigest();book=read(path)
  if label=='QQQ':
   s=book['summary']
   if s['anchor']!=anchor or s['last_close']!=end or s['first_open']!=expected[0]:raise ValueError('QQQ_WINDOW_MISMATCH')
   book=dict(status='COMPLETE',reason=None,initial_cash=str(s['initial']),daily_ledger=book['ledger'],order_log=[book['order']],external_flows=0)
  elif label=='V27':
   if F(book['fee_bps'])!=0 or F(book['slippage_bps'])!=5:raise ValueError('V27_COST_MISMATCH')
   if F(book['order_log'][0]['available_cash'])!=20000:raise ValueError('V27_INITIAL_CAPITAL_MISMATCH')
   if any(F(e.get('withholding_rate','0'))!=0 for e in inputs['dividend_events']):raise ValueError('V27_TAX_MISMATCH')
   book={**book,'initial_cash':'20000'}
  result[label]=summarize(book,anchor=anchor,expected_sessions=expected)
  result[label]['recorded_commission_usd']=str(sum((F(str(fill.get('fee','0'))) for fill in book['order_log'] if fill.get('side') in ('BUY','SELL') and ('event' not in fill or fill['event']=='ASSUMED_NEXT_OPEN_FILLED')),F(0)))
 reinvest_directory=ROOT/'tmp/qqq_reinvest_20261106'
 reinvest_report_path=reinvest_directory/'report.json'
 reinvest_report=read(reinvest_report_path)
 for source,digest in reinvest_report['source_hashes'].items():
  if sha256((ROOT/source).read_bytes()).hexdigest()!=digest:raise ValueError('QQQ_REINVEST_SOURCE_CHANGED')
  hashes[source]=digest
 reinvest_book_path=reinvest_directory/(window+'.book.json')
 reinvest_book=read(reinvest_book_path)
 if F(reinvest_book['initial_cash'])!=20000:raise ValueError('QQQ_REINVEST_CAPITAL_MISMATCH')
 reinvest_metrics=summarize(reinvest_book,anchor=anchor,expected_sessions=expected)
 if reinvest_metrics!=reinvest_report['results'][window]:raise ValueError('QQQ_REINVEST_REPORT_MISMATCH')
 result['QQQ_REINVESTED']=reinvest_metrics
 for path in (reinvest_book_path,reinvest_report_path):hashes[str(path)]=sha256(path.read_bytes()).hexdigest()
 hashes[str(base/'execution_inputs.json')]=sha256((base/'execution_inputs.json').read_bytes()).hexdigest()
 return dict(window=window,results=result,source_hashes=hashes,comparison_scope='CONDITIONAL_ACCOUNT_COMPARISON_WITH_PAID_CASH_QQQ_REINVESTMENT',caveats=['QQQ is retained as the old non-reinvestment reference; QQQ_REINVESTED is the paid-cash whole-share reinvestment comparator.','Initial 20000 and identical full calendar; terminal mark not forced liquidation. V27/QQQ references use 5bp and zero brokerage. Candidate commission is reported from its own executed ledger, not assumed zero.','Recorded commission is not all-in transaction cost; withholding and payment assumptions must be checked in each execution contract.','Scheduled issuer payment is a research assumption, not confirmed HSBC receipt.','Conditional action admissions and historical-universe limitations must accompany reported results.','V27 initial cash 20000 derives frozen baseline execution contract; no user capital used.'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--window',choices=WINDOWS,required=True);p.add_argument('--rsi-book');p.add_argument('--candidate-label',default='RSI2');p.add_argument('--output',required=True);a=p.parse_args();r=compare(a.window,a.rsi_book,a.candidate_label);Path(a.output).write_text(json.dumps(r,indent=2),encoding='utf8')
