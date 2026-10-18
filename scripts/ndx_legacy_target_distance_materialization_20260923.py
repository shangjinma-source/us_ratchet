"""Explicit LEGACY_TARGET_DISTANCE generation/fit/recovery step, never trades."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_legacy_target_distance_materialization_research as core

SOURCE=Path(__file__).resolve()
LOADED_SOURCES={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest(),str(core.SOURCE):core.LOADED_SHA}


def create_plan():
    core.verify(LOADED_SOURCES)
    core.require(not core.OUTPUT.exists(),'Fresh fixed LEGACY_TARGET_DISTANCE namespace required')
    saved=core.publish(core.OUTPUT/'plan.json',core.expected_plan())
    core.verify(LOADED_SOURCES);core.read(saved,{})
    return saved


def run(*,plan_path,plan_sha256,output,execution_date,execute=False,recover_raw=False,
        completed_finalization_path=None,completed_finalization_sha256=None,recovery_raw_sha256=None,recovery_started_sha256=None):
    paths=completed_finalization_path or [];hashes=completed_finalization_sha256 or []
    if len(paths)!=len(hashes):raise ValueError('Matching explicit prior finalization paths and SHAs required')
    core.verify(LOADED_SOURCES)
    result=core.run_step(plan_reference=dict(path=str(Path(plan_path).resolve()),sha256=plan_sha256),
        output=output,execution_date=execution_date,execute=execute,recover_raw=recover_raw,
        completed_finalizations=[dict(path=str(Path(path).resolve()),sha256=sha) for path,sha in zip(paths,hashes)],
        runner_sources=LOADED_SOURCES,
        recovery_raw_reference=dict(path=str(Path(output).resolve()/execution_date/'raw.json'),sha256=recovery_raw_sha256) if recovery_raw_sha256 else None,
        recovery_started_reference=dict(path=str(Path(output).resolve()/execution_date/'started.json'),sha256=recovery_started_sha256) if recovery_started_sha256 else None)
    core.verify(LOADED_SOURCES)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--create-plan',action='store_true')
    parser.add_argument('--plan-path',default=str(core.OUTPUT/'plan.json'))
    parser.add_argument('--plan-sha256')
    parser.add_argument('--output',default=str(core.OUTPUT))
    parser.add_argument('--execution-date',choices=core.DATES)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--recover-raw',action='store_true')
    parser.add_argument('--completed-finalization-path',action='append')
    parser.add_argument('--completed-finalization-sha256',action='append')
    parser.add_argument('--recovery-raw-sha256')
    parser.add_argument('--recovery-started-sha256')
    args=vars(parser.parse_args());creating=args.pop('create_plan')
    if creating:
        core.require(not any(args[k] for k in ('execute','recover_raw','plan_sha256','execution_date','completed_finalization_path',
            'completed_finalization_sha256','recovery_raw_sha256','recovery_started_sha256')) and
            Path(args['output']).resolve()==core.OUTPUT and Path(args['plan_path']).resolve()==core.OUTPUT/'plan.json',
            'Plan creation accepts no execution/recovery arguments')
        result=create_plan()
    else:
        core.require(bool(args['plan_sha256']) and bool(args['execution_date']),'External plan SHA and execution date required')
        result=run(**args)
    print(json.dumps(result))
