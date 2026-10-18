"""Bounded selected-input continuation after the independently audited max0/max1 run."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_selected_delta_drift_snapshot_runner_research as seed
core=seed.core
publish=seed.publish
FOLDER=seed.FOLDER
SOURCE=Path(__file__).resolve()
LOADED=core.drift.file_sha(SOURCE)
MANIFEST=FOLDER/'manifest.json'
MANIFEST_SHA='beb22a53d179a725e359272273b14c8fc6ed6fe669e0fac574c0a4ff5f45fb9e'
AUDIT=FOLDER/'first_two_independent_audit_20260919.json'
AUDIT_SHA='e722bf066d64a9de6dff174af54876459265767d32456eb78ee17e725cbc30c1'
RUN_SOURCES={str(SOURCE):LOADED,str(seed.SOURCE):seed.LOADED,str(AUDIT):AUDIT_SHA}


def load_verified_manifest(path,sha):
    if Path(path).resolve()!=MANIFEST or sha!=MANIFEST_SHA:raise ValueError('Hard actually tested manifest required')
    audit=core.read(AUDIT,AUDIT_SHA)
    if (audit['schema']!='ndx_selected_snapshot_first_two_independent_audit_20260919_v1' or len(audit['tasks'])!=2
        or any(audit[k] is not False for k in ('optimizer_or_original_simulator_called','historical_full_source_closure_verified','point_in_time_verified','promotion_allowed'))):
        raise ValueError('Hard limited two-task independent audit required')
    verified=core.drift.verify_expected_sources(audit['historical_expected_source_hashes'],core.drift.load_contract())
    if verified['verified_source_hashes']!=audit['verified_source_hashes'] or verified['historical_gap_observations']!=audit['historical_price_cache_gap_observations']:
        raise ValueError('Seed audit source partition differs')
    return seed.load_manifest(path,sha)


def run(*,manifest_path,manifest_sha256,output,max_new_tasks,resume_index=None,resume_index_sha256=None):
    if type(max_new_tasks) is not int or not 0<=max_new_tasks<=1000:raise ValueError('Explicit integer budget 0..1000 required')
    manifest_path=str(Path(manifest_path).resolve());manifest=load_verified_manifest(manifest_path,manifest_sha256)
    snapshot=core.begin(manifest_path=manifest_path,manifest_sha256=manifest_sha256)
    for path,sha in RUN_SOURCES.items():core.track(core.state(snapshot),path,sha)
    folder=Path(output);reference=dict(path=manifest_path,sha256=manifest_sha256);completed={};timings=[]
    def index(status,finalization=None):
        return dict(schema='ndx_selected_delta_exact_gap_completion_index_v1',manifest=reference,planned=manifest['planned'],status=status,
            completed=[completed[r['new_job_id']] for r in manifest['tasks'] if r['new_job_id'] in completed],finalization=finalization,
            historical_full_source_closure_verified=False,original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False)
    def save_index(value):return publish(folder/('index_'+core.selected.encoding._sha(value)+'.json'),value)
    if bool(resume_index)!=bool(resume_index_sha256):raise ValueError('External resume index and SHA required together')
    if resume_index:
        previous=core.read(resume_index,resume_index_sha256)
        core.track(core.state(snapshot),resume_index,resume_index_sha256)
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
        for source,sha in RUN_SOURCES.items():core.track(core.state(snapshot),source,sha)
        started=perf_counter();value=core.evaluate(snapshot,identifier);elapsed=perf_counter()-started
        completed[identifier]=publish(path,value);timings.append(dict(new_job_id=identifier,elapsed_seconds=elapsed))
        print(json.dumps(dict(completed=len(completed),planned=manifest['planned'],timing=timings[-1],index=save_index(index('PARTIAL')))),flush=True)
    for entry in completed.values():core.read(entry['path'],entry['sha256'])
    final=core.finish(snapshot);saved=save_index(index(final['status'],final));core.verify_finished(snapshot)
    for entry in completed.values():core.read(entry['path'],entry['sha256'])
    return dict(**saved,completed=len(completed),new_evaluations=len(timings),status=final['status'],timings=timings)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-new-tasks',type=int,required=True)
    parser.add_argument('--resume-index',required=True)
    parser.add_argument('--resume-index-sha256',required=True)
    args=parser.parse_args()
    print(json.dumps(run(manifest_path=MANIFEST,manifest_sha256=MANIFEST_SHA,output=FOLDER/'tasks',
        max_new_tasks=args.max_new_tasks,resume_index=args.resume_index,resume_index_sha256=args.resume_index_sha256)))

