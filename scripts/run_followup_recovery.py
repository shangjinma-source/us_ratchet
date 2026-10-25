"""Explicit failed-followup recovery. Separate output, original target, current capture.

Reuses sealed transport/decoder/review/CAS primitives, never calls old run().
Default is read-only. Failed or partial recovery is terminal and cannot retry.
"""
from datetime import datetime, timezone
from pathlib import Path
from fractions import Fraction
from zoneinfo import ZoneInfo
import argparse, json, os
from scripts.capture_followup_evidence import (canonical, parse, safe_path, read_bytes, STORAGE,
    MAX_FILES, MAX_TOTAL, digest, save, require, reason, preserve_progress,
    FollowupBundleProvider, PaperActionEvidenceSources, capture_saved_close, default_fetch,
    fetch_daily_actions, fetch_official_feed, review_reference_followup, CALENDAR, CALENDAR_SHA)
from scripts.preflight_followup_recovery import preflight
from data.current_research_saved_quote import read_saved_quote


def now(): return datetime.now(timezone.utc)


class PublicationAttention(RuntimeError):
    """Publication may have committed; callers must not classify this as retryable."""
    def __init__(self, receipt):
        self.receipt=receipt
        super().__init__(receipt['status'])


def index_evidence(index, root):
    evidence=dict(path=index.relative_to(root).as_posix(),exists=index.exists(),
        lock_exists=index.with_suffix('.lock').exists(),pending_exists=index.with_suffix('.pending').exists())
    try:
        if index.exists():
            raw=read_bytes(index,4096);evidence['sha256']=digest(raw)
            evidence['manifest_sha256']=parse(raw).get('manifest_sha256')
    except Exception as error:evidence['read_error']=reason(error)
    return evidence


def verify_sources(root, pins):
    for path,h in pins.items():
        require(digest(read_bytes(safe_path(root,path),32*1024*1024))==h,'RECOVERY_SOURCE_DRIFT')


def publish_exact_index(*, index, expected_index_sha256, expected_manifest, new_manifest, root, pins):
    """Reuse sealed create-only persistence; add byte-hash CAS inside the lock."""
    lock=index.with_suffix('.lock');lock.parent.mkdir(parents=True,exist_ok=True)
    save(lock,b'FOLLOWUP_RECOVERY_EXACT_INDEX_CAS')
    try:
        raw=read_bytes(index,4096) if index.exists() else None
        require((digest(raw) if raw is not None else None)==expected_index_sha256,'INDEX_HASH_CONFLICT')
        require((parse(raw)['manifest_sha256'] if raw is not None else None)==expected_manifest,'INDEX_CAS_CONFLICT')
        verify_sources(root,pins)
        pending=index.with_suffix('.pending');save(pending,canonical(dict(manifest_sha256=new_manifest)))
        os.replace(pending,index)
    finally:lock.unlink()


def compare_daily(*, root, old_directory, old_manifest, new_directory, observations, closes):
    """Conflicts against both failed evidence and any already-published bundle."""
    new_by_key={(r['security_id'],r['date']):r for r in observations}
    for prior in old_manifest['daily_observations']:
        key=(prior['security_id'],prior['date']);require(key in new_by_key,'DAILY_COVERAGE_REGRESSION')
        current=new_by_key[key];require(current['ticker']==prior['ticker'],'DAILY_IDENTITY_CONFLICT')
        def quote_at(base,item):
            return read_saved_quote(root=base,ticker=item['ticker'],expected_security_type='EQUITY',
                entry=item['entry'],relative_directory=item['relative_directory'],decision_date=item['date'],
                decision_session_close_at=closes[item['date']])['ohlc']
        left=quote_at(old_directory/'sources',prior);right=quote_at(new_directory/'sources',current)
        require(all(Fraction(left[k])==Fraction(right[k]) for k in ('open','high','low','close')),'HISTORICAL_DATA_CONFLICT')


def run(*,root,request,expected_request_sha256=None,execute=False,clock=now,fetch=default_fetch,
        action_fetch=fetch_daily_actions,rss_fetch=fetch_official_feed):
    root=Path(root).resolve();observed=clock()
    plan=preflight(root=root,request=request,observed_at=observed)
    if not execute:return plan
    require(expected_request_sha256==plan['request_sha256'],'EXACT_RECOVERY_REQUEST_HASH_REQUIRED')
    target=plan['target_session'];binding=plan['binding'];securities=plan['securities']
    matured=plan['matured_horizons'];pins=plan['validated_source_hashes']
    refs=request['evidence'];event_hash=refs['event']['sha256']
    event_raw=read_bytes(safe_path(root,refs['event']['path']),1024*1024);event=parse(event_raw)
    original=datetime.fromisoformat(event['observed_at'])
    failed_directory=safe_path(root,refs['bundle']['path']).parent
    failed_manifest=parse(read_bytes(failed_directory/'manifest.json',4*1024*1024))
    event_path=failed_manifest['event_path'];chain_sources=failed_manifest.get('trusted_chain_sources',{})
    files={name:read_bytes(safe_path(failed_directory/'sources',name),32*1024*1024)
        for name in failed_manifest['source_hashes'] if not name.startswith(('daily/','paper-action-capture/'))}
    calendar=parse(files[CALENDAR]);session=original.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    closed=[d for d in calendar['calendar'] if session<d<=target]
    expected=plan['previous_manifest_sha256'];storage=root/STORAGE
    index=safe_path(storage,'index/'+digest(canonical(binding))+'/'+event_hash+'.json')
    old=FollowupBundleProvider(repository_root=root).review(event_raw=event_raw,binding=binding,now=observed)
    require(old['status']!='BLOCKED_BUNDLE_VALIDATION' and old.get('bundle_sha256')==expected,'PUBLISHED_BUNDLE_INVALID_OR_CHANGED')
    published_manifest=None
    if expected:
        published_directory=storage/'bundles'/expected
        published_manifest=parse(read_bytes(published_directory/'manifest.json',4*1024*1024))
        pins=dict(pins)
        pins[(published_directory/'manifest.json').relative_to(root).as_posix()]=expected
        for path,h in published_manifest['source_hashes'].items():
            pins[(published_directory/'sources'/path).relative_to(root).as_posix()]=h
    verify_sources(root,pins)
    attempt=safe_path(root,plan['recovery_directory'])
    # The target-level reservation prevents concurrent differently named recoveries.
    cursor=attempt
    while cursor != root:
        require(not cursor.is_symlink() and not (hasattr(cursor,'is_junction') and cursor.is_junction()),'RECOVERY_PATH_ALIAS_REJECTED')
        cursor=cursor.parent
    attempt.parent.mkdir(parents=True,exist_ok=False)
    attempt.mkdir()
    started=dict(plan,status='RECOVERY_STARTED',started_at=observed.isoformat(),old_attempt=refs['failed']['path'].rsplit('/',1)[0])
    save(attempt/'request.json',canonical(request));save(attempt/'started.json',canonical(started))
    publication_attempted=False;publication_returned=False;bundle_hash=None
    try:
        observations=[]
        for ordinal,security in enumerate(securities):
            directory=(attempt/('daily-'+str(ordinal))).relative_to(root).as_posix()
            manifest=dict(schema='SAVED_CLOSE_CAPTURE_MANIFEST_V1',session=target,history_start_date=session,
                calendar_path=CALENDAR,calendar_source_hashes={CALENDAR:CALENDAR_SHA,**calendar['source_hashes']},
                securities=[security],output_directory=directory)
            path=attempt/('capture-'+str(ordinal)+'.json');raw=canonical(manifest);save(path,raw)
            result=capture_saved_close(path.relative_to(root).as_posix(),digest(raw),root=root,capture=True,fetch=fetch,clock=clock)
            entry=result['entries'][0];require(entry['status']=='SAVED_EXACT_SESSION_READER_VALIDATED_NOT_ADMITTED','DAILY_CAPTURE_FAILED')
            for suffix in ('.response.bin','.receipt.json','.decoded.json'):
                files['daily/'+str(ordinal)+'/'+security['ticker']+suffix]=read_bytes(root/directory/(security['ticker']+suffix),32*1024*1024)
            observations.extend(dict(security_id=security['security_id'],ticker=security['ticker'],date=d,
                relative_directory='daily/'+str(ordinal),entry=entry) for d in closed)
        number=[0]
        def retained(kind,function,*args,**kwargs):
            ordinal=number[0];number[0]+=1
            try:
                response=function(*args,**kwargs);body=response.get('body')
                if isinstance(body,bytes):save(attempt/f'{kind}-{ordinal}.raw',body)
                save(attempt/f'{kind}-{ordinal}.transport.json',canonical(dict(status=response.get('status'),received_at=clock().isoformat())))
                return response
            except Exception as error:
                save(attempt/f'{kind}-{ordinal}.failed.json',canonical(dict(error_type=type(error).__name__,reason=reason(error),at=clock().isoformat())));raise
        action=PaperActionEvidenceSources(fetch=lambda *a,**k:retained('actions',action_fetch,*a,**k),
            rss_fetch=lambda:retained('rss',rss_fetch),clock=clock).capture(dict(account_id='followup:'+event_hash,
            state_revision=event_hash,window_start=original.isoformat(),observed_floor=original.isoformat(),
            securities={s['security_id']:{'ticker':s['ticker']} for s in securities},current_target_quantities={}))
        files.update(action['files']);documents=action['documents']
        evidence={s['security_id']:dict(daily_receipt_path=documents['action_receipts'][s['security_id']],
            rss_raw_path=documents['rss_raw'],rss_receipt_path=documents['rss_receipt']) for s in securities}
        require(len(files)<=MAX_FILES and sum(map(len,files.values()))<=MAX_TOTAL,'BUNDLE_SIZE_LIMIT')
        source_hashes={p:digest(raw) for p,raw in files.items()}
        manifest=dict(schema='V2_FOLLOWUP_BUNDLE_V1',binding=binding,event_path=event_path,event_sha256=event_hash,
            source_hashes=source_hashes,trusted_chain_sources=chain_sources,daily_observations=observations,action_evidence=evidence)
        raw=canonical(manifest);bundle_hash=digest(raw);directory=storage/'bundles'/bundle_hash
        require(not directory.exists(),'BUNDLE_ALREADY_EXISTS');save(directory/'manifest.json',raw)
        for name,content in files.items():save(safe_path(directory/'sources',name),content)
        reviewed=review_reference_followup(root=directory/'sources',binding=binding,event_path=event_path,
            files=files,source_hashes=source_hashes,trusted_chain_sources=chain_sources,daily_observations=observations,
            action_evidence=evidence,now=clock())
        require(all(source_hashes.get(p)==h for p,h in reviewed['source_hashes'].items()),'UNDECLARED_REVIEW_SOURCE')
        save(attempt/'review.json',canonical(reviewed))
        require(reviewed['status']=='EVIDENCE_REVIEW_ONLY','BUNDLE_REVIEW_FAILED')
        require(all(h['status']=='CONDITIONAL_PRICE_CHANGE' for o in reviewed['orders'] for h in o['horizons']
            if h['sessions_after_reference'] in matured),'MATURED_HORIZON_UNRESOLVED')
        preserve_progress(old,reviewed)
        closes={r['date']:r['close_at'] for r in calendar['sessions']}
        compare_daily(root=root,old_directory=failed_directory,old_manifest=failed_manifest,new_directory=directory,observations=observations,closes=closes)
        if published_manifest is not None:
            compare_daily(root=root,old_directory=published_directory,old_manifest=published_manifest,new_directory=directory,observations=observations,closes=closes)
        verify_sources(root,pins)
        actual_index=digest(read_bytes(index,4096)) if index.exists() else None
        require(actual_index==plan['expected_index_sha256'],'INDEX_HASH_CONFLICT')
        publication_pins=dict(pins)
        publication_pins[(directory/'manifest.json').relative_to(root).as_posix()]=bundle_hash
        for path,h in source_hashes.items():publication_pins[(directory/'sources'/path).relative_to(root).as_posix()]=h
        verify_sources(root,publication_pins)
        publication_attempted=True
        publish_exact_index(index=index,expected_index_sha256=plan['expected_index_sha256'],
            expected_manifest=expected,new_manifest=bundle_hash,root=root,pins=publication_pins)
        publication_returned=True
        answer=dict(status='RECOVERY_FOLLOWUP_PUBLISHED',manifest_sha256=bundle_hash,previous_manifest_sha256=expected,
            target_session=target,matured_horizons=matured,request_sha256=plan['request_sha256'],
            old_attempt=started['old_attempt'],old_failed_sha256=refs['failed']['sha256'],
            captured_at=clock().isoformat(),account_writes=False,actual_fill_inferred=False)
        save(attempt/'complete.json',canonical(answer));return answer
    except Exception as error:
        if publication_attempted:
            evidence=index_evidence(index,root)
            committed=publication_returned or evidence.get('manifest_sha256')==bundle_hash
            receipt=dict(status='PUBLICATION_COMMITTED_COMPLETION_UNRECORDED' if committed else 'PUBLICATION_OUTCOME_UNCERTAIN',
                reason=reason(error),at=clock().isoformat(),publication_committed=True if committed else None,
                publication_returned=publication_returned,manifest_sha256=bundle_hash,
                manifest_path=(directory/'manifest.json').relative_to(root).as_posix(),index_evidence=evidence,
                request_sha256=plan['request_sha256'],old_attempt=started['old_attempt'],
                target_session=target,retry_allowed=False,requires_manual_reconciliation=True,account_writes=False)
            try:save(attempt/'publication_attention.json',canonical(receipt))
            except Exception as record_error:receipt['attention_record_write_error']=reason(record_error)
            raise PublicationAttention(receipt) from error
        save(attempt/'failed.json',canonical(dict(status='BLOCKED',reason=reason(error),at=clock().isoformat(),
            retry_allowed=False,request_sha256=plan['request_sha256'],old_attempt=started['old_attempt'])));raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',required=True)
    parser.add_argument('--request',required=True);parser.add_argument('--expected-request-sha256');parser.add_argument('--execute',action='store_true')
    args=vars(parser.parse_args(argv));root=Path(args['root']).resolve();request_path=safe_path(root,args.pop('request'))
    args['request']=parse(read_bytes(request_path,4*1024*1024))
    try:answer=run(**args)
    except PublicationAttention as error:answer=error.receipt
    except Exception as error:answer=dict(status='BLOCKED',reason=reason(error),account_writes=False)
    print(json.dumps(answer));return 0 if answer['status'] in ('RECOVERY_PREFLIGHT_ONLY_NOT_EXECUTED','RECOVERY_FOLLOWUP_PUBLISHED') else 2
if __name__=='__main__':raise SystemExit(main())
