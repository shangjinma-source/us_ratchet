"""Bounded current-advice follow-ups. No accounts, orders, or scheduler changes."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4
from core.strategy_account_ledger import require
from data.strategy_daily_advice_journal_v1 import encoded
from data.strategy_followup_queue_v1 import IDENTITY_FIELDS, PLAN_FIELDS
from data.strategy_followup_result_store_v1 import read_observation
from data.strategy_followup_capture_groups_v1 import group_due_observations
from scripts.queue_current_daily_followups_v3 import run as queue_run
from scripts.audit_current_daily_followup_sources_v4 import audit
from scripts.capture_daily_followup_groups_v1 import capture
from scripts.archive_saved_daily_followups_v4 import run as archive


def safe(path):
    require(not any(p.is_symlink() or (p.exists() and getattr(p.stat(),'st_file_attributes',0)&1024)
                    for p in (path,*path.parents)),'CURRENT_FOLLOWUP_LINK_REJECTED')


def save(path,value):
    safe(path)
    with path.open('xb') as stream:
        stream.write(encoded(value));stream.flush();os.fsync(stream.fileno())


def run(*,root,execute=False,max_observations=100):
    require(type(max_observations)is int and 1<=max_observations<=100,'CURRENT_FOLLOWUP_LIMIT')
    root=Path(root).absolute();base=root/'data/strategy_advice_followup';directory=base/'runner_v1'
    safe(directory);lock=directory/'run.lock';active=directory/'active.json'
    if lock.exists() or active.exists():return dict(status='NEEDS_RECOVERY',reason='INCOMPLETE_CURRENT_FOLLOWUP_RUN',account_writes=False)
    acquired=False;folder=None
    if execute:
        directory.mkdir(parents=True,exist_ok=True)
        try:
            with lock.open('xb') as stream:stream.write(b'CURRENT_FOLLOWUP_EXCLUSIVE')
            acquired=True
        except FileExistsError:return dict(status='NEEDS_RECOVERY',reason='CURRENT_FOLLOWUP_LOCK_PRESENT',account_writes=False)
    try:
        if execute:
            require(not active.exists(),'CURRENT_FOLLOWUP_ACTIVE_CHANGED')
            identifier=uuid4().hex;folder=directory/'runs'/identifier;folder.mkdir(parents=True)
            save(active,dict(run_id=identifier))
            save(folder/'started.json',dict(started_at=datetime.now(timezone.utc).isoformat(),max_observations=max_observations))
        queue=queue_run(root,execute=execute,include_plans=True)
        plans=queue.pop('plans')
        expected={row['observation_id']:row for row in plans if row['observation_close'] is not None}
        require(len(expected)==sum(row['observation_close'] is not None for row in plans),'CURRENT_FOLLOWUP_DUPLICATE_PLAN')
        now=datetime.now(timezone.utc);completed=0;waiting=0;pending=[]
        paths=sorted((base/'queue').glob('*.json'));require(len(paths)<=10000,'CURRENT_FOLLOWUP_QUEUE_BOUND')
        for path in paths:
            safe(path);require(path.stat().st_size<=65536,'CURRENT_FOLLOWUP_QUEUE_SIZE')
            row=json.loads(path.read_bytes());key=sha256(encoded({k:row[k] for k in IDENTITY_FIELDS})).hexdigest()
            require(key==row['observation_id']==path.stem,'CURRENT_FOLLOWUP_QUEUE_CHANGED')
            require(key in expected and all(row.get(k)==expected[key].get(k) for k in PLAN_FIELDS),
                    'CURRENT_FOLLOWUP_QUEUE_PLAN_CONFLICT')
            require(row['capture_admitted'] is False and row['actual_fill_inferred'] is False and
                    row['performance_computed'] is False,'CURRENT_FOLLOWUP_NOT_TRADES')
        if execute:require({path.stem for path in paths}==set(expected),'CURRENT_FOLLOWUP_QUEUE_INCOMPLETE')
        for row in expected.values():
            key=row['observation_id']
            close=datetime.fromisoformat(row['observation_close']);require(close.tzinfo is not None,'CURRENT_FOLLOWUP_CLOSE_TIME')
            if close>now:waiting+=1;continue
            index=base/'results/index'/(key+'.json');safe(index)
            if index.exists():read_observation(base/'results',key);completed+=1;continue
            pending.append(row)
        pending.sort(key=lambda r:(r['observation_close'],r['observation_id']))
        blocked=[];selected=[]
        if pending:
            reviewed=audit(root);valid={r['event_id'] for r in reviewed['rows'] if r['status']=='ARCHIVE_INTEGRITY_AND_TARGET_RECOMPUTED'}
            if execute:save(folder/'source-review.json',reviewed)
            for row in pending:
                if row['event_id'] in valid:selected.append(row)
                else:blocked.append(row['observation_id'])
        selected=selected[:max_observations]
        result=dict(status='SOURCE_REVIEW_BLOCKED' if blocked else 'WAIT_OBSERVATION_CLOSE' if not selected else 'DUE_READ_ONLY',
            queue=queue,completed_verified=completed,waiting=waiting,pending=len(pending),
            selected=len(selected),blocked=blocked,deferred=len(pending)-len(blocked)-len(selected),
            account_writes=False,performance_computed=False,network_calls=0)
        if execute and selected:
            plan=group_due_observations(selected,now=now);raw=encoded(plan)
            save(folder/'plan.json',plan)
            captured=capture(plan_bytes=raw,plan_sha256=sha256(raw).hexdigest(),output=folder/'capture')
            published=archive(root,capture_path=folder/'capture')
            require(published['observations']==len(selected) and published['readback_verified'] is True,
                    'CURRENT_FOLLOWUP_PUBLICATION_INCOMPLETE')
            for row in selected:read_observation(base/'results',row['observation_id'])
            result.update(status='PUBLISHED_WITH_BLOCKED' if blocked else 'PUBLISHED',publication=published,
                          network_calls=captured['network_calls'])
        if execute:
            save(folder/'complete.json',result)
            active.unlink()
        return result
    except Exception as error:
        if folder is not None:save(folder/'failed.json',dict(reason=str(error),error_type=type(error).__name__,automatic_retry=False))
        raise
    finally:
        if acquired:lock.unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True);parser.add_argument('--execute',action='store_true')
    parser.add_argument('--max-observations',type=int,default=100)
    try:
        result=run(**vars(parser.parse_args()))
    except Exception as error:result=dict(status='NEEDS_RECOVERY',reason=str(error),account_writes=False)
    print(json.dumps(result,ensure_ascii=False))
    return 2 if result['status'] in {'NEEDS_RECOVERY','SOURCE_REVIEW_BLOCKED','PUBLISHED_WITH_BLOCKED'} else 0

if __name__=='__main__':raise SystemExit(main())
