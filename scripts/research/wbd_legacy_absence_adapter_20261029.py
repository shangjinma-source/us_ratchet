"""Pinned WBD legacy receipt research adapter. Never modifies receipt bytes."""
from pathlib import Path
from hashlib import sha256
from copy import deepcopy
from datetime import datetime,timezone
from urllib.parse import urlparse,parse_qs
import json,gzip

SID='security:0001437107:934423104'
START='2023-12-29'
END='2026-07-30'
PINS = {'data/cache/research/current79_new_asof_capture_20260919_v1/WBD.response.bin': {'data/cache/research/current79_new_asof_capture_20260919_v1/WBD.response.bin': '5f376a5ee95adcc956b80e579e79084e2af6badb132d87bcbaf8c675de683622', 'data/cache/research/current79_new_asof_capture_20260919_v1/WBD.receipt.json': 'd6377bfb0a5e75cb9d5a521c22fd9e92c8fbe573102d482f712f1d3dc5d556b9', 'data/cache/research/current79_new_asof_capture_20260919_v1/WBD.started.json': 'c9016ac16510e9fe8f2a32797931efc5caf9dda08b437f9acf5d6ff0a1876d65'}, 'data/cache/research/new_cutoff_raw_capture_20260923_v1/WBD.response.bin': {'data/cache/research/new_cutoff_raw_capture_20260923_v1/WBD.response.bin': '55e9bdfa4d7d6c51a3d0795f6910d5cf175a32ea06afd2702131b233c951a145', 'data/cache/research/new_cutoff_raw_capture_20260923_v1/WBD.receipt.json': '23e9b2a9450c3e11ea339124eb817c890e104069956b194f981f71d57eda2cff', 'data/cache/research/new_cutoff_raw_capture_20260923_v1/WBD.started.json': '6da5947379047b19d35c91fa4a1575fb4e8162e436024a7d8446ff7af01971ec'}}

def need(ok, reason):
    if not ok:raise ValueError(reason)

def inspect(payload, receipt, started, *, required_sessions, expected_symbol='WBD'):
    need('body_truncated' not in receipt, 'EXACT_LEGACY_MISSING_FIELD_SCHEMA_REQUIRED')
    need(payload[:2]==b'\x1f\x8b', 'GZIP_REQUIRED')
    decoded=gzip.decompress(payload) # validates complete footer/CRC/size
    need(len(decoded)<=4000000,'BODY_TOO_LARGE')
    need(len(payload)==receipt['raw_bytes'] and sha256(payload).hexdigest()==receipt['raw_sha256'],'BODY_HASH_OR_SIZE')
    need(receipt['http_status']==200 and receipt['request_url']==started['request_url']==receipt['final_url'],'REQUEST_RECEIPT')
    url=urlparse(receipt['request_url']);query=parse_qs(url.query)
    need(url.scheme=='https' and url.hostname=='query1.finance.yahoo.com' and url.path=='/v8/finance/chart/'+expected_symbol,'SOURCE_IDENTITY')
    need(query.get('events')==['div,splits'] and query.get('interval')==['1d'],'EXPLICIT_EVENT_REQUEST')
    chart=json.loads(decoded)['chart'];need(chart['error'] is None and len(chart['result'])==1,'CHART_SUCCESS')
    result=chart['result'][0];need(result['meta']['symbol']==expected_symbol,'SYMBOL_MISMATCH')
    need('events' not in result,'EVENTS_PRESENT_REQUIRES_MAPPING')
    days=[datetime.fromtimestamp(t,timezone.utc).date().isoformat() for t in result['timestamp']]
    need(days==sorted(set(days)) and set(required_sessions)<=set(days),'INCOMPLETE_SESSION_COVERAGE')
    begin=datetime.fromtimestamp(int(query['period1'][0]),timezone.utc).date().isoformat()
    end=datetime.fromtimestamp(int(query['period2'][0]),timezone.utc).date().isoformat()
    need(begin<=START and end>END and min(days)<=START and max(days)>=END,'REQUEST_INTERVAL')
    quote=result['indicators']['quote'][0]
    for key in ('open','high','low','close'):
        need(len(quote[key])==len(days) and all(quote[key][days.index(d)] is not None for d in required_sessions),'MISSING_OHLC')
    return dict(first_bar=min(days),last_bar=max(days),verified_sessions=len(required_sessions),complete_gzip_crc_json=True)

def certify(root, sessions):
    root=Path(root);required=[d for d in sessions if START<=d<=END]
    need(required and required[0]==START and required[-1]==END,'FROZEN_CALENDAR_REQUIRED')
    checks=[]
    for source,pins in PINS.items():
        data={}
        for path,digest in pins.items():
            raw=(root/path).read_bytes();need(sha256(raw).hexdigest()==digest,'EXACT_LEGACY_SOURCE_PIN');data[path]=raw
        receipt_path=source.replace('.response.bin','.receipt.json');started_path=source.replace('.response.bin','.started.json')
        receipt=json.loads(data[receipt_path]);started=json.loads(data[started_path])
        need(receipt['started_sha256']==pins[started_path],'STARTED_PIN')
        checks.append(dict(source=source,**inspect(data[source],receipt,started,required_sessions=required)))
    need(len(checks)==2 and checks[0]['verified_sessions']==checks[1]['verified_sessions'],'TWO_CAPTURE_COVERAGE_REQUIRED')
    return dict(status='PINNED_LEGACY_PROVIDER_ABSENCE_REVIEW_PASS',security_id=SID,start_exclusive=START,end_inclusive=END,
                source_hashes={p:h for v in PINS.values() for p,h in v.items()},checks=checks,
                limitation='Same provider two captures; conditional div/split absence only. No official exhaustive absence; all explicit events and known barriers remain.')

def admit(gate, proof):
    need(proof['status']=='PINNED_LEGACY_PROVIDER_ABSENCE_REVIEW_PASS','PROOF_REQUIRED')
    result=deepcopy(gate);left=[];accepted=[]
    for item in result['missing_action_streams']:
        sources={r['source_path'] for r in item['selected_source_segments']}|{item['source']}
        if item['security_id']==SID and sources<=set(PINS) and START<=result['decision_date'] and result['exposure_end_by_security'][SID]<=END:
            accepted.append(item)
        else:left.append(item)
    result['missing_action_streams']=left
    result['legacy_absence_evidence']=dict(proof=proof,accepted=accepted)
    result['admitted']=not left and not result['unmapped_events']
    return result
