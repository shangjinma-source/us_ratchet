"""Explicit one-candidate cutoff fit; default validates the prepared queue only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_corrected_frontier_cutoff_refit_archive_research as adapter

SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def verify_sources(queue_path,queue_sha256):
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=LOADED:raise ValueError('Loaded single-fit runner source changed')
    raw=Path(queue_path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=queue_sha256:raise ValueError('Externally bound prepared queue changed')
    queue=json.loads(raw);adapter.verify(queue)
    if queue.get('schema')!='CORRECTED_FRONTIER_HISTORICAL_CUTOFF_QUEUE_V1' or queue.get('fit_performed') is not False:
        raise ValueError('Unexecuted complete corrected cutoff queue required')
    return queue


def publish(path,value):
    path=Path(path).resolve();path.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    descriptor,temporary=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.link(temporary,path)
    finally:Path(temporary).unlink(missing_ok=True)
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def run(*,queue_path,queue_sha256,job_id,output=None,execute=False):
    if type(execute) is not bool:raise ValueError('Explicit boolean execution option required')
    queue_path=Path(queue_path).resolve()
    if execute and output is None:raise ValueError('Execution requires create-only output')
    target=Path(output).resolve() if output is not None else None
    started=Path(str(target)+'.started.json') if target is not None else None
    if target is not None and (target.exists() or started.exists()):raise FileExistsError('Existing output or started attempt; read/reconcile instead of refitting')
    queue=verify_sources(queue_path,queue_sha256)
    entries=[e for e in queue['candidates'] if e['task']['job_id']==job_id]
    if type(job_id) is not str or not job_id or len(entries)!=1:raise ValueError('Exactly one explicit queue job required')
    reference=dict(path=str(queue_path),sha256=queue_sha256)
    runner_sources={str(SOURCE):LOADED,str(queue_path):queue_sha256}
    if not execute:
        return dict(schema='CORRECTED_FRONTIER_SINGLE_REFIT_PREFLIGHT_V1',queue=reference,job_id=job_id,
            candidate=entries[0],candidate_count=queue['candidate_count'],historical_cutoff=queue['historical_cutoff'],
            runner_source_hashes=runner_sources,fit_performed=False,selection_performed=False,promotion_allowed=False)
    # Persist a one-shot attempt before any numerical execution. A crashed fit is
    # not silently retried merely because its final output has not been published.
    attempt=dict(schema='CORRECTED_FRONTIER_SINGLE_REFIT_ATTEMPT_V1',queue=reference,job_id=job_id,
        output=str(target),runner_source_hashes=runner_sources,status='STARTED_NOT_COMPLETED')
    started_reference=publish(started,attempt)
    def verify_started():
        if hashlib.sha256(Path(started_reference['path']).read_bytes()).hexdigest()!=started_reference['sha256']:
            raise ValueError('Started attempt changed during execution')
    try:
        verify_sources(queue_path,queue_sha256)
        result=adapter.run_one(prepared=queue,job_id=job_id)
        verify_sources(queue_path,queue_sha256);adapter.verify(result)
        verify_started()
        value=dict(schema='CORRECTED_FRONTIER_SINGLE_REFIT_EXECUTION_V1',queue=reference,job_id=job_id,
            runner_source_hashes=runner_sources,started_attempt=started_reference,result=result,
            fit_performed=True,selection_performed=False,point_in_time_verified=False,promotion_allowed=False)
        saved=publish(target,value)
        verify_sources(queue_path,queue_sha256);adapter.verify(result)
        verify_started()
        return dict(saved,job_id=job_id,status=result['status'],fit_attempts=1)
    finally:
        verify_sources(queue_path,queue_sha256)
        verify_started()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('queue-path','queue-sha256','job-id'):parser.add_argument('--'+key,required=True)
    parser.add_argument('--output');parser.add_argument('--execute',action='store_true')
    print(json.dumps(run(**vars(parser.parse_args()))))
