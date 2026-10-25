"""Inspect preserved failed captures; never retry or replace their evidence."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from scripts.current_research_official_alert_capture import parse_official_feed


def diagnose(root):
    storage=Path(root)/'data/quantity_v2_followup'
    batch=json.loads((storage/'batch_runner/runs/d8178a53f6b545189bec8f85ad9930ac/complete.json').read_bytes())
    failed={event['event_sha256'] for page in batch['pages'] for event in page['events']
            if event.get('reason')=='MATURED_HORIZON_UNRESOLVED'}
    rows=[]
    for manifest_path in sorted((storage/'bundles').glob('*/manifest.json')):
        raw=manifest_path.read_bytes(); manifest=json.loads(raw)
        if manifest.get('event_sha256') not in failed:continue
        assert sha256(raw).hexdigest()==manifest_path.parent.name
        if not any(row['date']=='2026-10-22' for row in manifest['daily_observations']):continue
        sources=manifest_path.parent/'sources'
        def read(name):
            path=(sources/name).resolve()
            assert path.is_relative_to(sources.resolve())
            body=path.read_bytes()
            assert sha256(body).hexdigest()==manifest['source_hashes'][name]
            return body
        for security_id,evidence in manifest['action_evidence'].items():
            receipt=json.loads(read(evidence['rss_receipt_path']))
            feed_raw=read(evidence['rss_raw_path'])
            assert receipt['raw_sha256']==sha256(feed_raw).hexdigest()
            try:
                feed=parse_official_feed(feed_raw,observed_at=datetime.fromisoformat(receipt['received_at']))
            except ET.ParseError as error:
                rows.append(dict(event_sha256=manifest['event_sha256'],bundle_sha256=manifest_path.parent.name,
                    security_id=security_id,captured_at=receipt['received_at'],rss_sha256=sha256(feed_raw).hexdigest(),
                    parse_error=str(error),invalid_items=[]))
                continue
            invalid=[dict(index=item['index'],title=item['title'],pubDate=item['pubDate'],
                publication_time_issue=item['publication_time_issue'],future_publication=item['future_publication'],
                description_truncated=item['description_truncated']) for item in feed['items']
                if item['publication_time_issue'] or item['future_publication'] is not False or item['description_truncated']]
            rows.append(dict(event_sha256=manifest['event_sha256'],bundle_sha256=manifest_path.parent.name,
                security_id=security_id,captured_at=receipt['received_at'],rss_sha256=sha256(feed_raw).hexdigest(),
                channel=feed['channel'],invalid_items=invalid))
    return dict(observed_at=datetime.now(timezone.utc).isoformat(),expected_failed_events=len(failed),
        inspected_events=len({row['event_sha256'] for row in rows}),rows=rows,
        invalid_titles=dict(Counter(item['title'] for row in rows for item in row['invalid_items'])),
        failed_markers_changed=False,retries=0,network_calls=0,
        conclusion='Saved RSS item publication later than capture remains invalid at original capture time; a later clock cannot cure it.')


if __name__=='__main__':
    result=diagnose(Path.cwd())
    with Path('tmp/legacy_followup_rss_diagnosis_20261023_v1.json').open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({key:value for key,value in result.items() if key!='rows'},ensure_ascii=False))
