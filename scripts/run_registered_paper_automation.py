"""Versioned registered paper daily/monthly orchestration, preview by default.

No task installation. An externally approved descriptor binds registration,
publication authority and source pins. Shared account locks are never nested.
"""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from uuid import uuid4
from zoneinfo import ZoneInfo
from scripts import run_registered_quantity_v2_paper_simulation as runtime
from scripts import publish_registered_paper_monthly_route as publisher
from scripts import run_rolling_monthly_simulation as rolling
from scripts import register_quantity_v2_paper_protocol as registrar
from data import registered_quantity_v2_paper_protocol as core

REQUIRED={'scripts/run_registered_paper_automation.py':lambda:__file__,
 'scripts/run_registered_quantity_v2_paper_simulation.py':lambda:runtime.__file__,
 'scripts/publish_registered_paper_monthly_route.py':lambda:publisher.__file__,
 'scripts/run_rolling_monthly_simulation.py':lambda:rolling.__file__,
 'scripts/register_quantity_v2_paper_protocol.py':lambda:registrar.__file__,
 'data/registered_quantity_v2_paper_protocol.py':lambda:core.__file__}


def run(*,descriptor_path,expected_descriptor_sha256,mode,execute=False,clock=None,transports=None):
    core.need(mode in ('daily','monthly'),'AUTOMATION_MODE_INVALID')
    supplied=clock or (lambda:datetime.now(timezone.utc));last=[None]
    def now():
        value=core.stamp(supplied());core.need(last[0] is None or value>=last[0],'AUTOMATION_CLOCK_ROLLBACK');last[0]=value;return value
    descriptor_path=Path(descriptor_path).resolve()
    def gate():
        raw=descriptor_path.read_bytes();core.need(sha256(raw).hexdigest()==expected_descriptor_sha256,'AUTOMATION_DESCRIPTOR_CHANGED')
        value=json.loads(raw);core.need(value.get('schema')=='REGISTERED_PAPER_AUTOMATION_V1','AUTOMATION_DESCRIPTOR_SCHEMA')
        root=Path(value['root']).resolve();core.need(descriptor_path.is_relative_to(root),'AUTOMATION_DESCRIPTOR_OUTSIDE_ROOT')
        for path,h in value['source_hashes'].items():core.need(sha256(core.path_at(root,path).read_bytes()).hexdigest()==h,'AUTOMATION_SOURCE_CHANGED')
        for name,where in REQUIRED.items():core.need(value['source_hashes'].get(name)==sha256(Path(where()).read_bytes()).hexdigest(),'AUTOMATION_EXECUTABLE_PIN_REQUIRED')
        policy_ref=value['publication_policy'];raw_policy=core.path_at(root,policy_ref['path']).read_bytes()
        core.need(sha256(raw_policy).hexdigest()==policy_ref['sha256'],'AUTOMATION_POLICY_CHANGED')
        policy=json.loads(raw_policy)
        core.need(policy['request_sha256']==value['request_sha256'] and policy['registration_directory']==value['registration_directory'],'AUTOMATION_POLICY_REGISTRATION_MISMATCH')
        for path,h in policy['source_hashes'].items():core.need(sha256(core.path_at(root,path).read_bytes()).hexdigest()==h,'AUTOMATION_POLICY_SOURCE_CHANGED')
        return value,root,policy
    descriptor,root,policy=gate()
    def bundle():
        gate()
        return runtime.load_bundle(root=root,registration_directory=descriptor['registration_directory'],expected_request_sha256=descriptor['request_sha256'],now=now())
    validated=bundle();audit=runtime.audit_runtime_receipts(validated=validated,now=now())
    local=now().astimezone(ZoneInfo('America/New_York'));month=local.strftime('%Y-%m')
    evaluation=validated['request']['evaluation']
    route=None;proof=None
    publish_args=dict(root=root,registration_directory=descriptor['registration_directory'],expected_request_sha256=descriptor['request_sha256'],policy_path=descriptor['publication_policy']['path'],expected_policy_sha256=descriptor['publication_policy']['sha256'],clock=now)
    if mode=='daily':
        admission=runtime.inspect_admission(validated=validated,now=now())
        needs_route=admission['phase']=='DAILY_ELIGIBLE_NOT_EXECUTED' and month!=evaluation['start_session'][:7]
        if needs_route:
            route=publisher.run(**publish_args,target_month=month)
            core.need(route['status']=='POLICY_AUTHORIZED_ROUTE','CURRENT_MONTH_APPROVED_ROUTE_MISSING')
            proof_path=Path(route['route_path']).parent/'complete.json';proof_raw=proof_path.read_bytes();proof=json.loads(proof_raw)
            route=dict(route,proof_path=str(proof_path),proof_sha256=sha256(proof_raw).hexdigest())
        preview=dict(status='PREFLIGHT_ONLY',mode=mode,phase=admission['phase'],route_selected=route is not None,account_writes=False)
    else:
        if audit['state'] is None:return dict(status='WAITING_ACCOUNT',mode=mode,account_writes=False)
        if now()>=core.stamp(validated['end_close_at']):return dict(status='EVALUATION_ENDED_NO_MONTHLY_WORK',mode=mode,account_writes=False)
        core.need(policy.get('schema')=='REGISTERED_PAPER_MONTHLY_PUBLICATION_POLICY_V1' and policy.get('authorization')=='COMPLETED_PAPER_BIND_ONLY','AUTOMATION_MONTHLY_POLICY_REQUIRED')
        for name,where in publisher.MODULES.items():
            core.need(policy['source_hashes'].get(name)==sha256(Path(where()).read_bytes()).hexdigest(),'AUTOMATION_MONTHLY_EXECUTABLE_PIN_REQUIRED')
        for name in publisher.COMPILE_SOURCES:
            core.need(policy['source_hashes'].get(name)==sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest(),'AUTOMATION_MONTHLY_COMPILER_PIN_REQUIRED')
        def read_reference(ref):
            raw=core.path_at(root,ref['path']).read_bytes();core.need(sha256(raw).hexdigest()==ref['sha256'],'AUTOMATION_MONTHLY_CONFIG_CHANGED');return json.loads(raw)
        rolling_config=read_reference(policy['rolling'])
        core.need(rolling_config['bootstrap']==validated['request']['refs']['bootstrap'],'AUTOMATION_MONTHLY_BOOTSTRAP_MISMATCH')
        first=read_reference(rolling_config['first_coordinator'])
        base=validated['request']['refs']['daily']
        core.need(core.path_at(root,first['daily_config'])==core.path_at(root,base['path']) and first['daily_sha256']==base['sha256'],'AUTOMATION_MONTHLY_DAILY_MISMATCH')
        settings=read_reference({'path':first['settings_path'],'sha256':first['settings_sha256']})
        capture_plan=read_reference({'path':settings['plan_path'],'sha256':settings['plan_sha256']})
        core.need(capture_plan.get('domain_path')==policy['domain']['path'] and capture_plan.get('domain_source_hashes')==policy['domain_source_hashes'],'AUTOMATION_MONTHLY_DOMAIN_MISMATCH')
        for path,h in policy['domain_source_hashes'].items():
            core.need(sha256(core.path_at(root,path).read_bytes()).hexdigest()==h,'AUTOMATION_MONTHLY_DOMAIN_CHANGED')
        calendar=validated['request']['refs']['calendar']
        core.need(settings['schedule_path']==calendar['path'] and settings['fixed_source_hashes'][calendar['path']]==calendar['sha256'],'AUTOMATION_MONTHLY_CALENDAR_MISMATCH')
        preview=dict(status='PREFLIGHT_ONLY',mode=mode,account_writes=False)
    if not execute:return preview
    def contention():
        # Existing locks contain no PID or lease: do not assert they are live.
        return dict(status='LOCK_PRESENT_REVIEW_REQUIRED',account_writes=False,strategy_dispatches=0)
    if registrar.safe_path(root,registrar.LOCK).exists():return contention()
    logs=registrar.safe_path(root,descriptor['log_directory']);logs.mkdir(parents=True,exist_ok=True)
    own_lock=logs/'running.lock';token=uuid4().hex
    try:registrar.save_bytes(own_lock,token.encode())
    except FileExistsError:return contention()
    attempt=None
    try:
        for old in logs.iterdir():
            if not old.is_dir():continue
            core.need(not (old/'failed.json').exists() and (old/'started.json').is_file() and (old/'complete.json').is_file() and (old/'result.json').is_file(),'AUTOMATION_PARTIAL_RUN_REQUIRES_REVIEW')
            finished=json.loads((old/'complete.json').read_bytes())
            core.need(finished['result_sha256']==sha256((old/'result.json').read_bytes()).hexdigest(),'AUTOMATION_RESULT_CHANGED')
        attempt=logs/uuid4().hex;attempt.mkdir()
        registrar.save(attempt/'started.json',dict(descriptor_sha256=expected_descriptor_sha256,mode=mode,started_at=now().isoformat()))
        def guarded_clock():
            gate()
            if route is not None:
                core.need(sha256(Path(route['proof_path']).read_bytes()).hexdigest()==route['proof_sha256'],'AUTOMATION_ROUTE_PROOF_CHANGED')
                core.need(sha256(Path(route['route_path']).read_bytes()).hexdigest()==route['route_sha256'],'AUTOMATION_ROUTE_CHANGED')
                for path,h in proof['input_hashes'].items():core.need(sha256(core.path_at(root,path).read_bytes()).hexdigest()==h,'AUTOMATION_ROUTE_INPUT_CHANGED')
            return now()
        if mode=='daily':
            options=dict(root=root,registration_directory=descriptor['registration_directory'],expected_request_sha256=descriptor['request_sha256'],execute=True,clock=guarded_clock,transports=transports)
            if route is not None:options.update(route_path=route['route_path'],expected_route_sha256=route['route_sha256'])
            try:result=runtime.run(**options)
            except ValueError as error:
                # This exact runtime error occurs before acquiring its lock or dispatch.
                if str(error)!='RUN_LOCK_PRESENT_REVIEW_IF_STALE':raise
                result=contention()
        else:
            shared=registrar.safe_path(root,registrar.LOCK);shared.parent.mkdir(parents=True,exist_ok=True);shared_token=uuid4().hex
            try:registrar.save_bytes(shared,shared_token.encode())
            except FileExistsError:
                result=contention()
                registrar.save(attempt/'result.json',result)
                registrar.save(attempt/'complete.json',dict(descriptor_sha256=expected_descriptor_sha256,result_sha256=sha256((attempt/'result.json').read_bytes()).hexdigest(),finished_at=now().isoformat()))
                return result
            try:
                fresh=bundle();runtime.audit_runtime_receipts(validated=fresh,now=guarded_clock())
                core.need(now()<core.stamp(fresh['end_close_at']),'MONTHLY_EVALUATION_WINDOW_ELAPSED')
                selected=policy['rolling']
                result=rolling.run(config_path=core.path_at(root,selected['path']),config_sha256=selected['sha256'],execute=True,clock=guarded_clock)
            finally:
                core.need(shared.read_bytes()==shared_token.encode(),'MONTHLY_SHARED_LOCK_CHANGED');shared.unlink()
            # Publisher independently takes the shared lock and current SQLite CAS.
            # A crash between these stages leaves this attempt incomplete; no blind retry.
            months=list(result.get('completed_months',[]))
            if result.get('result',{}).get('status')=='MONTHLY_RUNTIME_PUBLISHED':months.append(result['target_month'])
            routes=[]
            for target in dict.fromkeys(months):
                if evaluation['start_session'][:7]<=target<=evaluation['end_session'][:7]:
                    routes.append(publisher.run(**dict(publish_args,clock=guarded_clock),target_month=target,execute=True))
            result=dict(result,registered_routes=routes)
        registrar.save(attempt/'result.json',result)
        registrar.save(attempt/'complete.json',dict(descriptor_sha256=expected_descriptor_sha256,result_sha256=sha256((attempt/'result.json').read_bytes()).hexdigest(),finished_at=guarded_clock().isoformat()))
        return result
    except BaseException:
        if attempt is not None and not (attempt/'failed.json').exists():registrar.save(attempt/'failed.json',dict(reason='AUTOMATION_RUN_REQUIRES_RECONCILIATION'))
        raise
    finally:
        try:
            core.need(own_lock.read_bytes()==token.encode(),'AUTOMATION_LOCK_OWNERSHIP_CHANGED');own_lock.unlink()
        except BaseException:
            if attempt is not None and not (attempt/'failed.json').exists():registrar.save(attempt/'failed.json',dict(reason='AUTOMATION_LOCK_CLEANUP_REQUIRES_RECONCILIATION'))
            raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--descriptor-path',required=True);parser.add_argument('--expected-descriptor-sha256',required=True)
    parser.add_argument('--mode',choices=['daily','monthly'],required=True);parser.add_argument('--execute',action='store_true')
    try:result=run(**vars(parser.parse_args(argv)))
    except Exception as error:
        reason=str(error) if isinstance(error,ValueError) and str(error).replace('_','').isalnum() else 'AUTOMATION_BLOCKED'
        result=dict(status='BLOCKED',reason=reason)
    print(json.dumps(result));return 0 if result.get('status') in {'PREFLIGHT_ONLY','COMPLETE','REGISTERED_BOOTSTRAP_COMPLETE','SKIPPED','SKIPPED_NO_DISPATCH','WAITING_ACCOUNT','WAITING_FIRST_SESSION','WAITING_SESSION_CLOSE','EVALUATION_ENDED_NO_MONTHLY_WORK','MONTHLY_COMPLETE_NEXT_PLAN_READY'} else 2

if __name__=='__main__':raise SystemExit(main())
