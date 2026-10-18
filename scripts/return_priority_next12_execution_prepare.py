"""Prepare next12 execution OHLC from admitted whole sources; no economic calls."""
import csv,gzip,json,hashlib,sys
from pathlib import Path
from fractions import Fraction
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
TRAINING='tmp/next12_training_prepare_20261014_v1/prepared.json'
COORDINATE='tmp/next12_coordinate_review_20261014_v1/coordinate_review.json'
SPECIAL='tmp/next12_nonsimple_final_admission_20261014_v1.json'
EA='tmp/next12_ea_alternate_source_20261014_v1/web_observation.json'
FIELDS=('open','high','low','close')
BASIS='CONDITIONAL_RESTORED_HISTORICAL_NOMINAL_NOT_CERTIFIED'

def prepare_parents():
 pins={};cache={}
 def read(path,expected=None):
  p=Path(path);p=p if p.is_absolute() else ROOT/p;raw=p.read_bytes();h=hashlib.sha256(raw).hexdigest();key=p.relative_to(ROOT).as_posix()
  if expected and h!=expected:raise ValueError('SOURCE_CHANGED:'+key)
  if key in pins and pins[key]!=h:raise ValueError('PIN_CONFLICT')
  pins[key]=h;return raw
 def doc(path):
  a=json.loads(read(path))
  for p,h in a.get('source_hashes',{}).items():read(p,h)
  return a
 training=doc(TRAINING);coord=doc(COORDINATE);special=doc(SPECIAL);ea=doc(EA)
 panel=doc('tmp/current_ohlc_actual_projection_20261014_v1/panel.json')
 days=[d for d in panel['calendar'] if '2025-07-31'<=d<='2026-07-30']
 read('scripts/return_priority_next12_execution_prepare.py');read('backtest/return_priority_fresh_cash_quantity_search.py')
 groups={};windows=[]
 for w in training['windows']:
  windows.append(dict(decision_date=w['decision_cutoff'],active_date=w['active_date'],search_arguments=w['search_arguments'],member_denominator=w['member_count'],exclusions=[]))
  assert days[days.index(w['decision_cutoff'])+1]==w['active_date']
  for r in w['candidates']:groups.setdefault(r['security_id'],[]).append((w['decision_cutoff'],r))
 assert len({w['active_date'][:7] for w in windows})==12
 def rawbars(path,ticker):
  if path in cache:return cache[path]
  raw=read(path);dividends=[]
  if path.endswith('.csv'):
   data={r['Date']:{k:r[k.title()] for k in FIELDS} for r in csv.DictReader(raw.decode('utf-8-sig').splitlines())}
  else:
   c=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=str)['chart']['result'][0]
   if c['meta']['symbol']!=ticker or c['meta']['currency']!='USD':raise ValueError('WRONG_SOURCE_IDENTITY')
   zone=ZoneInfo(c['meta']['exchangeTimezoneName']);date=lambda ts:datetime.fromtimestamp(ts,zone).date().isoformat();q=c['indicators']['quote'][0]
   data={date(ts):{k:q[k][i] for k in FIELDS} for i,ts in enumerate(c['timestamp'])}
   dividends=[dict(date=date(e['date']),provider_payload=e) for e in c.get('events',{}).get('dividends',{}).values()]
  cache[path]=(data,dividends);return data,dividends
 prices={};metadata={};provenance={};gaps=[];splits=[]
 for sid,records in groups.items():
  first,r=records[0];ticker=r['ticker'];path=r['training_source'];assert len({c['training_source'] for _,c in records})==1
  bars,divs=rawbars(path,ticker);start=first;end=days[-1]
  if ticker=='HON':
   if sid.endswith('438516106'):end='2026-06-26'
   elif sid.endswith('438516205'):start='2026-06-29'
   else:raise ValueError('UNREVIEWED_HON_SID')
  if ticker=='AZN':end='2026-01-30'
  factors=special['tickers'][ticker]['price_coordinate_factors'] if ticker in special['tickers'] else [dict(date=e['date'],factor=e['provider_ratio']) for e in coord['tickers'][ticker]['events'] if e['share_multiplier_allowed']]
  if ticker=='EA':factors=[]
  prices[sid]={}
  for day in days:
   if not start<=day<=end:continue
   source=bars.get(day,{})
   if ticker=='EA' and day>='2026-06-30':source=next((x for x in ea['rows'] if x['date']==day),{})
   factor=Fraction(1)
   for e in factors:
    if day<e['date']:factor*=Fraction(e['factor'])
   values={k:str(Fraction(source[k])*factor) if source.get(k) is not None else None for k in FIELDS}
   if all(v is not None for v in values.values()):
    op,hi,lo,cl=[Fraction(values[k]) for k in FIELDS]
    if not 0<lo<=min(op,cl)<=max(op,cl)<=hi:raise ValueError('INVALID_OHLC:'+ticker+day)
   else:gaps.append(dict(security_id=sid,ticker=ticker,date=day))
   prices[sid][day]=values
  for d,r in records:
   if Fraction(prices[sid][d]['close'])!=Fraction(r['decision_cost']):raise ValueError('DECISION_COST_MISMATCH:'+ticker+d)
  metadata[sid]=dict(ticker=ticker,issuer_id=r['issuer_id'])
  provenance[sid]=dict(whole_source=path,price_basis=BASIS,required_from=start,required_to=end,coordinate_factors=factors,returned_dividends=[e for e in divs if start<e['date']<=end],cash_dividends_included=False,dividend_payment_date_unknown=True)
  if ticker=='EA':provenance[sid].update(segments=[dict(start=start,end='2026-06-29',source_path=path),dict(start='2026-06-30',end=end,source_path=EA)],whole_source_claim=False,execution_alternate_overlap_differences=ea['archive_overlap_differences'])
  for e in coord['tickers'][ticker]['events']:
   if e['share_multiplier_allowed'] and start<e['date']<=end:
    ratio=Fraction(e['provider_ratio']);splits.append(dict(security_id=sid,date=e['date'],new_shares=ratio.numerator,old_shares=ratio.denominator,source_references=[COORDINATE,e['official_source']]))
 return dict(schema='NEXT12_FULL_DOMAIN_EXECUTION_INPUTS_V1',status='PARENTS_READY_PENDING_DISTRIBUTION_AND_AZN_BRIDGE',session_dates=days,windows=windows,metadata=metadata,ohlc=prices,source_provenance=provenance,split_events_reference_only=splits,identity_migrations=[],cash_stock_merger_events=[],fractional_settlements={},distribution_events=[],distribution_fractional_cash_values={},price_gaps=gaps,source_hashes=pins,initial_cash='20000',initial_shares={},fee_bps='0',minimum_cash_buffer='0',search_calls=0,book_calls=0,price_only=True,point_in_time_certified=False,independent_oos=False,limitations=['Full parent domain including removed-member residual coverage.','HON old identity ends before6/29; new identity starts6/29. AZN ADS ends1/30 pending explicit ordinary successor marks.','EA uses two explicitly nonoverlapping whole segments, not missing-day vendor stitching.','Cash dividends absent; distribution rights must be assembled before execution.'])

if __name__=='__main__':
 output=ROOT/'tmp/next12_parent_execution_prepare_20261014_v1.json'
 if output.exists():raise ValueError('CREATE_ONLY_OUTPUT_EXISTS')
 a=prepare_parents()
 with output.open('x',encoding='utf-8') as f:json.dump(a,f,ensure_ascii=False,indent=2,allow_nan=False)
 print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),securities=len(a['metadata']),sessions=len(a['session_dates']),gaps=len(a['price_gaps']))))
