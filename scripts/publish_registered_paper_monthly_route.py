"""Policy-authorized publication of completed paper monthly routes.

No capture, search, bootstrap or broker activity. A caller-approved policy binds
one registered series and its rolling coordinator chain; discovered output hashes
are evidence under that policy, never standalone approval.
"""
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
from data import registered_quantity_v2_paper_protocol as core
from scripts import run_registered_quantity_v2_paper_simulation as runtime
from scripts import register_quantity_v2_paper_protocol as registrar
from scripts import materialize_monthly_successor as successor
from scripts import coordinate_monthly_simulation as coordinator
from scripts import bind_monthly_simulation_runtime as binder
from scripts import run_rolling_monthly_simulation as rolling
from data.current_quantity_v2_monthly_composition import MonthlyFileConfiguration

SELF='scripts/publish_registered_paper_monthly_route.py'
MODULES={SELF:lambda:__file__,'scripts/materialize_monthly_successor.py':lambda:successor.__file__,
 'scripts/coordinate_monthly_simulation.py':lambda:coordinator.__file__,
 'scripts/bind_monthly_simulation_runtime.py':lambda:binder.__file__,
 'scripts/run_rolling_monthly_simulation.py':lambda:rolling.__file__,
 'scripts/run_registered_quantity_v2_paper_simulation.py':lambda:runtime.__file__}
COMPILE_SOURCES=('data/current_quantity_v2_monthly_training.py','scripts/return_priority_current_rebased_training.py',
 'backtest/return_priority_monthly_training_inputs.py','scripts/monthly_experimental_domain_capture.py')


def _check(*,root,registration_directory,expected_request_sha256,policy_path,expected_policy_sha256,target_month,now):
    root=Path(root).resolve();observed=core.stamp(now);pins={}
    def read(path,expected=None):
        p=core.path_at(root,path);raw=p.read_bytes();h=sha256(raw).hexdigest()
        core.need(expected is None or h==expected,'MONTHLY_PUBLICATION_SOURCE_CHANGED')
        core.need(str(p) not in pins or pins[str(p)]==h,'MONTHLY_PUBLICATION_PIN_CONFLICT')
        pins[str(p)]=h
        return json.loads(raw) if p.suffix.lower()=='.json' else None
    policy=read(policy_path,expected_policy_sha256)
    core.need(policy.get('schema')=='REGISTERED_PAPER_MONTHLY_PUBLICATION_POLICY_V1','PUBLICATION_POLICY_SCHEMA')
    core.need(policy.get('request_sha256')==expected_request_sha256 and policy.get('registration_directory')==registration_directory,'PUBLICATION_REGISTRATION_MISMATCH')
    core.need(policy.get('authorization')=='COMPLETED_PAPER_BIND_ONLY','PUBLICATION_AUTHORIZATION_REQUIRED')
    for path,h in policy['source_hashes'].items():
        p=core.path_at(root,path);raw=p.read_bytes();core.need(sha256(raw).hexdigest()==h,'PUBLICATION_SOURCE_PIN_CHANGED');pins[str(p)]=h
    for name,where in MODULES.items():
        core.need(policy['source_hashes'].get(name)==sha256(Path(where()).read_bytes()).hexdigest(),'PUBLICATION_EXECUTABLE_PIN_REQUIRED')
    for name in COMPILE_SOURCES:
        core.need(policy['source_hashes'].get(name)==sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest(),'PUBLICATION_COMPILER_PIN_REQUIRED')
    validated=runtime.load_bundle(root=root,registration_directory=registration_directory,expected_request_sha256=expected_request_sha256,now=observed)
    request=validated['request'];identity=request['identity'];evaluation=request['evaluation']
    core.need(type(target_month) is str and len(target_month)==7 and evaluation['start_session'][:7]<=target_month<=evaluation['end_session'][:7],'PUBLICATION_MONTH_OUTSIDE_EVALUATION')
    audited=runtime.audit_runtime_receipts(validated=validated,now=observed)
    core.need(audited['state'] is not None,'PUBLICATION_REGISTERED_START_REQUIRED')
    store=runtime.stores.SimulationStore(validated['database_path']);saved=store.read(identity['simulation_id'])
    core.need(saved['revision']==audited['revision'],'PUBLICATION_ACCOUNT_CHANGED_DURING_AUDIT')
    start=read(Path(registration_directory)/'runtime/start.json')
    start_complete=read(Path(registration_directory)/'runtime/start_complete.json')
    core.need(start_complete.get('status')=='REGISTERED_BOOTSTRAP_COMPLETE' and start_complete.get('start_sha256')==pins[str(core.path_at(root,Path(registration_directory)/'runtime/start.json'))]
        and start_complete.get('request_sha256')==expected_request_sha256 and start_complete.get('registration_receipt_sha256')==validated['registration_receipt_sha256'],'PUBLICATION_START_RECEIPT_MISMATCH')
    core.validate_start_receipt(validated=validated,receipt=start,simulation=saved['simulation'],now=observed)
    core.need(all(x['status']=='COMPLETE' for x in store.inspect_operations(identity['simulation_id'])['operations']),'PUBLICATION_ACCOUNT_RECOVERY_REQUIRED')
    plan=read(policy['rolling']['path'],policy['rolling']['sha256'])
    core.need(plan['schema']=='ROLLING_MONTHLY_SIMULATION_V1' and Path(plan['root']).resolve()==root,'PUBLICATION_ROLLING_MISMATCH')
    core.need(plan['bootstrap']==request['refs']['bootstrap'],'PUBLICATION_BOOTSTRAP_MISMATCH')
    read(plan['policy']['path'],plan['policy']['sha256'])
    selected=plan['first_coordinator'];visited=set()
    for _ in range(24):
        config=read(selected['path'],selected['sha256']);month=config['session'][:7]
        core.need(month not in visited and month<=target_month,'PUBLICATION_COORDINATOR_CHAIN_INVALID');visited.add(month)
        core.need(Path(config['root']).resolve()==root,'PUBLICATION_COORDINATOR_ROOT')
        core.need(core.path_at(root,config['daily_config'])==core.path_at(root,request['refs']['daily']['path']) and config['daily_sha256']==request['refs']['daily']['sha256'],'PUBLICATION_DAILY_BASE_MISMATCH')
        if month==target_month:break
        output=(Path(plan['rolling_output_directory'])/'plans'/('after-'+month)).as_posix()
        core.need((root/output/'materialization.complete.json').is_file(),'PUBLICATION_SUCCESSOR_NOT_COMPLETED')
        result=successor.run(previous_coordinator=core.path_at(root,selected['path']),previous_sha256=selected['sha256'],output_directory=output,execute=False,clock=lambda:observed)
        proof=read(Path(output)/'materialization.complete.json')
        for mapping in (proof['input_hashes'],proof['output_hashes']):
            for path,h in mapping.items():read(path,h)
        selected={'path':result['coordinator_path'],'sha256':result['coordinator_sha256']}
    else:raise ValueError('PUBLICATION_CHAIN_LIMIT')
    settings=read(config['settings_path'],config['settings_sha256'])
    capture_plan=read(settings['plan_path'],settings['plan_sha256'])
    core.need(capture_plan.get('domain_path')==policy['domain']['path'] and capture_plan.get('domain_source_hashes')==policy['domain_source_hashes'] and policy['domain_source_hashes'].get(policy['domain']['path'])==policy['domain']['sha256'],'PUBLICATION_FIXED_DOMAIN_MISMATCH')
    for path,h in policy['domain_source_hashes'].items():read(path,h)
    for path,h in settings['fixed_source_hashes'].items():read(path,h)
    boundary=read(settings['calendar_path'],settings['fixed_source_hashes'][settings['calendar_path']])
    core.need(boundary['target_month']==target_month and boundary['active_date']==config['session'],'PUBLICATION_BOUNDARY_MISMATCH')
    core.need(settings['schedule_path']==request['refs']['calendar']['path'] and settings['fixed_source_hashes'][settings['schedule_path']]==request['refs']['calendar']['sha256'],'PUBLICATION_CALENDAR_MISMATCH')
    stage=core.path_at(root,config['stage_directory']);receipts={}
    for name in ('capture','prepare','publish','bind'):
        core.need((stage/(name+'.complete.json')).is_file() and (stage/(name+'.started.json')).is_file(),'PUBLICATION_PIPELINE_INCOMPLETE')
        complete=read(stage/(name+'.complete.json'));started=read(stage/(name+'.started.json'))
        binding=complete['binding']
        core.need(binding==started['binding'] and binding['config_sha256']==selected['sha256'] and binding['settings_sha256']==config['settings_sha256'],'PUBLICATION_STAGE_BINDING_MISMATCH')
        core.need(not (stage/(name+'.failed.json')).exists() or complete.get('recovered_after_failure') is True,'PUBLICATION_STAGE_FAILED')
        core.need(core.stamp(boundary['decision_close_at'])<=core.stamp(started['at'])<=core.stamp(complete['at'])<core.stamp(boundary['active_open_at']) and core.stamp(complete['at'])<=observed,'PUBLICATION_STAGE_TIME_INVALID')
        core.need(bool(complete['output_hashes']),'PUBLICATION_OUTPUT_CLOSURE_MISSING')
        for path,h in complete['output_hashes'].items():read(path,h)
        receipts[name]=complete
    core.need(receipts['prepare']['result']['status']=='READY_CONDITIONAL' and receipts['publish']['result']['status']=='PUBLISHED_CONDITIONAL_NOT_ACTIVATED','PUBLICATION_PIPELINE_INCOMPLETE')
    published=receipts['publish']['result'];bound=receipts['bind']['result']
    core.need(bound['status']=='VALIDATED_MONTHLY_RUNTIME_RELEASE_PUBLISHED' and bound['session']==config['session'] and bound['simulation_id']==identity['simulation_id'],'PUBLICATION_BIND_IDENTITY_MISMATCH')
    core.need(bound['monthly_sha256']==published['config_sha256'] and bound['monthly_path']==published['config_path'],'PUBLICATION_MONTHLY_BIND_MISMATCH')
    publish_request=read(settings['publish_request'],receipts['publish']['binding']['inputs']['request_sha256'])
    for path,h in publish_request['supplemental_hashes'].items():read(path,h)
    candidate=read(bound['config_path'],bound['config_sha256']);base=validated['documents']['daily']
    core.need(set(candidate)==set(base) and all(candidate[k]==base[k] for k in base if k not in ('monthly','monthly_blob_root')),'PUBLICATION_FIXED_CONFIG_CHANGED')
    core.need(candidate['monthly']['path']==bound['monthly_path'] and candidate['monthly']['sha256']==bound['monthly_sha256'],'PUBLICATION_CANDIDATE_MONTHLY_CHANGED')
    release=read(bound['monthly_release'])
    core.need(release['config_sha256']==bound['config_sha256'] and core.path_at(root,release['config_path'])==core.path_at(root,bound['config_path']) and release['target_month']==target_month and release['base_sha256']==config['daily_sha256'],'PUBLICATION_OLD_ROUTE_MISMATCH')
    monthly=MonthlyFileConfiguration(root=root,path=bound['monthly_path'],sha256_value=bound['monthly_sha256'],clock=lambda:datetime.fromisoformat(config['session']+'T10:00:00').replace(tzinfo=ZoneInfo('America/New_York')).isoformat())
    package=monthly.market_reader(saved['simulation']['chain'])
    for path,h in package['source_package']['source_hashes'].items():read(path,h)
    route=dict(schema='REGISTERED_PAPER_ROUTE_V1',request_sha256=expected_request_sha256,identity=identity,target_month=target_month,configuration=dict(path=core.path_at(root,bound['config_path']).relative_to(root).as_posix(),sha256=bound['config_sha256']))
    output=registrar.safe_path(root,policy['output_directory'])/target_month
    return dict(route=route,policy_sha256=expected_policy_sha256,input_hashes=pins,output=output,
        validated=validated,store=store,saved=saved,bound=bound,deadline=boundary['active_open_at'])


def run(*,root,registration_directory,expected_request_sha256,policy_path,expected_policy_sha256,target_month,execute=False,clock=None):
    supplied_clock=clock or (lambda:datetime.now(timezone.utc));root=Path(root).resolve();last=[None]
    def clock():
        value=core.stamp(supplied_clock())
        core.need(last[0] is None or value>=last[0],'PUBLICATION_CLOCK_ROLLBACK')
        last[0]=value
        return value
    args=dict(root=root,registration_directory=registration_directory,expected_request_sha256=expected_request_sha256,policy_path=policy_path,expected_policy_sha256=expected_policy_sha256,target_month=target_month)
    def check():return _check(**args,now=clock())
    checked=check();output=checked['output']
    def existing(value):
        core.need(not (output/'failed.json').exists() and not (output/'lock_cleanup_failed.json').exists() and (output/'complete.json').is_file(),'PUBLICATION_PARTIAL_REQUIRES_REVIEW')
        complete=json.loads((output/'complete.json').read_bytes());started=json.loads((output/'started.json').read_bytes())
        core.need(started==dict(request_sha256=expected_request_sha256,policy_sha256=expected_policy_sha256,input_hashes=value['input_hashes']),'PUBLICATION_START_RECEIPT_CHANGED')
        raw=(output/'route.json').read_bytes()
        core.need(complete['policy_sha256']==expected_policy_sha256 and complete['request_sha256']==expected_request_sha256 and complete['input_hashes']==value['input_hashes'] and json.loads(raw)==value['route'] and complete['route_sha256']==sha256(raw).hexdigest(),'PUBLICATION_RECEIPT_CHANGED')
        core.validate_route_binding(validated=value['validated'],route_path=output/'route.json',expected_route_sha256=complete['route_sha256'],simulation=value['saved']['simulation'])
        return dict(status='POLICY_AUTHORIZED_ROUTE',route_path=str(output/'route.json'),route_sha256=complete['route_sha256'],policy_sha256=expected_policy_sha256,account_writes=False)
    lock=registrar.safe_path(root,registrar.LOCK)
    core.need(not lock.exists(),'RUN_LOCK_PRESENT_REVIEW_IF_STALE')
    if not output.exists():
        core.need(checked['saved']['revision']==checked['bound']['validated_revision'],'PUBLICATION_BOUND_ACCOUNT_CHANGED')
        core.need(core.stamp(clock())<core.stamp(checked['deadline']),'PUBLICATION_WINDOW_MISSED')
    if not execute:
        return existing(checked) if output.exists() else dict(status='PREFLIGHT_ONLY',target_month=target_month,account_writes=False)
    lock=registrar.safe_path(root,registrar.LOCK);lock.parent.mkdir(parents=True,exist_ok=True);token=uuid4().hex
    try:registrar.save_bytes(lock,token.encode())
    except FileExistsError:raise ValueError('RUN_LOCK_PRESENT_REVIEW_IF_STALE') from None
    try:
        checked=check()
        if output.exists():return existing(checked)
        core.need(checked['saved']['revision']==checked['bound']['validated_revision'],'PUBLICATION_BOUND_ACCOUNT_CHANGED')
        core.need(core.stamp(clock())<core.stamp(checked['deadline']),'PUBLICATION_WINDOW_MISSED')
        output.mkdir(parents=True,exist_ok=False)
        registrar.save(output/'started.json',dict(request_sha256=expected_request_sha256,policy_sha256=expected_policy_sha256,input_hashes=checked['input_hashes']))
        try:
            with binder.publication_guard(checked['validated']['documents']['daily'],checked['saved']['revision']):
                for path,h in checked['input_hashes'].items():core.need(sha256(Path(path).read_bytes()).hexdigest()==h,'PUBLICATION_INPUT_CHANGED_BEFORE_WRITE')
                core.need(core.stamp(clock())<core.stamp(checked['deadline']),'PUBLICATION_WINDOW_MISSED')
                registrar.save(output/'route.json',checked['route'])
                registrar.save(output/'complete.json',dict(request_sha256=expected_request_sha256,policy_sha256=expected_policy_sha256,input_hashes=checked['input_hashes'],route_sha256=sha256((output/'route.json').read_bytes()).hexdigest()))
        except BaseException:
            registrar.save(output/'failed.json',dict(reason='PUBLICATION_INCOMPLETE_REVIEW_REQUIRED'));raise
        return existing(checked)
    finally:
        try:
            core.need(lock.read_bytes()==token.encode(),'PUBLICATION_LOCK_OWNERSHIP_CHANGED');lock.unlink()
        except BaseException:
            if output.exists() and not (output/'lock_cleanup_failed.json').exists():
                registrar.save(output/'lock_cleanup_failed.json',dict(reason='PUBLICATION_LOCK_RECONCILIATION_REQUIRED'))
            raise


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('root','registration-directory','expected-request-sha256','policy-path','expected-policy-sha256','target-month'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--execute',action='store_true')
    try:result=run(**vars(parser.parse_args(argv)))
    except Exception as error:
        reason=str(error) if isinstance(error,ValueError) and str(error).replace('_','').isalnum() else 'PUBLICATION_BLOCKED_REVIEW_REQUIRED'
        result=dict(status='BLOCKED',reason=reason,account_writes=False)
    print(json.dumps(result));return 2 if result['status']=='BLOCKED' else 0


if __name__=='__main__':raise SystemExit(main())
