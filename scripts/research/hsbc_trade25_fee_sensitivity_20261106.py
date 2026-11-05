"""Trade25 frozen-fill cost scenarios using the existing verified core contract."""
from fractions import Fraction as F
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from hashlib import sha256
import argparse,json
from pathlib import Path
from core.hsbc_trade25_commission import quote_commission
from scripts.research.rsi2_complete_window_metrics_20261106 import read
RULE='research_contracts/hsbc_trade25_20261024.json'

def standard_fee(quantity):
 return F(quote_commission(executed_at='2024-01-02T14:30:00Z',turnover_month='2024-01',prior_turnover_hkd='250001',gross_usd='1',quantity=quantity,execution_hkd_per_usd='7.8',charging_unit_confirmed=True)['commission_usd'])

def quote_scenario(*,prior_hkd,quantity,gross_usd,executed_at,month,fx='7.8'):
 q=quote_commission(executed_at=executed_at,turnover_month=month,prior_turnover_hkd=str(prior_hkd),gross_usd=str(gross_usd),quantity=quantity,execution_hkd_per_usd=fx,charging_unit_confirmed=True)
 if q['commission_usd']is None:
  if q['status']!='EXACT_THRESHOLD_REQUIRES_CONFIRMATION':raise ValueError(q['status'])
  low=F(0);high=standard_fee(quantity)
 else:low=high=F(q['commission_usd'])
 return q,low,high

def analyze_scenario(book,phase_timing,fx):
 months={};details=[];previous=None
 for row in book['order_log']:
  if row.get('side')not in ('BUY','SELL')or(row.get('event')and row['event']!='ASSUMED_NEXT_OPEN_FILLED'):continue
  clock='09:30:00' if row.get('phase')=='OPEN'or phase_timing=='EARLIEST_INTRADAY'else '16:00:00'
  instant=datetime.fromisoformat(row['date']+'T'+clock).replace(tzinfo=ZoneInfo('America/New_York'))
  # Daily records do not establish order within intraday phase; preserve engine order.
  if previous and row['date']<previous:raise ValueError('CHRONOLOGICAL_FILL_ORDER_REQUIRED')
  previous=row['date'];month=instant.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m')
  m=months.setdefault(month,dict(turnover_hkd=F(0),notional_usd=F(0),lower_fee=F(0),upper_fee=F(0),fills=0))
  gross=F(str(row['price']))*row['quantity'];q,low,high=quote_scenario(prior_hkd=m['turnover_hkd'],quantity=row['quantity'],gross_usd=gross,executed_at=instant.isoformat(),month=month,fx=fx)
  m['turnover_hkd']=F(q['after_turnover_hkd']);m['notional_usd']+=gross;m['lower_fee']+=low;m['upper_fee']+=high;m['fills']+=1
  details.append(dict(date=row['date'],hk_month=month,assumed_execution_time=instant.isoformat(),core_status=q['status'],lower_fee=str(low),upper_fee=str(high)))
 return dict(timing_scenario=phase_timing,monthly={k:{n:str(v)if isinstance(v,F)else v for n,v in m.items()}for k,m in months.items()},first_fill=details[0]['date']if details else None,last_fill=previous,fills=len(details),lower_commission_usd=str(sum((m['lower_fee']for m in months.values()),F(0))),upper_commission_usd=str(sum((m['upper_fee']for m in months.values()),F(0))),fill_details=details)

def analyze(book,usd_hkd='7.8'):
 return dict(source_status=book['status'],scope='OBSERVED_FILLS_ONLY_NOT_ANNUALIZED',rule_source=RULE,rule_sha256=sha256(Path(RULE).read_bytes()).hexdigest(),usd_hkd_assumed=usd_hkd,scenarios=[analyze_scenario(book,t,usd_hkd)for t in ['EARLIEST_INTRADAY','LATEST_INTRADAY']],limitations=['First crossing order is VERIFIED WAIVED; prior report treating it as unresolved is superseded.','Only exact pre-trade HKD250000 retains official wording ambiguity; fee bounds apply only there.','Hong Kong calendar month reset00:00; NY open is known, intraday fill timestamp unknown. Earliest/latest intraday scenarios are NOT exact broker bills or exhaustive extrema.','7.8FX is scenario assumption, not actual HSBC rate; each simulated fill assumed one charging unit, not verified partial-fill grouping.','Combined buy+sell gross turnover; only brokerage modeled, regulatory and other costs excluded.','Frozen fills cost pressure, not net strategy return. No annualization of partial periods. No account replay or production changes.'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--book',required=True);p.add_argument('--output',required=True);a=p.parse_args();Path(a.output).write_text(json.dumps(analyze(read(a.book)),indent=2))
