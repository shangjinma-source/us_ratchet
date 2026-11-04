"""Read-only single-window draft; no forced admission, search, or ledger."""
import sys,json,gzip,csv,io
from pathlib import Path
from copy import deepcopy
from fractions import Fraction as F
from datetime import datetime,date
from zoneinfo import ZoneInfo
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from backtest.return_priority_monthly_training_inputs import compile_monthly_training_window

def main():
 pins={}
 def read(name):
  raw=(ROOT/name).read_bytes();pins[name]=sha256(raw).hexdigest();return raw
 def doc(name):return json.loads(read(name))
 old=doc('tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json')['windows'][-1]
 calendar=doc('tmp/old_window_official_calendar_20261026/review.json')
 ea=doc('tmp/ea_final_prices_20261104/candidate.json')
 baseline=doc('tmp/old_continuous_baseline_20261026_v9/execution_inputs.json')
 review=doc('tmp/july31_single_input_20261104/coordinate_review.json')
 for name,digest in review['source_hashes'].items():assert sha256(read(name)).hexdigest()==digest
 assert review['status']=='REVIEWED_CONDITIONAL'
 from bs4 import BeautifulSoup
 html=read('tmp/ea_final_prices_20261104/chartexchange.html')
 assert sha256(html).hexdigest()==ea['source_sha256']
 table=[[cell.get_text(' ',strip=True) for cell in row.find_all(['td','th'])] for row in BeautifulSoup(html,'html.parser').select('tr')]
 ea_row=next(row for row in table if row and row[0]=='2026-07-31')
 secondary=doc('tmp/ea_final_prices_20261104/stockanalysis_observation.json')['rows']['2026-07-31']
 assert all(F(ea_row[i+1])==F(ea['rows']['2026-07-31'][key])==F(secondary[key]) for i,key in enumerate(['open','high','low','close']))
 for name,digest in calendar['source_hashes'].items():assert sha256(read(name)).hexdigest()==digest
 assert date(2026,7,31).weekday()<5 and '2026-07-31' not in calendar['full_holidays']
 from data.current_quantity_v2_monthly_training import _daily
 _,reference=_daily(read('data/cache/research/current_raw_capture_20261014_v1/AAPL.response.bin'),'AAPL')
 assert reference.get('2026-07-31') is not None
 days=(calendar['official_sessions']+['2026-07-31'])[-253:]
 assert all(reference.get(d) is not None for d in days)
 coordinate_differences=[]
 rows=[]
 for previous in old['candidates']:
  c=deepcopy(previous);name=c['training_source'];raw=read(name);events=[]
  if name.endswith('.csv'):
   values={r['Date']:r['Close'] for r in csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))}
  else:
   body=json.loads(gzip.decompress(raw) if raw[:2]==b"\x1f\x8b" else raw,parse_float=str);r=body['chart']['result'][0]
   assert r['meta']['symbol']==c['ticker'];zone=ZoneInfo(r['meta']['exchangeTimezoneName'])
   values={datetime.fromtimestamp(t,zone).date().isoformat():v for t,v in zip(r['timestamp'],r['indicators']['quote'][0]['close'])}
   events=[(datetime.fromtimestamp(e['date'],zone).date().isoformat(),F(e['numerator'])/F(e['denominator'])) for e in r.get('events',{}).get('splits',{}).values()]
  if c['ticker']=='EA':
   original_values=dict(values)
   for day,bar in baseline['ohlc'][c['security_id']].items():
    if values.get(day) is None:values[day]=bar['close']
   values['2026-07-31']=ea['rows']['2026-07-31']['close']
   c['extension_source']='tmp/ea_final_prices_20261104/candidate.json';c['cross_source_overlap_disagreements']=ea['differing_dates']
   assert all(values[d]==v for d,v in original_values.items())
   c['historical_preservation_proof']=dict(original_entries=len(original_values),unchanged_entries=sum(values[d]==v for d,v in original_values.items()),overwritten_entries=0,baseline_source_hash=pins['tmp/old_continuous_baseline_20261026_v9/execution_inputs.json'])
  missing=[d for d in days if values.get(d) is None];c['missing_training_dates']=missing
  c['training_close']=[str(F(values[d])) if values.get(d) is not None else None for d in days];c.pop('training_gross',None)
  c['decision_cost']=None
  if values.get('2026-07-31') is not None:
   cost=F(values['2026-07-31'])
   for effective,ratio in events:
    if '2026-07-31'<effective:cost*=ratio
   c['decision_cost']=str(cost)
  June=values.get('2026-06-30');factor=F(1)
  for effective,ratio in events:
   if '2026-06-30'<effective:factor*=ratio
  delta=None if June is None else F(June)*factor-F(previous['decision_cost'])
  share_changes=[day for day,ratio in events if '2026-06-30'<day<='2026-07-31']
  c['coordinate_reuse_audit']=dict(june30_delta=None if delta is None else str(delta),new_provider_share_events=share_changes,previous_identity=previous['security_id'],previous_reviewed=bool(previous.get('identity_reviewed') and previous.get('coordinate_reviewed')),provider_absence_not_exhaustive=True)
  c['coordinate_reuse_audit'].update(july31_provider_close=str(F(values['2026-07-31'])),july31_nominal_cost=c['decision_cost'])
  blockers=[]
  if delta is None or abs(delta)>F('0.00001'):blockers.append('PRIOR_NOMINAL_COORDINATE_REPLAY_MISMATCH')
  if share_changes:
   if c['ticker']=='CRWD' and [(d,r) for d,r in events if '2026-06-30'<d<='2026-07-31']==[('2026-07-02',F(4))] and review['CRWD']['status']=='REVIEWED_CONDITIONAL':
    c['new_share_event_review']=review['CRWD']
   else:blockers.append('NEW_SHARE_EVENT_REQUIRES_REVIEW')
  if missing:blockers.append('MISSING_PREDECISION_CLOSE')
  if c['ticker']=='EA':
   assert c['security_id']==ea['security_id'] and review['EA']['append_only']=='2026-07-31'
   c['cross_source_review']=review['EA']
  c['blockers']=blockers;c['status']='BLOCKED' if blockers else 'READY_CONDITIONAL'
  if blockers:coordinate_differences.append(dict(ticker=c['ticker'],blockers=blockers,audit=c['coordinate_reuse_audit']))
  rows.append(c)
 for ticker in ['SPCX','HONA']:
  name=f'data/cache/research/current_raw_capture_20261014_v1/{ticker}.response.bin';read(name)
  rows.append(dict(ticker=ticker,status='EXCLUDED_TRAINING_RULE',blockers=[],training_source=name,reason='INSUFFICIENT_253_SESSION_PREDECISION_HISTORY'))
 window=dict(decision_cutoff='2026-07-31',training_dates=days,candidates=rows)
 admission=dict(status='PENDING_REVIEW' if coordinate_differences else review['status'],decision_date='2026-07-31',members=[c['ticker'] for c in rows],source_references=list(pins),limitations=review['membership'],training_exclusions={t:dict(reason='INSUFFICIENT_253_SESSION_PREDECISION_HISTORY',known_asof='2026-07-31',source_references=[f'data/cache/research/current_raw_capture_20261014_v1/{t}.response.bin']) for t in ['SPCX','HONA']})
 try:compiled=compile_monthly_training_window(window=window,source_hashes=pins,admission=admission);reason=None
 except ValueError as e:compiled=None;reason=str(e)
 out=ROOT/'tmp/july31_single_input_20261104';out.mkdir(exist_ok=True)
 result=dict(status='DRAFT_REQUIRES_REVIEW',reason=reason,window=window,admission=admission,source_hashes=pins,compiled=compiled,search_calls=0,book_calls=0,complete_numeric_training=sum(not c.get('missing_training_dates') and len(c.get('training_close',[]))==253 for c in rows),calendar_extension='Derived from pinned official annual holidays plus observed AAPL date; 253 references present; unscheduled closure archive not exhaustive',coordinate_differences=coordinate_differences,membership='Old101 plus2 excluded draft; not confirmed7/31 membership',ea='Append only7/31; preserve historical prices and overlap discrepancy; not certified splice')
 if compiled is not None:
  result.update(status='COMPILED_CONDITIONAL',ea='Append-only7/31 conditionally reviewed; eight overlap differences retained; no historical overrides')
  (out/'single_window_draft.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
  (out/'single_window_input.json').write_text(json.dumps(compiled,indent=2),encoding='utf-8')
  print('COMPILED_CONDITIONAL',len(compiled['prices']),len(compiled['training_scenarios']))
 (out/'single_window_draft.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps({k:result[k] for k in ['status','reason','complete_numeric_training','search_calls','book_calls']}))
if __name__=='__main__':main()
