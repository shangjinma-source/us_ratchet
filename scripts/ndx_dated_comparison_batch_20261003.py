"""Immutable bounded comparison batch; no accounts, fitting or old-stage replay."""
import argparse
from copy import deepcopy
import hashlib,json,os,shutil,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/dated_comparison_batch_20261003_v1'
COMPARISON_ROOT=ROOT/'data/cache/research/dated_per_task_economic_comparison_20261003_v1'
FIRST='89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
INITIAL_IDS={FIRST,'530200b2ffe3b841c27f62dc68c5440c9b0f1cab7e7249592eaebae304713a68','046b0ad4dc7a207abf15e72ac1786848ad3a2a339515edc3b98e479bfb3678b9'}
ECONOMIC_STAGES=('inputs','input_readback','account_postcheck','account_readback','continuous','continuous_readback')
STAGES=('comparison','independent_readback')
FULL=6222659648236112670
MIN_FREE_BYTES=5*1024**3
FLAGS=dict.fromkeys(('fit_performed','account_executed','continuous_recomputed','retry_allowed','promotion_allowed','point_in_time_verified','formal_comparison_passed','winner_selected','all_plan_tasks_completed'),False)
PINS={
 'producer':('scripts/ndx_dated_per_task_economic_comparison_20261003.py','3b808e10071b7e5f67f337a79ae95ab974d4245c4201436ffde85fc54c66531f'),
 'reader':('scripts/ndx_dated_per_task_comparison_independent_readback_20261003.py','6067301133e1662e6021c53e25d1c79c72e91e2b91b71cd5b8b874db035532ad'),
 'economic_reader':('scripts/ndx_dated_economic_batch_independent_readback_20261003.py','d927253295a571eb7e344b30b588e6d65f55de7e29b71d887a4c838728fd1a0b'),
}
BOUND={
 'summary':dict(path=str(ROOT/'data/cache/research/dated_batch_summary_20261003_v1/summary.json'),sha256='406922de9ffc292417d4b495af30691833f5bb8c2b5b60449c010d5178acb378'),
 'economic_initial':dict(path=str(ROOT/'research_contracts/dated_initial_economic_completed_20261003_v1.json'),sha256='1b5f549979e82653f2448d75ff48a6fa8a79497af1fcbe5066b77a2bcb48ffec'),
 'economic_result':dict(path=str(ROOT/'data/cache/research/dated_economic_batch_20261003_v1/result.json'),sha256='6aaa8963043b54ad5de9a380302b3a7ae2007830a41de870a7947ce236d74218'),
 'economic_audit':dict(path=str(ROOT/'data/cache/research/dated_economic_batch_independent_readback_20261003_v1/independent_readback.json'),sha256='322cec25f0a4deed92eeb98fa323d3cbbaece814e5544ad7026ceace958c15c7'),
 'initial':dict(path=str(ROOT/'research_contracts/dated_initial_comparisons_20261003_v1.json'),sha256='2c03cb138ccc3c5af8e9f21a93cdb57322318f4d9e04b4a4dbca407b878d7ef2'),
}
PREPARATION_REFERENCE=dict(path=str(ROOT/'data/cache/research/dated_fixed_task_preparation_20261003_v1/preparation.json'),sha256='ff24a6b732bc55ea6dbb7b453a41ff58d0f2ee316e3f2120aa4006f3b82d3d0e')
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

def execute_queue(task_ids,*,initial_rows,stage_functions,verify_sources,output,context=None,validate_stage=None,resource_check=None):
    """Bounded orchestrator; exceptions preserve completed stages, never retry."""
    require(type(task_ids) is list and len(task_ids)==len(set(task_ids)) and all(type(t) is str and len(t)==64 for t in task_ids),'Unique task order')
    require(set(stage_functions)==set(STAGES),'Exact stage callbacks');require(not output.exists(),'Immutable batch namespace exists');verify_sources();output.mkdir(parents=True,exist_ok=False)
    save(output/'started.json',dict(schema='DATED_COMPARISON_BATCH_STARTED_V1',ordered_remaining_task_ids=task_ids,initial_rows=initial_rows,context=context,**FLAGS))
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
    value=dict(schema='DATED_COMPARISON_BATCH_RESULT_V1',status='STOPPED_WITH_EVIDENCE' if failure else 'REQUESTED_COMPARISONS_FINISHED',initial_rows_preserved=initial_rows,new_completed_rows=completed,failure=failure,undispatched_task_ids=task_ids[len(completed)+(1 if failure and failure['stage_may_have_written_evidence'] else 0):],unresolved_task_ids=[failure['numerical_task_id']] if failure and failure['stage_may_have_written_evidence'] else [],planned_remaining_count=len(task_ids),new_completed_count=len(completed),context=context,**FLAGS)
    if failure:save(output/'failure.json',failure)
    return save(output/'result.json',value)


def validate_queue(summary,economic_initial,economic_result,initial):
    require(summary['schema']=='DATED_BATCH_SAVED_READBACK_SUMMARY_V1','New dated summary')
    ids=[r['numerical_task_id'] for r in summary['rows']]
    require(len(ids)==len(set(ids))==1632,'Complete unique fixed queue')
    require(type(summary['full_new_cutoff_task_denominator']) is int and summary['full_new_cutoff_task_denominator']==FULL,'Unchanged complete denominator')
    require(economic_initial['schema']=='DATED_INITIAL_ECONOMIC_COMPLETED_V1','Original economic initial schema');exact(economic_initial['preparation_reference'],PREPARATION_REFERENCE,'Original dated preparation')
    previous=economic_initial['rows'];require(len(previous)==3 and {r['numerical_task_id'] for r in previous}==INITIAL_IDS,'Exactly existing economic three')
    require(economic_result['schema']=='DATED_ECONOMIC_BATCH_RESULT_V1','Economic batch schema');exact(economic_result['initial_rows_preserved'],previous,'Economic initial refs unchanged')
    # A stopped batch is not silently shortened. This version cannot start on incomplete parents.
    require(economic_result['status']=='REQUESTED_ECONOMIC_STAGES_FINISHED' and economic_result['failure'] is None and economic_result['unresolved_task_ids']==[] and economic_result['undispatched_task_ids']==[],'Economic parent incomplete: retain entire 1632 denominator, no dispatch')
    expected=[t for t in ids if t not in INITIAL_IDS];new=economic_result['new_completed_rows']
    require(type(economic_result['planned_remaining_count']) is int and economic_result['planned_remaining_count']==1629 and type(economic_result['new_completed_count']) is int and economic_result['new_completed_count']==1629,'Exact completed economic count')
    require([r['numerical_task_id'] for r in new]==expected,'Economic queue original order and full coverage')
    sources={}
    for row in previous:
        require(set(row)=={'numerical_task_id',*ECONOMIC_STAGES,'inputs_publication','continuous_publication'},'Initial complete economic refs')
        sources[row['numerical_task_id']]={k:deepcopy(row[k]) for k in ECONOMIC_STAGES}
    for row in new:
        require(set(row)=={'numerical_task_id','stage_references'} and set(row['stage_references'])==set(ECONOMIC_STAGES),'Every economic stage present')
        sources[row['numerical_task_id']]=deepcopy(row['stage_references'])
    for refs in sources.values():
        for r in refs.values():reference(r)
    require(initial['schema']=='DATED_INITIAL_COMPARISONS_V1','Explicit comparison initial contract');exact(initial['preparation_reference'],PREPARATION_REFERENCE,'Comparison dated preparation')
    require(len(initial['rows'])==3 and {r['numerical_task_id'] for r in initial['rows']}==INITIAL_IDS,'Exactly original three comparisons')
    for row in initial['rows']:
        require(set(row)=={'numerical_task_id','comparison_reference','publication_reference','independent_readback_reference'},'Exact completed comparison refs')
        for key in ('comparison_reference','publication_reference','independent_readback_reference'):reference(row[key])
    return ids,sources

def load_module(role,sources):
    relative,expected=PINS[role];path=ROOT/relative;raw=path.read_bytes();require(type(expected) is str and sha(raw)==expected,'Pinned new module')
    sources[str(path)]=expected;module=types.ModuleType('_dated_comparison_batch_'+role);module.__file__=str(path);exec(compile(raw,str(path),'exec'),module.__dict__);require(Path(module.__file__)==path,'Module path');guard(sources);return module

def preflight():
    require(not OUTPUT.exists(),'Immutable batch namespace exists')
    for r in BOUND.values():reference(r)
    for relative,h in PINS.values():require(type(h) is str and len(h)==64,'Unreviewed module pin pending')
    sources={str(SOURCE):LOADED};docs={k:read(r,sources) for k,r in BOUND.items()}
    audit=docs['economic_audit'];require(audit['schema']=='DATED_ECONOMIC_BATCH_INDEPENDENT_READBACK_V1' and audit['status']=='PASS','Economic batch independent receipt');exact(audit['result_reference'],BOUND['economic_result'],'Economic audit result');require(audit['reader_sha256']==PINS['economic_reader'][1],'Audited economic reader')
    ids,stage_refs=validate_queue(docs['summary'],docs['economic_initial'],docs['economic_result'],docs['initial'])
    for row in docs['initial']['rows']:
        tid=row['numerical_task_id'];d=read(row['comparison_reference'],sources);pub=read(row['publication_reference'],sources);a=read(row['independent_readback_reference'],sources)
        exact(pub['comparison_reference'],row['comparison_reference'],'Existing publication');require(a['status']=='PASS','Existing independent comparison')
        exact(a['comparison_reference'],row['comparison_reference'],'Existing audit result');exact(a['publication_reference'],row['publication_reference'],'Existing audit receipt')
        if tid==FIRST:
            require(d['schema']=='SOURCE_BOUND_DATED_FIRST_ECONOMIC_COMPARISON_V1','First immutable comparison')
        else:
            require(d['schema']=='SOURCE_BOUND_DATED_PER_TASK_ECONOMIC_COMPARISON_V1' and d['numerical_task_id']==tid and a['schema']=='DATED_PER_TASK_COMPARISON_INDEPENDENT_READBACK_V1' and a['numerical_task_id']==tid,'Existing task comparison')
            exact(d['input_references']['account_audit'],stage_refs[tid]['account_readback'],'Existing account audit binding');exact(d['input_references']['continuous_audit'],stage_refs[tid]['continuous_readback'],'Existing continuous audit binding')
            require(Path(row['comparison_reference']['path'])==COMPARISON_ROOT/tid/'comparison.json','Existing fixed namespace')
    require(COMPARISON_ROOT.is_dir() and {p.name for p in COMPARISON_ROOT.iterdir()}==INITIAL_IDS-{FIRST},'No unexpected existing comparison attempts')
    for tid in INITIAL_IDS-{FIRST}:require({p.name for p in (COMPARISON_ROOT/tid).iterdir()}=={'started.json','comparison.json','publication.json','independent_readback.json'},'Only fully audited comparison directories')
    for relative,h in PINS.values():require(sha((ROOT/relative).read_bytes())==h,'Pinned source bytes');sources[str(ROOT/relative)]=h
    guard(sources);return dict(order=ids,stage_refs=stage_refs,initial=docs['initial'],sources=sources)

def run(*,execute=False):
    require(type(execute) is bool and execute,'Explicit execute=True required');checked=preflight();sources=checked['sources'];producer=load_module('producer',sources);reader=load_module('reader',sources);common=producer.load_common();guard(sources)
    def comparison(tid,refs):
        parents=checked['stage_refs'][tid]
        return producer.run(tid,parents['account_readback'],parents['continuous_readback'],execute=True,common=common)
    def independent(tid,refs):
        path=Path(refs['comparison']['path']).with_name('publication.json');pub=dict(path=str(path),sha256=sha(path.read_bytes()));temporary={};value=read(pub,temporary);exact(value['comparison_reference'],refs['comparison'],'Current publication target');guard(temporary)
        return reader.readback(tid,pub,execute=True)
    def validate_stage(tid,stage,reference_value,refs):
        temporary={};d=read(reference_value,temporary);guard(temporary)
        if stage=='comparison':require(d['schema']=='SOURCE_BOUND_DATED_PER_TASK_ECONOMIC_COMPARISON_V1' and d['numerical_task_id']==tid,'New comparison target')
        else:
            require(d['schema']=='DATED_PER_TASK_COMPARISON_INDEPENDENT_READBACK_V1' and d['status']=='PASS' and d['numerical_task_id']==tid and d['reader_sha256']==PINS['reader'][1],'Independent comparison accepted');exact(d['comparison_reference'],refs['comparison'],'Current independent target')
    return execute_queue([t for t in checked['order'] if t not in INITIAL_IDS],initial_rows=checked['initial']['rows'],stage_functions=dict(comparison=comparison,independent_readback=independent),verify_sources=lambda:guard(sources),output=OUTPUT,validate_stage=validate_stage,resource_check=lambda:shutil.disk_usage(ROOT).free,context=dict(input_references=BOUND,source_hashes=deepcopy(sources),full_task_count=1632,full_new_cutoff_task_denominator=FULL,minimum_free_disk_bytes=MIN_FREE_BYTES,resource_gate_does_not_reduce_domain=True,**FLAGS))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
