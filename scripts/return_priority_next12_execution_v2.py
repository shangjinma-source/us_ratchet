"""Versioned explicit DTC action admission; prices and selections unchanged."""
import json,hashlib,sys
from pathlib import Path
from fractions import Fraction
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4
OLD='tmp/next12_execution_prepare_20261014_v1/prepared.json'
ACTION='tmp/next12_action_inputs_20261015_v2/action_inputs.json'
BINDING='tmp/next12_dtc_conversion_binding_20261015_v1.json'
HELPER='backtest/return_priority_monthly_execution_inputs_v4.py'
OUTPUT=ROOT/'tmp/next12_execution_prepare_20261014_v2'
def prepare():
 pins={};superseded=[]
 def read(path,expected=None):
  p=Path(path);p=p if p.is_absolute() else ROOT/p;raw=p.read_bytes();h=hashlib.sha256(raw).hexdigest();key=p.relative_to(ROOT).as_posix()
  if expected and h!=expected:raise ValueError('SOURCE_CHANGED:'+key)
  if key in pins and pins[key]!=h:raise ValueError('PIN_CONFLICT:'+key)
  pins[key]=h;return raw
 old=json.loads(read(OLD));a=json.loads(json.dumps(old))
 for path,h in old['source_hashes'].items():
  if path==HELPER:
   raw=read(path);superseded.append(dict(path=path,old_sha256=h,new_sha256=hashlib.sha256(raw).hexdigest(),reason='ROOT_AUTHORIZED_UNSUPPORTED_AND_SUPPORTED_CONVERSION_WIRING'))
  else:read(path,h)
 def doc(path):
  result=json.loads(read(path))
  for f,h in result.get('source_hashes',{}).items():read(f,h)
  return result
 actions=doc(ACTION);binding=doc(BINDING);read('scripts/return_priority_next12_execution_v2.py')
 a['distribution_events']=actions['distribution_events'];a['child_instruments']=actions['child_instruments']
 expected=binding['superseded_guard_identity'];matched=[];remaining=[]
 for event in actions['unsupported_conversions']:
  if all(event[k]==expected[k] for k in ('date','old_sid','new_sid')):matched.append(event)
  else:remaining.append(event)
 if len(matched)!=1:raise ValueError('EXACT_SUPERSEDED_GUARD_NOT_FOUND')
 supported=binding['supported_unit_conversion_events']
 if len(supported)!=1 or supported[0]['date']!=expected['date'] or supported[0]['security_id']!=expected['old_sid'] or supported[0]['new_security_id']!=expected['new_sid']:raise ValueError('SUPPORTED_IDENTITY_MISMATCH')
 a.update(account_model=binding['account_model'],supported_conversions=supported,unsupported_conversions=remaining,superseded_unsupported_conversions=matched,conversion_unresolved=binding['unresolved'],conversion_limitations=binding['limitations'],superseded_code_pins=superseded,source_hashes=pins)
 a['required_exposure_guards']=[g for g in a['required_exposure_guards'] if not(g['date']==expected['date'] and g['security_id']==expected['old_sid'])]
 a['required_exposure_guards'].append(dict(date=expected['date'],security_id=expected['old_sid'],scope='ODD_ACTUAL_ADS_OR_UNSUPPORTED_CUSTODY_MODEL',reason='UNPRICED_FRACTION_OR_WRONG_DELIVERY_MODEL_MUST_BLOCK'))
 a['limitations']=[s for s in a['limitations'] if s!='Unsupported AZN conversion must block actual exposure, never imply automatic delivery.']+binding['limitations']
 for key in ['ohlc','metadata','windows','session_dates','source_provenance']:assert a[key]==old[key]
 assembled=assemble_monthly_execution_inputs_v4(a)
 if assembled.get('account_model')!=binding['account_model']:raise ValueError('HELPER_ACCOUNT_MODEL_NOT_WIRED')
 for key in ('actions','provider_actions'):
  found=[e for e in assembled[key] if e.get('type')=='ads_conversion']
  if found!=supported:raise ValueError('HELPER_SUPPORTED_EVENT_NOT_EXACTLY_ONCE:'+key)
 count=0
 for w in a['windows']:
  for sid,price in w['search_arguments']['prices'].items():assert Fraction(price)==Fraction(a['ohlc'][sid][w['decision_date']]['close']);count+=1
 summary=dict(status='V2_PURE_ASSEMBLY_PASS_NO_ECONOMIC_RUN',all_parent_child_ohlc_unchanged=True,all_search_arguments_unchanged=True,exact_decision_costs=count,source_pins=len(pins),supported_conversion_events=len(supported),remaining_unsupported=len(remaining),account_model=binding['account_model'],search_calls=0,book_calls=0)
 return a,summary
if __name__=='__main__':
 if OUTPUT.exists():raise ValueError('CREATE_ONLY_OUTPUT_EXISTS')
 a,summary=prepare();OUTPUT.mkdir()
 for name,value in [('prepared.json',a),('assembly_readback.json',summary)]:
  with (OUTPUT/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
 print(json.dumps(dict(path=str(OUTPUT/'prepared.json'),sha256=hashlib.sha256((OUTPUT/'prepared.json').read_bytes()).hexdigest(),**summary)))
