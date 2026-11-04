"""Independent exact diff and raw-source verification of all2729 zero-event pairs."""
import json,gzip,hashlib,time
from pathlib import Path
from fractions import Fraction as F
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs,urlparse

ROOT=Path(__file__).resolve().parents[2]

def main():
    started=time.monotonic();base=ROOT/'tmp/risk_budget_pair_extension_20261105'
    path=base/'risk_inputs_zero_event_frontier_v1.json';extended=json.loads(path.read_bytes())
    parent_path=ROOT/extended['parent_artifact']['path']
    assert hashlib.sha256(parent_path.read_bytes()).hexdigest()==extended['parent_artifact']['sha256']
    parent=json.loads(parent_path.read_bytes());sources={};receipts={};checked=[]
    assert len(parent['windows'])==len(extended['windows'])==67
    for original,current in zip(parent['windows'],extended['windows']):
        copy=json.loads(json.dumps(current));evidence=copy.pop('extension_pair_evidence',[])
        for item in evidence:
            sid=item['security_id'];gross=copy['arguments']['stock_gross_returns'].pop(sid)
            assert sid not in original['arguments']['stock_gross_returns']
            assert (item['window'],item['decision_date'])==(original['window'],original['decision_date'])
            source=item['source'];receipt_path=item['receipt_path']
            if source not in sources:
                raw=(ROOT/source).read_bytes();assert hashlib.sha256(raw).hexdigest()==item['source_sha256']
                body=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=str)['chart']['result'][0]
                prices={datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat():F(body['indicators']['quote'][0]['close'][i])
                        for i,t in enumerate(body['timestamp']) if body['indicators']['quote'][0]['close'][i] is not None}
                sources[source]=(body,prices)
            body,prices=sources[source];assert body['meta']['symbol']==item['ticker']
            if receipt_path not in receipts:receipts[receipt_path]=json.loads((ROOT/receipt_path).read_bytes())
            receipt=receipts[receipt_path]
            if isinstance(receipt.get('rows'),list):
                matches=[r for r in receipt['rows'] if r.get('ticker')==item['ticker'] and r.get('sha256')==item['source_sha256']]
                assert len(matches)==1;receipt=matches[0]
            assert receipt['http_status']==200 and not receipt.get('body_truncated')
            assert receipt.get('raw_sha256',receipt.get('sha256'))==item['source_sha256']
            requested=parse_qs(urlparse(receipt.get('request_url',receipt.get('url',''))).query)['events'][0]
            assert {'div','splits'}<=set(requested.split(','))
            days=[item['first_close']]+sorted(gross);assert len(days)==64 and days[-1]==item['last_close']==original['decision_date']
            assert set(gross)==set(original['arguments']['qqq_gross_returns'])
            for events in body.get('events',{}).values():
                for event in events.values():
                    d=datetime.fromtimestamp(event['date'],ZoneInfo('America/New_York')).date().isoformat()
                    assert not days[0]<d<=days[-1]
            for prev,day in zip(days,days[1:]):assert F(gross[day])==prices[day]/prices[prev]
            checked.append(dict(window=original['window'],decision_date=original['decision_date'],security_id=sid,source=source,returns_checked=63))
        assert copy==original,'PARENT_ROW_CHANGED'
    assert len(checked)==2729 and len({(r['window'],r['decision_date'],r['security_id']) for r in checked})==2729
    for name,expected in extended['source_hashes'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name
    report=dict(status='INDEPENDENT_2729_PAIR_RAW_AND_PARENT_DIFF_PASS',parent=extended['parent_artifact'],
                extension_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pairs=checked,checked_returns=len(checked)*63,
                elapsed_seconds=time.monotonic()-started,network_calls=0,economic_runs=0,
                audit_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitations='Conditional provider no-reported-event windows only, not exhaustive corporate-action/PIT certification or trading performance.')
    (base/'zero_event_independent_review.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='pairs'}))

if __name__=='__main__':main()
