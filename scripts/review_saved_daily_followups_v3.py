"""Read saved current-advice captures, preserve per-observation review outcomes."""
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from collections import Counter
from scripts.audit_current_daily_followup_sources_v3 import audit
from data.strategy_followup_close_review_v1 import review_close


def review(root, *, capture_path):
    root=Path(root).resolve()
    audited=audit(root);valid={r['event_id'] for r in audited['rows'] if r['status']=='ARCHIVE_INTEGRITY_AND_TARGET_RECOMPUTED'}
    capture=Path(capture_path).resolve()
    assert capture.is_relative_to(root), 'CAPTURE_OUTSIDE_ROOT'
    complete=json.loads((capture/'complete.json').read_bytes());plan_raw=(capture/'plan.json').read_bytes()
    assert sha256(plan_raw).hexdigest()==complete['plan_sha256']
    plan=json.loads(plan_raw);daily={r['security_id']:r for r in complete['receipts'] if r['kind']=='daily'}
    official=[r for r in complete['receipts'] if r['kind']=='official'];assert len(official)==1
    official=official[0];official_raw=(capture/official['raw_path']).read_bytes()
    journal=root/'data/strategy_account/daily_advice_v1.sqlite3'
    with sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True) as db:
        events={key:(raw,digest) for key,raw,digest in db.execute('SELECT event_id,body,digest FROM advice_events')}
    now=datetime.now(timezone.utc);rows=[]
    for group in plan['groups']:
        sid=group['security_id'];receipt=daily[sid];raw=(capture/receipt['raw_path']).read_bytes()
        for item in group['observations']:
            observation=json.loads((root/'data/strategy_advice_followup/queue'/(item['observation_id']+'.json')).read_bytes())
            assert all(observation[k]==v for k,v in item.items())
            assert item['event_id'] in valid
            event_raw,event_hash=events[item['event_id']]
            assert sha256(event_raw).hexdigest()==event_hash==item['event_sha256']
            event=json.loads(event_raw);order=event['response']['new_orders'][observation['order_index']]
            assert order['security_id']==sid and order['side']==observation['side'] and order['limit_price']==observation['reference_limit'] and order['quantity']==observation['reference_quantity']
            archive=event['response']['evidence_archive'];folder=Path(archive['receipt_path']).parent
            receipt_raw=(folder/'receipt.json').read_bytes();assert sha256(receipt_raw).hexdigest()==archive['receipt_sha256']
            original=json.loads(receipt_raw);files={n:(folder/'sources'/(h+'.bin')).read_bytes() for n,h in original['source_sha256'].items()}
            assert all(sha256(body).hexdigest()==original['source_sha256'][name] for name,body in files.items())
            options=dict(observation=observation,baseline_inputs=json.loads(files[original['normalized_inputs_path']]),
                baseline_files=files,daily_bytes=raw,daily_receipt=receipt,official_bytes=official_raw,official_receipt=official,now=now)
            try:
                outcome=review_close(**options)
            except (ValueError,KeyError,TypeError) as error:
                outcome=dict(status='REVIEW_BLOCKED',observation_id=item['observation_id'],reason=str(error))
            rows.append(outcome)
    return dict(status='OFFLINE_REVIEW_NOT_PUBLISHED',observed_at=now.isoformat(),rows=rows,
        counts=dict(Counter(r['status'] for r in rows)),account_writes=False,network_calls=0,performance_computed=False)


