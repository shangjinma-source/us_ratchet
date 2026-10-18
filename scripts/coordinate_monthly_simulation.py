"""Create-only monthly preparation coordinator. No search or account mutations."""
import argparse,json,hashlib,os,re
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import datetime,timezone
from scripts.monthly_experimental_domain_capture import run as capture,default_fetch
from scripts.build_monthly_successor_plan import prepare
from scripts.prepare_monthly_captured_training import build
from scripts.publish_monthly_market_configuration import publish
from scripts.bind_monthly_simulation_runtime import bind,publication_guard
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require


def safe_reason(error):
    value=str(error)
    return value if type(error) is ValueError and re.fullmatch(r'[A-Z][A-Z0-9_:]{0,159}',value) else type(error).__name__

def now():return datetime.now(timezone.utc)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def read(path,expected=None):
    path=Path(path);require(not path.is_symlink() and path.is_file() and path.stat().st_size<=32*1024*1024,'INVALID_FILE')
    raw=path.read_bytes();require(expected is None or digest(raw)==expected,'SOURCE_CHANGED');return raw

def save(path,value):
    with Path(path).open('xb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())

def within(root,path):
    path=Path(path);resolved=(root/path).resolve()
    require(resolved.is_relative_to(root) and resolved!=root,'OUTPUT_OUTSIDE_ROOT')
    return resolved

def files(root,paths):
    result={}
    for path in paths:
        path=Path(path)
        selected=sorted(path.rglob('*')) if path.is_dir() else [path]
        for item in selected:
            require(not item.is_symlink(),'SYMLINK_OUTPUT')
            if item.is_file():result[str(item.resolve())]=digest(read(item))
    require(result,'EMPTY_STAGE_OUTPUT');return result

def run(*,config_path,config_sha256,execute=False,review_request_sha256=None,auto_review_inputs=None,auto_review_inputs_sha256=None,clock=now,fetch=default_fetch):
    raw=read(config_path,config_sha256);config=json.loads(raw)
    require(set(config)=={'schema','root','settings_path','settings_sha256','daily_config','daily_sha256','session','monthly_blob_root','daily_output','monthly_runtime_directory','stage_directory'},'COORDINATOR_CONFIG_FIELDS')
    require(config['schema']=='MONTHLY_PREPARATION_COORDINATOR_V1','CONFIG_SCHEMA')
    root=Path(config['root']).resolve();settings=json.loads(read(within(root,config['settings_path']),config['settings_sha256']))
    require(Path(settings['root']).resolve()==root,'ROOT_MISMATCH')
    read(config['daily_config'],config['daily_sha256'])
    for path,h in settings['fixed_source_hashes'].items():read(within(root,path),h)
    require(Path(config['monthly_runtime_directory']).is_absolute() and Path(config['monthly_blob_root']).is_absolute(),'EXPLICIT_ABSOLUTE_RUNTIME_PATH_REQUIRED')
    plan,checked=prepare(settings['plan_path'],settings['plan_sha256'],root=root,clock=clock)
    for key in ('previous_manifest_path','previous_manifest_sha256'):require(settings[key]==plan[key],'SETTINGS_PLAN_MISMATCH')
    capture_output=within(root,plan['output_directory']);index=within(root,settings['capture_index_path'])
    require(index==capture_output/'completion_index.json','INDEX_OUTPUT_MISMATCH')
    boundary=json.loads(read(within(root,settings['calendar_path']),settings['fixed_source_hashes'][settings['calendar_path']]))
    require(boundary['active_open_at'][:10]==config['session'],'TARGET_SESSION_MISMATCH')
    destinations=[capture_output,within(root,settings['preparation_output']),within(root,settings['publish_output']),within(root,config['daily_output']),within(root,config['stage_directory'])]
    require(len(set(destinations))==len(destinations) and not any(a in b.parents or b in a.parents for i,a in enumerate(destinations) for b in destinations[i+1:]),'OUTPUT_DIRECTORIES_OVERLAP')
    require((auto_review_inputs is None)==(auto_review_inputs_sha256 is None),'AUTO_REVIEW_INPUT_PAIR_REQUIRED')
    require(auto_review_inputs is None or review_request_sha256 is None,'REVIEW_MODE_CONFLICT')
    if not execute:return dict(status='PREFLIGHT_ONLY',ready_after_close=checked['ready_after_close'],session=config['session'],capture_session=plan['session'],account_writes=False,search_calls=0,http_calls=0)
    if not checked['ready_after_close']:return dict(status='WAITING_SESSION_CLOSE',session_close_at=checked['session_close_at'],http_calls=0,account_writes=False)
    if auto_review_inputs is not None:
        from scripts.build_monthly_automatic_review_request import account_snapshot
        try:
            daily=json.loads(read(config['daily_config'],config['daily_sha256']))
            inputs=json.loads(read(within(root,auto_review_inputs),auto_review_inputs_sha256))
            require(account_snapshot(daily)['revision']==inputs['expected_revision'],'AUTO_REVIEW_ACCOUNT_CHANGED')
        except (ValueError,KeyError) as error:
            return dict(status='WAITING_REVIEW',reason=safe_reason(error),account_writes=False,http_calls=0)
    stage_root=destinations[-1];stage_root.mkdir(parents=True,exist_ok=True)
    def stage(name,inputs,operation,outputs):
        start=stage_root/(name+'.started.json');done=stage_root/(name+'.complete.json');failed=stage_root/(name+'.failed.json')
        binding=dict(config_sha256=config_sha256,settings_sha256=config['settings_sha256'],inputs=inputs)
        if done.exists():
            receipt=json.loads(read(done));require(receipt['binding']==binding,'STAGE_INPUT_CHANGED')
            require(json.loads(read(start))['binding']==binding and (not failed.exists() or receipt.get('recovered_after_failure') is True),'STAGE_STATE_INVALID')
            for path,h in receipt['output_hashes'].items():read(path,h)
            return receipt['result']
        recovering=name=='bind' and start.exists() and destinations[3].exists()
        if recovering:
            require(json.loads(read(start))['binding']==binding,'STAGE_INPUT_CHANGED')
        else:
            require(not start.exists() and not failed.exists(),'PARTIAL_OR_FAILED_STAGE_NO_AUTOMATIC_RETRY')
            save(start,dict(binding=binding,at=clock().isoformat()))
        try:
            result=operation();hashes=files(root,outputs(result));save(done,dict(binding=binding,result=result,output_hashes=hashes,recovered_after_failure=recovering,at=clock().isoformat()));return result
        except BaseException as error:
            if not failed.exists():save(failed,dict(binding=binding,error_type=type(error).__name__,reason=safe_reason(error),automatic_retry=False,at=clock().isoformat()))
            raise
    def do_capture():
        result=capture(settings['plan_path'],settings['plan_sha256'],root=root,clock=clock,fetch=fetch,capture=True,plan_validator=prepare)
        require(result['status']=='EXPERIMENTAL_DOMAIN_CAPTURED_NOT_ADMITTED','CAPTURE_INCOMPLETE_NO_RETRY');return result
    stage('capture',dict(plan_sha256=settings['plan_sha256']),do_capture,lambda result:[capture_output])
    preparation={key:settings[key] for key in ('previous_manifest_path','previous_manifest_sha256','capture_index_path','plan_path','plan_sha256')}
    preparation['capture_index_sha256']=digest(read(index))
    def do_prepare():
        output=destinations[1];require(not output.exists(),'CREATE_ONLY_OUTPUT_EXISTS')
        manifest,compiled,report=build(**preparation,root=root,clock=clock,plan_validator=prepare)
        require(compiled['status']=='READY_CONDITIONAL','TRAINING_NOT_READY');output.mkdir(parents=True,exist_ok=False)
        for name,value in [('manifest',manifest),('preparation',compiled),('input',compiled['input']),('report',report)]:save(output/(name+'.json'),value)
        return dict(status='READY_CONDITIONAL',output=str(output))
    stage('prepare',preparation,do_prepare,lambda result:[destinations[1]])
    request_path=within(root,settings['publish_request'])
    automatic_revision=None
    require((auto_review_inputs is None)==(auto_review_inputs_sha256 is None),'AUTO_REVIEW_INPUT_PAIR_REQUIRED')
    require(auto_review_inputs is None or review_request_sha256 is None,'REVIEW_MODE_CONFLICT')
    if auto_review_inputs is not None:
        from scripts.build_monthly_automatic_review_request import construct,account_snapshot
        daily=json.loads(read(config['daily_config'],config['daily_sha256']))
        inputs=json.loads(read(within(root,auto_review_inputs),auto_review_inputs_sha256))
        require(account_snapshot(daily)['revision']==inputs['expected_revision'],'AUTO_REVIEW_ACCOUNT_CHANGED')
        require(re.fullmatch(r'[0-9a-f]{64}',auto_review_inputs_sha256) is not None,'AUTO_REVIEW_HASH_INVALID')
        attempt_name='automatic-review-'+auto_review_inputs_sha256
        auto_output=stage_root/attempt_name
        def do_review():
            built=construct(preparation_arguments=dict(preparation,root=root,clock=clock,plan_validator=prepare),settings=settings,daily=daily,inputs=inputs,output_prefix=auto_output.relative_to(root).as_posix())
            require(not auto_output.exists(),'CREATE_ONLY_OUTPUT_EXISTS')
            auto_output.mkdir()
            for path,raw in built['artifacts'].items():
                destination=within(root,path);destination.parent.mkdir(parents=True,exist_ok=True)
                with destination.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            if built['request'] is not None:save(request_path,built['request'])
            return dict(status=built['status'],reason=built['reason'],revision=built['revision'],request_sha256=digest(read(request_path)) if built['request'] else None)
        try:
            automatic=stage(attempt_name,dict(inputs_sha256=auto_review_inputs_sha256),do_review,lambda result:[auto_output]+([request_path] if result['request_sha256'] else []))
        except ValueError as error:
            return dict(status='WAITING_REVIEW',reason=safe_reason(error),account_writes=False,search_calls=0,automatic_retry=False)
        if automatic['status']!='READY_REQUEST':return dict(status='WAITING_REVIEW',reason=automatic['reason'],account_writes=False,search_calls=0)
        automatic_revision=automatic['revision'];require(account_snapshot(daily)['revision']==automatic_revision,'AUTO_REVIEW_ACCOUNT_CHANGED')
        review_request_sha256=automatic['request_sha256']
    if review_request_sha256 is None or not request_path.exists():
        return dict(status='WAITING_REVIEW',reason='ACTUAL_PINNED_PUBLISH_REQUEST_REQUIRED',completed_stages=['capture','prepare'],required=['post-close full-domain known-source review','current identity and unit evidence','actual held outside-domain close sources','supplemental source hashes'],account_writes=False,search_calls=0)
    request=json.loads(read(request_path,review_request_sha256))
    require(set(request)=={'preparation_arguments','supplemental_hashes','calendar_path','schedule_path','identities_path','held_bar_sources','review_path','output_directory'},'PUBLISH_REQUEST_FIELDS')
    require(request['preparation_arguments']==preparation,'PUBLISH_PREPARATION_MISMATCH')
    for field,expected in [('calendar_path',settings['calendar_path']),('schedule_path',settings['schedule_path']),('output_directory',settings['publish_output'])]:require(request[field]==expected,'PUBLISH_FIXED_PATH_MISMATCH')
    require(all(request['supplemental_hashes'].get(k)==v for k,v in settings['fixed_source_hashes'].items()),'PUBLISH_FIXED_PINS_MISMATCH')
    for path,h in request['supplemental_hashes'].items():read(within(root,path),h)
    def do_publish():
        if automatic_revision is not None:require(account_snapshot(daily)['revision']==automatic_revision,'AUTO_REVIEW_ACCOUNT_CHANGED')
        args=dict(request);args['preparation_arguments']=dict(preparation,root=root,clock=clock,plan_validator=prepare);return publish(**args)
    published=stage('publish',dict(request_sha256=review_request_sha256),do_publish,lambda result:[destinations[2]])
    def do_bind():
        if automatic_revision is not None:require(account_snapshot(daily)['revision']==automatic_revision,'AUTO_REVIEW_ACCOUNT_CHANGED')
        args=dict(daily_config=config['daily_config'],daily_sha256=config['daily_sha256'],monthly_path=published['config_path'],monthly_sha256=published['config_sha256'],session=config['session'],monthly_blob_root=config['monthly_blob_root'],publication_time_guard=lambda: clock())
        if automatic_revision is not None:args['expected_revision']=automatic_revision
        destination=destinations[3]
        if not destination.exists():
            return bind(**args,output=destination,monthly_runtime_directory=config['monthly_runtime_directory'])
        # A prior attempt may have durably written the candidate before slot publication.
        # Re-run the complete existing binder validation, but never overwrite that file.
        with TemporaryDirectory(prefix='monthly-coordinator-revalidate-') as temporary:
            validated=Path(temporary)/'daily.json'
            result=bind(**args,output=validated)
            require(read(destination)==read(validated),'RECOVERY_CANDIDATE_CHANGED')
        from scripts.monthly_runtime_routes import publish as publish_route,resolve
        slot=Path(config['monthly_runtime_directory'])/(config['session'][:7]+'.json')
        require(not slot.is_symlink(),'INVALID_MONTHLY_RELEASE_FILE')
        with publication_guard(json.loads(read(config['daily_config'],config['daily_sha256'])),result['validated_revision']):
            if slot.exists():
                selected,h=resolve(directory=config['monthly_runtime_directory'],session=config['session'],base_path=config['daily_config'],base_hash=config['daily_sha256'])
                require(Path(selected)==destination and h==result['config_sha256'],'MONTHLY_SLOT_CONFLICT')
            else:
                clock()  # Recheck the caller's bounded publication window under the writer lock.
                publish_route(directory=config['monthly_runtime_directory'],session=config['session'],base_path=config['daily_config'],base_hash=config['daily_sha256'],candidate_path=destination,candidate_hash=result['config_sha256'])
        result.update(config_path=str(destination),monthly_release=str(slot),status='VALIDATED_MONTHLY_RUNTIME_RELEASE_PUBLISHED')
        return result
    if automatic_revision is not None:require(account_snapshot(daily)['revision']==automatic_revision,'AUTO_REVIEW_ACCOUNT_CHANGED')
    bound=stage('bind',dict(monthly_sha256=published['config_sha256'],daily_sha256=config['daily_sha256']),do_bind,lambda result:[Path(result['config_path']),Path(result['monthly_release'])])
    return dict(status='MONTHLY_RUNTIME_PUBLISHED',release=bound['monthly_release'],daily_config=bound['config_path'],daily_sha256=bound['config_sha256'],account_writes=False,search_calls=0,automatic_trading=False)

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--config-sha256',required=True);parser.add_argument('--review-request-sha256');parser.add_argument('--auto-review-inputs');parser.add_argument('--auto-review-inputs-sha256');parser.add_argument('--execute',action='store_true');a=parser.parse_args(argv)
    try:result=run(config_path=a.config,config_sha256=a.config_sha256,review_request_sha256=a.review_request_sha256,auto_review_inputs=a.auto_review_inputs,auto_review_inputs_sha256=a.auto_review_inputs_sha256,execute=a.execute)
    except Exception as error:result=dict(status='BLOCKED',reason=safe_reason(error),account_writes=False,automatic_retry=False)
    print(json.dumps(result));return 2 if result['status']=='BLOCKED' else 0
if __name__=='__main__':raise SystemExit(main())
