"""Create-only next12 training preparation. No optimizer or ledger imports."""
import csv,gzip,hashlib,json,sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from fractions import Fraction
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest.return_priority_monthly_training_inputs import compile_monthly_training_window
OUTPUT=ROOT/'tmp/next12_training_prepare_20261014_v1'
MANIFEST='tmp/next12_candidate_source_manifest_20261014_v1.json'
IDENTITY='tmp/next12_merged_identity_review_20261014_v1.json'
COORDINATE='tmp/next12_coordinate_review_20261014_v1/coordinate_review.json'
POLICY='research_contracts/next12_conditional_source_policy_20261014_v1.json'

def prepare(nonsimple_path):
 pins={};cache={}
 def read(path,expected=None):
  p=Path(path);p=p if p.is_absolute() else ROOT/p
  raw=p.read_bytes();h=hashlib.sha256(raw).hexdigest()
  if expected and h!=expected:raise ValueError('SOURCE_CHANGED:'+str(path))
  key=p.relative_to(ROOT).as_posix()
  if key in pins and pins[key]!=h:raise ValueError('PIN_CONFLICT:'+key)
  pins[key]=h;return raw
 def document(path):
  doc=json.loads(read(path))
  for source,h in doc.get('source_hashes',{}).items():read(source,h)
  return doc
 manifest=document(MANIFEST);identity=document(IDENTITY);coordinate=document(COORDINATE);policy=document(POLICY);special=document(nonsimple_path)
 document('tmp/azn_next12_conditional_admission_20261014_v1.json')
 read('backtest/return_priority_monthly_training_inputs.py');read('scripts/return_priority_next12_training_prepare.py')
 def closes(path,ticker):
  if path in cache:return cache[path]
  raw=read(path)
  if path.endswith('.csv'):
   values={r['Date']:r['Close'] for r in csv.DictReader(raw.decode('utf-8-sig').splitlines())}
  else:
   c=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=str)['chart']['result'][0]
   if c['meta']['symbol']!=ticker:raise ValueError('SYMBOL_MISMATCH:'+ticker)
   zone=ZoneInfo(c['meta']['exchangeTimezoneName']);q=c['indicators']['quote'][0]['close']
   values={datetime.fromtimestamp(ts,zone).date().isoformat():q[i] for i,ts in enumerate(c['timestamp'])}
  cache[path]=values;return values
 windows=[]
 for w,iw in zip(manifest['windows'],identity['windows']):
  decision=w['decision_date'];assert decision==iw['decision_date']
  ids={r['ticker']:r for r in iw['candidates']};rows=[]
  assert set(ids)==set(w['members'])
  for ticker in w['members']:
   coord=coordinate['tickers'][ticker];source=Path(coord['source_path']).as_posix();cw=next(x for x in coord['windows'] if x['decision_date']==decision)
   row=dict(ticker=ticker,security_id=ids[ticker]['security_id'],issuer_id=ids[ticker]['issuer_id'],identity_reviewed=True,coordinate_reviewed=False,source_references=[MANIFEST,IDENTITY,COORDINATE,POLICY,nonsimple_path],blockers=[])
   values=closes(source,ticker);days=w['training_dates'];missing=[d for d in days if values.get(d) is None]
   row.update(training_source=source,missing_training_dates=missing)
   if missing:row['blockers'].append('MISSING_PREDECISION_CLOSE')
   mode='ORDINARY_WHOLE_QUOTE'
   if ticker in ('HON','CMCSA','WDC','AZN','EA'):
    admitted=(dict(source_path=source,training_admitted=True,price_coordinate_factors=[],true_share_events=[],training_rule='ROOT_POLICY_WHOLE_ARCHIVE') if ticker=='EA' else special['tickers'][ticker])
    if Path(admitted['source_path']).as_posix()!=source:raise ValueError('ADMISSION_SOURCE_MISMATCH:'+ticker)
    if not admitted['training_admitted']:row['blockers'].append('NON_SIMPLE_NOT_ADMITTED')
    mode='SPECIAL_'+ticker
   elif not cw['coordinate_only_ready']:row['blockers'].append('COORDINATE_NOT_READY')
   def nominal(d):
    value=Fraction(values[d])
    if mode.startswith('SPECIAL_'):
     for event in admitted['price_coordinate_factors']:
      if d<event['date']:value*=Fraction(event['factor'])
     return value
    if d!=decision:raise ValueError('ORDINARY_NOMINAL_ONLY_DECISION')
    return value*Fraction(cw['decision_factor'])
   def training(d):
    if ticker in ('HON','CMCSA','WDC'):
     value=nominal(d)
     for event in admitted['true_share_events']:
      if d<event['date']:value/=Fraction(event['ratio'])
     return value
    return Fraction(values[d])
   if not row['blockers']:
    row.update(status='READY_CONDITIONAL',coordinate_reviewed=True,training_close=[str(training(d)) for d in days],decision_cost=str(nominal(decision)),training_basis=mode,source_references=row['source_references']+[source])
   else:row['status']='BLOCKED'
   rows.append(row)
  window=dict(decision_cutoff=decision,active_date=w['active_date'],training_dates=w['training_dates'],candidates=rows,member_count=len(rows),status='BLOCKED')
  if not any(r['blockers'] for r in rows):
   admission=dict(decision_date=decision,status='REVIEWED_CONDITIONAL',members=w['members'],training_exclusions={},source_references=[MANIFEST,IDENTITY,COORDINATE,POLICY,nonsimple_path])
   window['search_arguments']=compile_monthly_training_window(window=window,source_hashes=pins,admission=admission);window['status']='READY_CONDITIONAL';window['admission']=admission
  windows.append(window)
 return dict(schema='NEXT12_TRAINING_PREPARED_V1',windows=windows,source_hashes=pins,hona_sensitivity=manifest['hona_membership_sensitivity'],status='READY_CONDITIONAL' if all(w['status']=='READY_CONDITIONAL' for w in windows) else 'BLOCKED',membership_pit_certified=False,independent_oos=False,price_only=True,search_calls=0,book_calls=0,limitations=policy)

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--nonsimple-admission',required=True);args=parser.parse_args()
 if OUTPUT.exists():raise ValueError('CREATE_ONLY_OUTPUT_EXISTS')
 result=prepare(args.nonsimple_admission)
 OUTPUT.mkdir()
 p=OUTPUT/'prepared.json'
 with p.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
 print(json.dumps(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),status=result['status'],windows=len(result['windows']))))
