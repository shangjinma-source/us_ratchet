"""Explicit after-close evidence collector; no publication, search, or account writes."""
import json
from pathlib import Path
from hashlib import sha256
from types import SimpleNamespace
from fractions import Fraction
from scripts.coordinate_monthly_simulation import read,within,save,now,safe_reason,files as output_hashes
from scripts.build_monthly_successor_plan import prepare
from scripts.prepare_monthly_captured_training import build
from scripts.current_research_official_alert_capture import capture_official_alerts,fetch_official_feed
from scripts.current_research_close_capture import capture_saved_close,default_fetch
from scripts.build_monthly_automatic_review_request import construct,account_snapshot
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources as IdentityReader,MANIFEST
from data.current_quantity_v2_verified_snapshot_bundle import VerifiedSnapshotBundleService
from data.current_quantity_v2_source_admission_policy import SOURCE_WITHDRAWALS
from data.current_quantity_v2_late_unit_review import BoundedLateUnitReview
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources,fetch_daily_actions
from data.current_quantity_v2_simulation_origin_files import SimulationOriginFilesReader
from backtest.current_quantity_v2_simulated_settlement import _references
from data.current_quantity_v2_difference_plan import require


def collect(*,coordinator_config,coordinator_sha256,bootstrap_config,bootstrap_sha256,policy_path,policy_sha256,output_directory,execute=False,clock=now,rss_fetch=fetch_official_feed,close_fetch=default_fetch,action_fetch=fetch_daily_actions):
    coordinator=json.loads(read(coordinator_config,coordinator_sha256));root=Path(coordinator['root']).resolve()
    settings=json.loads(read(within(root,coordinator['settings_path']),coordinator['settings_sha256']))
    initial=json.loads(read(bootstrap_config,bootstrap_sha256));daily=json.loads(read(coordinator['daily_config'],coordinator['daily_sha256']))
    require(all(initial[k]==daily[k] for k in ('root','database_path','simulation_id','pullback')) and initial['fees']==dict(path=daily['fees_path'],sha256=daily['fees_sha256']) and initial['schedule']==dict(path=daily['schedule_path'],sha256=daily['schedule_sha256']),'BOOTSTRAP_DAILY_CONFIG_MISMATCH')
    policy_raw=read(within(root,policy_path),policy_sha256)
    policy=json.loads(policy_raw)
    require(set(policy)=={'schema','authority','maximum_capture_age_seconds','matching','coverage','retention'} and policy['schema']=='MONTHLY_VISIBLE_OFFICIAL_FEED_SCREEN_V1' and policy['authority']=='RESEARCH_BOUNDED_SOURCE_ASSUMPTION' and type(policy['maximum_capture_age_seconds'])is int and 0<policy['maximum_capture_age_seconds']<=86400 and policy['matching']=='ALL_VISIBLE_ITEMS_EXACT_TICKER_OR_META_NAME' and policy['coverage']=='INCOMPLETE_MAY_OMIT_ACTIONS' and policy['retention']=='UNKNOWN','INVALID_MONTHLY_SCREEN_POLICY')
    plan,pre=prepare(settings['plan_path'],settings['plan_sha256'],root=root,clock=clock)
    destination=within(root,output_directory)
    binding=dict(coordinator_sha256=coordinator_sha256,bootstrap_sha256=bootstrap_sha256,policy_path=policy_path,policy_sha256=policy_sha256,output_directory=output_directory)
    if not pre['ready_after_close']:return dict(status='WAITING_SESSION_CLOSE',http_calls=0,account_writes=False)
    try:saved=account_snapshot(daily)
    except ValueError as error:return dict(status='WAITING_ACCOUNT',reason=safe_reason(error),http_calls=0,account_writes=False)
    binding['expected_revision']=saved['revision']
    descriptor=json.loads(read(within(root,initial['descriptor']['path']),initial['descriptor']['sha256']))
    pins=dict(descriptor['source_hashes']);guard=VerifiedSnapshotBundleService(SimpleNamespace(root=root),source_withdrawals=SOURCE_WITHDRAWALS)
    guard.require_source_hashes_admitted(pins)
    source_files={};total=0
    for path,h in pins.items():
        body=read(within(root,path),h);total+=len(body);require(total<=128*1024*1024,'IDENTITY_SOURCE_BYTES_LIMIT');source_files[path]=body
    identity_path=initial.get('identity_manifest_path',MANIFEST);require(identity_path in source_files,'PINNED_MANIFEST_REQUIRED')
    if not execute:return dict(status='PREFLIGHT_ONLY',session=plan['session'],revision=saved['revision'],identity_source_pins=len(pins),http_calls=0,account_writes=False)
    index=within(root,settings['capture_index_path'])
    binding['capture_index_sha256']=sha256(read(index)).hexdigest() if index.exists() else None
    completion=destination/'complete.json'
    if destination.exists():
        require(completion.is_file(),'PARTIAL_OR_FAILED_COLLECTION_NO_RETRY')
        result=json.loads(read(completion));require(result['binding']==binding,'COLLECTION_INPUT_OR_ACCOUNT_CHANGED')
        for path,h in result['output_hashes'].items():read(path,h)
        return result['result']
    # Preparation must exist and pass before the first request. Never fill future placeholders.
    index=within(root,settings['capture_index_path'])
    if not index.exists():return dict(status='WAITING_TRAINING_CAPTURE',http_calls=0,account_writes=False)
    preparation={k:settings[k] for k in ('previous_manifest_path','previous_manifest_sha256','capture_index_path','plan_path','plan_sha256')}
    preparation.update(capture_index_sha256=sha256(read(index)).hexdigest(),root=root,clock=clock,plan_validator=prepare)
    manifest,compiled,_=build(**preparation);meta=dict(compiled['input']['search_arguments']['metadata'])
    chain=saved['simulation']['chain'];ledger=chain['ledger'];refs=_references(chain)
    outside={sid for sid,q in ledger['shares'].items() if Fraction(q)>0}-set(meta)
    approved=json.loads(source_files[identity_path])
    for sid in outside:
        rows=[r for r in approved['candidates'] if r.get('security_id')==sid]
        require(len(rows)==1 and rows[0]['ticker']==refs[sid]['ticker'],'HELD_IDENTITY_UNAVAILABLE')
        meta[sid]=dict(ticker=rows[0]['ticker'],issuer_id=rows[0]['issuer_id'])
    previous=json.loads(source_files[descriptor['input_path']])
    decision=dict(decision_date=previous['search_arguments']['decision_date'],binding=dict(search_arguments=dict(metadata=meta)))
    reader=IdentityReader(root=root,snapshot_service=None,server_account_id=ledger['account_id'],identity_manifest_path=identity_path)
    for sid in meta:reader._identity(decision,source_files,pins,sid,plan['session'])
    require(account_snapshot(daily)['revision']==saved['revision'],'COLLECTION_ACCOUNT_CHANGED')
    destination.mkdir(parents=True,exist_ok=False);save(destination/'started.json',dict(binding=binding,started_at=clock().isoformat(),retry=False))
    # Archive any action transport response immediately, even if later replay rejects it.
    counter=[0]
    def retained(fetch,kind):
        def wrapped(*args,**kwargs):
            index=counter[0];counter[0]+=1;at=clock().isoformat()
            try:
                response=fetch(*args,**kwargs);body=response.get('body',response.get('raw'))
                require(type(body)is bytes and len(body)<=4*1024*1024,'TRANSPORT_BYTES_LIMIT')
                name=f'transport-{index}-{kind}.bin'
                with (destination/name).open('xb') as stream:stream.write(body)
                save(destination/(name+'.json'),dict(started_at=at,received_at=clock().isoformat(),status=response.get('status',response.get('http_status')),raw_sha256=sha256(body).hexdigest(),kind=kind))
                return response
            except BaseException as error:
                save(destination/(f'transport-{index}-{kind}.failed.json'),dict(reason=safe_reason(error),at=clock().isoformat()));raise
        return wrapped
    rss=retained(rss_fetch,'rss');held={}
    try:
        feed_dir=output_directory+'/official-feed'
        result=capture_official_alerts(feed_dir,root=root,capture=True,fetch=rss,clock=clock)
        require(result['status']!='UNAVAILABLE','OFFICIAL_FEED_UNAVAILABLE')
        for name in ('response.bin','receipt.json'):
            p=feed_dir+'/'+name;pins[p]=sha256(read(root/p)).hexdigest()
        pins[policy_path]=policy_sha256
        source=PaperActionEvidenceSources(fetch=retained(action_fetch,'action'),rss_fetch=rss,clock=clock)
        late=BoundedLateUnitReview(action_sources=source,clock=clock)
        origins=SimulationOriginFilesReader(capture_audit_roots=daily['capture_audit_roots'])
        for sid in sorted(outside):
            ticker=meta[sid]['ticker'];relative=output_directory+'/held-'+sha256(sid.encode()).hexdigest()[:16]
            capture_plan=dict(schema='SAVED_CLOSE_CAPTURE_MANIFEST_V1',session=plan['session'],history_start_date=plan['session'],calendar_path=plan['calendar_path'],calendar_source_hashes=plan['calendar_source_hashes'],securities=[dict(ticker=ticker,security_id=sid,security_type='EQUITY')],output_directory=relative)
            locator=relative+'-plan.json';save(root/locator,capture_plan)
            result=capture_saved_close(locator,sha256(read(root/locator)).hexdigest(),root=root,capture=True,fetch=close_fetch,clock=clock)
            require(all(r['status']=='SAVED_EXACT_SESSION_READER_VALIDATED_NOT_ADMITTED' for r in result['entries']),'HELD_CLOSE_CAPTURE_UNAVAILABLE')
            rawpath=relative+'/'+ticker+'.response.bin';receiptpath=relative+'/'+ticker+'.receipt.json';raw=read(root/rawpath);receipt=json.loads(read(root/receiptpath))
            package=late.capture(reference=refs[sid],capture_raw=raw,captured_at=receipt['received_at_utc'],origin_files=origins(saved['simulation'],refs[sid]),account_id=ledger['account_id'],state_revision=saved['revision'])
            for path,body in package['files'].items():
                target=within(root,path);target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists():require(read(target)==body,'COLLECTION_SOURCE_COLLISION')
                else:
                    with target.open('xb') as stream:stream.write(body)
                require(path not in pins or pins[path]==sha256(body).hexdigest(),'COLLECTION_PIN_CONFLICT');pins[path]=sha256(body).hexdigest()
            for p in (rawpath,receiptpath,locator):pins[p]=sha256(read(root/p)).hexdigest()
            held[sid]=dict(raw_path=rawpath,receipt_path=receiptpath,unit_review_path=package['review_path'])
        inputs=dict(schema='MONTHLY_AUTOMATIC_REVIEW_INPUTS_V1',expected_revision=saved['revision'],source_hashes=pins,feed_path=feed_dir+'/response.bin',feed_receipt_path=feed_dir+'/receipt.json',policy_path=policy_path,identity_manifest_path=identity_path,held_bar_sources=held)
        checked=construct(preparation_arguments=preparation,settings=settings,daily=daily,inputs=inputs,output_prefix=output_directory+'/screened')
        for path,raw in checked['artifacts'].items():
            target=within(root,path);target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(raw)
        require(account_snapshot(daily)['revision']==saved['revision'],'COLLECTION_ACCOUNT_CHANGED')
        path=destination/'automatic-inputs.json';save(path,inputs)
        result=dict(status='EVIDENCE_READY' if checked['status']=='READY_REQUEST' else 'WAITING_REVIEW',reason=checked['reason'],inputs_path=path.relative_to(root).as_posix(),inputs_sha256=sha256(read(path)).hexdigest(),account_writes=False,publication=False)
        hashes=output_hashes(root,[destination]);hashes.update({str(root/p):h for p,h in pins.items()})
        for dependency in (manifest['source_hashes'],settings['fixed_source_hashes']):
            for p,h in dependency.items():read(within(root,p),h);hashes[str(root/p)]=h
        save(completion,dict(binding=binding,result=result,output_hashes=hashes,completed_at=clock().isoformat()))
        return result
    except BaseException as error:
        save(destination/'failed.json',dict(binding=binding,reason=safe_reason(error),at=clock().isoformat(),automatic_retry=False));raise


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('coordinator-config','coordinator-sha256','bootstrap-config','bootstrap-sha256','policy-path','policy-sha256','output-directory'):parser.add_argument('--'+field,required=True)
    parser.add_argument('--execute',action='store_true')
    try:result=collect(**vars(parser.parse_args(argv)))
    except Exception as error:result=dict(status='BLOCKED',reason=safe_reason(error),account_writes=False,automatic_retry=False)
    print(json.dumps(result));return 2 if result['status']=='BLOCKED' else 0
if __name__=='__main__':raise SystemExit(main())
