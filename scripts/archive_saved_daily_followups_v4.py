"""Re-review and archive current observations with their original evidence."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from scripts.review_saved_daily_followups_v4 import review
from data.strategy_followup_result_store_v1 import publish,read_observation


def collect_historical_sources(*, root, checked, original_sources):
    """Build a self-contained immutable source map; caller publishes with its manifest."""
    result={};provenance=checked.get('historical_provenance')
    if not provenance:return result
    for name,pin in provenance['materialized_sha256'].items():
        body=original_sources.get(name)
        if body is None:
            cached=root/'data/cache/followup_historical_sources'/(pin+'.bin')
            source=cached if cached.exists() else root/name
            from data.strategy_followup_historical_reader_v1 import safe_path
            source=safe_path(root,source.absolute().relative_to(root.absolute()))
            assert source.stat().st_size<=32*1024*1024,'HISTORICAL_ARCHIVE_COPY_SIZE'
            body=source.read_bytes()
        assert sha256(body).hexdigest()==pin,'HISTORICAL_ARCHIVE_COPY_CHANGED'
        result['historical-materialized/'+pin+'.bin']=body
    for name,pin in provenance['preparation_chain'].items():
        from data.strategy_followup_historical_reader_v1 import safe_path
        source=safe_path(root,name);assert source.stat().st_size<=1024*1024
        body=source.read_bytes();assert sha256(body).hexdigest()==pin
        result['historical-preparations/'+pin+'.json']=body
    return result


def run(root, *, capture_path):
    root=Path(root).resolve();result=review(root,capture_path=capture_path)
    assert result['rows'] and set(result['counts'])=={'CONDITIONAL_PRICE_OBSERVATION'}, 'REVIEW_NOT_COMPLETE'
    sources={}
    def add(name,raw):
        assert name not in sources or sources[name]==raw
        sources[name]=raw
    capture=Path(capture_path).resolve()
    for path in capture.iterdir():
        if path.is_file():add('capture/'+path.name,path.read_bytes())
    journal=root/'data/strategy_account/daily_advice_v1.sqlite3'
    with sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True) as db:
        events={event_id:(raw,digest) for event_id,raw,digest in db.execute('SELECT event_id,body,digest FROM advice_events')}
    reviewed_sources={row['event_id']:row for row in result['source_reviews']}
    archived_events=set()
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
        if observation['event_id'] not in archived_events:
            checked=reviewed_sources[observation['event_id']]
            add('independent-source-reviews/'+observation['event_id']+'.json',json.dumps(checked,sort_keys=True).encode('utf-8'))
            original_sources={name:(folder/'sources'/(pin+'.bin')).read_bytes() for name,pin in receipt['source_sha256'].items()}
            for name,body in collect_historical_sources(root=root,checked=checked,original_sources=original_sources).items():add(name,body)
            for leaf,key in [('manifest.json','manifest_sha256'),('complete.json',None)]:
                body=(folder/leaf).read_bytes()
                if key:assert sha256(body).hexdigest()==archive[key]
                add('original-archive-markers/'+archive['receipt_sha256']+'/'+leaf,body)
            archived_events.add(observation['event_id'])
    for name in ('data/strategy_followup_frontier_source_v1.py','data/strategy_followup_historical_reader_v1.py',
        'data/saved_frontier_source_review_v1.py','data/frontier_monthly_peak_raw_history_v1.py','data/saved_frontier_first_window_v1.py','data/monthly_peak_raw_history.py','data/monthly_peak_exit_history.py','core/monthly_peak_exit.py','data/strategy_advice_followup_plan_v3.py','data/strategy_followup_close_review_v2.py','data/strategy_followup_price_basis_v2.py','data/strategy_followup_close_review_v1.py','data/strategy_followup_price_basis_v1.py',
        'data/strategy_followup_cap_source_v2.py','data/strategy_followup_supplement_authorization_v1.py',
        'scripts/review_saved_daily_followups_v4.py','scripts/audit_current_daily_followup_sources_v4.py','scripts/audit_legacy_daily_followup_sources_v2.py','data/strategy_followup_cap_source_v1.py','data/strategy_followup_cap_replay_v1.py','data/strategy_followup_authorization_v1.py','data/strategy_advice_followup_plan_v2.py','data/strategy_followup_execution_binding_v1.py',
        'research_contracts/daily_calendar_2026_extension_v1/calendar.candidate.json'):
        add(name,(root/name).read_bytes())
    directory=root/'data/strategy_advice_followup/results'
    archived=publish(directory,rows=result['rows'],sources=sources)
    # Independently traverse the public index, completion marker and copied
    # sources for every observation; no tmp source is needed by this reader.
    for row in result['rows']:assert read_observation(directory,row['observation_id'])==row
    return dict(archived,readback_verified=True,source_documents=len(sources),source_bytes=sum(map(len,sources.values())),
        actual_fill_inferred=False,performance_computed=False,frontend_connected=False)
