"""Create-only registration evidence; never bootstrap an account or change tasks.

An independently approved request file SHA is required. Its source pins must
already include this registrar and the shared validator. CLI uses real UTC time.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import sys
from pathlib import Path, PurePosixPath
from uuid import uuid4

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from data import registered_quantity_v2_paper_protocol as core

LOCK = 'data/local_scheduler/quantity_v2_daily/running.lock'
REGISTRAR = 'scripts/register_quantity_v2_paper_protocol.py'
CORE = 'data/registered_quantity_v2_paper_protocol.py'


def require(condition, reason):
    if not condition: raise ValueError(reason)


def safe_path(root, relative):
    require(isinstance(relative,str) and relative and '\\' not in relative and ':' not in relative,
            'INVALID_REGISTRATION_PATH')
    parts=PurePosixPath(relative)
    require(not parts.is_absolute() and '..' not in parts.parts and '.' not in parts.parts,
            'INVALID_REGISTRATION_PATH')
    path=root
    for component in parts.parts:
        path=path/component
        require(not path.is_symlink(),'REGISTRATION_SYMLINK_NOT_ALLOWED')
        require(not getattr(path,'is_junction',lambda:False)(),'REGISTRATION_JUNCTION_NOT_ALLOWED')
    require(path.resolve().is_relative_to(root),'REGISTRATION_PATH_OUTSIDE_ROOT')
    return path


def save_bytes(path, value):
    with path.open('xb') as stream:
        stream.write(value);stream.flush();os.fsync(stream.fileno())


def save(path, value):
    save_bytes(path,(json.dumps(value,sort_keys=True,indent=2)+'\n').encode())


def run(*,root,request_path,expected_request_sha256,execute=False,clock=None):
    root=Path(root).resolve()
    clock=clock or (lambda:datetime.now(timezone.utc))
    last_clock=[None]
    def now():
        value=clock()
        require(isinstance(value,datetime) and value.tzinfo is not None,'AWARE_REGISTRATION_CLOCK_REQUIRED')
        value=value.astimezone(timezone.utc)
        require(last_clock[0] is None or value>=last_clock[0],'REGISTRATION_CLOCK_ROLLBACK')
        last_clock[0]=value
        return value
    source=safe_path(root,request_path)
    def verify():
        checked=core.validate_registration_request(root=root,request_path=source,
            expected_request_sha256=expected_request_sha256,now=now())
        request=checked['request'];pins=request['source_hashes']
        for name,loaded in [(REGISTRAR,Path(__file__)),(CORE,Path(core.__file__))]:
            require(name in pins,'REGISTRATION_EXECUTABLE_PIN_REQUIRED')
            require(sha256(loaded.read_bytes()).hexdigest()==pins[name],'REGISTRATION_EXECUTABLE_PIN_MISMATCH')
        database=Path(request['identity']['database_path'])
        if not database.is_absolute():database=safe_path(root,request['identity']['database_path'])
        require(database.resolve().is_relative_to(root),'DATABASE_PATH_OUTSIDE_ROOT')
        require(not any(Path(str(database)+suffix).exists() for suffix in ('','-wal','-shm','-journal')),
                'PREEXISTING_ACCOUNT_REQUIRES_SEPARATE_AUTHORIZED_SERIES')
        return checked
    checked=verify();request=checked['request']
    output=safe_path(root,request['output_directory'])
    lock=safe_path(root,LOCK)
    require(not source.is_relative_to(output),'REQUEST_INSIDE_REGISTRATION_OUTPUT')
    require(not lock.is_relative_to(output),'OUTPUT_OVERLAPS_SHARED_LOCK')
    require(not output.exists(),'REGISTRATION_ATTEMPT_EXISTS_NO_AUTOMATIC_RETRY')
    if not execute:return dict(status='PREFLIGHT_ONLY',request_sha256=expected_request_sha256,
        output_directory=str(output),account_created=False,task_changed=False)
    output.mkdir(parents=True,exist_ok=False)
    owned=False;token=uuid4().hex
    try:
        save(output/'started.json',dict(status='STARTED',request_sha256=expected_request_sha256,
            started_at=now().isoformat()))
        lock.parent.mkdir(parents=True,exist_ok=True)
        try:save_bytes(lock,token.encode())
        except FileExistsError:raise ValueError('RUN_LOCK_PRESENT_REVIEW_IF_STALE') from None
        owned=True
        verify()
        raw=source.read_bytes()
        require(sha256(raw).hexdigest()==expected_request_sha256,'REGISTRATION_REQUEST_CHANGED')
        receipt=dict(schema='REGISTERED_PAPER_RECEIPT_V1',request_sha256=expected_request_sha256,
            registered_at=now().isoformat())
        core.validate_registration(root=root,request_path=source,
            expected_request_sha256=expected_request_sha256,receipt=receipt,now=now())
        verify()
        save_bytes(output/'request.json',raw)
        save(output/'receipt.json',receipt)
        verify()
        save(output/'complete.json',dict(status='REGISTERED_NOT_ACTIVATED',
            request_sha256=expected_request_sha256,receipt_sha256=sha256((output/'receipt.json').read_bytes()).hexdigest(),
            completed_at=now().isoformat(),account_created=False,task_changed=False))
        return dict(status='REGISTERED_NOT_ACTIVATED',directory=str(output),request_sha256=expected_request_sha256,
            account_created=False,task_changed=False)
    except Exception as error:
        reason=str(error) if isinstance(error,ValueError) and str(error).replace('_','').isalnum() else 'REGISTRATION_FAILED_REVIEW_REQUIRED'
        save(output/'failed.json',dict(status='FAILED_REVIEW_REQUIRED',reason=reason,
            request_sha256=expected_request_sha256,failed_at=datetime.now(timezone.utc).isoformat()))
        raise
    finally:
        if owned:
            try:
                require(lock.read_bytes()==token.encode(),'REGISTRATION_LOCK_OWNERSHIP_CHANGED')
                lock.unlink()
            except Exception:
                save(output/'lock_cleanup_failed.json',dict(status='BLOCKED_LOCK_RECONCILIATION_REQUIRED',
                    request_sha256=expected_request_sha256,complete_marker_is_not_activation=True))
                raise ValueError('REGISTRATION_LOCK_RECONCILIATION_REQUIRED') from None


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--request',dest='request_path',required=True)
    parser.add_argument('--request-sha256',dest='expected_request_sha256',required=True)
    parser.add_argument('--execute',action='store_true')
    try:result=run(**vars(parser.parse_args(argv)))
    except Exception as error:
        reason=str(error) if isinstance(error,ValueError) and str(error).replace('_','').isalnum() else 'REGISTRATION_FAILED_REVIEW_REQUIRED'
        result=dict(status='BLOCKED',reason=reason)
    print(json.dumps(result));return 2 if result['status']=='BLOCKED' else 0


if __name__=='__main__':raise SystemExit(main())
