"""Strict success payload and required seed guards over frozen readback v1."""
import argparse
from pathlib import Path
import sys
from types import FunctionType
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_cutoff_snapshot_independent_readback_20260919 as previous
archive=previous.archive
SEED_JOB='008d7221048cf94902a831e987641d33e6ba747d8cbe45f2d072b1f7509c6f7b'
SCHEMA='CUTOFF_SNAPSHOT_COMPLETED_INDEPENDENT_TYPED_DECIMAL_READBACK_V2'
LOADED=dict(previous.LOADED)
for path in (Path(__file__).resolve(),Path(previous.__file__).resolve()):
    archive.merge(LOADED,{str(path):archive.drift.file_sha(path)})


def validate_index(index,queue):
    candidates=previous.validate_index(index,queue)
    if not index['completed'] or SEED_JOB not in {entry['job_id'] for entry in index['completed']}:
        raise ValueError('Finalized seed-import queue must retain its completed seed')
    return candidates


def validate_task(value,attempt,**kwargs):
    result=previous.validate_task(value,attempt,**kwargs)
    if result['status'].startswith('FITTED_'):
        if type(result['refit']) is not dict:raise ValueError('Successful status requires a full fitted payload')
        checks=result['independently_recomputed_five_checks']
        if (type(checks) is not dict or set(checks)!={'MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT'}
            or any(type(value) is not bool for value in checks.values())):
            raise ValueError('Successful status requires five explicit boolean checks')
    elif result['refit'] is not None:raise ValueError('Numerical failure must not contain fitted payload')
    return result


def build(index_path,index_sha256):
    # Private lexical binding: no changes to the frozen module's global namespace.
    namespace=dict(previous.build.__globals__,validate_index=validate_index,validate_task=validate_task,LOADED=LOADED)
    readback=FunctionType(previous.build.__code__,namespace,name='strict_completed_readback')
    result=readback(index_path,index_sha256)
    result['schema']=SCHEMA
    result['successful_tasks_require_typed_decimal_payload']=True
    result['completed_seed_presence_verified']=True
    verify(result)
    return result


def verify(value):
    if (value['schema']!=SCHEMA or value.get('successful_tasks_require_typed_decimal_payload') is not True
        or value.get('completed_seed_presence_verified') is not True):raise ValueError('Strict v2 readback required')
    if any(value['historical_expected_source_hashes'].get(p)!=h for p,h in LOADED.items()):raise ValueError('V1 and v2 loaded sources required')
    if archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract())!=value['archive_resolution']:raise ValueError('Source partition differs')
    previous.gaps(value)


def publish_verified(path,value):
    if Path(path).exists():raise FileExistsError('Create-only independent v2 audit')
    verify(value);saved=previous.publish(path,value);verify(value);return saved


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('index-path','index-sha256','output'):p.add_argument('--'+name,required=True)
    args=p.parse_args();print(previous.json.dumps(publish_verified(args.output,build(args.index_path,args.index_sha256))))
