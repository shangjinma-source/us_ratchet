"""Bounded legacy capture inspection, no invented economic events."""
import gzip,json
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from scripts.research.review_downside_account_20261105 import read
ROOT=Path(__file__).resolve().parents[2]
SID='security:0001104506:457669307'
SOURCE='tmp/next12_missing_quote_capture_20261014_v1/INSM.response.bin'
EXPECTED='ab2e13fd75f88ed8f178d08c99ed21be7e656c0cf3f8996894139c32aa396ba7'
START='2023-12-29';END='2026-07-30'

def inspect_capture(raw,receipt,started,sessions):
    assert sha256(raw).hexdigest()==EXPECTED==receipt['raw_sha256'] and len(raw)==receipt['raw_bytes']
    assert raw[:2]==b'\x1f\x8b'
    decoded=gzip.decompress(raw)
    assert sha256(decoded).hexdigest()==receipt['decoded_sha256']
    assert receipt['http_status']==200 and receipt['status']=='RAW_CAPTURED_NOT_ADMITTED'
    assert receipt['request_url']==receipt['final_url']==started['request_url']
    assert receipt['started_at_utc']==started['started_at_utc'] and receipt['credentials_sent'] is False
    url=urlparse(receipt['request_url']);q=parse_qs(url.query)
    assert url.scheme=='https' and url.hostname=='query1.finance.yahoo.com' and url.path=='/v8/finance/chart/INSM'
    assert q['events']==['div,splits'] and q['interval']==['1d']
    chart=json.loads(decoded)['chart'];assert chart['error'] is None and len(chart['result'])==1
    result=chart['result'][0];assert result['meta']['symbol']=='INSM' and result['meta']['instrumentType']=='EQUITY'
    assert 'events' not in result and receipt['returned_events']=={}
    days=[datetime.fromtimestamp(t,timezone.utc).date().isoformat() for t in result['timestamp']]
    assert days==sorted(set(days)) and len(days)==receipt['rows'] and set(sessions)<=set(days)
    begin=datetime.fromtimestamp(int(q['period1'][0]),timezone.utc).date().isoformat()
    end=datetime.fromtimestamp(int(q['period2'][0]),timezone.utc).date().isoformat()
    assert begin<=START and end>END and days[0]<=START and days[-1]>=END
    quote=result['indicators']['quote'][0]
    for key in ('open','high','low','close'):
        assert len(quote[key])==len(days) and all(quote[key][days.index(d)] is not None and quote[key][days.index(d)]>0 for d in sessions)
    return dict(first_bar=days[0],last_bar=days[-1],verified_sessions=len(sessions),complete_gzip_crc_json=True,decoded_sha256=sha256(decoded).hexdigest(),request_start=begin,request_end_exclusive=end)

def main():
    docpath='tmp/old_continuous_baseline_20261026_v9/execution_inputs.json'
    document=read(ROOT/docpath);parent=read(ROOT/'tmp/downside_max10_20261105_late_v5/contract.json',True)
    assert document['prepared_input_candidate']['metadata'][SID]==dict(ticker='INSM',issuer_id='issuer:0001104506')
    sessions=document['assembled']['session_dates'];assert sessions[0]==START and sessions[-1]==END
    receiptname=SOURCE.replace('.response.bin','.receipt.json');startedname=SOURCE.replace('.response.bin','.started.json')
    checks=inspect_capture((ROOT/SOURCE).read_bytes(),read(ROOT/receiptname),read(ROOT/startedname),sessions)
    assert not any(e['ticker']=='INSM' for e in document['provider_event_inventory'])
    names=[SOURCE,receiptname,startedname,docpath,Path(__file__).relative_to(ROOT).as_posix()]
    pins={n:sha256((ROOT/n).read_bytes()).hexdigest() for n in names}
    for n in (SOURCE,docpath):assert pins[n]==parent['source_hashes'][n]
    row=dict(status='REVIEWED_NO_ACTION_FOR_PERIOD',security_id=SID,start_exclusive=START,end_inclusive=END,selected_price_sources=[SOURCE],source_references=[SOURCE,receiptname,startedname],evidence_strength='CONDITIONAL_SINGLE_CAPTURE_PROVIDER_DIV_SPLIT_ABSENCE_NOT_OFFICIAL_EXHAUSTIVE_CERTIFICATION')
    artifact=dict(schema='BOUNDED_PROVIDER_ABSENCE_V1',status='REVIEWED_CONDITIONAL_PROVIDER_ABSENCE',security_id=SID,source_hashes=pins,review_rows=[row],checks=checks,
        limitations=['Single existing provider capture, unlike WBD dual-capture corroboration.','Explicit div/splits request and complete gzip/JSON/647 session coverage; omitted events is conditional no-returned-event evidence, not universal no-action proof.','Receipt price_basis_authenticated and identity_authenticated remain false; this review only fills event-stream absence under existing frozen SID/price assumptions.','No dividends, split ratios, mergers, stock conversions or new economic events created. Known actions and any source change remain blockers.'])
    out=ROOT/'tmp/insm_absence_evidence_20261105/supplement.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(artifact,indent=2),encoding='utf8')
    print(out.relative_to(ROOT),sha256(out.read_bytes()).hexdigest(),checks)

if __name__=='__main__':main()
