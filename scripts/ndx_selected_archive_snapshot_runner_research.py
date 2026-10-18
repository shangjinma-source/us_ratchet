"""Explicit new archive manifest and bounded continuation; no default fitting."""
import argparse
import json
import os
import tempfile
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_selected_archive_snapshot_research as core
SOURCE=Path(__file__).resolve();LOADED=core.old.drift.file_sha(SOURCE)


def publish(path,value):
    path=Path(path).resolve();path.parent.mkdir(parents=True,exist_ok=True)
    raw=core.old.selected.encoding._json_bytes(value)
    descriptor,temporary=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.link(temporary,path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return dict(path=str(path),sha256=core.old.drift.file_sha(path))


def reconcile(folder,entries):
    required=set()
    for entry in entries:
        path=Path(entry['path']).resolve()
        if path.parent!=folder.resolve() or path.name.startswith('index_') or path in required:raise ValueError('Exact distinct task output coordinates required')
        required.add(path)
    actual={p.resolve() for p in folder.glob('*.json') if not p.name.startswith('index_')}
    if actual!=required:raise ValueError('Unindexed output artifact; reconcile before any restore or fit')


def run(*,manifest_path,manifest_sha256,output,max_new_tasks=0,resume_index=None,resume_index_sha256=None):
    if type(max_new_tasks) is not int or not 0<=max_new_tasks<=1000:raise ValueError('Explicit integer budget 0..1000 required')
    if bool(resume_index)!=bool(resume_index_sha256):raise ValueError('External resume pair required')
    folder=Path(output).resolve();reference=dict(path=str(Path(manifest_path).resolve()),sha256=manifest_sha256)
    manifest=core.old.read(manifest_path,manifest_sha256);completed={};previous=None
    if resume_index:
        previous=core.old.read(resume_index,resume_index_sha256)
        if previous.get('schema')!='SELECTED_ARCHIVE_RESOLUTION_COMPLETION_INDEX_V1' or previous['manifest']!=reference or previous['planned']!=manifest['planned']:raise ValueError('Resume index coordinate differs')
        if any(previous.get(k) is not False for k in ('historical_full_source_closure_verified','original_live_price_paths_verified','point_in_time_verified','promotion_allowed')):raise ValueError('Resume scope upgraded')
        for entry in previous['completed']:
            identifier=Path(entry['path']).stem
            if identifier in completed:raise ValueError('Duplicate saved task')
            completed[identifier]=entry
        expected_ids=[r['new_job_id'] for r in manifest['tasks'][:len(completed)]]
        if list(completed)!=expected_ids:raise ValueError('Ordered completed prefix required')
        final=previous.get('finalization')
        expected_status='COMPLETE' if len(completed)==manifest['planned'] else 'PARTIAL'
        if previous.get('status')!=expected_status:raise ValueError('Resume status differs')
        if final is not None:
            if (final.get('schema')!='SELECTED_ARCHIVE_RESOLUTION_FINALIZATION_V1'
                or type(final.get('completed')) is not int or final['completed']!=len(completed)
                or type(final.get('planned')) is not int or final['planned']!=manifest['planned']
                or final.get('status')!=expected_status
                or any(final.get(k) is not False for k in ('historical_full_source_closure_verified','original_live_price_paths_verified','point_in_time_verified','promotion_allowed'))):raise ValueError('Resume finalization differs')
    reconcile(folder,list(completed.values()))
    snapshot=core.begin(manifest_path=manifest_path,manifest_sha256=manifest_sha256)
    core.track(snapshot,SOURCE,LOADED)
    if previous:
        core.track(snapshot,resume_index,resume_index_sha256)
        for entry in completed.values():core.restore(snapshot,entry['path'],entry['sha256'])
    def save_index(final=None):
        value=dict(schema='SELECTED_ARCHIVE_RESOLUTION_COMPLETION_INDEX_V1',manifest=reference,planned=manifest['planned'],completed=[completed[r['new_job_id']] for r in manifest['tasks'] if r['new_job_id'] in completed],
            finalization=final,status=final['status'] if final else 'PARTIAL',historical_full_source_closure_verified=False,original_live_price_paths_verified=False,point_in_time_verified=False,promotion_allowed=False)
        return publish(folder/('index_'+core.old.selected.encoding._sha(value)+'.json'),value)
    fits=0;imports=0
    for row in manifest['tasks']:
        identifier=row['new_job_id']
        if identifier in completed:continue
        s=core.state(snapshot)
        if identifier not in s['legacy_entries'] and fits>=max_new_tasks:break
        core.track(snapshot,SOURCE,LOADED)
        if identifier in s['legacy_entries']:
            value=core.restore_legacy(snapshot,identifier);imports+=1
        else:value=core.evaluate(snapshot,identifier);fits+=1
        completed[identifier]=publish(folder/(identifier+'.json'),value)
        save_index()
    final=core.finish(snapshot);saved=save_index(final);core.verify_finished(snapshot)
    for entry in completed.values():core.old.read(entry['path'],entry['sha256'])
    return dict(saved,completed=len(completed),new_fits=fits,legacy_imports=imports,status=final['status'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-path',required=True);parser.add_argument('--manifest-sha256')
    parser.add_argument('--prepare',action='store_true');parser.add_argument('--legacy-index');parser.add_argument('--legacy-index-sha256')
    parser.add_argument('--output');parser.add_argument('--max-new-tasks',type=int,default=0)
    parser.add_argument('--resume-index');parser.add_argument('--resume-index-sha256');args=parser.parse_args()
    if args.prepare:
        if not args.legacy_index or not args.legacy_index_sha256:parser.error('Prepare requires external legacy index pair')
        result=publish(args.manifest_path,core.build_manifest(legacy_index_path=args.legacy_index,legacy_index_sha256=args.legacy_index_sha256))
    else:
        if not args.manifest_sha256 or not args.output:parser.error('Execution requires manifest SHA and separate output directory')
        result=run(manifest_path=args.manifest_path,manifest_sha256=args.manifest_sha256,output=args.output,max_new_tasks=args.max_new_tasks,resume_index=args.resume_index,resume_index_sha256=args.resume_index_sha256)
    print(json.dumps(result))
