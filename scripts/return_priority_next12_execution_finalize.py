"""Assemble parent evidence with child rights sources; prepare only."""
import json,gzip,hashlib,sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from fractions import Fraction
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4
PARENT='tmp/next12_parent_execution_prepare_20261014_v1.json'
ACTION='tmp/next12_action_inputs_20261015_v1/action_inputs.json'
OUTPUT=ROOT/'tmp/next12_execution_prepare_20261014_v1'

def prepare():
 pins={}
 def read(path,expected=None):
  p=Path(path);p=p if p.is_absolute() else ROOT/p;raw=p.read_bytes();h=hashlib.sha256(raw).hexdigest();key=p.relative_to(ROOT).as_posix()
  if expected and h!=expected:raise ValueError('SOURCE_CHANGED:'+key)
  if key in pins and pins[key]!=h:raise ValueError('PIN_CONFLICT:'+key)
  pins[key]=h;return raw
 def doc(path):
  a=json.loads(read(path))
  for p,h in a.get('source_hashes',{}).items():read(p,h)
  return a
 a=doc(PARENT);events=doc(ACTION)
 for path in ['scripts/return_priority_next12_execution_finalize.py','backtest/return_priority_monthly_execution_inputs_v4.py','backtest/return_priority_monthly_execution_inputs.py','backtest/return_priority_limit_book_v2.py']:read(path)
 def add_instrument(ticker,sid,issuer,path,start,refs,role):
  raw=read(path);c=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=str)['chart']['result'][0]
  if c['meta']['symbol']!=ticker or c['meta']['currency']!='USD':raise ValueError('CHILD_IDENTITY_MISMATCH')
  # New child evidence contains no split-coordinate actions. Never infer an adjustment.
  if c.get('events',{}).get('splits'):raise ValueError('CHILD_UNIT_ACTION_REQUIRES_REVIEW')
  zone=ZoneInfo(c['meta']['exchangeTimezoneName']);day=lambda ts:datetime.fromtimestamp(ts,zone).date().isoformat();q=c['indicators']['quote'][0]
  bars={day(ts):{k:q[k][i] for k in ('open','high','low','close')} for i,ts in enumerate(c['timestamp'])}
  a['metadata'][sid]=dict(ticker=ticker,issuer_id=issuer);a['ohlc'][sid]={}
  for d in a['session_dates']:
   if d<start:continue
   bar=bars.get(d,{})
   vals={k:str(Fraction(bar[k])) if bar.get(k) is not None else None for k in ('open','high','low','close')}
   if any(v is None for v in vals.values()):a['price_gaps'].append(dict(security_id=sid,ticker=ticker,date=d))
   else:
    op,hi,lo,cl=[Fraction(vals[k]) for k in ('open','high','low','close')]
    if not 0<lo<=min(op,cl)<=max(op,cl)<=hi:raise ValueError('INVALID_CHILD_OHLC')
   a['ohlc'][sid][d]=vals
  a['source_provenance'][sid]=dict(whole_source=path,price_basis='CONDITIONAL_RESTORED_HISTORICAL_NOMINAL_NOT_CERTIFIED',source_coordinate_note='Raw provider units explicitly conditional; no returned split, not comprehensive action certification.',required_from=start,required_to=a['session_dates'][-1],valuation_only=True,not_search_candidate=True,role=role,identity_source_references=refs,returned_dividends=c.get('events',{}).get('dividends',{}),delivery_confirmed=False)
 for ticker,child in events['child_instruments'].items():add_instrument(ticker,child['security_id'],child['issuer_id'],child['whole_ohlc_source'],child['regular_way_start'],child['identity_source_references'],'PASSIVE_DISTRIBUTION_NONTRADABLE_RIGHTS')
 for e in events['unsupported_conversions']:
  # Ordinary-side price series after conversion date only. Never treat these as old ADS prices.
  raw=read(e['whole_ohlc_source']);c=json.loads(gzip.decompress(raw),parse_float=str)['chart']['result'][0]
  # AZN raw contains the historical ADS coordinate event before this ordinary-only slice.
  zone=ZoneInfo(c['meta']['exchangeTimezoneName']);day=lambda ts:datetime.fromtimestamp(ts,zone).date().isoformat();q=c['indicators']['quote'][0]
  sid=e['new_sid'];a['metadata'][sid]=dict(ticker='AZN',issuer_id=e['issuer_id']);a['ohlc'][sid]={}
  for i,ts in enumerate(c['timestamp']):
   d=day(ts)
   if d in a['session_dates'] and d>=e['date']:
    values={k:str(Fraction(q[k][i])*Fraction(e['post_date_price_factor'])) if q[k][i] is not None else None for k in ('open','high','low','close')}
    if any(v is None for v in values.values()):a['price_gaps'].append(dict(security_id=sid,ticker='AZN',date=d))
    else:
     op,hi,lo,cl=[Fraction(values[k]) for k in ('open','high','low','close')]
     if not 0<lo<=min(op,cl)<=max(op,cl)<=hi:raise ValueError('INVALID_AZN_OHLC')
    a['ohlc'][sid][d]=values
  if set(a['ohlc'][sid])!={d for d in a['session_dates'] if d>=e['date']}:raise ValueError('MISSING_AZN_ORDINARY_DATES')
  a['source_provenance'][sid]=dict(whole_source=e['whole_ohlc_source'],price_basis='CONDITIONAL_RESTORED_HISTORICAL_NOMINAL_NOT_CERTIFIED',required_from=e['date'],required_to=a['session_dates'][-1],valuation_only=True,not_search_candidate=True,delivery_confirmed=False,source_references=e['source_references'],open_conflict=e['open_conflict_retained'])
 # Verify ordinary events agree with parent's reviewed factors; no duplicate HON reverse.
 left={(e['security_id'],e['date'],Fraction(e['new_shares'])/Fraction(e['old_shares'])) for e in a['split_events_reference_only']}
 right={(e['security_id'],e['date'],Fraction(e['new_shares'])/Fraction(e['old_shares'])) for e in events['simple_actions']}
 if left!=right:raise ValueError('ORDINARY_ACTION_MISMATCH')
 a.update(distribution_events=events['distribution_events'],distribution_fractional_cash_values={},unsupported_conversions=events['unsupported_conversions'],child_instruments=events['child_instruments'],source_hashes=pins,status='PREPARED_CONDITIONAL_EXPOSED_ACTION_GUARDS_REQUIRED',required_exposure_guards=[dict(date=e['date'],security_id=e['old_sid'],reason=e['execution_status'],source_references=e['source_references'],scope='ANY_HELD_OR_PENDING_ORDER_OR_TARGET_EXPOSURE_MUST_BLOCK') for e in events['unsupported_conversions']])
 a['limitations']+=['No child is added to any search domain; all new instruments are passive valuation evidence only.','Unknown fractional cash or delivery remains unknown; original event blockers preserved.','Unsupported AZN conversion must block actual exposure, never imply automatic delivery.']
 assembled=assemble_monthly_execution_inputs_v4(a)
 summary=dict(status='PURE_ASSEMBLY_CHECK_PASSED_NOT_ECONOMIC_RUN',monthly_inputs=len(assembled['monthly_inputs']),source_pins=len(pins),sid_count=len(a['metadata']),bars=sum(map(len,a['ohlc'].values())),gaps=len(a['price_gaps']),source_segments_preserved=assembled['source_provenance']==a['source_provenance'],unsupported_conversion_passthrough='unsupported_conversions' in assembled,search_calls=0,book_calls=0)
 return a,summary
if __name__=='__main__':
 if OUTPUT.exists():raise ValueError('CREATE_ONLY_OUTPUT_EXISTS')
 a,summary=prepare();OUTPUT.mkdir()
 for name,value in [('prepared.json',a),('assembly_readback.json',summary)]:
  with (OUTPUT/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
 print(json.dumps(dict(path=str(OUTPUT/'prepared.json'),sha256=hashlib.sha256((OUTPUT/'prepared.json').read_bytes()).hexdigest(),**summary)))
