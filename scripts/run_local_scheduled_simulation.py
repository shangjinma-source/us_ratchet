"""Fixed local launcher. Default is read-only; --execute retains original clock gates."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT=Path('E:/Git/us_ratchet')
PYTHON=Path('D:/python/python.exe')
BOOTSTRAP='research_contracts/isolated_trial_20261016/bootstrap-v10.json'
DAILY='research_contracts/isolated_trial_20261016/daily.json'
PINS={BOOTSTRAP:'3dc94f6f6d02f3a6d8e93897aabc9f572bfe459196d5cd127e5f50b2d766d4e7',
      DAILY:'1939ff1614f87d6732a4d4e731244d759a4e067159ad4a940628ece2deea0c3f',
      'scripts/run_scheduled_quantity_v2_simulation.py':'2627153ece64c724d6af5288343dee275369e77a34311038ac540faa5bb4b079'}
MONTHLY='research_contracts/isolated_trial_20261016/monthly-releases'
LOGS='data/local_scheduler/quantity_v2_daily'


def now():return datetime.now(timezone.utc).isoformat()


def checked_command():
    for path,expected in PINS.items():
        source=ROOT/path
        if source.is_symlink() or sha256(source.read_bytes()).hexdigest()!=expected:
            raise ValueError('PINNED_INPUT_CHANGED')
    return [str(PYTHON),'-X','utf8','-E','-B','-m','scripts.run_scheduled_quantity_v2_simulation',
        '--bootstrap-config',str(ROOT/BOOTSTRAP),'--bootstrap-sha256',PINS[BOOTSTRAP],
        '--daily-config',str(ROOT/DAILY),'--daily-sha256',PINS[DAILY],
        '--monthly-runtime-directory',str(ROOT/MONTHLY),'--execute']


def save(path,value):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())


def run(*,execute=False):
    if not execute:
        checked_command()
        return dict(status='PREFLIGHT_ONLY',execute=False,source_hashes=PINS,working_directory=str(ROOT))
    directory=ROOT/LOGS;directory.mkdir(parents=True,exist_ok=True)
    run_directory=directory/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex)
    run_directory.mkdir()
    save(run_directory/'started.json',dict(status='STARTED',started_at=now(),scheduled_module='scripts.run_scheduled_quantity_v2_simulation',
        source_hashes=PINS,launcher_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
    lock=directory/'running.lock';owned=False
    try:
        try:
            with lock.open('x',encoding='utf-8') as stream:stream.write(str(os.getpid()))
            owned=True
        except FileExistsError:
            result=dict(status='SKIPPED',reason='RUN_LOCK_PRESENT_REVIEW_IF_STALE')
        else:
            command=checked_command()
            # Raw output is retained even if the child is terminated or returns invalid JSON.
            with (run_directory/'stdout.txt').open('xb') as stdout,(run_directory/'stderr.txt').open('xb') as stderr:
                completed=subprocess.run(command,cwd=ROOT,stdout=stdout,stderr=stderr,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=False)
            raw=(run_directory/'stdout.txt').read_bytes()
            if len(raw)>1024*1024:raise ValueError('CHILD_OUTPUT_TOO_LARGE')
            try:child=json.loads(raw.decode('utf-8').strip().splitlines()[-1])
            except (ValueError,IndexError,UnicodeError):raise ValueError('CHILD_RESULT_INVALID') from None
            if not isinstance(child,dict) or child.get('status') not in {'SKIPPED','COMPLETE','BLOCKED','CREATED_ISOLATED_SIMULATION'}:
                raise ValueError('CHILD_STATUS_UNRECOGNIZED')
            result=dict(status=child['status'],child_result=child,exit_code=completed.returncode)
            if completed.returncode:result['status']='BLOCKED'
    except Exception as error:
        result=dict(status='BLOCKED',reason=str(error) if isinstance(error,ValueError) and str(error).replace('_','').isalnum() else 'LOCAL_RUN_FAILED')
    finally:
        if owned:lock.unlink()
    result['finished_at']=now();save(run_directory/'finished.json',result)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true')
    try:result=run(**vars(parser.parse_args(argv)))
    except Exception:result=dict(status='BLOCKED',reason='LOCAL_PREFLIGHT_FAILED',finished_at=now())
    print(json.dumps(result,ensure_ascii=False));return 2 if result['status']=='BLOCKED' else 0


if __name__=='__main__':raise SystemExit(main())
