"""One real-clock 10:00 New York dispatch; never changes a broker account."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from backtest.current_quantity_v2_close_capture_simulation import _read
from backtest.current_quantity_v2_simulation_store import SimulationStore
from data.current_quantity_v2_difference_plan import require, stamp
from scripts.bootstrap_current_quantity_v2_simulation import run as bootstrap_run, public_bootstrap_reason
from scripts.run_current_quantity_v2_simulation import run_runtime


def _now(): return datetime.now(timezone.utc)


def run(*, bootstrap_config, bootstrap_sha256, daily_config, daily_sha256, execute=False,monthly_runtime_directory=None):
    started=_now(); ny=started.astimezone(ZoneInfo('America/New_York'))
    if (ny.hour,ny.minute)!=(10,0):
        return dict(status='SKIPPED',reason='OUTSIDE_1000_NEW_YORK',observed_at=started.isoformat())
    def read(path,h):
        path=Path(path).resolve()
        return json.loads(_read(path.parent,path.name,{path.name:h}))
    if monthly_runtime_directory is not None:
        from scripts.monthly_runtime_routes import resolve
        daily_config,daily_sha256=resolve(directory=monthly_runtime_directory,session=ny.date().isoformat(),
                                         base_path=daily_config,base_hash=daily_sha256)
    initial=read(bootstrap_config,bootstrap_sha256);daily=read(daily_config,daily_sha256)
    require(all(initial[k]==daily[k] for k in ('root','database_path','simulation_id','pullback'))
        and initial['fees']==dict(path=daily['fees_path'],sha256=daily['fees_sha256'])
        and initial['schedule']==dict(path=daily['schedule_path'],sha256=daily['schedule_sha256']),
        'BOOTSTRAP_DAILY_CONFIG_MISMATCH')
    root=Path(initial['root']);schedule=json.loads(_read(root,initial['schedule']['path'],
        {initial['schedule']['path']:initial['schedule']['sha256']}))
    session=ny.date().isoformat()
    if session not in {row['date'] for row in schedule['sessions']}:
        return dict(status='SKIPPED',reason='NOT_REGISTERED_SESSION',session=session)
    store=SimulationStore(initial['database_path']);existing=None
    if store.path.exists():
        try:existing=store.read(initial['simulation_id'])
        except ValueError as error:
            if str(error)!='SIMULATION_NOT_FOUND':raise
    if existing is not None:
        accepted=stamp(existing['simulation']['origin']['ledger']['acceptance']['accepted_at'])
        if accepted.astimezone(ZoneInfo('America/New_York')).date().isoformat()==session:
            return dict(status='SKIPPED',reason='BOOTSTRAPPED_THIS_SESSION',session=session)
        return run_runtime(config_path=daily_config,config_sha256=daily_sha256,
            session=session,triggered_at=started.isoformat(),execute=execute,clock=_now)
    def bootstrap_clock():
        now=_now();local=now.astimezone(ZoneInfo('America/New_York'))
        require(local.date()==ny.date() and (local.hour,local.minute)==(10,0),
                'BOOTSTRAP_1000_WINDOW_ELAPSED')
        return now
    kwargs=dict(config_path=bootstrap_config,config_sha256=bootstrap_sha256,clock=bootstrap_clock)
    checked=bootstrap_run(**kwargs)
    if not execute:return checked
    bootstrap_clock()
    attempt=Path(initial['audit_directory']).parent/'scheduled-bootstrap-attempt.json'
    attempt.parent.mkdir(parents=True,exist_ok=True)
    try:
        with attempt.open('x',encoding='utf-8') as stream:
            json.dump(dict(status='STARTED_NO_AUTOMATIC_RETRY',started_at=started.isoformat(),
                bootstrap_sha256=bootstrap_sha256,daily_sha256=daily_sha256,simulation_id=initial['simulation_id']),stream)
    except FileExistsError:raise ValueError('BOOTSTRAP_ATTEMPT_REQUIRES_REVIEW') from None
    return bootstrap_run(**kwargs,execute=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('bootstrap-config','bootstrap-sha256','daily-config','daily-sha256'):
        parser.add_argument('--'+field,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--monthly-runtime-directory')
    try:
        result=run(**vars(parser.parse_args(argv)))
        daily=result.get('daily_status','')
        status=result.get('status')
        if daily:
            status={'CONTINUATION_COMPLETE':'COMPLETE','MONTHLY_COMPLETE':'COMPLETE',
                    'ALREADY_COMPLETED':'SKIPPED','LATE_NO_NEW_DECISION':'SKIPPED'}.get(daily,'BLOCKED')
        output={k:result[k] for k in ('status','reason','daily_status','session','simulation_id','accepted_at','revision') if k in result}
        output['status']=status
        output['finished_at']=_now().isoformat()
        print(json.dumps(output));return 2 if status=='BLOCKED' else 0
    except Exception as error:
        reason=public_bootstrap_reason(error)
        if not str(error).startswith('BOOTSTRAP_FRESH_PROPOSAL_UNAVAILABLE:'):
            reason=str(error) if type(error)is ValueError and str(error).replace('_','').isalnum() else reason
        print(json.dumps(dict(status='BLOCKED',reason=reason,finished_at=_now().isoformat())));return 2


if __name__=='__main__':raise SystemExit(main())
