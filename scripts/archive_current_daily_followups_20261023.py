"""Re-review and archive current observations with their original evidence."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from scripts.review_current_daily_followups_20261023 import review
from data.strategy_followup_result_store_v1 import publish,read_observation


def run(root):
    root=Path(root).resolve();result=review(root)
    assert result['counts']=={'CONDITIONAL_PRICE_OBSERVATION':52}
    sources={}
    def add(name,raw):
        assert name not in sources or sources[name]==raw
        sources[name]=raw
    capture=root/'tmp/current_daily_followup_raw_20261023_v1'
    for path in capture.iterdir():
        if path.is_file():add('capture/'+path.name,path.read_bytes())
    journal=root/'data/strategy_account/daily_advice_v1.sqlite3'
    with sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True) as db:
        events={event_id:(raw,digest) for event_id,raw,digest in db.execute('SELECT event_id,body,digest FROM advice_events')}
    for row in result['rows']:
        path=root/'data/strategy_advice_followup/queue'/(row['observation_id']+'.json')
        raw=path.read_bytes();observation=json.loads(raw);add('observations/'+path.name,raw)
        event_raw,event_hash=events[observation['event_id']]
        assert sha256(event_raw).hexdigest()==event_hash==observation['event_sha256']
        add('events/'+event_hash+'.json',event_raw)
        event=json.loads(event_raw);archive=event['response']['evidence_archive'];folder=Path(archive['receipt_path']).parent
        receipt_raw=(folder/'receipt.json').read_bytes();assert sha256(receipt_raw).hexdigest()==archive['receipt_sha256']
        receipt=json.loads(receipt_raw);add('original-receipts/'+archive['receipt_sha256']+'.json',receipt_raw)
        for name,pin in receipt['source_sha256'].items():
            body=(folder/'sources'/(pin+'.bin')).read_bytes();assert sha256(body).hexdigest()==pin
            add('original-sources/'+pin+'.bin',body)
    for name in ('data/strategy_followup_close_review_v1.py','data/strategy_followup_price_basis_v1.py',
        'scripts/review_current_daily_followups_20261023.py','scripts/audit_daily_followup_sources_20261023.py',
        'research_contracts/daily_calendar_2026_extension_v1/calendar.candidate.json'):
        add(name,(root/name).read_bytes())
    directory=root/'data/strategy_advice_followup/results'
    archived=publish(directory,rows=result['rows'],sources=sources)
    # Independently traverse the public index, completion marker and copied
    # sources for every observation; no tmp source is needed by this reader.
    for row in result['rows']:assert read_observation(directory,row['observation_id'])==row
    return dict(archived,readback_verified=True,source_documents=len(sources),source_bytes=sum(map(len,sources.values())),
        actual_fill_inferred=False,performance_computed=False,frontend_connected=False)


if __name__=='__main__':
    result=run(Path.cwd())
    with Path('tmp/current_daily_followup_archive_20261023_v1.json').open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(result))
