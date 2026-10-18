"""Explicit bounded execution/resume of a source-bound BASE date snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_base_window_snapshot_research as core
from scripts import ndx_base_three_cell_window_delta_research as legacy
SELF=Path(__file__).resolve();LOADED=hashlib.sha256(SELF.read_bytes()).hexdigest()


def run(*,manifest_path,manifest_sha256,output,max_new_tasks,probes=(),resume_index=None,resume_index_sha256=None):
    if type(max_new_tasks) is not int or max_new_tasks<0:raise ValueError('Explicit nonnegative new-task budget required')
    manifest_path=str(Path(manifest_path).resolve());manifest=legacy.read(manifest_path,manifest_sha256)
    if manifest['source_hashes'].get(str(SELF))!=LOADED:raise ValueError('Runner source missing from manifest')
    snapshot=core.begin_snapshot(manifest_path=manifest_path,manifest_sha256=manifest_sha256)
    folder=Path(output);completed={};latest=None;timings=[]
    reference=dict(path=manifest_path,sha256=manifest_sha256)
    def index(status,finalization=None):
        return dict(schema='ndx_base_window_snapshot_completion_index_v1',manifest=reference,
            completed=[completed[row['new_job_id']] for row in manifest['tasks'] if row['new_job_id'] in completed],
            planned=len(manifest['tasks']),status=status,finalization=finalization,promotion_allowed=False)
    def save_progress():
        value=index('PARTIAL');return legacy.publish(folder/('index_'+legacy.original._sha(value)+'.json'),value)
    if resume_index is not None:
        if resume_index_sha256 is None:raise ValueError('External resume index SHA required')
        prior=legacy.read(resume_index,resume_index_sha256)
        if prior['schema']!='ndx_base_window_snapshot_completion_index_v1' or prior['manifest']!=reference or prior['planned']!=len(manifest['tasks']):
            raise ValueError('Resume index manifest/denominator differs')
        core.prepare_restore_sources(snapshot,prior['completed'])
        for entry in prior['completed']:
            value=core.restore_task(snapshot,checkpoint_path=entry['path'],checkpoint_sha256=entry['sha256'])
            completed[value['new_job_id']]=entry
        if prior['status'] not in ('PARTIAL','COMPLETE') or (prior['status']=='COMPLETE' and len(completed)!=len(manifest['tasks'])):
            raise ValueError('Resume completion denominator differs')
    for probe in probes:
        value=core.import_probe(snapshot,probe_path=probe['path'],probe_sha256=probe['sha256'])
        completed[value['new_job_id']]=legacy.publish(folder/(value['new_job_id']+'.json'),value)
        latest=save_progress()
    for row in manifest['tasks']:
        identifier=row['new_job_id']
        if identifier in completed:continue
        if len(timings)>=max_new_tasks:break
        destination=folder/(identifier+'.json')
        if destination.exists():raise ValueError('Unindexed task exists; supply its externally verified completion index')
        start=perf_counter();value=core.evaluate_task(snapshot,identifier);elapsed=perf_counter()-start
        completed[identifier]=legacy.publish(destination,value);timings.append(dict(new_job_id=identifier,elapsed_seconds=elapsed))
        latest=save_progress()
        print(json.dumps(dict(completed=len(completed),planned=len(manifest['tasks']),last_task=timings[-1],external_index=latest)),flush=True)
    for entry in completed.values():core._bytes(entry['path'],entry['sha256'])
    finalization=core.finish_snapshot(snapshot)
    final=index(finalization['status'],finalization)
    latest=legacy.publish(folder/('index_'+legacy.original._sha(final)+'.json'),final)
    legacy.original._verify_sources(finalization['source_hashes'])
    for entry in completed.values():core._bytes(entry['path'],entry['sha256'])
    return dict(**latest,status=final['status'],completed=len(completed),new_tasks=len(timings),timings=timings)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-path',required=True);parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--max-new-tasks',type=int,required=True)
    parser.add_argument('--probe-index');parser.add_argument('--probe-index-sha256')
    parser.add_argument('--resume-index');parser.add_argument('--resume-index-sha256')
    options=parser.parse_args();probes=[]
    if options.probe_index:
        if not options.probe_index_sha256:raise ValueError('External probe index SHA required')
        probes=legacy.read(options.probe_index,options.probe_index_sha256)['probes']
    print(json.dumps(run(manifest_path=options.manifest_path,manifest_sha256=options.manifest_sha256,
        output=options.output,max_new_tasks=options.max_new_tasks,probes=probes,
        resume_index=options.resume_index,resume_index_sha256=options.resume_index_sha256)))
