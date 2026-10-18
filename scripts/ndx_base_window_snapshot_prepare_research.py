"""Prepare an immutable shared date manifest; never evaluate or refit a task."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_base_three_cell_window_delta_research as previous
from backtest import ndx_base_window_snapshot_research as snapshot
from scripts import ndx_base_window_snapshot_runner_research as runner

SELF=Path(__file__).resolve();LOADED=hashlib.sha256(SELF.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/base_window_snapshot_20260912_v1'


def prepare(*,plan_path,plan_sha256,date):
    plan=previous.load_plan(plan_path,plan_sha256)
    day,=[row for row in plan['dates'] if row['date']==date]
    sources=previous.merge(day['source_hashes'],snapshot._sources(),
        {str(Path(plan_path).resolve()):plan_sha256,str(SELF):LOADED,str(runner.SELF):runner.LOADED})
    previous.original._verify_sources(sources)
    return dict(schema='ndx_base_window_snapshot_manifest_v1',source_hashes=sources,
        parent_plan_path=str(Path(plan_path).resolve()),parent_plan_sha256=plan_sha256,date=date,
        context=dict(path=day['context_path'],sha256=day['context_sha256']),
        typed_context=dict(path=day['typed_context_path'],sha256=day['typed_context_sha256']),
        corrections=plan['errors'],tasks=day['tasks'],planned_k_ge_2=day['planned_k_ge_2'],planned_k1=day['planned_k1'],
        global_planned_k_ge_2=15488,global_planned_k1=90,
        preparation_only=True,numerical_evaluation_performed=False,promotion_allowed=False)


def save_new(path,manifest):
    path=Path(path);raw=(json.dumps(manifest,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    if path.exists():raise FileExistsError('Existing snapshot manifest must be verified, not replaced')
    path.parent.mkdir(parents=True,exist_ok=True);fd,temp=tempfile.mkstemp(prefix='.publishing-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.link(temp,path)
    finally:Path(temp).unlink(missing_ok=True)
    previous.original._verify_sources(manifest['source_hashes'])
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),tasks=len(manifest['tasks']))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan-path',required=True)
    parser.add_argument('--plan-sha256',required=True);parser.add_argument('--selection-date',required=True)
    options=parser.parse_args()
    manifest=prepare(plan_path=options.plan_path,plan_sha256=options.plan_sha256,date=options.selection_date)
    print(json.dumps(save_new(OUTPUT/('manifest_'+options.selection_date.replace('-','')+'.json'),manifest)))
