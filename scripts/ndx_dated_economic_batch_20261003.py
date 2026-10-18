"""One immutable economic-stage batch over the saved dated queue; no fitting."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
import shutil
from pathlib import Path
import types

ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/dated_economic_batch_20261003_v1'
INPUT_ROOT=ROOT/'data/cache/research/dated_account_inputs_20261003_v1'
ACCOUNT_ROOT=ROOT/'data/cache/research/dated_account_execution_20261003_v1/candidates'
CONTINUOUS_ROOT=ROOT/'data/cache/research/dated_per_task_continuous_weight_diagnostic_20261003_v1'
FIRST='89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
INITIAL_IDS={FIRST,'530200b2ffe3b841c27f62dc68c5440c9b0f1cab7e7249592eaebae304713a68','046b0ad4dc7a207abf15e72ac1786848ad3a2a339515edc3b98e479bfb3678b9'}
STAGES=('inputs','input_readback','account_postcheck','account_readback','continuous','continuous_readback')
FLAGS=dict.fromkeys(('fit_performed','incumbent_executed','incumbent_continuous_recomputed','retry_allowed','economic_comparison_performed','promotion_allowed','point_in_time_verified','formal_benchmark_qualified','all_plan_tasks_completed'),False)
PINS={
 'inputs':('scripts/ndx_dated_account_inputs_20261003.py','67ae96e5d71053606a9cfc28694af193cb92449ca02671aada755a3e2395c5ee'),
 'input_readback':('scripts/ndx_dated_account_input_independent_readback_20261003.py','688685ffffad650b30647cf2be5205aacf819b1aed5215867b0d4c565ed22295'),
 'account':('scripts/ndx_dated_account_execution_20261003.py','33752035971557f2ae1d273bd9424f293c9d4530938bee4bae44581cfab496cd'),
 'account_readback':('scripts/ndx_dated_account_independent_readback_20261003.py','2e412e1dfe66d858656ed68c52ed5a2d976b84c8e7306612b4dc66b60ce0249a'),
 'continuous':('scripts/ndx_dated_per_task_continuous_20261003.py','d6ece8c31eefd25ec019b1acbb0f9d5a8b25403e2b0065f56b5c03acd5584464'),
 'continuous_readback':('scripts/ndx_dated_per_task_continuous_independent_readback_20261003.py','4a947e8c6f0d96ddae74bb87fc0a5a8dbb691865d550e543e5ecb9311b20e03a'),
 'summary_reader':('scripts/ndx_dated_batch_summary_independent_readback_20261003.py','1e7ef358ec186aac0997a2f34ed3d690f89fb907b557e08befa2dd67e9235c11'),
}
BOUND={
 'summary':dict(path=str(ROOT/'data/cache/research/dated_batch_summary_20261003_v1/summary.json'),sha256='406922de9ffc292417d4b495af30691833f5bb8c2b5b60449c010d5178acb378'),
 'summary_publication':dict(path=str(ROOT/'data/cache/research/dated_batch_summary_20261003_v1/publication.json'),sha256='23480ca1d99000206344d0176e555b2f16ba12542f2784002854652b7720782b'),
 'summary_audit':dict(path=str(ROOT/'DYNAMIC_DATED_BATCH_SUMMARY_INDEPENDENT_READBACK_20261003.json'),sha256='d60fefc9121db9a14667d0994cd8e4ee58e1d6c62135f042234396d2212b555a'),
 'initial':dict(path=str(ROOT/'research_contracts/dated_initial_economic_completed_20261003_v1.json'),sha256='1b5f549979e82653f2448d75ff48a6fa8a79497af1fcbe5066b77a2bcb48ffec'),
}
PREPARATION_REFERENCE=dict(path=str(ROOT/'data/cache/research/dated_fixed_task_preparation_20261003_v1/preparation.json'),sha256='ff24a6b732bc55ea6dbb7b453a41ff58d0f2ee316e3f2120aa4006f3b82d3d0e')
FULL=6222659648236112670
MIN_FREE_BYTES=5*1024**3

def require(ok,message):
    if not ok:raise ValueError(message)
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,message):require(encode(a)==encode(b),message)
def reference(v):require(type(v) is dict and set(v)=={'path','sha256'} and type(v['path']) is str and type(v['sha256']) is str and len(v['sha256'])==64 and all(c in '0123456789abcdef' for c in v['sha256']),'Exact external reference')
def read(ref,sources):
    reference(ref);raw=Path(ref['path']).read_bytes();require(sha(raw)==ref['sha256'],'External evidence drift');require(ref['path'] not in sources or sources[ref['path']]==ref['sha256'],'Source conflict');sources[ref['path']]=ref['sha256']
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda s:(_ for _ in ()).throw(ValueError(s)))
def guard(sources):
    for p,h in sources.items():require(type(h) is str and sha(Path(p).read_bytes())==h,'Source pending or drift')
def save(path,value):
    raw=encode(value)
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==raw,'Saved evidence changed');return dict(path=str(path),sha256=sha(raw))
def record(stream,value):stream.write(encode(value)+b'\n');stream.flush();os.fsync(stream.fileno())

def validate_queue(summary,initial):
    require(summary['schema']=='DATED_BATCH_SAVED_READBACK_SUMMARY_V1','Dated summary schema');rows=summary['rows'];ids=[r['numerical_task_id'] for r in rows]
    require(len(ids)==len(set(ids))==1632 and all(type(x) is str and len(x)==64 for x in ids),'Complete dated order')
    require(type(summary['full_new_cutoff_task_denominator']) is int and summary['full_new_cutoff_task_denominator']==FULL and summary['old_different_cutoff_completed_count_deducted']==0,'New cutoff denominator')
    require(initial['schema']=='DATED_INITIAL_ECONOMIC_COMPLETED_V1','Explicit economic initial contract');exact(initial['preparation_reference'],PREPARATION_REFERENCE,'Initial dated preparation')
    require(len(initial['rows'])==3 and {r['numerical_task_id'] for r in initial['rows']}==INITIAL_IDS and INITIAL_IDS.issubset(ids),'Exactly three initial tasks')
    for row in initial['rows']:
        require(set(row)=={'numerical_task_id',*STAGES,'inputs_publication','continuous_publication'},'Exact initial stage references')
        for stage in (*STAGES,'inputs_publication','continuous_publication'):reference(row[stage])
    for row in rows:
        require(row['category'] in ('RISK_PASSED','RISK_FAILED'),'All requested fits must have returned audited weights; no silent skipping')
        reference(row['saved_batch_row']['independent_readback_reference'])
    return ids

def execute_queue(task_ids,*,initial_rows,stage_functions,verify_sources,output,context=None,validate_stage=None,resource_check=None):
    """Bounded orchestrator; exceptions preserve completed stages, never retry."""
    require(type(task_ids) is list and len(task_ids)==len(set(task_ids)) and all(type(t) is str and len(t)==64 for t in task_ids),'Unique task order')
    require(set(stage_functions)==set(STAGES),'Exact stage callbacks');require(not output.exists(),'Immutable batch namespace exists');verify_sources();output.mkdir(parents=True,exist_ok=False)
    save(output/'started.json',dict(schema='DATED_ECONOMIC_BATCH_STARTED_V1',ordered_remaining_task_ids=task_ids,initial_rows=initial_rows,context=context,**FLAGS))
    completed=[];failure=None
    with (output/'progress.jsonl').open('xb') as log:
        for ordinal,tid in enumerate(task_ids):
            refs={};stage=None;task_stage_invoked=False;current_stage_invoked=False
            try:
                if resource_check is not None:
                    free=resource_check();require(type(free) is int and free>=0,'Exact free bytes')
                    if free<MIN_FREE_BYTES:
                        failure=dict(numerical_task_id=tid,ordinal=ordinal,stage=None,reason='RESOURCE_STOP_BEFORE_DISPATCH',available_bytes=free,minimum_free_bytes=MIN_FREE_BYTES,completed_stage_references={},task_stage_invoked=False,current_stage_invoked=False,stage_may_have_written_evidence=False,retry_allowed=False)
                        record(log,dict(status='STOPPED',**failure));break
                for stage in STAGES:
                    current_stage_invoked=False
                    verify_sources();record(log,dict(numerical_task_id=tid,ordinal=ordinal,stage=stage,status='DISPATCHING'))
                    task_stage_invoked=True;current_stage_invoked=True
                    result=stage_functions[stage](tid,refs);reference(result);refs[stage]=result
                    record(log,dict(numerical_task_id=tid,ordinal=ordinal,stage=stage,status='REFERENCE_RETURNED',reference=result))
                    if validate_stage is not None:validate_stage(tid,stage,result,refs)
                    verify_sources()
                completed.append(dict(numerical_task_id=tid,stage_references=deepcopy(refs)))
                if len(completed)%10==0 or len(completed)==len(task_ids):print(json.dumps(dict(completed_count=len(completed),planned_count=len(task_ids),numerical_task_id=tid)),flush=True)
            except Exception as error:
                failure=dict(numerical_task_id=tid,ordinal=ordinal,stage=stage,completed_stage_references=deepcopy(refs),error_type=type(error).__name__,error=str(error),task_stage_invoked=task_stage_invoked,current_stage_invoked=current_stage_invoked,stage_may_have_written_evidence=task_stage_invoked,retry_allowed=False)
                record(log,dict(status='STOPPED',**failure));break
    value=dict(schema='DATED_ECONOMIC_BATCH_RESULT_V1',status='STOPPED_WITH_EVIDENCE' if failure else 'REQUESTED_ECONOMIC_STAGES_FINISHED',initial_rows_preserved=initial_rows,new_completed_rows=completed,failure=failure,undispatched_task_ids=task_ids[len(completed)+(1 if failure and failure['stage_may_have_written_evidence'] else 0):],unresolved_task_ids=[failure['numerical_task_id']] if failure and failure['stage_may_have_written_evidence'] else [],planned_remaining_count=len(task_ids),new_completed_count=len(completed),context=context,**FLAGS)
    if failure:save(output/'failure.json',failure)
    return save(output/'result.json',value)

def load_module(role,sources):
    relative,expected=PINS[role];path=ROOT/relative;require(type(expected) is str and len(expected)==64,'Module pin pending');raw=path.read_bytes();require(sha(raw)==expected,'Pinned module changed');sources[str(path)]=expected
    module=types.ModuleType('_dated_economic_'+role);module.__file__=str(path);exec(compile(raw,str(path),'exec'),module.__dict__);require(Path(module.__file__)==path,'Module path changed');guard(sources);return module

def preflight():
    """Read and hash saved metadata only: no module imports or dispatch."""
    require(not OUTPUT.exists(),'Immutable batch exists')
    # Check every pending pin before importing modules or touching any output.
    for ref in BOUND.values():reference(ref)
    for relative,h in PINS.values():require(type(h) is str and len(h)==64,'Module pin pending')
    sources={str(SOURCE):LOADED};docs={k:read(ref,sources) for k,ref in BOUND.items()}
    summary=docs['summary'];audit=docs['summary_audit'];pub=docs['summary_publication'];initial=docs['initial']
    require(audit['schema']=='DATED_BATCH_SUMMARY_INDEPENDENT_READBACK_V1' and audit['status']=='PASS','Independent complete summary');exact(audit['summary_reference'],BOUND['summary'],'Summary audit');exact(audit['publication_reference'],BOUND['summary_publication'],'Summary receipt');exact(pub['summary_reference'],BOUND['summary'],'Published summary')
    require(audit['reader_sha256']==PINS['summary_reader'][1],'Frozen summary reader');order=validate_queue(summary,initial)
    for row in initial['rows']:
        tid=row['numerical_task_id'];saved={k:read(row[k],sources) for k in (*STAGES,'inputs_publication','continuous_publication')}
        exact(saved['inputs_publication']['inputs_reference'],row['inputs'],'Initial input receipt');exact(saved['input_readback']['inputs_reference'],row['inputs'],'Initial input audit');require(saved['input_readback']['status']=='PASS','Initial input accepted')
        exact(saved['continuous_publication']['diagnostic_reference'],row['continuous'],'Initial continuous receipt')
        if tid==FIRST:
            require(saved['account_readback']['schema']=='DATED_FIRST_ACCOUNTS_INDEPENDENT_ACCOUNTING_READBACK_V1' and saved['account_readback']['status']=='PASS','First existing accounting')
            require(saved['continuous_readback']['schema']=='DATED_CONTINUOUS_INDEPENDENT_READBACK_V1' and saved['continuous_readback']['status']=='PASS','First existing continuous')
        else:
            require(saved['account_readback']['schema']=='DATED_ACCOUNT_INDEPENDENT_READBACK_V1' and saved['account_readback']['status']=='PASS' and saved['account_readback']['numerical_task_id']==tid,'Existing candidate accounting')
            exact(saved['account_readback']['postcheck_reference'],row['account_postcheck'],'Initial accounting post')
            require(saved['continuous_readback']['schema']=='DATED_PER_TASK_CONTINUOUS_INDEPENDENT_READBACK_V1' and saved['continuous_readback']['status']=='PASS' and saved['continuous_readback']['numerical_task_id']==tid,'Existing candidate continuous')
        exact(saved['continuous_readback']['diagnostic_reference'],row['continuous'],'Initial continuous audit')
    require({p.name for p in INPUT_ROOT.iterdir()}==INITIAL_IDS and {p.name for p in ACCOUNT_ROOT.iterdir()}==INITIAL_IDS and {p.name for p in CONTINUOUS_ROOT.iterdir()}==INITIAL_IDS-{FIRST},'Only explicitly audited existing task namespaces')
    for relative,h in PINS.values():
        require(sha((ROOT/relative).read_bytes())==h,'Module source drift');sources[str(ROOT/relative)]=h
    guard(sources)
    return dict(summary=summary,initial=initial,order=order,sources=sources)

def run(*,execute=False):
    require(type(execute) is bool and execute,'Explicit execute required')
    checked=preflight();summary=checked['summary'];initial=checked['initial'];order=checked['order'];sources=checked['sources']
    modules={k:load_module(k,sources) for k in PINS if k!='summary_reader'};common_inputs=modules['inputs'].load_common();common_continuous=modules['continuous'].load_common();guard(sources)
    fitrefs={r['numerical_task_id']:r['saved_batch_row']['independent_readback_reference'] for r in summary['rows']}
    def publication(result):
        path=Path(result['path']).with_name('publication.json');ref=dict(path=str(path),sha256=sha(path.read_bytes()));stage_sources={};read(ref,stage_sources);guard(stage_sources);return ref
    def inputs(tid,refs):return modules['inputs'].run(tid,fitrefs[tid],execute=True,common=common_inputs)
    def input_readback(tid,refs):return modules['input_readback'].run(refs['inputs'],publication(refs['inputs']))
    def account(tid,refs):return modules['account'].run('candidate',refs['inputs'],refs['input_readback'],execute=True)
    def account_readback(tid,refs):
        return modules['account_readback'].readback(tid,refs['account_postcheck'],execute=True)
    def continuous(tid,refs):return modules['continuous'].run(tid,refs['inputs'],refs['input_readback'],execute=True,common=common_continuous)
    def continuous_readback(tid,refs):
        return modules['continuous_readback'].readback(tid,publication(refs['continuous']),execute=True)
    def validate_stage(tid,stage,ref,refs):
        stage_sources={};value=read(ref,stage_sources);guard(stage_sources)
        if stage=='account_readback':require(value['status']=='PASS' and value['attempt_outcome'] in ('ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING','NOT_EXECUTED_NONPOSITIVE_TARGET'),'Technical account failure stops batch')
        if stage in ('input_readback','continuous_readback'):require(value['status']=='PASS','Independent stage failed')
    callbacks=dict(zip(STAGES,(inputs,input_readback,account,account_readback,continuous,continuous_readback)))
    return execute_queue([t for t in order if t not in INITIAL_IDS],initial_rows=initial['rows'],stage_functions=callbacks,verify_sources=lambda:guard(sources),output=OUTPUT,validate_stage=validate_stage,resource_check=lambda:shutil.disk_usage(ROOT).free,context=dict(minimum_free_disk_bytes=MIN_FREE_BYTES,disk_gate_is_resource_limit_not_task_domain=True,input_references=BOUND,source_hashes=deepcopy(sources),full_task_count=1632,full_new_cutoff_task_denominator=FULL,comparison_stage_not_implemented=True,**FLAGS))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
