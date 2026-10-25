"""Prospective prewake launcher. No registration, account initialization or task install by default."""
import argparse,json,time
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from data.strategy_paper_window_planning_v1 import planning_state


def wait_for_window(*,calendar,start_session,end_session,account_initialized,clock,sleep,dispatch):
    previous=None
    while True:
        now=clock()
        if previous is not None and now<previous:raise ValueError('PREWAKE_CLOCK_ROLLBACK')
        previous=now
        state=planning_state(now=now,calendar=calendar,start_session=start_session,
                             end_session=end_session,account_initialized=account_initialized)
        if state['dispatch']:
            # Dispatcher revalidates the actual clock, source pins, locks and account.
            return dispatch()
        if state['status']!='WAITING_1000':return dict(state,account_writes=False,strategy_dispatches=0)
        sleep(min(.25,state['wait_seconds']))


def run(*,config_path,expected_sha256,execute=False):
    path=Path(config_path).resolve();raw=path.read_bytes()
    if sha256(raw).hexdigest()!=expected_sha256:raise ValueError('PREWAKE_CONFIGURATION_CHANGED')
    config=json.loads(raw);root=Path(config['root']).resolve()
    def read(ref):
        p=(root/ref['path']).resolve()
        if not p.is_relative_to(root) or sha256(p.read_bytes()).hexdigest()!=ref['sha256']:raise ValueError('PREWAKE_REFERENCE_CHANGED')
        return json.loads(p.read_bytes())
    def gate():
        if path.read_bytes()!=raw:raise ValueError('PREWAKE_CONFIGURATION_CHANGED')
        for name,expected in config['source_pins'].items():
            p=(root/name).resolve()
            if not p.is_relative_to(root) or sha256(p.read_bytes()).hexdigest()!=expected:raise ValueError('PREWAKE_SOURCE_CHANGED')
    gate();descriptor=read(config['automation']);request=read(config['request']);calendar=read(request['refs']['calendar'])
    if descriptor['request_sha256']!=config['request']['sha256']:raise ValueError('PREWAKE_REQUEST_BINDING')
    if not execute:return dict(status='PREFLIGHT_CANDIDATE_ONLY',activation_reviewed=config['activation_reviewed'],account_writes=False,task_changed=False)
    if config['activation_reviewed'] is not True:raise ValueError('PREWAKE_CANDIDATE_NOT_ACTIVATED')
    from scripts import run_registered_paper_automation as original
    from scripts import run_registered_quantity_v2_paper_simulation as runtime
    def clock():return datetime.now(timezone.utc)
    validated=runtime.load_bundle(root=root,registration_directory=descriptor['registration_directory'],
        expected_request_sha256=descriptor['request_sha256'],now=clock())
    audited=runtime.audit_runtime_receipts(validated=validated,now=clock())
    def dispatch():
        gate()
        return original.run(descriptor_path=root/config['automation']['path'],
            expected_descriptor_sha256=config['automation']['sha256'],mode='daily',execute=True)
    return wait_for_window(calendar=calendar,start_session=request['evaluation']['start_session'],
        end_session=request['evaluation']['end_session'],account_initialized=audited['state'] is not None,
        clock=clock,sleep=time.sleep,dispatch=dispatch)


def main():
    p=argparse.ArgumentParser();p.add_argument('--config-path',required=True);p.add_argument('--expected-sha256',required=True);p.add_argument('--execute',action='store_true')
    try:result=run(**vars(p.parse_args()))
    except Exception as e:result=dict(status='BLOCKED',reason=str(e) if isinstance(e,ValueError) else 'PREWAKE_FAILED',account_writes=False)
    print(json.dumps(result));return 2 if result['status']=='BLOCKED' or 'REVIEW_REQUIRED' in result['status'] else 0
if __name__=='__main__':raise SystemExit(main())
