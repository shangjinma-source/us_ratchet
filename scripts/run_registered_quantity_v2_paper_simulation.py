"""Registration-bound bootstrap, daily dispatch and terminal settlement.

Default is read-only. --verify-under-lock repeats checks under the existing
daily lock without dispatch. --execute requires an approved registration bundle.
"""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
import sys
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from backtest import current_quantity_v2_simulation_store as stores
from data import registered_quantity_v2_paper_protocol as core
from scripts import register_quantity_v2_paper_protocol as registrar
from scripts import bootstrap_current_quantity_v2_simulation as bootstrap
from scripts import run_current_quantity_v2_simulation as daily
from scripts import finalize_registered_paper_runtime as terminal
from backtest import registered_paper_settlement_runtime as settlement

SELF='scripts/run_registered_quantity_v2_paper_simulation.py'
STORE='backtest/current_quantity_v2_simulation_store.py'
EXECUTION_MODULES={'scripts/bootstrap_current_quantity_v2_simulation.py':bootstrap,
    'scripts/run_current_quantity_v2_simulation.py':daily,
    'scripts/finalize_registered_paper_runtime.py':terminal,
    'backtest/registered_paper_settlement_runtime.py':settlement}


def load_bundle(*,root,registration_directory,expected_request_sha256,now):
    root=Path(root).resolve();directory=registrar.safe_path(root,registration_directory)
    for name in ('failed.json','lock_cleanup_failed.json'):
        registrar.require(not (directory/name).exists(),'REGISTRATION_RECONCILIATION_REQUIRED')
    def read(name):
        path=registrar.safe_path(root,(directory/name).relative_to(root).as_posix())
        return json.loads(path.read_bytes())
    complete=read('complete.json');receipt=read('receipt.json');started=read('started.json')
    registrar.require(complete.get('status')=='REGISTERED_NOT_ACTIVATED'
        and complete.get('request_sha256')==expected_request_sha256,'REGISTRATION_COMPLETE_MISMATCH')
    registrar.require(complete.get('receipt_sha256')==sha256((directory/'receipt.json').read_bytes()).hexdigest(),
                      'REGISTRATION_RECEIPT_HASH_MISMATCH')
    registrar.require(started.get('status')=='STARTED' and started.get('request_sha256')==expected_request_sha256,
                      'REGISTRATION_STARTED_MISMATCH')
    registrar.require(core.stamp(started['started_at'])<=core.stamp(receipt['registered_at'])<=core.stamp(complete['completed_at'])<=core.stamp(now),
                      'REGISTRATION_TIME_ORDER_INVALID')
    checked=core.validate_registration(root=root,request_path=directory/'request.json',
        expected_request_sha256=expected_request_sha256,receipt=receipt,now=now)
    registrar.require(registrar.safe_path(root,checked['request']['output_directory'])==directory,'REGISTRATION_DIRECTORY_MISMATCH')
    for name,module in [(SELF,Path(__file__)),(registrar.CORE,Path(core.__file__)),
                        (registrar.REGISTRAR,Path(registrar.__file__)),(STORE,Path(stores.__file__))]:
        registrar.require(checked['request']['source_hashes'].get(name)==sha256(module.read_bytes()).hexdigest(),
                          'REGISTERED_RUNTIME_EXECUTABLE_PIN_MISMATCH')
    return dict(checked,registration_directory=str(directory),registration_receipt_sha256=complete['receipt_sha256'])


def audit_runtime_receipts(*,validated,now):
    """Read-only account/receipt integrity audit, without decision-time admission.

    Caller must validate the registration bundle first and hold the shared lock
    for any subsequent mutation. This helper grants no dispatch permission.
    """
    request=validated['request'];root=Path(validated['root']);directory=Path(validated['registration_directory'])
    identity=request['identity'];database=Path(validated['database_path'])
    core.stamp(now)
    runtime=directory/'runtime'
    for name in ('bootstrap_failed.json','bootstrap_reconciliation_required.json','start_failed.json','execution_reconciliation_required.json'):
        registrar.require(not (runtime/name).exists(),'BOOTSTRAP_RECONCILIATION_REQUIRED')
    if runtime.exists():
        for attempt in runtime.iterdir():
            if attempt.name not in ('bootstrap-attempt','finalize-attempt') and not attempt.name.startswith('daily-'):continue
            registrar.require(attempt.is_dir() and not attempt.is_symlink(),'INVALID_EXECUTION_ATTEMPT_DIRECTORY')
            registrar.require(not (attempt/'failed.json').exists()
                and all((attempt/name).is_file() for name in ('started.json','complete.json','result.json')),
                'INCOMPLETE_EXECUTION_ATTEMPT_RECONCILIATION_REQUIRED')
            started=json.loads((attempt/'started.json').read_bytes())
            complete=json.loads((attempt/'complete.json').read_bytes())
            raw=(attempt/'result.json').read_bytes();result=json.loads(raw)
            phase={'bootstrap-attempt':'FIRST_BOOTSTRAP_ELIGIBLE_NOT_EXECUTED',
                'finalize-attempt':'SETTLEMENT_ONLY_ELIGIBLE_NOT_EXECUTED'}.get(attempt.name,'DAILY_ELIGIBLE_NOT_EXECUTED')
            expected_session=('terminal-'+request['evaluation']['end_session'] if attempt.name=='finalize-attempt' else
                request['evaluation']['start_session'] if attempt.name=='bootstrap-attempt' else attempt.name.removeprefix('daily-'))
            registrar.require(all(value.get('request_sha256')==validated['request_sha256'] and value.get('phase')==phase
                for value in (started,complete,result))
                and complete.get('registration_receipt_sha256')==validated['registration_receipt_sha256']
                and started.get('registration_receipt_sha256')==validated['registration_receipt_sha256']
                and complete.get('session')==expected_session
                and complete.get('result_sha256')==sha256(raw).hexdigest()
                and complete.get('revision')==result.get('revision')
                and core.stamp(started['started_at'])<=core.stamp(result['finished_at'])<=core.stamp(now),
                'EXECUTION_ATTEMPT_BINDING_RECONCILIATION_REQUIRED')
    state=None;revision=None
    if database.exists():
        registrar.require((runtime/'start.json').is_file() and (runtime/'start_complete.json').is_file(),
                          'EXISTING_DATABASE_WITHOUT_REGISTERED_START')
        start=json.loads((runtime/'start.json').read_bytes());complete=json.loads((runtime/'start_complete.json').read_bytes())
        registrar.require(complete.get('status')=='REGISTERED_BOOTSTRAP_COMPLETE'
            and complete.get('request_sha256')==validated['request_sha256']
            and complete.get('registration_receipt_sha256')==validated['registration_receipt_sha256']
            and complete.get('start_sha256')==sha256((runtime/'start.json').read_bytes()).hexdigest(),
            'REGISTERED_START_COMPLETE_MISMATCH')
        store=stores.SimulationStore(database);current=store.read(identity['simulation_id'])
        core.validate_start_receipt(validated=validated,receipt=start,simulation=current['simulation'],now=now)
        registrar.require(all(x['status']=='COMPLETE' for x in store.inspect_operations(identity['simulation_id'])['operations']),
                          'ACCOUNT_OPERATION_RECONCILIATION_REQUIRED')
        state=current['simulation'];revision=current['revision']
    else:
        registrar.require(not any(Path(str(database)+s).exists() for s in ('-wal','-shm','-journal')),
                          'ACCOUNT_SIDECAR_WITHOUT_DATABASE')
        registrar.require(not runtime.exists(),'PRIOR_BOOTSTRAP_ARTIFACTS_REQUIRE_RECONCILIATION')
    return dict(state=state,revision=revision,account_writes=False,strategy_dispatches=0)


def inspect_admission(*,validated,now,route_path=None,expected_route_sha256=None):
    request=validated['request'];root=Path(validated['root'])
    local=core.stamp(now).astimezone(ZoneInfo('America/New_York'))
    audited=audit_runtime_receipts(validated=validated,now=now)
    state=audited['state'];revision=audited['revision']
    registrar.require((route_path is None)==(expected_route_sha256 is None),'EXTERNAL_ROUTE_HASH_REQUIRED')
    route_status=None
    if route_path is not None:
        registrar.require(state is not None,'ROUTE_REQUIRES_REGISTERED_ACCOUNT')
        route_status=core.validate_route_binding(validated=validated,route_path=route_path,
            expected_route_sha256=expected_route_sha256,simulation=state)
        raw=core.path_at(root,route_path).read_bytes()
        registrar.require(sha256(raw).hexdigest()==expected_route_sha256,'ROUTE_CHANGED_AFTER_VALIDATION')
        registrar.require(json.loads(raw)['target_month']==local.strftime('%Y-%m'),'ROUTE_NOT_CURRENT_SESSION_MONTH')
    first=core.stamp(validated['first_decision_at']);end=core.stamp(validated['end_close_at'])
    if state is None:
        if core.stamp(now)<first:phase='WAITING_FIRST_SESSION'
        else:
            core.validate_decision_time(validated=validated,now=now)
            registrar.require(local.date().isoformat()==request['evaluation']['start_session'],'MISSED_REGISTERED_START')
            phase='FIRST_BOOTSTRAP_ELIGIBLE_NOT_EXECUTED'
    elif core.stamp(now)>=end:phase='SETTLEMENT_ONLY_ELIGIBLE_NOT_EXECUTED'
    else:
        core.validate_decision_time(validated=validated,now=now)
        accepted=core.stamp(state['origin']['ledger']['acceptance']['accepted_at']).astimezone(ZoneInfo('America/New_York'))
        phase='BOOTSTRAPPED_CURRENT_SESSION_NO_NEW_DECISION' if accepted.date()==local.date() else 'DAILY_ELIGIBLE_NOT_EXECUTED'
    return dict(status='ADMISSION_ONLY_NO_DISPATCH',phase=phase,request_sha256=validated['request_sha256'],
        revision=revision,route_validated=route_status is not None,account_writes=False,strategy_dispatches=0)


def run(*,root,registration_directory,expected_request_sha256,verify_under_lock=False,execute=False,
        route_path=None,expected_route_sha256=None,clock=None,transports=None):
    root=Path(root).resolve();clock=clock or (lambda:datetime.now(timezone.utc));previous=[None]
    def now():
        value=core.stamp(clock());registrar.require(previous[0] is None or value>=previous[0],'RUNTIME_CLOCK_ROLLBACK')
        previous[0]=value;return value
    def check():
        validated=load_bundle(root=root,registration_directory=registration_directory,
            expected_request_sha256=expected_request_sha256,now=now())
        return inspect_admission(validated=validated,now=now(),route_path=route_path,expected_route_sha256=expected_route_sha256)
    if not verify_under_lock and not execute:return check()
    lock=registrar.safe_path(root,registrar.LOCK);lock.parent.mkdir(parents=True,exist_ok=True)
    token=uuid4().hex
    preserve_lock=[False]
    reconciliation_directory=[None]
    try:registrar.save_bytes(lock,token.encode())
    except FileExistsError:raise ValueError('RUN_LOCK_PRESENT_REVIEW_IF_STALE') from None
    try:
        admitted=check()
        if not execute:return admitted
        phase=admitted['phase']
        if phase in ('WAITING_FIRST_SESSION','BOOTSTRAPPED_CURRENT_SESSION_NO_NEW_DECISION'):
            return dict(admitted,status='SKIPPED_NO_DISPATCH')
        def gate():
            observed=now()
            validated=load_bundle(root=root,registration_directory=registration_directory,
                expected_request_sha256=expected_request_sha256,now=observed)
            for name,module in EXECUTION_MODULES.items():
                registrar.require(validated['request']['source_hashes'].get(name)==sha256(Path(module.__file__).read_bytes()).hexdigest(),
                                  'REGISTERED_EXECUTION_PIN_REQUIRED')
            return validated,observed
        validated,observed=gate();request=validated['request'];identity=request['identity']
        directory=Path(validated['registration_directory']);runtime=directory/'runtime'
        reconciliation_directory[0]=runtime
        session=observed.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        is_boot=phase=='FIRST_BOOTSTRAP_ELIGIBLE_NOT_EXECUTED'
        is_final=phase=='SETTLEMENT_ONLY_ELIGIBLE_NOT_EXECUTED'
        attempt=runtime/('bootstrap-attempt' if is_boot else ('finalize-attempt' if is_final else 'daily-'+session))
        if attempt.exists():
            registrar.require(not (attempt/'failed.json').exists() and (attempt/'complete.json').is_file(),
                              'REGISTERED_ATTEMPT_REQUIRES_RECONCILIATION')
            previous_result=json.loads((attempt/'complete.json').read_bytes())
            registrar.require(previous_result.get('request_sha256')==expected_request_sha256
                and previous_result.get('registration_receipt_sha256')==validated['registration_receipt_sha256']
                and previous_result.get('phase')==phase
                and previous_result.get('session')==('terminal-'+request['evaluation']['end_session'] if is_final else session)
                and previous_result.get('revision')==admitted['revision'],'ATTEMPT_REGISTRATION_MISMATCH')
            raw=(attempt/'result.json').read_bytes()
            registrar.require(sha256(raw).hexdigest()==previous_result.get('result_sha256'),'ATTEMPT_RESULT_CHANGED')
            return dict(json.loads(raw),replayed=True,account_writes=False)
        attempt.mkdir(parents=True,exist_ok=False)
        registrar.save(attempt/'started.json',dict(request_sha256=expected_request_sha256,
            registration_receipt_sha256=validated['registration_receipt_sha256'],started_at=observed.isoformat(),phase=phase))
        def guarded_clock():
            _,value=gate()
            if is_boot:
                core.validate_decision_time(validated=validated,now=value)
                registrar.require(value.astimezone(ZoneInfo('America/New_York')).date().isoformat()==request['evaluation']['start_session'],
                                  'BOOTSTRAP_START_WINDOW_ELAPSED')
            if route_path is not None:
                registrar.require(sha256(core.path_at(root,route_path).read_bytes()).hexdigest()==expected_route_sha256,'ROUTE_CHANGED_AFTER_VALIDATION')
            return value
        try:
            if is_boot:
                ref=request['refs']['bootstrap']
                bootstrap.run(config_path=core.path_at(root,ref['path']),config_sha256=ref['sha256'],execute=True,
                    clock=guarded_clock,fetch=(transports or {}).get('quotes'))
                saved=stores.SimulationStore(validated['database_path']).read(identity['simulation_id'])
                start=dict(schema='REGISTERED_PAPER_START_V1',request_sha256=expected_request_sha256,
                    started_at=saved['simulation']['origin']['ledger']['acceptance']['accepted_at'],
                    origin_sha256=core.digest(saved['simulation']['origin']))
                core.validate_start_receipt(validated=validated,receipt=start,simulation=saved['simulation'],now=guarded_clock())
                registrar.save(runtime/'start.json',start)
                registrar.save(runtime/'start_complete.json',dict(status='REGISTERED_BOOTSTRAP_COMPLETE',
                    request_sha256=expected_request_sha256,registration_receipt_sha256=validated['registration_receipt_sha256'],
                    start_sha256=sha256((runtime/'start.json').read_bytes()).hexdigest(),initial_revision=saved['revision']))
                result=dict(status='REGISTERED_BOOTSTRAP_COMPLETE',revision=saved['revision'])
            else:
                ref=request['refs']['daily']
                if not is_final and route_path is not None:
                    ref=json.loads(core.path_at(root,route_path).read_bytes())['configuration']
                if is_final:
                    result=terminal.run(config_path=core.path_at(root,ref['path']),config_sha256=ref['sha256'],
                        account_id=identity['account_id'],expected_revision=admitted['revision'],evaluation_end=request['evaluation']['end_session'],
                        execute=True,clock=guarded_clock,transports=transports)
                else:
                    result=daily.run_runtime(config_path=core.path_at(root,ref['path']),config_sha256=ref['sha256'],
                        session=session,triggered_at=observed.isoformat(),execute=True,clock=guarded_clock,transports=transports)
                saved=stores.SimulationStore(validated['database_path']).read(identity['simulation_id'])
                start=json.loads((runtime/'start.json').read_bytes())
                core.validate_start_receipt(validated=validated,receipt=start,simulation=saved['simulation'],now=guarded_clock())
            summary={k:result[k] for k in ('status','daily_status','settlement_status','revision','new_decisions') if k in result}
            summary.update(request_sha256=expected_request_sha256,phase=phase,finished_at=guarded_clock().isoformat())
            if not is_boot:
                outcome=result.get('settlement_status') if is_final else result.get('daily_status')
                successes=('FINALIZED_DECLARED_END','ALREADY_FINALIZED') if is_final else ('CONTINUATION_COMPLETE','MONTHLY_COMPLETE','ALREADY_COMPLETED')
                summary['status']='COMPLETE' if outcome in successes else ('SKIPPED' if outcome=='LATE_NO_NEW_DECISION' else 'BLOCKED')
                if summary['status']=='BLOCKED':summary['reason']=outcome or 'UNRECOGNIZED_RUNTIME_OUTCOME'
            registrar.save(attempt/'result.json',summary)
            registrar.save(attempt/'complete.json',dict(request_sha256=expected_request_sha256,
                registration_receipt_sha256=validated['registration_receipt_sha256'],phase=phase,
                session='terminal-'+request['evaluation']['end_session'] if is_final else session,
                revision=summary['revision'],result_sha256=sha256((attempt/'result.json').read_bytes()).hexdigest()))
            return summary
        except Exception:
            current_revision=None
            try:current_revision=stores.SimulationStore(validated['database_path']).read(identity['simulation_id'])['revision']
            except Exception:pass
            failure=dict(status='EXECUTION_RECONCILIATION_REQUIRED',request_sha256=expected_request_sha256,
                previous_revision=admitted['revision'],observed_revision=current_revision,
                database_exists=Path(validated['database_path']).exists(),attempt=str(attempt),
                reason='COMPLETION_UNRECORDED_REVIEW_STORE_AND_ATTEMPT')
            try:registrar.save(runtime/'execution_reconciliation_required.json',failure)
            except Exception:
                preserve_lock[0]=True
                raise
            registrar.save(attempt/'failed.json',failure)
            if is_boot:
                registrar.save(runtime/'bootstrap_reconciliation_required.json',dict(status='RECONCILIATION_REQUIRED',request_sha256=expected_request_sha256))
            raise
    finally:
        try:
            registrar.require(not preserve_lock[0],'RUNTIME_LOCK_PRESERVED_FOR_RECONCILIATION')
            registrar.require(lock.read_bytes()==token.encode(),'RUNTIME_LOCK_OWNERSHIP_CHANGED')
            lock.unlink()
        except Exception:
            destination=reconciliation_directory[0]
            if destination is not None:
                destination.mkdir(parents=True,exist_ok=True)
                marker=destination/'execution_reconciliation_required.json'
                if not marker.exists():
                    registrar.save(marker,dict(status='LOCK_RECONCILIATION_REQUIRED',request_sha256=expected_request_sha256,
                        reason='LOCK_CLEANUP_FAILED_AFTER_DISPATCH_OR_ADMISSION'))
            raise ValueError('RUNTIME_LOCK_RECONCILIATION_REQUIRED') from None


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
    p.add_argument('--registration-directory',required=True)
    p.add_argument('--request-sha256',dest='expected_request_sha256',required=True)
    p.add_argument('--verify-under-lock',action='store_true')
    p.add_argument('--execute',action='store_true')
    p.add_argument('--route-path');p.add_argument('--route-sha256',dest='expected_route_sha256')
    try:result=run(**vars(p.parse_args(argv)))
    except Exception as error:
        reason=str(error) if isinstance(error,ValueError) and str(error).replace('_','').isalnum() else 'REGISTERED_ADMISSION_BLOCKED'
        result=dict(status='BLOCKED',reason=reason)
    print(json.dumps(result));return 2 if result['status']=='BLOCKED' else 0


if __name__=='__main__':raise SystemExit(main())
