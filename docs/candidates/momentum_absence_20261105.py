"""Five fixed capture/interval absence reviews; never synthesizes receipts."""
import gzip, json, importlib.util
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import FunctionType
from scripts.run_old_continuous_probe_v4 import validate_absence_review, admit_period_absence
ROOT=Path(__file__).resolve().parents[2]
INSPECTION='tmp/momentum_absence_inspection_20261105/inspection.json'
INSPECTION_SHA='daa1b83d03a28e486a6fa8d03a6980379b8358fa37fb7451f91bfdbf47d072bc'
LEGACY='tmp/two_stage_bull_bear_20261029/wbd_local_review/legacy_absence_adapter.py'
LEGACY_SHA='2016ac8bfc802ae3042bd7592e3a897bcb0568c88a79161a8de05d58dc8f3aa5'

def need(condition,reason):
    if not condition:raise ValueError(reason)

def normalize(document):
    raw=(ROOT/INSPECTION).read_bytes();need(sha256(raw).hexdigest()==INSPECTION_SHA,'FIXED_INSPECTION_CHANGED')
    report=json.loads(raw);pins=report['source_hashes']
    for path,digest in pins.items():need(sha256((ROOT/path).read_bytes()).hexdigest()==digest,'SOURCE_PIN_CHANGED:'+path)
    need(sha256((ROOT/LEGACY).read_bytes()).hexdigest()==LEGACY_SHA,'LEGACY_VALIDATOR_CHANGED')
    spec=importlib.util.spec_from_file_location('fixed_momentum_legacy',ROOT/LEGACY);legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
    rows=[]
    for record in report['records']:
        sid=record['security_id'];source=record['source'];ticker=record['ticker'];start=record['start'];end=record['end']
        need(document['prepared_input_candidate']['metadata'][sid]['ticker']==ticker,'FROZEN_SID_IDENTITY')
        need(document['source_hashes'][source]==pins[source],'EXECUTION_SOURCE_CHANGED')
        receipt_path=source.replace('.response.bin','.receipt.json');started_path=source.replace('.response.bin','.started.json')
        receipt=json.loads((ROOT/receipt_path).read_bytes());started=json.loads((ROOT/started_path).read_bytes());payload=(ROOT/source).read_bytes()
        need(payload[:2]==b'\x1f\x8b','GZIP_REQUIRED');decoded=gzip.decompress(payload)
        need(len(payload)==receipt['raw_bytes'] and sha256(payload).hexdigest()==receipt['raw_sha256'] and receipt['started_at_utc']==started['started_at_utc'] and receipt['credentials_sent'] is False,'REQUEST_BINDING')
        if 'decoded_sha256' in receipt:need(sha256(decoded).hexdigest()==receipt['decoded_sha256'],'DECODED_HASH')
        result=json.loads(decoded)['chart']['result'][0]
        need('events' not in result and result['meta']['instrumentType']=='EQUITY','EXPLICIT_ACTION_OR_NON_EQUITY')
        days=[datetime.fromtimestamp(t,timezone.utc).date().isoformat() for t in result['timestamp']]
        sessions=[d for d in document['assembled']['session_dates'] if start<=d<=end]
        need(len(sessions)==record['sessions_checked'] and sessions[0]==start and sessions[-1]==end and days==sorted(set(days)) and set(sessions)<=set(days),'EXACT_SCOPE_COVERAGE')
        for key in ('open','high','low','close'):
            values=result['indicators']['quote'][0][key]
            need(len(values)==len(days) and all(values[days.index(d)] is not None and values[days.index(d)]>0 for d in sessions),'POSITIVE_OHLC')
        if 'rows' in receipt:need(receipt['rows']==len(days),'RECEIPT_ROWS')
        if 'returned_events' in receipt:need(receipt['returned_events']=={},'RECEIPT_EVENTS')
        row=dict(status='REVIEWED_NO_ACTION_FOR_PERIOD',security_id=sid,ticker=ticker,start_exclusive=start,end_inclusive=end,selected_price_sources=[source],source_references=[source,receipt_path,started_path],request_checks=[dict(source=source)])
        if record['legacy_receipt']:
            # Reuse exact validated inspector with isolated interval globals only.
            namespace=dict(legacy.inspect.__globals__);namespace.update(START=start,END=end)
            inspector=FunctionType(legacy.inspect.__code__,namespace,legacy.inspect.__name__,legacy.inspect.__defaults__);inspector.__kwdefaults__=legacy.inspect.__kwdefaults__
            row['capture_checks']=inspector(payload,receipt,started,required_sessions=sessions,expected_symbol=ticker)
        else:
            validate_absence_review(row,dict(source_hashes=pins),document)
            row['capture_checks']=dict(first_bar=days[0],last_bar=days[-1],verified_sessions=len(sessions),complete_gzip_crc_json=True)
        row['receipt_fields_not_present']=[k for k in ('body_truncated','rows','returned_events') if k not in receipt]
        rows.append(row)
    need(len(rows)==5 and len({r['security_id'] for r in rows})==5,'FIVE_ONLY')
    return dict(rows=rows,source_hashes={**pins,INSPECTION:INSPECTION_SHA,LEGACY:LEGACY_SHA},limitation='Five fixed captures and bounded intervals only. Conditional provider div/split absence, not complete corporate actions or identity certification. No receipt fields fabricated, no financial events.')

def append_review(document,review):
    proof=normalize(document)
    for row in proof['rows']:
        need(not any(x.get('security_id')==row['security_id'] and x.get('status')==row['status'] and x.get('start_exclusive')==row['start_exclusive'] for x in review['rows']),'DUPLICATE_ABSENCE')
    for path,digest in proof['source_hashes'].items():need(path not in review['source_hashes'] or review['source_hashes'][path]==digest,'REVIEW_PIN_CONFLICT')
    review['rows'].extend(deepcopy(proof['rows']));review['source_hashes'].update(proof['source_hashes'])
    return proof
