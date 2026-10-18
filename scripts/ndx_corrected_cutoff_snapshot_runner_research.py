"""Explicit 0..100 cutoff tasks with create-only attempts and externally bound resume."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_corrected_cutoff_snapshot_research as core
SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
SCHEMA='CORRECTED_CUTOFF_SNAPSHOT_COMPLETION_INDEX_V1'


def reconcile(folder,entries):
    required=set()
    for entry in entries:
        job=entry['job_id'];path=folder/(job+'.json');attempt=folder/(job+'.started.json')
        if entry['result']['path']!=str(path) or entry['started']['path']!=str(attempt):raise ValueError('Exact output coordinates required')
        required.update((path,attempt))
    actual={p.resolve() for p in folder.glob('*.json') if not p.name.startswith('index_')}
    if actual!=required:raise ValueError('Unindexed result/started attempt; reconcile before any fitting')


def run(*,queue_path,queue_sha256,output,max_new_tasks=0,seed_path=None,seed_sha256=None,resume_index=None,resume_index_sha256=None):
    if type(max_new_tasks) is not int or not 0<=max_new_tasks<=100:raise ValueError('Explicit task budget 0..100 required')
    if bool(resume_index)!=bool(resume_index_sha256) or bool(seed_path)!=bool(seed_sha256):raise ValueError('External SHA pairs required')
    folder=Path(output).resolve();queue_ref=dict(path=str(Path(queue_path).resolve()),sha256=queue_sha256)
    seed_ref=dict(path=str(Path(seed_path).resolve()),sha256=seed_sha256) if seed_path else None
    queue=core.read(queue_ref['path'],queue_ref['sha256']);jobs=[r['task']['job_id'] for r in queue['candidates']];completed={}
    if len(jobs)!=queue['candidate_count'] or len(set(jobs))!=len(jobs):raise ValueError('Complete unique queue required')
    if resume_index:
        previous=core.read(resume_index,resume_index_sha256)
        if (previous.get('schema')!=SCHEMA or previous['queue']!=queue_ref or previous.get('seed')!=seed_ref
            or type(previous['planned']) is not int or previous['planned']!=len(jobs)):raise ValueError('Resume queue coordinate differs')
        core.adapter.audit.original.require_false(previous,core.FLAGS)
        entries=previous['completed'];ids=[e['job_id'] for e in entries]
        if len(set(ids))!=len(ids) or ids!=[j for j in jobs if j in set(ids)]:raise ValueError('Ordered distinct completed queue subset required')
        final=previous.get('finalization');status='COMPLETE' if len(ids)==len(jobs) else 'PARTIAL'
        if previous['status']!=status:raise ValueError('Resume status differs')
        if final is not None:
            if (final.get('schema')!='CORRECTED_CUTOFF_SNAPSHOT_FINALIZATION_V1' or type(final['completed']) is not int or final['completed']!=len(ids)
                or type(final['planned']) is not int or final['planned']!=len(jobs) or final['status']!=status):raise ValueError('Finalization denominator differs')
            core.adapter.audit.original.require_false(final,core.FLAGS)
            checked=core.adapter.archive.verify_expected_sources(final['historical_expected_source_hashes'],core.adapter.archive.load_contract())
            if not core.adapter.audit.original.exact(checked,final['archive_resolution']):raise ValueError('Finalized source partition differs')
            core.adapter.audit.original.verify_gaps(final['historical_loader_gap_observations'])
        completed={e['job_id']:e for e in entries}
    reconcile(folder,list(completed.values()))
    snapshot=core.begin(queue_path=queue_path,queue_sha256=queue_sha256,seed_path=seed_path,seed_sha256=seed_sha256)
    def verify_runner():
        if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=LOADED:raise ValueError('Loaded runner changed')
    verify_runner();core.track(snapshot,SOURCE,LOADED)
    if resume_index:core.track(snapshot,resume_index,resume_index_sha256)
    def attempt_for(job,mode):
        return dict(schema='CORRECTED_CUTOFF_SNAPSHOT_ATTEMPT_V1',queue=queue_ref,seed=seed_ref,job_id=job,mode=mode,
            runner_source_hashes={str(SOURCE):LOADED},status='STARTED_NOT_COMPLETED')
    for job,entry in completed.items():
        result=core.read(entry['result']['path'],entry['result']['sha256']);mode=result['mode']
        attempt=core.read(entry['started']['path'],entry['started']['sha256'])
        if attempt!=attempt_for(job,mode):raise ValueError('Restored attempt coordinate/source differs')
        core.restore(snapshot,entry['result']['path'],entry['result']['sha256']);core.track(snapshot,entry['started']['path'],entry['started']['sha256'])
    def save_index(final=None):
        value=dict(schema=SCHEMA,queue=queue_ref,seed=seed_ref,planned=len(jobs),completed=[completed[j] for j in jobs if j in completed],
            status='COMPLETE' if len(completed)==len(jobs) else 'PARTIAL',finalization=final,**dict.fromkeys(core.FLAGS,False))
        return core.single.publish(folder/('index_'+core.adapter.digest(value)+'.json'),value)
    def save_job(job,mode,execute):
        verify_runner();started=core.single.publish(folder/(job+'.started.json'),attempt_for(job,mode))
        core.track(snapshot,started['path'],started['sha256'])
        value=execute()
        core.read(started['path'],started['sha256']);verify_runner()
        result=core.single.publish(folder/(job+'.json'),value)
        core.read(started['path'],started['sha256']);core.track(snapshot,result['path'],result['sha256'])
        completed[job]=dict(job_id=job,started=started,result=result)
        saved=save_index();print(json.dumps(dict(completed=len(completed),planned=len(jobs),job_id=job,index=saved)),flush=True)
    imported=0;fitted=0
    s=core.state(snapshot)
    if seed_ref:
        seed_job=s['seed_value']['job_id']
        if seed_job not in completed:save_job(seed_job,'EXTERNAL_SINGLE_FIT_IMPORTED_WITHOUT_REFIT',lambda:core.import_seed(snapshot));imported=1
    for job in jobs:
        if job in completed:continue
        if fitted>=max_new_tasks:break
        save_job(job,'ONE_NEW_HISTORICAL_CUTOFF_FIT',lambda job=job:core.evaluate(snapshot,job));fitted+=1
    verify_runner();final=core.finish(snapshot);saved=save_index(final);core.verify_finished(snapshot);verify_runner()
    return dict(saved,completed=len(completed),planned=len(jobs),new_fit_attempts=fitted,seed_imports=imported,status=final['status'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('queue-path','queue-sha256','output'):p.add_argument('--'+key,required=True)
    for key in ('seed-path','seed-sha256','resume-index','resume-index-sha256'):p.add_argument('--'+key)
    p.add_argument('--max-new-tasks',type=int,default=0);print(json.dumps(run(**vars(p.parse_args()))))
