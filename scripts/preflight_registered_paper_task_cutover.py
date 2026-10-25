"""Read-only deployment admission. Does not register, dispatch, or create accounts."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import run_registered_paper_automation as automation


def preflight(*, descriptor_path, expected_descriptor_sha256, owned_lock_token=None, clock=None):
    raw=Path(descriptor_path).read_bytes()
    automation.core.need(sha256(raw).hexdigest()==expected_descriptor_sha256,'DESCRIPTOR_CHANGED')
    descriptor=json.loads(raw);root=Path(descriptor['root']).resolve()
    automation.core.need(descriptor['schema']=='REGISTERED_PAPER_AUTOMATION_V1','DESCRIPTOR_SCHEMA')
    automation.core.need(Path(descriptor_path).resolve().is_relative_to(root),'DESCRIPTOR_OUTSIDE_ROOT')
    for path,h in descriptor['source_hashes'].items():
        automation.core.need(sha256(automation.core.path_at(root,path).read_bytes()).hexdigest()==h,'SOURCE_CHANGED')
    for path,where in automation.REQUIRED.items():
        automation.core.need(descriptor['source_hashes'].get(path)==sha256(Path(where()).read_bytes()).hexdigest(),'EXECUTABLE_PIN_REQUIRED')
    ref=descriptor['publication_policy'];policy_raw=automation.core.path_at(root,ref['path']).read_bytes()
    automation.core.need(sha256(policy_raw).hexdigest()==ref['sha256'],'POLICY_CHANGED')
    policy=json.loads(policy_raw)
    automation.core.need(policy.get('schema')=='REGISTERED_PAPER_MONTHLY_PUBLICATION_POLICY_V1' and policy.get('authorization')=='COMPLETED_PAPER_BIND_ONLY','MONTHLY_PUBLICATION_AUTHORITY_REQUIRED')
    for path,h in policy['source_hashes'].items():
        automation.core.need(sha256(automation.core.path_at(root,path).read_bytes()).hexdigest()==h,'MONTHLY_SOURCE_CHANGED')
    for path,where in automation.publisher.MODULES.items():
        automation.core.need(policy['source_hashes'].get(path)==sha256(Path(where()).read_bytes()).hexdigest(),'MONTHLY_EXECUTABLE_PIN_REQUIRED')
    for path in automation.publisher.COMPILE_SOURCES:
        automation.core.need(policy['source_hashes'].get(path)==sha256((Path(__file__).resolve().parents[1]/path).read_bytes()).hexdigest(),'MONTHLY_COMPILER_PIN_REQUIRED')
    automation.core.need(policy['request_sha256']==descriptor['request_sha256'] and policy['registration_directory']==descriptor['registration_directory'],'POLICY_REGISTRATION_MISMATCH')
    lock=automation.registrar.safe_path(root,automation.registrar.LOCK)
    if owned_lock_token is None:
        automation.core.need(not lock.exists(),'SHARED_LOCK_PRESENT_REVIEW_REQUIRED')
    else:
        automation.core.need(lock.read_text()==owned_lock_token,'CUTOVER_LOCK_OWNERSHIP_CHANGED')
    observed=(clock or (lambda:datetime.now(timezone.utc)))()
    validated=automation.runtime.load_bundle(root=root,registration_directory=descriptor['registration_directory'],expected_request_sha256=descriptor['request_sha256'],now=observed)
    def read(ref):
        raw=automation.core.path_at(root,ref['path']).read_bytes()
        automation.core.need(sha256(raw).hexdigest()==ref['sha256'],'MONTHLY_REFERENCE_CHANGED')
        return json.loads(raw)
    refs=validated['request']['refs'];rolling=read(policy['rolling'])
    automation.core.need(rolling['bootstrap']==refs['bootstrap'],'MONTHLY_BOOTSTRAP_MISMATCH')
    first=read(rolling['first_coordinator'])
    automation.core.need(automation.core.path_at(root,first['daily_config'])==automation.core.path_at(root,refs['daily']['path']) and first['daily_sha256']==refs['daily']['sha256'],'MONTHLY_DAILY_MISMATCH')
    settings=read({'path':first['settings_path'],'sha256':first['settings_sha256']})
    plan=read({'path':settings['plan_path'],'sha256':settings['plan_sha256']})
    automation.core.need(settings['schedule_path']==refs['calendar']['path'] and settings['fixed_source_hashes'][refs['calendar']['path']]==refs['calendar']['sha256'],'MONTHLY_CALENDAR_MISMATCH')
    automation.core.need(plan['domain_path']==policy['domain']['path'] and plan['domain_source_hashes']==policy['domain_source_hashes'],'MONTHLY_DOMAIN_MISMATCH')
    read(policy['domain'])
    for path,h in policy['domain_source_hashes'].items():
        automation.core.need(sha256(automation.core.path_at(root,path).read_bytes()).hexdigest()==h,'MONTHLY_DOMAIN_CHANGED')
    audit=automation.runtime.audit_runtime_receipts(validated=validated,now=observed)
    return dict(status='CUTOVER_ADMISSION_VERIFIED',root=str(root),database_state='ABSENT' if audit['state'] is None else 'REGISTERED_START_VERIFIED',revision=audit['revision'],account_writes=False,task_writes=False,heartbeat_action='Root must remove monthly execution from heartbeat 11; retain followup review responsibility.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--descriptor-path',required=True);parser.add_argument('--expected-descriptor-sha256',required=True)
    parser.add_argument('--owned-lock-token')
    try:result=preflight(**vars(parser.parse_args()))
    except Exception:print(json.dumps({'status':'BLOCKED','reason':'CUTOVER_PREFLIGHT_REJECTED'}));return 2
    print(json.dumps(result));return 0

if __name__=='__main__':raise SystemExit(main())
