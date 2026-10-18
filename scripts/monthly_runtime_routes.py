"""Local create-only monthly releases; directory contents are not hash-pinned.

The caller explicitly trusts this local publication directory. Each release pins
its candidate bytes and baseline; runtime validation still checks all sources.
"""
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from datetime import date

from backtest.current_quantity_v2_close_capture_simulation import _read
from data.current_quantity_v2_difference_plan import require
from data.current_quantity_v2_current_cash_plan import canonical


def _directory(value):
    path=Path(value)
    require(path.is_absolute(),'ABSOLUTE_MONTHLY_RELEASE_DIRECTORY_REQUIRED')
    return path.resolve()


def _month(session):
    require(date.fromisoformat(session).isoformat()==session,'INVALID_ROUTE_SESSION')
    return session[:7]


def _candidate(base_path,base_hash,candidate_path,candidate_hash):
    base_path=Path(base_path).resolve();candidate_path=Path(candidate_path)
    require(candidate_path.is_absolute(),'ABSOLUTE_MONTHLY_CANDIDATE_REQUIRED')
    base=json.loads(_read(base_path.parent,base_path.name,{base_path.name:base_hash}))
    candidate=json.loads(_read(candidate_path.parent,candidate_path.name,{candidate_path.name:candidate_hash}))
    allowed={'monthly','monthly_blob_root'}
    require(set(base)==set(candidate) and all(base[k]==candidate[k] for k in base if k not in allowed),
            'MONTHLY_ROUTE_CHANGED_BASE_CONFIGURATION')
    require(candidate.get('monthly') is not None and candidate.get('monthly_blob_root') is not None,
            'MONTHLY_ROUTE_REQUIRES_MONTHLY_CONFIGURATION')
    return candidate


def publish(*,directory,session,base_path,base_hash,candidate_path,candidate_hash):
    """Called only after binder's real monthly/source/account preflight."""
    folder=_directory(directory);month=_month(session)
    _candidate(base_path,base_hash,candidate_path,candidate_hash)
    record=dict(schema='LOCAL_MONTHLY_RUNTIME_RELEASE_V1',target_month=month,
                base_sha256=base_hash,config_path=str(Path(candidate_path).resolve()),config_sha256=candidate_hash)
    folder.mkdir(parents=True,exist_ok=True);target=folder/(month+'.json')
    # Hard-link publication is atomic and fails if the month already exists.
    # Readers cannot see a partially written release; failed temp files are removed.
    temporary=None
    try:
        with NamedTemporaryFile(dir=folder,prefix='.release-',delete=False) as stream:
            temporary=Path(stream.name);stream.write(canonical(record));stream.flush();os.fsync(stream.fileno())
        os.link(temporary,target)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return str(target)


def resolve(*,directory,session,base_path,base_hash):
    folder=_directory(directory);month=_month(session);path=folder/(month+'.json')
    require(not path.is_symlink(),'INVALID_MONTHLY_RELEASE_FILE')
    if not path.exists():
        # Base remains usable for its original month. The real preflight rejects
        # it when a new target month requires an unpublished configuration.
        return str(base_path),base_hash
    require(path.is_file() and path.stat().st_size<=16384,'INVALID_MONTHLY_RELEASE_FILE')
    raw=path.read_bytes();require(len(raw)<=16384,'INVALID_MONTHLY_RELEASE_FILE')
    release=json.loads(raw)
    require(type(release)is dict and set(release)=={'schema','target_month','base_sha256','config_path','config_sha256'}
            and release['schema']=='LOCAL_MONTHLY_RUNTIME_RELEASE_V1'
            and release['target_month']==month and release['base_sha256']==base_hash,
            'MONTHLY_RELEASE_BINDING_MISMATCH')
    _candidate(base_path,base_hash,release['config_path'],release['config_sha256'])
    return release['config_path'],release['config_sha256']
