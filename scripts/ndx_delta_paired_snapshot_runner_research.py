"""Prepare and explicitly budget the isolated 614-task DELTA paired snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_delta_paired_snapshot_research as core
from scripts import ndx_delta_three_cell_paired_v2_probe_research as previous
SELF=Path(__file__).resolve();LOADED=hashlib.sha256(SELF.read_bytes()).hexdigest()
PLAN=previous.OUTPUT/'plan.json';PLAN_SHA='fb2e514516123efe67dffb92821410ce2eb52d3e757494c4dfaf517c7ea9b330'
PROBE=previous.OUTPUT/'first_probe.json';PROBE_SHA='1e39d8149e6d2d82853958bae413e75b608a02461a7b587da49f2a917a3cd519'
AUDIT=previous.OUTPUT/'first_probe_independent_audit_20260912.json';AUDIT_SHA='d5fff21e8fbe0663998a22de7058c54f307f2e6b282ffa3a2dd34b218010359d'
OUTPUT=ROOT/'data/cache/research/delta_paired_snapshot_20260912_v1'
publish=previous.prior.original.publish


def prepare_manifest():
    plan=previous.load_plan(PLAN,PLAN_SHA)
    audit=previous.prior.original.read(AUDIT,AUDIT_SHA)
    if (audit['schema']!='ndx_delta_gap_probe_independent_audit_v1' or audit['source_hashes'].get(str(PROBE))!=PROBE_SHA or
        audit['original_full_result_exact_to_checkpoint'] is not True or audit['only_paired_four_fields_may_change'] is not True or
        audit['no_fitter_or_evaluator_called'] is not True or audit['promotion_allowed'] is not False):
        raise ValueError('External independent first-probe audit required')
    sources=previous.prior.original.merge(plan['source_hashes'],audit['source_hashes'],core.source_hashes(),
        {str(SELF):LOADED,str(PLAN):PLAN_SHA,str(PROBE):PROBE_SHA,str(AUDIT):AUDIT_SHA})
    core.sealed.equivalence.previous._verify(sources)
    rows=[row for day in plan['dates'] for row in day['tasks']]
    if len(rows)!=614 or len({row['context_path'] for row in rows})!=67:raise ValueError('Exact 614 / 67 denominator required')
    for row in rows:core.validate_runtime(row['runtime'])
    return dict(schema='ndx_delta_paired_snapshot_manifest_v1',parent_plan_path=str(PLAN),parent_plan_sha256=PLAN_SHA,
        tasks=rows,planned=614,context_count=67,corrections=plan['errors'],source_hashes=sources,
        completed_probe=dict(path=str(PROBE),sha256=PROBE_SHA,new_job_id=plan['probe']['task']['new_job_id']),
        independent_probe_audit=dict(path=str(AUDIT),sha256=AUDIT_SHA),
        preparation_only=True,historical_training_performed=False,original_historical_provenance_verified=False,
        point_in_time_verified=False,promotion_allowed=False)


def load_manifest(path,sha):
    manifest=previous.prior.original.read(path,sha)
    if (manifest['schema']!='ndx_delta_paired_snapshot_manifest_v1' or manifest['parent_plan_path']!=str(PLAN) or
        manifest['parent_plan_sha256']!=PLAN_SHA or manifest['planned']!=614 or manifest['context_count']!=67 or
        manifest['completed_probe']['path']!=str(PROBE) or manifest['completed_probe']['sha256']!=PROBE_SHA or
        manifest['independent_probe_audit']!=dict(path=str(AUDIT),sha256=AUDIT_SHA) or
        manifest['source_hashes'].get(str(SELF))!=LOADED or manifest['promotion_allowed'] is not False or
        manifest['point_in_time_verified'] is not False or manifest['original_historical_provenance_verified'] is not False):
        raise ValueError('Exact source-bound isolated DELTA manifest required')
    return manifest


def run(*,manifest_path,manifest_sha256,output,max_new_tasks,resume_index=None,resume_index_sha256=None):
    if type(max_new_tasks) is not int or max_new_tasks<0:raise ValueError('Explicit nonnegative new trace budget required')
    manifest_path=str(Path(manifest_path).resolve());manifest=load_manifest(manifest_path,manifest_sha256)
    snapshot=core.begin_snapshot(manifest_path=manifest_path,manifest_sha256=manifest_sha256)
    folder=Path(output);reference=dict(path=manifest_path,sha256=manifest_sha256);completed={};timings=[]
    def index(status,finalization=None):
        return dict(schema='ndx_delta_paired_snapshot_completion_index_v1',manifest=reference,
            completed=[completed[row['new_job_id']] for row in manifest['tasks'] if row['new_job_id'] in completed],
            planned=manifest['planned'],status=status,finalization=finalization,
            original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False)
    def progress():
        value=index('PARTIAL');return publish(folder/('index_'+core.sealed.encoding._sha(value)+'.json'),value)
    if resume_index is not None:
        if resume_index_sha256 is None:raise ValueError('External completion index SHA required')
        prior=previous.prior.original.read(resume_index,resume_index_sha256)
        if (prior['schema']!='ndx_delta_paired_snapshot_completion_index_v1' or prior['manifest']!=reference or
            prior['planned']!=manifest['planned'] or prior['status'] not in ('PARTIAL','COMPLETE') or prior['promotion_allowed'] is not False):
            raise ValueError('Resume manifest/completion state differs')
        for entry in prior['completed']:
            value=core.restore_task(snapshot,checkpoint_path=entry['path'],checkpoint_sha256=entry['sha256']);completed[value['new_job_id']]=entry
        if prior['status']=='COMPLETE' and len(completed)!=manifest['planned']:raise ValueError('Incomplete complete-index denominator')
    known=manifest['completed_probe']
    if known['new_job_id'] not in completed:
        destination=folder/(known['new_job_id']+'.json')
        if destination.exists():raise ValueError('Unindexed imported task exists; external index required')
        value=core.import_probe(snapshot,probe_path=known['path'],probe_sha256=known['sha256'])
        if value['new_job_id']!=known['new_job_id']:raise ValueError('External first probe identifier differs')
        completed[value['new_job_id']]=publish(destination,value);progress()
    for row in manifest['tasks']:
        identifier=row['new_job_id']
        if identifier in completed:continue
        if len(timings)>=max_new_tasks:break
        destination=folder/(identifier+'.json')
        if destination.exists():raise ValueError('Unindexed task exists; do not repeat original trace')
        started=perf_counter();value=core.evaluate_task(snapshot,identifier);elapsed=perf_counter()-started
        completed[identifier]=publish(destination,value);timings.append(dict(new_job_id=identifier,elapsed_seconds=elapsed))
        external=progress();print(json.dumps(dict(completed=len(completed),planned=manifest['planned'],last_trace=timings[-1],external_index=external)),flush=True)
    for entry in completed.values():core._bytes(entry['path'],entry['sha256'])
    finalization=core.finish_snapshot(snapshot);value=index(finalization['status'],finalization)
    saved=publish(folder/('index_'+core.sealed.encoding._sha(value)+'.json'),value)
    core.verify_finalization(snapshot)
    for entry in completed.values():core._bytes(entry['path'],entry['sha256'])
    return dict(**saved,status=value['status'],completed=len(completed),new_traces=len(timings),timings=timings)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--manifest-path');parser.add_argument('--manifest-sha256');parser.add_argument('--output')
    parser.add_argument('--max-new-tasks',type=int);parser.add_argument('--resume-index');parser.add_argument('--resume-index-sha256')
    options=parser.parse_args()
    if options.prepare:
        if options.max_new_tasks is not None:raise ValueError('Preparation cannot evaluate tasks')
        path=Path(options.output) if options.output else OUTPUT/'manifest.json'
        if path.exists():raise FileExistsError('Existing manifest must be externally verified')
        value=prepare_manifest();saved=publish(path,value);core.sealed.equivalence.previous._verify(value['source_hashes']);print(json.dumps(saved))
    else:
        if not options.manifest_path or not options.manifest_sha256 or options.max_new_tasks is None:raise ValueError('External manifest and explicit budget required')
        print(json.dumps(run(manifest_path=options.manifest_path,manifest_sha256=options.manifest_sha256,output=options.output or OUTPUT/'tasks',
            max_new_tasks=options.max_new_tasks,resume_index=options.resume_index,resume_index_sha256=options.resume_index_sha256)))
