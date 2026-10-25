"""Create-only observation plans. A queued plan never authorizes capture."""
from hashlib import sha256
import json
import os
from pathlib import Path
from data.strategy_daily_advice_journal_v1 import encoded
from core.strategy_account_ledger import require

IDENTITY_FIELDS=('schema','account_id','target_id','account_revision','event_id','event_sha256',
                 'policy_id','policy_release_sha256','security_id','side','order_index','horizon_sessions')
PLAN_FIELDS=IDENTITY_FIELDS+('observation_id','final_return_sha256','ticker','reference_limit',
    'reference_quantity','reference_session','observation_session','observation_close')


def store_plans(directory, observations):
    """Persist resolved plans; future calendar gaps remain for the planner to retry.

    Current DUE/WAIT state is deliberately not persisted. Readers must compare
    the saved close to the real clock; no completion or approval is implied.
    """
    directory=Path(directory).absolute()
    require(not directory.is_symlink() and not any(p.is_symlink() for p in directory.parents),'QUEUE_SYMLINK')
    prepared=[]
    for row in observations:
        identity={key:row[key] for key in IDENTITY_FIELDS}
        digest=sha256(encoded(identity)).hexdigest()
        require(digest==row['observation_id'],'QUEUE_IDENTITY_CHANGED')
        require(row['capture_admitted'] is False,'QUEUE_DOES_NOT_ACCEPT_ADMISSION')
        if row['observation_session'] is None or row['observation_close'] is None:
            continue
        document={key:row[key] for key in PLAN_FIELDS}
        document.update(queue_schema='DAILY_FOLLOWUP_QUEUE_V1',capture_admitted=False,
                        actual_fill_inferred=False,performance_computed=False)
        prepared.append((digest,encoded(document)))
    require(len({key for key,_ in prepared})==len(prepared),'QUEUE_DUPLICATE_INPUT')
    # Validate every existing entry before adding any; a conflicting date cannot
    # silently redirect a previously scheduled observation.
    for key,body in prepared:
        path=directory/(key+'.json')
        require(not path.is_symlink(),'QUEUE_SYMLINK')
        if path.exists():
            require(path.stat().st_size<=65536 and path.read_bytes()==body,'QUEUE_PLAN_CONFLICT')
    directory.mkdir(parents=True,exist_ok=True)
    created=0;existing=0
    for key,body in prepared:
        path=directory/(key+'.json')
        try:
            with path.open('xb') as stream:
                stream.write(body);stream.flush();os.fsync(stream.fileno())
            created+=1
        except FileExistsError:
            require(not path.is_symlink() and path.stat().st_size<=65536 and path.read_bytes()==body,'QUEUE_PLAN_CONFLICT')
            existing+=1
    return dict(created=created,existing=existing,unresolved_calendar=len(observations)-len(prepared),
                capture_admitted=False,account_writes=False)
