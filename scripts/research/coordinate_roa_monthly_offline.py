"""Offline ROA month coordination. No acquisition, activation, account writes or scheduler."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
from scripts.research.prepare_roa_monthly_package import prepare as prepare_package
from scripts.research.prepare_roa_monthly_registration import prepare as prepare_registration
from data.roa_monthly_loader import RoaMonthlySelectionLoader


def coordinate(*, root, request, now):
    root=Path(root).resolve()
    if now.tzinfo is None: raise ValueError('AWARE_TIME_REQUIRED')
    def bounded(name):
        p=Path(name)
        if p.is_absolute() or '..' in p.parts or ':' in str(name): raise ValueError('PATH_OUTSIDE_ROOT')
        p=(root/p).resolve()
        if not p.is_relative_to(root): raise ValueError('PATH_OUTSIDE_ROOT')
        return p
    def read(spec):
        p=bounded(spec['path'])
        if not p.is_file(): raise FileNotFoundError(spec['path'])
        raw=p.read_bytes()
        if sha256(raw).hexdigest()!=spec['sha256']: raise ValueError('SOURCE_CHANGED:'+spec['path'])
        return json.loads(raw)
    def save(p,value):
        with p.open('xb') as f:f.write(json.dumps(value,sort_keys=True,indent=2).encode())
    active=read(request['active'])
    configuration=read(dict(path=active['configuration_path'],sha256=active['configuration_sha256']))
    if active.get('schema')!='STRATEGY_SERVER_ACTIVE_V6' or configuration.get('schema')!='ROA_UNIFIED_PREPARATION_V34':raise ValueError('ACTIVE_ROA_REQUIRED')
    for name,digest in configuration['source_pins'].items():
        if sha256(bounded(name).read_bytes()).hexdigest()!=digest:raise ValueError('CODE_SOURCE_CHANGED:'+name)
    calendar=read(request['package']['session_calendar'])
    day=request['decision_date']
    rows=[r for r in calendar['sessions'] if r['date']==day]
    if len(rows)!=1: raise ValueError('WAIT_MONTH_END_SESSION_CALENDAR')
    close=datetime.fromisoformat(rows[0]['close'])
    if close.tzinfo is None: raise ValueError('AWARE_CLOSE_REQUIRED')
    if now<close:return dict(status='WAIT_COMPLETED_MONTH_END',decision_date=day,account_writes=False)
    missing=[s['path'] for s in (request['package'][k] for k in ('manifest','session_calendar','training_calendar')) if not bounded(s['path']).is_file()]
    if missing:return dict(status='WAIT_REQUIRED_MONTH_INPUT',missing=missing,acquisition_implemented=False,account_writes=False)
    manifest=read(request['package']['manifest'])
    if manifest['decision_date']!=day: raise ValueError('REQUEST_DECISION_CONFLICT')
    output=bounded(request['output_directory'])
    inputs=[bounded(request['active']['path']),bounded(active['configuration_path'])]+[bounded(request['package'][k]['path']) for k in ('manifest','session_calendar','training_calendar')]
    if output==root or any(output==p or output in p.parents for p in inputs):raise ValueError('OUTPUT_INPUT_OVERLAP')
    output.mkdir(parents=True,exist_ok=True)
    key=sha256(json.dumps(request,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    lock=output/'running.lock'
    try:
        with lock.open('xb') as f:f.write(key.encode())
    except FileExistsError:return dict(status='BUSY_OR_NEEDS_LOCK_RECONCILIATION',automatic_retry=False,account_writes=False)
    try:
        complete=output/'complete.json'
        if complete.exists():
            old=json.loads(complete.read_bytes())
            if old['request_sha256']!=key:raise ValueError('REQUEST_CONFLICT')
            read(request['active'])
            for name,digest in old['artifact_hashes'].items():
                if sha256(bounded(name).read_bytes()).hexdigest()!=digest:raise ValueError('PREPARED_ARTIFACT_CHANGED:'+name)
            registry=json.loads(bounded(old['registry_proposal']).read_bytes())
            RoaMonthlySelectionLoader(root=root,registry=registry)(old['execution_session'])
            read(request['active'])
            return dict(old,reused=True)
        attempt=output/('attempt-'+uuid4().hex);attempt.mkdir()
        save(attempt/'request.json',request)
        try:
            package=dict(request['package'],output_directory=(attempt/'package').relative_to(root).as_posix())
            result=prepare_package(root=root,request=package,now=now,create=True)
            read(request['active'])
            receipt_path=(attempt/'package/receipt.json').relative_to(root).as_posix()
            registration=prepare_registration(root=root,active_path=request['active']['path'],active_sha256=request['active']['sha256'],receipt_path=receipt_path,receipt_sha256=sha256(bounded(receipt_path).read_bytes()).hexdigest(),output_directory=(attempt/'registration').relative_to(root).as_posix())
            read(request['active'])
            runtime=json.loads(bounded(result['runtime_path']).read_bytes())
            hashes={p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest() for p in attempt.rglob('*') if p.is_file()}
            ready=dict(status='PREPARED_REGISTRATION_NOT_ACTIVATED',request_sha256=key,month=result['month'],registry_proposal=result['registry_proposal'],execution_session=runtime['first_execution_session'],registration=registration,artifact_hashes=hashes,account_writes=False,schedules_changed=False,acquisition_implemented=False,automatic_activation=False)
            read(request['active'])
            save(complete,ready)
            read(request['active'])
            return dict(ready,reused=False)
        except Exception as error:
            save(attempt/'failure.json',dict(status='FAILED_NOT_ACTIVATED',error=str(error),account_writes=False))
            raise
    finally:lock.unlink()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True,help='Trusted server-owned coordinator request JSON')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    request_path=Path(args.request).resolve()
    if not request_path.is_relative_to(root):raise ValueError('REQUEST_OUTSIDE_ROOT')
    result=coordinate(root=root,request=json.loads(request_path.read_bytes()),now=datetime.now(timezone.utc))
    print(json.dumps(result,ensure_ascii=False))
