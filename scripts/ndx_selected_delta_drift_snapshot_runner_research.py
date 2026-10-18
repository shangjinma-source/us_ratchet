"""Explicit prepare and max0/max1 selected-input research runs with exact gaps."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_selected_delta_drift_snapshot_research as core
from scripts.ndx_base_three_cell_window_delta_research import publish
SOURCE=Path(__file__).resolve();LOADED=core.drift.file_sha(SOURCE)
FOLDER=ROOT/'data/cache/research/selected_delta_drift_snapshot_20260919_v1'
PROBE=ROOT/'data/cache/research/delta_selected_input_20260912_v1/first_probe.json'
PROBE_SHA='241ac517d78668761f32a25da68856cf396d28a1ef5591d9da993a0e2307607a'
AUDIT=PROBE.parent/'legacy_close_decimal_oracle_20260919.json'
AUDIT_SHA='e151de0ad7cfefce56cce6db54da91f31c3e3880eb1f8f7f04a2b832815eb25e'


def prepare_manifest():
    parent=core.read(core.drift.SELECTED_PLAN,core.drift.SELECTED_PLAN_SHA)
    audit=core.read(AUDIT,AUDIT_SHA);probe=core.read(PROBE,PROBE_SHA)
    if (audit['schema']!='ndx_selected_legacy_close_decimal_oracle_20260919_v1' or
        audit['same_close_legacy_accounting_validated'] is not True or audit['optimizer_or_original_simulator_called'] is not False
        or audit['verified_source_hashes'].get(str(PROBE))!=PROBE_SHA or probe['selected']!=parent['probe']):
        raise ValueError('Independent externally bound first-probe accounting audit required')
    expected=dict(parent['source_hashes']);core.merge(expected,probe['result']['source_hashes']);core.merge(expected,core.sources())
    core.merge(expected,{str(SOURCE):LOADED,str(PROBE):PROBE_SHA,str(AUDIT):AUDIT_SHA,
        str(core.drift.SELECTED_PLAN):core.drift.SELECTED_PLAN_SHA,str(Path(publish.__code__.co_filename).resolve()):core.drift.file_sha(publish.__code__.co_filename)})
    contract=core.drift.load_contract();checked=core.drift.verify_expected_sources(expected,contract)
    rows=[r for day in parent['dates'] for r in day['tasks']]
    if len(rows)!=11254 or len({r['context_path'] for r in rows})!=161:raise ValueError('Exact original full denominator required')
    for r in rows:
        if r['runtime']!=core.selected.current_runtime():raise ValueError('Actual numerical runtime differs')
    return dict(schema='ndx_selected_delta_exact_gap_manifest_v1',parent_plan_path=str(core.drift.SELECTED_PLAN),parent_plan_sha256=core.drift.SELECTED_PLAN_SHA,
        tasks=rows,planned=11254,context_count=161,corrections=parent['errors'],historical_expected_source_hashes=expected,
        verified_source_hashes=checked['verified_source_hashes'],historical_price_cache_gap_observations=checked['historical_gap_observations'],
        completed_probe=dict(path=str(PROBE),sha256=PROBE_SHA,new_job_id=parent['probe']['task']['new_job_id']),
        independent_probe_audit=dict(path=str(AUDIT),sha256=AUDIT_SHA),historical_full_source_closure_verified=False,
        original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False,preparation_only=True)


def load_manifest(path,sha):
    manifest=core.read(path,sha)
    if manifest!=prepare_manifest():raise ValueError('Manifest differs from exact hard-plan reconstruction')
    return manifest


def run(*,manifest_path,manifest_sha256,output,max_new_tasks,resume_index=None,resume_index_sha256=None):
    if type(max_new_tasks) is not int or max_new_tasks not in (0,1):raise ValueError('Explicit max0/max1 only; bulk not authorized by this runner')
    manifest_path=str(Path(manifest_path).resolve());manifest=load_manifest(manifest_path,manifest_sha256)
    snapshot=core.begin(manifest_path=manifest_path,manifest_sha256=manifest_sha256)
    folder=Path(output);reference=dict(path=manifest_path,sha256=manifest_sha256);completed={};timings=[]
    def index(status,finalization=None):
        return dict(schema='ndx_selected_delta_exact_gap_completion_index_v1',manifest=reference,planned=manifest['planned'],status=status,
            completed=[completed[r['new_job_id']] for r in manifest['tasks'] if r['new_job_id'] in completed],finalization=finalization,
            historical_full_source_closure_verified=False,original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False)
    def save_index(value):return publish(folder/('index_'+core.selected.encoding._sha(value)+'.json'),value)
    if bool(resume_index)!=bool(resume_index_sha256):raise ValueError('External resume index and SHA required together')
    if resume_index:
        previous=core.read(resume_index,resume_index_sha256)
        if previous['schema']!='ndx_selected_delta_exact_gap_completion_index_v1' or previous['manifest']!=reference or previous['planned']!=manifest['planned']:
            raise ValueError('External resume index belongs to another manifest')
        for flag in ('historical_full_source_closure_verified','original_historical_provenance_verified','point_in_time_verified','promotion_allowed'):
            if previous[flag] is not False:raise ValueError('Resume upgraded unsupported flag')
        for entry in previous['completed']:
            restored=core.restore(snapshot,entry['path'],entry['sha256']);completed[restored['new_job_id']]=entry
    # Reconcile the entire dedicated task directory before any import or fit,
    # including later queue items outside this run's max0/max1 budget.
    indexed_paths=set()
    for identifier,entry in completed.items():
        expected_path=(folder/(identifier+'.json')).resolve()
        if Path(entry['path']).resolve()!=expected_path:raise ValueError('Indexed task outside dedicated output coordinate')
        indexed_paths.add(expected_path)
    disk_paths={p.resolve() for p in folder.glob('*.json') if not p.name.startswith('index_')}
    if disk_paths!=indexed_paths:raise ValueError('Unindexed task anywhere in output directory; reconcile external index before any fit')
    known=manifest['completed_probe']
    if known['new_job_id'] not in completed:
        path=folder/(known['new_job_id']+'.json')
        if path.exists():raise ValueError('Unindexed imported probe exists; external index required')
        value=core.import_probe(snapshot,known['path'],known['sha256']);completed[value['new_job_id']]=publish(path,value)
        save_index(index('PARTIAL'))
    for row in manifest['tasks']:
        identifier=row['new_job_id']
        if identifier in completed:continue
        if len(timings)>=max_new_tasks:break
        path=folder/(identifier+'.json')
        if path.exists():raise ValueError('Unindexed task exists; do not repeat fitting')
        started=perf_counter();value=core.evaluate(snapshot,identifier);elapsed=perf_counter()-started
        completed[identifier]=publish(path,value);timings.append(dict(new_job_id=identifier,elapsed_seconds=elapsed))
        print(json.dumps(dict(completed=len(completed),planned=manifest['planned'],timing=timings[-1],index=save_index(index('PARTIAL')))),flush=True)
    for entry in completed.values():core.read(entry['path'],entry['sha256'])
    final=core.finish(snapshot);saved=save_index(index(final['status'],final));core.verify_finished(snapshot)
    for entry in completed.values():core.read(entry['path'],entry['sha256'])
    return dict(**saved,completed=len(completed),new_evaluations=len(timings),status=final['status'],timings=timings)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare',action='store_true');parser.add_argument('--manifest-path');parser.add_argument('--manifest-sha256')
    parser.add_argument('--output');parser.add_argument('--max-new-tasks',type=int);parser.add_argument('--resume-index');parser.add_argument('--resume-index-sha256');args=parser.parse_args()
    if args.prepare:
        if args.max_new_tasks is not None:raise ValueError('Preparation cannot evaluate tasks')
        path=Path(args.output) if args.output else FOLDER/'manifest.json'
        if path.exists():raise FileExistsError('Manifest already exists')
        value=prepare_manifest();saved=publish(path,value);core.drift.verify_expected_sources(value['historical_expected_source_hashes'],core.drift.load_contract());print(json.dumps(saved))
    else:
        if not args.manifest_path or not args.manifest_sha256 or args.max_new_tasks is None:raise ValueError('Explicit external manifest and max0/max1 required')
        print(json.dumps(run(manifest_path=args.manifest_path,manifest_sha256=args.manifest_sha256,output=args.output or FOLDER/'tasks',
            max_new_tasks=args.max_new_tasks,resume_index=args.resume_index,resume_index_sha256=args.resume_index_sha256)))
