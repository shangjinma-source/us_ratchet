"""Bounded original-shard worker: durable per-task records, no implicit retries."""
import argparse,hashlib,json,os,platform,shutil,sys,types,uuid
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/cash_topup_neighbor_shard_evaluation_20261003_v1'
PREP=ROOT/'data/cache/research/cash_topup_neighbor_preparation_20261003_v1'
ADAPTER=ROOT/'scripts/ndx_cash_topup_neighbor_single_evaluation_20261003.py';ADAPTER_SHA='6328a40a4c07f90b10b120ef348f924cf7cfa0dda9b12e63a80939e183c651ba'
JOURNAL=ROOT/'backtest/ndx_cash_topup_neighbor_journal_research.py';JOURNAL_SHA='d04eb2772432ed1fea291d699a25d4eeaac49b12aa228ee560d5d5613de8f637'
FIRST_ID='8b5320eb5ac613ddf6a69478f7e2360811688d1951b38c9e1d7b4ff34678febd'
FIRST_ROOT=ROOT/'data/cache/research/cash_topup_neighbor_evaluation_20261003_v1'/FIRST_ID
BOUND={
'preparation':(str(PREP/'preparation.json'),'04cf54101f56303cc656e60079f1434661845da6e13c6c7d23305f3e9f1dde2b'),
'publication':(str(PREP/'publication.json'),'dbe1e731c02293dab4a5cca4f0fa7fbf84367cd201dbf90b9e703cab1fd86b53'),
'audit':(str(ROOT/'data/cache/research/cash_topup_neighbor_preparation_independent_readback_20261003_v1/independent_readback.json'),'c29c98c5c48d61e2533c7a587291932eda3b5776d81a9d0288a75a6b7d891ce8'),
'first_started':(str(FIRST_ROOT/'started.json'),'b2d44ac6acff14561f325fa1b3fa859895e253475bd924c764a7eeba6766ff3a'),
'first_raw':(str(FIRST_ROOT/'raw.json'),'9dd01e5f9fc167f462c00c7858b89de51d540b810c0a2b5a3d0b18fc5d04719c'),
'first_postcheck':(str(FIRST_ROOT/'postcheck.json'),'7df4aa5f7285af105bcca01cafa2e132c0c0a3b15eca8bc0d7ae9b78615a0a57'),
'first_audit':(str(ROOT/'data/cache/research/cash_topup_neighbor_single_evaluation_independent_readback_20261003_v1'/FIRST_ID/'independent_readback.json'),'942edc8840a4ff81b273988663b8e3318e12453076ba4034ad1a26412368b411')}
PINS={
'evaluator':('backtest/ndx_explicit_cash_plan_evaluation_research.py','bc98beb6afdf04110c61857aef4b573a3840811076d729d4efc022d9b6523191'),
'kernel':('backtest/ndx_conditional_new_cash_fork_research.py','5bb17d621b42707cfe312676279d59b565c3e97900bf3bdd6f9335df65aa0c5f'),
'preparation_reader':('scripts/ndx_cash_topup_neighbor_preparation_independent_readback_20261003.py','483a11cbb1037ec9c30ff01ded864e883c2570110b0fe03660d209b3d2fe2f76'),
'original_score_semantics':('scripts/ndx_old_holding_topup_research_20261002.py','3898ab695053108742acc8e13d3fce7c81231f72d81d12c37156e07211c8723c'),
'first_reader':('scripts/ndx_cash_topup_neighbor_single_evaluation_independent_readback_20261003.py','0106433db9e123a3786a1656e495387b8c58a0c42019be50a113b4c311176140')}
MIN_FREE_BYTES=5*1024**3
FLAGS=dict.fromkeys(('fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed','full_integer_domain_exhausted','economic_winner_selected','target_weights_changed','holdings_sold','runtime_binary_closure_verified','continuous_source_monitoring_claimed','automatic_retry_allowed'),False)
def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(v):return sha(enc(v))
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def decode(b):
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'Duplicate key');d[k]=v
        return d
    def bad(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=bad)
def reference(p,h):return dict(path=str(p),sha256=h)
def save(path,value):
    b=enc(value)
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Durable exact bytes');return reference(path,sha(b))
def runtime():return dict(python=sys.version,implementation=platform.python_implementation(),executable=str(Path(sys.executable).resolve()),platform=platform.platform())
def guard(sources):
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Frozen source drift: '+p)
def load_module(path,h):
    b=path.read_bytes();require(sha(b)==h,'Private loaded bytes');m=types.ModuleType('_private_'+path.stem);m.__file__=str(path);exec(compile(b,str(path),'exec'),m.__dict__);return m

def load_common():
    sources={str(SOURCE):LOADED,str(ADAPTER):ADAPTER_SHA,str(JOURNAL):JOURNAL_SHA,**{str(ROOT/p):h for p,h in PINS.values()}};refs={k:reference(p,h) for k,(p,h) in BOUND.items()};docs={}
    for k,r in refs.items():b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed fixed parent');docs[k]=decode(b);sources[r['path']]=r['sha256']
    guard(sources);p=docs['preparation'];require(p['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_V1' and len(p['rows'])==40 and p['scenario_count']==40 and type(p['scenario_count']) is int,'All40 scenarios')
    exact(p['task_evaluation_count'],0,'Unevaluated preparation');require(p['declared_local_neighborhood_complete'] is True,'Complete local domain')
    require(docs['publication']['status']=='PUBLISHED_UNEVALUATED_CANDIDATES_ONLY' and docs['audit']['status']=='PASS','Successful external preparation')
    for key in ('publication','audit'):exact(docs[key]['preparation_reference'],refs['preparation'],'Preparation receipt')
    exact(docs['audit']['publication_reference'],refs['publication'],'Preparation audit publication');require(docs['audit']['reader_sha256']==PINS['preparation_reader'][1],'Preparation audit reader')
    a=docs['first_audit'];require(a['schema']=='CASH_TOPUP_SINGLE_EVALUATION_INDEPENDENT_READBACK_V1' and a['status']=='PASS' and a['task_id']==FIRST_ID and a['attempt_outcome'] in ('FEASIBLE','INFEASIBLE') and a['returned_arithmetic_independently_verified'] is True,'Only completed audited first task reused')
    require(a['reader_sha256']==PINS['first_reader'][1],'First reader source')
    for key in ('started','raw','postcheck'):exact(a[key+'_reference'],refs['first_'+key],'First complete references')
    exact(docs['first_postcheck']['raw_reference'],refs['first_raw'],'First raw link');exact(docs['first_raw']['started_reference'],refs['first_started'],'First start link')
    queue=[];position=0
    for i,row in enumerate(p['rows']):
        require(Path(row['contract_reference']['path'])==PREP/f'scenario-{i:02d}'/'contract.json','Scenario path');offset=0
        for j,s in enumerate(row['shards']):
            require(type(s['start']) is int and type(s['stop']) is int and s['start']==offset and 0<s['stop']-offset<=1000 and Path(s['path'])==PREP/f'scenario-{i:02d}'/f'tasks-{j:05d}.jsonl','Original contiguous shard')
            queue.append(dict(scenario_index=i,shard_index=j,global_shard_index=len(queue),global_task_start=position,global_task_stop=position+s['stop']-offset,shard=deepcopy(s),contract_reference=row['contract_reference']));position+=s['stop']-offset;offset=s['stop']
        exact(offset,row['statistics']['new_candidate_count'],'Complete scenario shard count')
    require(len(queue)==324 and position==301657,'Unchanged full original denominator')
    context=dict(schema='CASH_NEIGHBOR_SHARD_EXECUTION_CONTEXT_V1',input_references=refs,source_hashes=sources,scenario_count=40,shard_count=324,task_count=301657,new_call_count=301656,externally_referenced_task_id=FIRST_ID,runtime=runtime(),rule='ORIGINAL_PREPARATION_ORDER_ONE_EXPLICIT_CALL_PER_NEW_TASK',minimum_free_bytes=MIN_FREE_BYTES,**FLAGS)
    return dict(preparation=p,queue=queue,context=context,context_sha256=digest(context),sources=sources,refs=refs,first_started=docs['first_started'])

class _Journal:
    def __init__(self,path,core,context_hash):
        self.stream=path.open('xb');self.core=core;self.context_hash=context_hash;self.previous=core.ZERO;self.sequence=0;self.offset=0;self.index=[]
    def append(self,task,position,stage,payload):
        row=self.core.make_record(sequence=self.sequence,previous_hash=self.previous,context_sha256=self.context_hash,task_id=task['task_id'],task_position=position,stage=stage,payload=payload);b=enc(row)+b'\n';self.stream.write(b);self.stream.flush();os.fsync(self.stream.fileno())
        self.index.append(dict(sequence=self.sequence,byte_start=self.offset,byte_stop=self.offset+len(b),record_sha256=row['record_sha256'],task_id=task['task_id'],stage=stage));self.offset+=len(b);self.sequence+=1;self.previous=row['record_sha256'];return row['record_sha256']
    def close(self):self.stream.close()

def _process_shard(*,folder,tasks,prepared,descriptor,context_hash,adapter,evaluate,journal_core,verify,external):
    # Private implementation; public APIs construct all callables from fixed code bytes.
    folder.mkdir(exist_ok=False);ids=[t['task_id'] for t in tasks];require(len(ids)==len(set(ids)),'Unique bounded task IDs')
    start=save(folder/'started.json',dict(schema='CASH_NEIGHBOR_SHARD_STARTED_V1',descriptor=descriptor,context_sha256=context_hash,ordered_task_ids=ids,contract_sha256=prepared['contract_sha256'],**FLAGS));writer=_Journal(folder/'journal.jsonl',journal_core,context_hash);terminal=[];error=None
    try:
        for pos,task in enumerate(tasks):
            # Source task validation happens before recording dispatch.
            adapter.validate_task(prepared,task,task['task_id'])
            if task['task_id'] in external:
                writer.append(task,pos,'EXTERNAL_REFERENCE',external[task['task_id']]);terminal.append(dict(task_id=task['task_id'],outcome='EXTERNALLY_REFERENCED'));continue
            require(not (ROOT/'data/cache/research/cash_topup_neighbor_evaluation_20261003_v1'/task['task_id']).exists(),'Prior individual attempt exists; never redispatch')
            arguments=adapter.evaluation_arguments(prepared,task)
            writer.append(task,pos,'TASK_STARTED',dict(task_reference=dict(reference(descriptor['shard']['path'],descriptor['shard']['sha256']),jsonl_line_index=pos,scenario_candidate_ordinal=task['scenario_candidate_ordinal']),global_task_position=descriptor['global_task_start']+pos,evaluation_argument_sha256=digest(arguments)))
            result=None;exception=None
            try:result=evaluate(**arguments)
            except Exception as e:exception=dict(type=type(e).__name__,message=str(e))
            writer.append(task,pos,'RAW_EXCEPTION' if exception else 'RAW_RETURNED',dict(result=result,error=exception,explicit_evaluator_call_attempt_count=1,returned_evaluation_count=int(exception is None)))
            validation=None
            if exception:detail=dict(outcome='EVALUATION_EXCEPTION',original_target_stock_weight_l1=None,score_absence_reason='NO_RETURNED_EVALUATION')
            else:
                try:detail=adapter.inspect_return(prepared,task,result)
                except Exception as e:validation=dict(type=type(e).__name__,message=str(e));detail=dict(outcome='VALIDATION_FAILURE',original_target_stock_weight_l1=None,score_absence_reason='UNACCEPTED_RETURNED_EVALUATION')
            writer.append(task,pos,'POSTCHECK',dict(**detail,evaluation_error=exception,validation_error=validation));terminal.append(dict(task_id=task['task_id'],**detail))
            if detail['outcome'] in ('EVALUATION_EXCEPTION','VALIDATION_FAILURE'):raise RuntimeError('Technical failure: stop without retry')
        writer.close();verify();raw=(folder/'journal.jsonl').read_bytes();scan=journal_core.inspect_journal(raw,context_sha256=context_hash,ordered_task_ids=ids);require(scan['complete'],'Only complete shard accepted');exact(scan['records'],writer.index,'Durable full record offsets')
        counts={k:sum(t['outcome']==k for t in terminal) for k in ('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE','EXTERNALLY_REFERENCED')}
        completion=dict(schema='CASH_NEIGHBOR_SHARD_COMPLETION_V1',status='COMPLETE_SAVED_DIAGNOSTICS_NOT_INDEPENDENTLY_AUDITED',started_reference=start,context_sha256=context_hash,descriptor=descriptor,journal_reference=reference(folder/'journal.jsonl',sha(raw)),record_index=writer.index,record_count=len(writer.index),terminal_record_sha256=writer.previous,task_count=len(ids),outcome_counts=counts,new_evaluator_call_count=len(ids)-counts['EXTERNALLY_REFERENCED'],unresolved_dispatch_count=0,undispatched_count=0,**FLAGS)
        ref=save(folder/'completion.json',completion);verify();require({p.name for p in folder.iterdir()}=={'started.json','journal.jsonl','completion.json'},'Exact completed shard files');return ref
    except Exception as e:
        writer.close();raw=(folder/'journal.jsonl').read_bytes()
        try:scan=journal_core.inspect_journal(raw,context_sha256=context_hash,ordered_task_ids=ids)
        except Exception as recovery_error:scan=dict(status='CORRUPT_JOURNAL_REQUIRES_MANUAL_REVIEW',journal_sha256=sha(raw),error=str(recovery_error),no_dispatch_retry_allowed=True)
        save(folder/'failure.json',dict(status='STOPPED_SHARD_DO_NOT_RETRY',error_type=type(e).__name__,error=str(e),context_sha256=context_hash,recovery=scan,**FLAGS));raise

def _verify_completed(folder,descriptor,context_hash,ids,journal_core,external_reference,expected_contract_sha256):
    require({p.name for p in folder.iterdir()}=={'started.json','journal.jsonl','completion.json'},'Existing shard incomplete or failed; do not retry')
    path=folder/'completion.json';b=path.read_bytes();v=decode(b);require(v['schema']=='CASH_NEIGHBOR_SHARD_COMPLETION_V1' and v['status']=='COMPLETE_SAVED_DIAGNOSTICS_NOT_INDEPENDENTLY_AUDITED','Completed shard only');exact(v['descriptor'],descriptor,'Original shard position');require(v['context_sha256']==context_hash,'Frozen batch context')
    sr=v['started_reference'];require(Path(sr['path'])==folder/'started.json' and sha((folder/'started.json').read_bytes())==sr['sha256'],'Started bytes');start=decode((folder/'started.json').read_bytes());exact(start['ordered_task_ids'],ids,'Original full task order')
    raw=(folder/'journal.jsonl').read_bytes();exact(v['journal_reference'],reference(folder/'journal.jsonl',sha(raw)),'Saved journal digest');scan=journal_core.inspect_journal(raw,context_sha256=context_hash,ordered_task_ids=ids);require(scan['complete'],'Complete old journal only');exact(v['record_index'],scan['records'],'All persisted byte indexes');require(v['terminal_record_sha256']==scan['last_record_sha256'],'Terminal chain')
    require(all(t['status'] in ('FEASIBLE','INFEASIBLE','EXTERNALLY_REFERENCED') for t in scan['tasks']),'Technical failure shard cannot be accepted')
    rows=[decode(line) for line in raw.splitlines()]
    for record in rows:
        if record['stage']=='EXTERNAL_REFERENCE':
            require(record['task_id']==FIRST_ID and record['task_position']==0 and descriptor['global_task_start']==0,'Only stable original first task can be external')
            exact(record['payload'],external_reference,'Exact four first-result references')
    counts={k:sum(t['status']==k for t in scan['tasks']) for k in ('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE','EXTERNALLY_REFERENCED')}
    require(counts['EXTERNALLY_REFERENCED']==int(FIRST_ID in ids),'First task must be external, never reevaluated')
    exact(v['outcome_counts'],counts,'Saved terminal partition');exact(v['task_count'],len(ids),'All task count');exact(v['new_evaluator_call_count'],len(ids)-counts['EXTERNALLY_REFERENCED'],'Actual new calls');exact(v['record_count'],len(scan['records']),'Record count');exact(v['unresolved_dispatch_count'],0,'No unresolved');exact(v['undispatched_count'],0,'No undispatched')
    exact(start['contract_sha256'],expected_contract_sha256,'Started original contract');exact(start['descriptor'],descriptor,'Started descriptor');require(start['context_sha256']==context_hash,'Started context')
    for obj in (start,v):
        for k in FLAGS:require(obj[k] is False,'Completed scope')
    return reference(path,sha(b))

def run_batch(*,execute=False,max_shards=None,prior_run_reference=None):
    require(type(execute) is bool and execute,'Explicit new batch action');require(max_shards is None or type(max_shards) is int and 1<=max_shards<=324,'Engineering shard-run bound, no domain deletion')
    common=load_common();context=common['context'];context_hash=common['context_sha256'];guard(common['sources'])
    reused_refs={}
    if OUTPUT.exists():
        require(type(prior_run_reference) is dict and set(prior_run_reference)=={'path','sha256'},'Explicit prior run external anchor required')
        prior_path=Path(prior_run_reference['path']);require(prior_path.parent.parent==OUTPUT and prior_path.name=='result.json','Fixed prior run path');require({p.name for p in prior_path.parent.iterdir()}=={'started.json','result.json'},'Prior run failure or unknown residue blocks continuation')
        prior_bytes=prior_path.read_bytes();require(sha(prior_bytes)==prior_run_reference['sha256'],'External prior run bytes');prior=decode(prior_bytes)
        request_ref=prior['request_started_reference'];require(Path(request_ref['path'])==prior_path.parent/'started.json','Original request path');request_raw=Path(request_ref['path']).read_bytes();require(sha(request_raw)==request_ref['sha256'],'Externally linked request bytes');original_request=decode(request_raw)
        require(original_request['context_sha256']==context_hash and type(original_request['full_shard_count']) is int and original_request['full_shard_count']==324 and type(original_request['full_task_count']) is int and original_request['full_task_count']==301657,'Original request scope')
        limit=original_request['max_new_shards'];require(limit is None or type(limit) is int and 1<=limit<=324,'Original engineering request')
        for k in FLAGS:require(original_request[k] is False,'Original request flags')
        require(prior['schema']=='CASH_NEIGHBOR_SHARD_BATCH_RUN_V1' and prior['context_sha256']==context_hash,'Original prior run context')
        require(prior['failure'] is None or prior['failure']['status'] in ('ENGINEERING_RUN_BOUND_BEFORE_DISPATCH','RESOURCE_STOP_BEFORE_DISPATCH'),'Technical stop requires separate reviewed recovery, no automatic continuation')
        reused_refs={r['path']:r['sha256'] for r in prior['completed_shard_references']};require(len(reused_refs)==len(prior['completed_shard_references']),'Unique prior completions')
        start_bytes=(OUTPUT/'started.json').read_bytes();exact(prior['batch_started_reference'],reference(OUTPUT/'started.json',sha(start_bytes)),'Original started external link');exact(decode(start_bytes),dict(context=context,context_sha256=context_hash),'Existing original context')
        batch_started=prior['batch_started_reference']
    else:
        require(prior_run_reference is None,'No prior run in new namespace');OUTPUT.mkdir(parents=True,exist_ok=False);batch_started=save(OUTPUT/'started.json',dict(context=context,context_sha256=context_hash))
    request=OUTPUT/('request-'+uuid.uuid4().hex);request.mkdir(exist_ok=False);request_started=save(request/'started.json',dict(context_sha256=context_hash,max_new_shards=max_shards,full_shard_count=324,full_task_count=301657,**FLAGS))
    loaded_runtime=runtime();accepted=[];new_count=0;failure=None;current=None;counts=dict.fromkeys(('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE','EXTERNALLY_REFERENCED','UNRESOLVED_DISPATCH'),0);partial_recovery=None;counts['EXTERNALLY_REFERENCED']=1
    prepared_cache={};contract_sources={}
    try:
        adapter=load_module(ADAPTER,ADAPTER_SHA);journal_core=load_module(JOURNAL,JOURNAL_SHA);evaluate=adapter.fresh_evaluator()
        for descriptor in common['queue']:
            current=descriptor;i=descriptor['scenario_index'];j=descriptor['shard_index'];folder=OUTPUT/f'scenario-{i:02d}-shard-{j:05d}'
            if i not in prepared_cache:
                cr=descriptor['contract_reference'];b=Path(cr['path']).read_bytes();require(sha(b)==cr['sha256'],'Consumed scenario contract');prepared_cache={i:decode(b)};contract_sources={cr['path']:cr['sha256']}
            prepared=prepared_cache[i];s=descriptor['shard'];blob=Path(s['path']).read_bytes();require(sha(blob)==s['sha256'],'Consumed original shard');tasks=[decode(line) for line in blob.splitlines()];require(len(tasks)==s['stop']-s['start'],'Full original shard')
            for pos,t in enumerate(tasks):require(type(t['scenario_candidate_ordinal']) is int and t['scenario_candidate_ordinal']==s['start']+pos,'Original task ordinal');adapter.validate_task(prepared,t,t['task_id'])
            ids=[t['task_id'] for t in tasks];require(len(ids)==len(set(ids)),'Unique shard ids');local_sources={**common['sources'],**contract_sources,s['path']:s['sha256']}
            def verify():guard(local_sources);exact(runtime(),loaded_runtime,'Runtime changed')
            verify()
            if folder.exists():
                cp=folder/'completion.json';require(str(cp) in reused_refs and cp.is_file() and sha(cp.read_bytes())==reused_refs[str(cp)],'Existing completion needs exact external prior reference')
                accepted.append(_verify_completed(folder,descriptor,context_hash,ids,journal_core,{k:common['refs'][k] for k in ('first_started','first_raw','first_postcheck','first_audit')},prepared['contract_sha256']))
                old_completion=decode(Path(accepted[-1]['path']).read_bytes())
                for k,v in old_completion['outcome_counts'].items():
                    if k!='EXTERNALLY_REFERENCED':counts[k]+=v
                continue
            if max_shards is not None and new_count>=max_shards:failure=dict(status='ENGINEERING_RUN_BOUND_BEFORE_DISPATCH',next_global_shard_index=descriptor['global_shard_index']);break
            free=shutil.disk_usage(OUTPUT).free;require(type(free) is int and free>=0,'Disk resource measurement')
            if free<MIN_FREE_BYTES:failure=dict(status='RESOURCE_STOP_BEFORE_DISPATCH',free_bytes=free,minimum_free_bytes=MIN_FREE_BYTES,next_global_shard_index=descriptor['global_shard_index']);break
            external={}
            if descriptor['global_shard_index']==0:
                require(ids[0]==FIRST_ID,'Original first position');exact(common['first_started']['task'],tasks[0],'Same complete externally audited task');exact(common['first_started']['original_contract'],prepared,'Same external contract');external[FIRST_ID]={k:common['refs'][k] for k in ('first_started','first_raw','first_postcheck','first_audit')}
            else:require(FIRST_ID not in ids,'First reference cannot recur')
            accepted.append(_process_shard(folder=folder,tasks=tasks,prepared=prepared,descriptor=descriptor,context_hash=context_hash,adapter=adapter,evaluate=evaluate,journal_core=journal_core,verify=verify,external=external));new_count+=1
            completed=decode(Path(accepted[-1]['path']).read_bytes())
            for k,v in completed['outcome_counts'].items():
                if k!='EXTERNALLY_REFERENCED':counts[k]+=v
            print(json.dumps(dict(completed_shards=len(accepted),full_shard_count=324,last_global_shard_index=descriptor['global_shard_index'])),flush=True)
    except Exception as e:
        failure=dict(status='STOPPED_NO_AUTOMATIC_RETRY',error_type=type(e).__name__,error=str(e),current_shard=deepcopy(current))
        if current is not None and 'folder' in locals() and (folder/'journal.jsonl').exists():
            raw=(folder/'journal.jsonl').read_bytes()
            try:
                partial_recovery=journal_core.inspect_journal(raw,context_sha256=context_hash,ordered_task_ids=ids)
                for task in partial_recovery['tasks']:
                    k=task['status']
                    if task['task_id']!=FIRST_ID:counts[k if k in counts else 'UNRESOLVED_DISPATCH']+=1
                if partial_recovery['tail'] is not None and len(partial_recovery['tasks'])<len(ids) and (not partial_recovery['tasks'] or partial_recovery['tasks'][-1]['status'] in ('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE','EXTERNALLY_REFERENCED')):
                    if ids[len(partial_recovery['tasks'])]!=FIRST_ID:counts['UNRESOLVED_DISPATCH']+=1
                    partial_recovery['conservatively_unresolved_partial_tail_task_id']=ids[len(partial_recovery['tasks'])]
            except Exception as scan_error:
                partial_recovery=dict(status='CORRUPT_JOURNAL_REQUIRES_MANUAL_REVIEW',journal_sha256=sha(raw),error=str(scan_error));failure['partition_unknown_for_current_shard']=True
    counts['UNDISPATCHED']=301657-sum(counts.values())
    if failure and failure.get('partition_unknown_for_current_shard'):
        unknown_count=current['global_task_stop']-current['global_task_start']-int(current['global_task_start']==0);counts['UNRESOLVED_DISPATCH']+=unknown_count;counts['UNDISPATCHED']-=unknown_count
    result=dict(schema='CASH_NEIGHBOR_SHARD_BATCH_RUN_V1',request_started_reference=request_started,batch_started_reference=batch_started,prior_run_reference=prior_run_reference,status='COMPLETE' if len(accepted)==324 and failure is None else 'STOPPED',context_sha256=context_hash,full_shard_count=324,full_task_count=301657,completed_shard_references=accepted,new_completed_shard_count=new_count,accepted_task_count=sum(common['queue'][i]['global_task_stop']-common['queue'][i]['global_task_start'] for i in range(len(accepted))),remaining_shard_descriptors=common['queue'][len(accepted):],failure=failure,outcome_counts=counts,known_externally_completed_task_count=1,actual_new_undispatched_task_count=counts['UNDISPATCHED'],partition_includes_external_first_even_before_its_shard_is_referenced=True,partial_shard_recovery=partial_recovery,whole_batch_status_is_partition_not_feasibility=True,remaining_scope_includes_unresolved_failed_shard=failure is not None and failure['status']=='STOPPED_NO_AUTOMATIC_RETRY',**FLAGS)
    try:
        answer=save(request/'result.json',result);guard(common['sources']);require(Path(answer['path']).read_bytes()==enc(result),'Final result bytes');require({p.name for p in request.iterdir()}=={'started.json','result.json'},'Exact successful request files');return answer
    except Exception as e:
        if not (request/'failure.json').exists():save(request/'failure.json',dict(status='FAILED_RUN_RESULT_DO_NOT_CONSUME_OR_CONTINUE',error_type=type(e).__name__,error=str(e),**FLAGS))
        raise
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--max-shards',type=int);p.add_argument('--prior-run-path');p.add_argument('--prior-run-sha');a=p.parse_args();print(json.dumps(run_batch(execute=a.execute,max_shards=a.max_shards,prior_run_reference=reference(a.prior_run_path,a.prior_run_sha) if a.prior_run_path else None)))
