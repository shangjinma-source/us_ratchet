"""Prepare saved close evidence for every held security, including closed orders.

No marks or unit-continuity conclusions are fabricated. Reused captures retain
their original receipt time; a failed create-only attempt is never refetched.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path, PurePosixPath
import json

from backtest.current_quantity_v2_simulated_settlement import _rebuild, _references
from backtest.current_quantity_v2_monthly_simulation import digest
from data.current_quantity_v2_completed_session_minutes import capture, decode, stamp, boundaries, LIMIT
from data.current_quantity_v2_difference_plan import require


def _read(root, name, pins=None):
    require(type(name) is str and '\\' not in name and ':' not in name
            and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,
            'INVALID_CLOSE_CAPTURE_PATH')
    path=root/name
    require(not path.is_symlink() and path.resolve().is_relative_to(root)
            and not any(p.is_symlink() for p in path.parents), 'INVALID_CLOSE_CAPTURE_PATH')
    with path.open('rb') as stream: raw=stream.read(LIMIT+1)
    require(len(raw)<=LIMIT, 'CLOSE_CAPTURE_TOO_LARGE')
    if pins is not None:
        require(name in pins and sha256(raw).hexdigest()==pins[name], 'CLOSE_CAPTURE_SOURCE_CHANGED')
    return raw


def _write(path, value):
    with path.open('xb') as stream:
        stream.write(value if type(value) is bytes else json.dumps(value,sort_keys=True).encode())


def _verified(root, paths, pins, identity, observed):
    require(set(paths)=={'raw','receipt','minutes'}, 'INVALID_CLOSE_CAPTURE_FILES')
    files={k:_read(root,v,pins) for k,v in paths.items()}
    receipt=json.loads(files['receipt']); saved=json.loads(files['minutes'])
    require(all(receipt.get(k)==identity[k] for k in ('security_id','ticker','session'))
            and all(stamp(receipt[k])==stamp(identity[k]) for k in ('session_open','session_close'))
            and sha256(files['raw']).hexdigest()==receipt.get('raw_sha256')
            and stamp(receipt['started_at'])<=stamp(receipt['captured_at'])<=observed,
            'CLOSE_CAPTURE_IDENTITY_OR_TIME_CHANGED')
    replay=decode(files['raw'],**identity,captured_at=receipt['captured_at'])
    replay['source_reference']='sha256:'+receipt['raw_sha256']
    require(replay==saved and receipt['status']==replay['status'], 'CLOSE_CAPTURE_REPLAY_CHANGED')
    return files,replay['status']


def prepare_close_captures(*, store, simulation_id, expected_revision, session,
                           root, schedule_path, schedule_sha256, directory, fetch, clock,
                           existing_captures=None, existing_source_hashes=None):
    current=store.read(simulation_id)
    require(current['revision']==expected_revision, 'STALE_SIMULATION_REVISION')
    simulation,_,last_at=_rebuild(current['simulation'])
    require('valuation' in simulation, 'VALUATION_REGISTRATION_REQUIRED')
    calendar=simulation['valuation']['registration']['calendar']
    require(session in calendar['session_dates'], 'SIMULATION_SESSION_NOT_REGISTERED')
    base=Path(root).resolve();raw=_read(base,schedule_path,{schedule_path:schedule_sha256})
    schedule=json.loads(raw)
    require(schedule['schema']=='SCHEDULED_REGULAR_SESSIONS_V1', 'SIMULATION_SCHEDULE_SCHEMA')
    rows=[row for row in schedule['sessions'] if row['date']==session]
    require(len(rows)==1, 'SIMULATION_SESSION_NOT_SCHEDULED')
    opening,closing=boundaries(session,rows[0]['open_at'],rows[0]['close_at'])
    require(closing==stamp(calendar['closes'][session]), 'REGISTERED_CLOSE_MISMATCH')
    ledger=simulation['chain']['ledger'];refs=_references(simulation['chain'])
    require(stamp(ledger['last_effective_at'])<=closing, 'STATE_ALREADY_AFTER_REQUESTED_CLOSE')
    held={sid for sid,q in ledger['shares'].items() if q};identities={}
    for sid in held:
        require(sid in refs, 'HELD_SECURITY_REFERENCE_REQUIRED')
        identities[sid]=dict(security_id=sid,ticker=refs[sid]['ticker'],session=session,
            session_open=opening.isoformat(),session_close=closing.isoformat())
    existing=deepcopy(existing_captures or {});pins=deepcopy(existing_source_hashes or {})
    require(set(existing)<=held, 'UNHELD_CAPTURE_REUSE')
    request=dict(kind='ISOLATED_HELD_CLOSE_CAPTURE_V1',simulation_id=simulation_id,expected_revision=expected_revision,
        session=session,root=str(base),schedule_path=schedule_path,schedule_sha256=schedule_sha256,
        identities=identities,reference_hashes={sid:digest(refs[sid]) for sid in held},
        existing_captures=existing,existing_source_hashes=pins)
    output=Path(directory).resolve();now=stamp(clock().isoformat())
    require(now>=max(last_at,closing), 'CLOSE_CAPTURE_TOO_EARLY')
    if output.exists():
        require(json.loads(_read(output,'request.json'))==request, 'CLOSE_CAPTURE_REQUEST_CONFLICT')
        require((output/'ready.json').is_file(), 'CLOSE_CAPTURE_INCOMPLETE_NO_RETRY')
        result=json.loads(_read(output,'ready.json'))
        require(result['request_sha256']==digest(request) and result['root']==str(output)
                and set(result['captures'])==held, 'CLOSE_CAPTURE_READY_CHANGED')
        observed=stamp(result['observed_at'])
        require(max(last_at,closing)<=observed<=now, 'CLOSE_CAPTURE_OBSERVATION_CHANGED')
        statuses={}
        for sid in held:
            _,statuses[sid]=_verified(output,result['captures'][sid],result['source_hashes'],identities[sid],observed)
        require(result['statuses']==statuses and result['unit_review_required'] is True
                and result['source_authenticated'] is False and result['official_close'] is False
                and result['initial_valuation_supported'] is False, 'CLOSE_CAPTURE_READY_CHANGED')
        return result
    output.mkdir(parents=True,exist_ok=False);_write(output/'request.json',request)
    last=[now]
    def actual_clock():
        value=stamp(clock().isoformat());require(value>=last[0], 'CLOCK_ROLLBACK');last[0]=value;return value
    captures={};source_hashes={};statuses={}
    for sid in sorted(held):
        child=digest(sid);target=output/child
        paths={key:child+'/'+name for key,name in [('raw','response.bin'),('receipt','receipt.json'),('minutes','minutes.json')]}
        if sid in existing:
            files,_=_verified(base,existing[sid],pins,identities[sid],actual_clock())
            target.mkdir(exist_ok=False)
            for key,name in paths.items():_write(output/name,files[key])
        else:
            capture(directory=target,**identities[sid],calendar_source_reference='sha256:'+schedule_sha256,
                    fetch=fetch,clock=actual_clock)
        for name in paths.values():source_hashes[name]=sha256(_read(output,name)).hexdigest()
        _,statuses[sid]=_verified(output,paths,source_hashes,identities[sid],actual_clock())
        captures[sid]=paths
    result=dict(root=str(output),captures=captures,source_hashes=source_hashes,statuses=statuses,
        request_sha256=digest(request),observed_at=actual_clock().isoformat(),
        unit_review_required=True,source_authenticated=False,official_close=False,
        initial_valuation_supported=False)
    _write(output/'ready.json',result)
    return result
