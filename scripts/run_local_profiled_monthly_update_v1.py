"""Single-instance versioned profiled monthly launcher; never changes tasks."""
from datetime import datetime, timezone
from pathlib import Path
from hashlib import sha256
from uuid import uuid4
import argparse
import json
import os
from core.strategy_account_ledger import canonical, require
from scripts.prepare_real_monthly_release import _read, _safe
from scripts.run_rolling_profiled_monthly_update_v1 import run as scheduled_run, SOURCES as SCHEDULE_SOURCES
from data.strategy_bounded_source_gate_v1 import BoundedSourceGateV1

SOURCES = SCHEDULE_SOURCES | {'scripts/run_local_profiled_monthly_update_v1.py'}


def run(*, root, config_path, config_sha256, execute=False):
    root=Path(root).absolute();config=_read(root,config_path,config_sha256)
    require(set(config)=={'schema','schedule','log_directory','source_pins'} and
            config['schema']=='LOCAL_PROFILED_MONTHLY_LAUNCHER_V1','PROFILE_LAUNCHER_FIELDS')
    require(SOURCES<=set(config['source_pins']),'PROFILE_LAUNCHER_SOURCE_SCOPE')
    gate=BoundedSourceGateV1(root=root,source_pins=config['source_pins'],
        configuration_pins={config_path:config_sha256,config['schedule']['path']:config['schedule']['sha256']})
    gate();schedule=_read(root,config['schedule']['path'],config['schedule']['sha256'])
    require(all(config['source_pins'].get(p)==h for p,h in schedule['source_pins'].items()),'PROFILE_LAUNCHER_CHILD_PINS')
    arguments=dict(root=root,config_path=config['schedule']['path'],config_sha256=config['schedule']['sha256'])
    if not execute: return scheduled_run(**arguments)
    logs=_safe(root,config['log_directory']);destination=_safe(root,schedule['output_directory'])
    require(logs!=destination and logs not in destination.parents and destination not in logs.parents,
            'PROFILE_LAUNCHER_OUTPUT_OVERLAP')
    logs.mkdir(parents=True,exist_ok=True);lock=logs/'running.lock'
    try:
        with lock.open('xb') as stream:
            stream.write(canonical(dict(pid=os.getpid(),config_sha256=config_sha256)))
            stream.flush();os.fsync(stream.fileno())
    except FileExistsError:
        return dict(status='NEEDS_RECOVERY',reason='PROFILE_RUN_LOCK_PRESENT',automatic_retry=False)
    attempt=logs/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex)
    try:
        attempt.mkdir(exist_ok=False)
        def save(name,value):
            with (attempt/name).open('xb') as stream:
                stream.write(canonical(value));stream.flush();os.fsync(stream.fileno())
        save('started.json',dict(config_sha256=config_sha256,at=datetime.now(timezone.utc).isoformat()))
        try:
            gate();result=scheduled_run(**arguments,execute=True);gate()
        except Exception as error:
            result=dict(status='BLOCKED',reason=str(error) if isinstance(error,ValueError) else 'PROFILE_LAUNCHER_FAILED',automatic_retry=False)
        save('finished.json',dict(result=result,at=datetime.now(timezone.utc).isoformat()))
        return result
    finally:
        # The lock is owned by this run. Abrupt process loss leaves it for review.
        lock.unlink()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('root','config-path','config-sha256'):parser.add_argument('--'+key,required=True)
    parser.add_argument('--execute',action='store_true')
    try:result=run(**vars(parser.parse_args(argv)))
    except Exception as error:result=dict(status='BLOCKED',reason=str(error) if isinstance(error,ValueError) else 'PROFILE_LAUNCHER_FAILED')
    print(json.dumps(result,ensure_ascii=False));return 2 if result['status'] in {'BLOCKED','NEEDS_RECOVERY','MISSED_PREPARATION_WINDOW'} else 0


if __name__=='__main__':raise SystemExit(main())
