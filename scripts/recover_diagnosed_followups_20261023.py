"""One bounded recovery pass over a fixed diagnosed batch; stop on first failure."""
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import json
from pathlib import Path
from scripts.capture_followup_evidence import run, reason
from data.current_quantity_v2_followup_provider import FollowupBundleProvider


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='tmp/followup_recovery_remaining_20261023_v1')
    args=parser.parse_args()
    root=Path.cwd();out=(root/args.output).resolve()
    assert out.is_relative_to(root/'tmp')
    out.mkdir()
    diagnosis_path=root/'tmp/legacy_followup_rss_diagnosis_20261023_v1.json'
    diagnosis_raw=diagnosis_path.read_bytes();diagnosis=json.loads(diagnosis_raw)
    batch=json.loads((root/'data/quantity_v2_followup/batch_runner/runs/d8178a53f6b545189bec8f85ad9930ac/complete.json').read_bytes())
    events=[event for page in batch['pages'] for event in page['events'] if event.get('reason')=='MATURED_HORIZON_UNRESOLVED']
    assert len(events)==34
    provider=FollowupBundleProvider(repository_root=root);results=[]
    def save(name,value):
        body=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
        with (out/name).open('xb') as stream:stream.write(body)
        return sha256(body).hexdigest()
    save('started.json',dict(started_at=datetime.now(timezone.utc).isoformat(),events=len(events),account_writes=False))
    for index,event in enumerate(events):
        event_hash=event['event_sha256'];day,event_file=event['event'].split('/')
        original=root/'data/quantity_v2_followup/attempts'/event_hash/'2026-10-22'
        started=json.loads((original/'started.json').read_bytes())
        options=dict(root=root,event_day=day,event_id=event_file[:-5],event_sha256=event_hash,**started['binding'])
        preflight=run(**options,execute=False)
        if preflight['status']=='ALREADY_COVERED':
            result=dict(event_sha256=event_hash,status='ALREADY_COVERED')
        else:
            assert preflight['status']=='NEEDS_RECOVERY' and preflight['reason']=='PRIOR_CAPTURE_FAILED_REQUIRES_REVIEW'
            assert preflight['session']=='2026-10-22'
            rows=[row for row in diagnosis['rows'] if row['event_sha256']==event_hash]
            assert rows
            kind='RSS_NON_XML_RESPONSE' if all('parse_error' in row for row in rows) else 'RSS_FUTURE_PUBLICATION'
            pins={name:sha256((original/name).read_bytes()).hexdigest() for name in ['started.json','failed.json','review.json']}
            request=dict(schema='FOLLOWUP_CAPTURE_RECOVERY_V1',event_sha256=event_hash,session=preflight['session'],
                expected_manifest_sha256=preflight['expected_manifest_sha256'],prior_files=pins,diagnosis=kind,
                diagnosis_reference=dict(path=diagnosis_path.relative_to(root).as_posix(),sha256=sha256(diagnosis_raw).hexdigest()))
            name=f'{index:02d}-request.json';digest=save(name,request)
            try:
                result=run(**options,recovery_path=(out/name).relative_to(root).as_posix(),recovery_sha256=digest,execute=True)
                assert result['status']=='FOLLOWUP_PUBLISHED'
                assert all(sha256((original/n).read_bytes()).hexdigest()==h for n,h in pins.items())
                raw=(root/'data/quantity_v2_observations/events'/event['event']).read_bytes()
                readback=provider.review(event_raw=raw,binding=started['binding'],now=datetime.now(timezone.utc))
                assert readback['bundle_sha256']==result['manifest_sha256']
                assert all(h['status']=='CONDITIONAL_PRICE_CHANGE' for order in readback['orders'] for h in order['horizons'] if h['sessions_after_reference'] in result['matured_horizons'])
                save(f'{index:02d}-readback.json',readback)
                result.update(event_sha256=event_hash,readback_verified=True,original_attempt_unchanged=True)
            except Exception as error:
                result=dict(event_sha256=event_hash,status='STOPPED',reason=reason(error))
        save(f'{index:02d}-result.json',result);results.append(result)
        print(json.dumps(dict(index=index,status=result['status'])),flush=True)
        if result['status']=='STOPPED':break
    final=dict(finished_at=datetime.now(timezone.utc).isoformat(),results=results,
        published=sum(r['status']=='FOLLOWUP_PUBLISHED' for r in results),
        already_covered=sum(r['status']=='ALREADY_COVERED' for r in results),
        stopped=any(r['status']=='STOPPED' for r in results),account_writes=False)
    save('complete.json',final)
    print(json.dumps({key:value for key,value in final.items() if key!='results'}),flush=True)


if __name__=='__main__':main()
