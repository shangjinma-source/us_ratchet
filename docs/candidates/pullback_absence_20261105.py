"""Two scoped captured-provider absence reviews. Not official exhaustive actions."""
from pathlib import Path
import json,importlib.util
from types import FunctionType
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2]
LEGACY='tmp/two_stage_bull_bear_20261029/wbd_local_review/legacy_absence_adapter.py'
LEGACY_SHA='2016ac8bfc802ae3042bd7592e3a897bcb0568c88a79161a8de05d58dc8f3aa5'
SCOPES=[('security:0000935703:256746108','DLTR','2024-03-01','2024-03-08'),('security:0001097864:682189105','ON','2024-05-28','2024-05-29')]
def need(ok,reason):
 if not ok:raise ValueError(reason)
def append_review(document,review):
 need(sha256((ROOT/LEGACY).read_bytes()).hexdigest()==LEGACY_SHA,'VALIDATOR_PIN')
 spec=importlib.util.spec_from_file_location('pullback_original_absence',ROOT/LEGACY);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 pins={LEGACY:LEGACY_SHA};rows=[]
 for sid,ticker,start,end in SCOPES:
  source='tmp/fixed12_extended_quote_capture_20261014_v1/'+ticker+'.response.bin';receipt_path=source.replace('.response.bin','.receipt.json');started_path=source.replace('.response.bin','.started.json')
  raw=(ROOT/source).read_bytes();need(sha256(raw).hexdigest()==document['source_hashes'][source],'FROZEN_RAW_SOURCE')
  receipt=json.loads((ROOT/receipt_path).read_bytes());started=json.loads((ROOT/started_path).read_bytes())
  need(receipt['credentials_sent'] is False and receipt['started_at_utc']==started['started_at_utc'],'REQUEST_LIFECYCLE')
  need(document['prepared_input_candidate']['metadata'][sid]['ticker']==ticker,'SID_IDENTITY')
  namespace=dict(m.inspect.__globals__);namespace.update(START=start,END=end);f=FunctionType(m.inspect.__code__,namespace,m.inspect.__name__,m.inspect.__defaults__);f.__kwdefaults__=m.inspect.__kwdefaults__
  sessions=[d for d in document['assembled']['session_dates'] if start<=d<=end];check=f(raw,receipt,started,required_sessions=sessions,expected_symbol=ticker)
  for path in (source,receipt_path,started_path):pins[path]=sha256((ROOT/path).read_bytes()).hexdigest()
  rows.append(dict(status='REVIEWED_NO_ACTION_FOR_PERIOD',security_id=sid,ticker=ticker,start_exclusive=start,end_inclusive=end,selected_price_sources=[source],source_references=[source,receipt_path,started_path],request_checks=[dict(source=source)],capture_checks=check,limitation='Single provider capture; exact div/split request and complete payload, not exhaustive official actions or authenticated identity/price units.'))
 review['rows'].extend(rows);review['source_hashes'].update(pins)
 return dict(rows=rows,source_hashes=pins)
