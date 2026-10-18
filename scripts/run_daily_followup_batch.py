"""Durable bounded follow-up scanning. Explicit execute; no scheduling or accounts."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from scripts.dispatch_followup_evidence import run as dispatch
from scripts.capture_followup_evidence import run as capture, reason
from data.current_quantity_v2_followup_provider import canonical, read_bytes, safe_path

STATE_ROOT = 'data/quantity_v2_followup/batch_runner'


def now():
    return datetime.now(timezone.utc)


def save(path, value):
    with path.open('xb') as stream:
        stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())


def run(*, root, max_pages=1, max_scan=100, max_dispatch=10, execute=False,
        clock=now, single_event=capture):
    if not (type(max_pages) is int and 1 <= max_pages <= 10
            and type(max_scan) is int and 1 <= max_scan <= 10000
            and type(max_dispatch) is int and 1 <= max_dispatch <= 100):
        raise ValueError('INVALID_RUN_LIMIT')
    root = Path(root).resolve(); directory = safe_path(root, STATE_ROOT)
    state_path = directory/'state.json'; active = directory/'active.json'; lock = directory/'run.lock'
    def state():
        if state_path.is_symlink(): raise ValueError('INVALID_RUNNER_STATE_PATH')
        value = json.loads(read_bytes(state_path, 4096)) if state_path.exists() else dict(schema='FOLLOWUP_BATCH_CURSOR_V1', cursor=None, cycles=0)
        if (value.get('schema') != 'FOLLOWUP_BATCH_CURSOR_V1' or type(value.get('cycles')) is not int
                or value['cycles'] < 0 or set(value) != {'schema','cursor','cycles'}):
            raise ValueError('INVALID_RUNNER_STATE')
        return value
    if any(p.exists() or p.is_symlink() for p in (active, lock, directory/'state.pending')):
        return dict(status='NEEDS_RECOVERY', reason='INCOMPLETE_BATCH_RUN', account_writes=False)
    before = state(); observed = clock()
    if observed.tzinfo is None: raise ValueError('AWARE_CLOCK_REQUIRED')
    if not execute:
        page = dispatch(root=root,max_scan=max_scan,max_dispatch=max_dispatch,after=before['cursor'],clock=clock,single_event=single_event)
        return dict(status='READ_ONLY',state=before,page=page,state_changed=False,account_writes=False)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with lock.open('xb') as stream:
            stream.write(b'EXCLUSIVE_FOLLOWUP_BATCH');stream.flush();os.fsync(stream.fileno())
    except FileExistsError:
        return dict(status='NEEDS_RECOVERY',reason='BATCH_LOCK_PRESENT',account_writes=False)
    try:
        if active.exists() or (directory/'state.pending').exists() or state()!=before:
            raise ValueError('RUNNER_STATE_CHANGED_OR_INCOMPLETE')
        identifier=uuid4().hex; receipt_directory=directory/'runs'/identifier
        receipt_directory.mkdir(parents=True)
        request=dict(run_id=identifier,started_at=observed.isoformat(),state_before=before,
                     max_pages=max_pages,max_scan=max_scan,max_dispatch=max_dispatch)
        save(receipt_directory/'started.json',request)
        save(active,dict(run_id=identifier))
        pages=[];cursor=before['cursor'];remaining=max_dispatch;cycle_complete=False
        try:
            for _ in range(max_pages):
                page=dispatch(root=root,max_scan=max_scan,max_dispatch=remaining,after=cursor,execute=True,clock=clock,single_event=single_event)
                pages.append(page);save(receipt_directory/('page-%02d.json'%len(pages)),page)
                remaining-=page['counts']['dispatched']+page['counts']['failed']
                cursor=page['next_scan_cursor']
                if not page['repeat_current_page'] and cursor is None:
                    cycle_complete=True;break
                if page['repeat_current_page'] or remaining<=0:break
            after=dict(schema=before['schema'],cursor=cursor,cycles=before['cycles']+int(cycle_complete))
            result=dict(status='CYCLE_COMPLETE' if cycle_complete else 'BOUNDED_RUN_COMPLETE',run_id=identifier,
                        state_before=before,state_after=after,pages=pages,finished_at=clock().isoformat(),
                        account_writes=False,automatic_orders=False,
                        failed_events=sum(p['counts']['failed'] for p in pages),
                        recovery_events=sum(p['counts']['prior_attempt_blocked'] for p in pages))
            save(receipt_directory/'complete.json',result)
            save(directory/'state.pending',after);os.replace(directory/'state.pending',state_path)
            active.unlink()
            return result
        except Exception as error:
            save(receipt_directory/'failed.json',dict(reason=reason(error),finished_at=clock().isoformat(),automatic_retry=False))
            raise
    finally:
        lock.unlink()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--max-pages',type=int,default=1)
    parser.add_argument('--max-scan',type=int,default=100)
    parser.add_argument('--max-dispatch',type=int,default=10)
    parser.add_argument('--execute',action='store_true')
    try: result=run(**vars(parser.parse_args(argv)))
    except Exception as error: result=dict(status='BLOCKED',reason=reason(error),account_writes=False)
    print(json.dumps(result));return 2 if result['status'] in ('BLOCKED','NEEDS_RECOVERY') or result.get('failed_events',0) else 0


if __name__=='__main__':raise SystemExit(main())
