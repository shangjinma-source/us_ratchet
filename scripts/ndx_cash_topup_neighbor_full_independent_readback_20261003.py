"""Immutable per-shard saved arithmetic audits; never calls a production evaluator."""
import argparse,hashlib,json,os,re,types,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/cash_topup_neighbor_full_independent_readback_20261003_v1'
BATCH=ROOT/'data/cache/research/cash_topup_neighbor_shard_evaluation_20261003_v1'
RESULT_PATH=None
RESULT_SHA=None
REQUEST_SHA=None
HELPER=ROOT/'scripts/ndx_cash_topup_neighbor_shard_independent_readback_20261003.py'
HELPER_SHA='39a7194291584195eed09d2b1e2d83f97cd9b53a20bd4858e192fd4ba4d728ad'
FIRST_REPORT=ROOT/'data/cache/research/cash_topup_neighbor_shard_independent_readback_20261003_v1/15d9742bec44074dc09d8c23fee12bff0b9a096618f86c9cf809abb96fc138ff/shard-00000/independent_readback.json'
FIRST_REPORT_SHA='9a17d90a72406a56313d5d6cab4d1cf807f65a80dd492cec17bf196879a34ba5'
FLAGS=dict.fromkeys(('producer_called','evaluator_called','fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed','full_integer_domain_exhausted','economic_winner_selected','old_audits_reexecuted','existing_first_arithmetic_recomputed','automatic_retry_allowed'),False)

def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(v):return sha(enc(v))
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def reference(p,h):return dict(path=str(p),sha256=h)
def integer(v):require(type(v) is int and v>=0,'Nonboolean count');return v
def decode(b):
    def pairs(xs):
        d={}
        for k,v in xs:require(k not in d,'Duplicate key');d[k]=v
        return d
    def bad(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=bad)
def read(ref,sources):
    require(type(ref) is dict and set(ref)=={'path','sha256'} and type(ref['path']) is str and type(ref['sha256']) is str and re.fullmatch('[a-f0-9]{64}',ref['sha256']),'External exact reference')
    p=ref['path'];h=ref['sha256'];require(p not in sources or sources[p]==h,'Conflicting reference')
    b=Path(p).read_bytes();require(sha(b)==h,'Consumed bytes hash');sources[p]=h;return b
def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED,'Loaded source changed')
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Source drift '+p)
def save(path,value):
    b=enc(value)
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Saved bytes');return reference(path,sha(b))
def fresh_helper():
    b=HELPER.read_bytes();require(sha(b)==HELPER_SHA,'Frozen independent helper')
    m=types.ModuleType('_cash_independent_shard_arithmetic');m.__file__=str(HELPER)
    exec(compile(b,str(HELPER),'exec'),m.__dict__)
    return m

def validate_partition(result,request,batch,queue,expected_context):
    exact(batch['context'],expected_context,'Fixed producer context');ch=digest(expected_context)
    exact(batch['context_sha256'],ch,'Context digest');require(result['context_sha256']==request['context_sha256']==ch,'Request context')
    require(result['schema']=='CASH_NEIGHBOR_SHARD_BATCH_RUN_V1' and result['status']=='COMPLETE','All production shards must be terminal complete')
    for obj in (result,request):
        for k in expected_context:
            if k in ('fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed','full_integer_domain_exhausted','economic_winner_selected','target_weights_changed','holdings_sold','runtime_binary_closure_verified','continuous_source_monitoring_claimed','automatic_retry_allowed'):require(obj[k] is False,'Producer flags')
        exact(obj['full_shard_count'],324,'324 shard denominator');exact(obj['full_task_count'],301657,'301657 tasks')
    limit=request['max_new_shards'];require(limit is None or type(limit) is int and 1<=limit<=324,'Engineering bound')
    require(result['failure'] is None and result['partial_shard_recovery'] is None,'Partial/technical run not complete')
    exact(result['remaining_shard_descriptors'],[],'No omitted domain');exact(result['accepted_task_count'],301657,'Whole accepted saved tasks')
    exact(result['known_externally_completed_task_count'],1,'Original external only');exact(result['actual_new_undispatched_task_count'],0,'No undispatched')
    require(result['partition_includes_external_first_even_before_its_shard_is_referenced'] is True and result['whole_batch_status_is_partition_not_feasibility'] is True,'Partition interpretation')
    require(result['remaining_scope_includes_unresolved_failed_shard'] is False,'No unresolved scope')
    cs=result['completed_shard_references'];require(type(cs) is list and len(cs)==len(queue)==324 and len({r['path'] for r in cs})==324,'324 unique complete refs')
    for r,d in zip(cs,queue):require(Path(r['path'])==BATCH/f'scenario-{d["scenario_index"]:02d}-shard-{d["shard_index"]:05d}'/'completion.json','Ordered complete shard paths')
    counts=result['outcome_counts'];require(set(counts)=={'FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE','EXTERNALLY_REFERENCED','UNRESOLVED_DISPATCH','UNDISPATCHED'},'All outcome partitions')
    require(sum(integer(v) for v in counts.values())==301657,'Whole task sum')
    for k,n in dict(EXTERNALLY_REFERENCED=1,EVALUATION_EXCEPTION=0,VALIDATION_FAILURE=0,UNRESOLVED_DISPATCH=0,UNDISPATCHED=0).items():exact(counts[k],n,'Complete nontechnical partition')
    return ch

def validate_first(first,queue,completion_reference,helper):
    require(first['schema']=='CASH_NEIGHBOR_SHARD_INDEPENDENT_READBACK_V1' and first['status']=='PASS' and first['reader_sha256']==HELPER_SHA,'Previously audited first shard')
    exact(first['global_shard_index'],0,'First only');exact(first['descriptor'],queue[0],'Same preparation first descriptor');exact(first['completion_reference'],completion_reference,'Same actual first completion')
    require(first['all_completed_prefix_arithmetic_checked_in_this_report'] is True and first['existing_first_arithmetic_recomputed'] is False,'Existing audit scope')
    for k in helper.FALSE:require(first[k] is False,'Preserved first limitations')
    exact(first['task_count'],532,'First original task count');exact(first['new_arithmetic_checked_count'],531,'Previously audited new531')
    exact(first['outcome_counts'],dict(FEASIBLE=98,INFEASIBLE=433,EVALUATION_EXCEPTION=0,VALIDATION_FAILURE=0,EXTERNALLY_REFERENCED=1),'First saved audit partition')
    require(len(first['task_results'])==532 and len({t['task_id'] for t in first['task_results']})==532,'First audit task identity set')
    require(first['task_results'][0]['task_id']==helper.FIRST_ID,'First external task')

def compact_detail(detail):
    # Retain exact per-task identity/outcome/score in each bounded audit; do not retain source raw objects.
    return {k:detail[k] for k in ('task_count','new_arithmetic_checked_count','outcome_counts','task_results','record_count','journal_sha256')}

def validate_reused(report,index,context,result_ref,descriptor,completion_ref):
    require(report['schema']=='CASH_NEIGHBOR_FULL_AUDIT_SHARD_V1' and report['status']=='PASS' and report['reader_sha256']==LOADED,'Explicit reused audit code/success')
    exact(report['global_shard_index'],index,'Reused ordinal');exact(report['audit_context_sha256'],context,'Reused audit context')
    exact(report['result_reference'],result_ref,'Same final run');exact(report['descriptor'],descriptor,'Same original descriptor');exact(report['completion_reference'],completion_ref,'Same completion')
    for k in FLAGS:require(report[k] is False,'No authority upgrade')
    detail=report['detail'];n=descriptor['global_task_stop']-descriptor['global_task_start']
    exact(detail['task_count'],n,'Full reused task count');exact(detail['new_arithmetic_checked_count'],n,'All reused nonfirst new arithmetic')
    require(len(detail['task_results'])==n and len({r['task_id'] for r in detail['task_results']})==n,'Unique audited tasks')
    observed=dict(FEASIBLE=0,INFEASIBLE=0,EVALUATION_EXCEPTION=0,VALIDATION_FAILURE=0,EXTERNALLY_REFERENCED=0)
    for t in detail['task_results']:
        require(t['outcome'] in ('FEASIBLE','INFEASIBLE') and t['new_arithmetic_checked'] is True,'Complete new arithmetic outcome');observed[t['outcome']]+=1
    exact(detail['outcome_counts'],observed,'Reused task outcome partition')
    return detail

def validate_reused_metadata(report,*,completion,started,prepared,tasks,descriptor,expected_sources,execution_context_sha256):
    exact(report['source_hashes'],expected_sources,'Independently constructed reused source closure')
    exact(report['journal_reference'],completion['journal_reference'],'Reused journal reference')
    exact(report['started_reference'],completion['started_reference'],'Reused started reference')
    require(completion['schema']=='CASH_NEIGHBOR_SHARD_COMPLETION_V1' and completion['status']=='COMPLETE_SAVED_DIAGNOSTICS_NOT_INDEPENDENTLY_AUDITED','Saved complete source')
    require(started['schema']=='CASH_NEIGHBOR_SHARD_STARTED_V1','Saved shard start')
    for obj in (completion,started):
        exact(obj['descriptor'],descriptor,'Original reused descriptor');exact(obj['context_sha256'],execution_context_sha256,'Reused execution context')
    require(digest(prepared['contract'])==prepared['contract_sha256'],'Full prepared contract hash')
    exact(started['contract_sha256'],prepared['contract_sha256'],'Original reused contract')
    ids=[t['task_id'] for t in tasks]
    require(len(ids)==len(set(ids))==descriptor['global_task_stop']-descriptor['global_task_start'],'Prepared task cardinality')
    for offset,task in enumerate(tasks):
        require(digest(task['identity'])==task['task_id'],'Prepared numerical task identity')
        exact(task['identity']['scenario_contract_sha256'],prepared['contract_sha256'],'Prepared task contract')
        exact(task['scenario_candidate_ordinal'],descriptor['shard']['start']+offset,'Prepared ordered position')
    exact(started['ordered_task_ids'],ids,'Started ordered prepared IDs')
    exact([t['task_id'] for t in report['detail']['task_results']],ids,'Audited exact prepared task order')
    for key in ('task_count','new_arithmetic_checked_count'):
        exact(report['detail'][key],len(ids),'Reused full new task count')
    exact(completion['task_count'],len(ids),'Producer complete task count')
    exact(completion['outcome_counts'],report['detail']['outcome_counts'],'Reused audited outcome totals')
    exact(completion['new_evaluator_call_count'],len(ids),'Reused producer calls')
    exact(completion['record_count'],report['detail']['record_count'],'Reused record count')
    exact(completion['journal_reference']['sha256'],report['detail']['journal_sha256'],'Reused journal bytes')

def validate_request_link(result,request,prior_prefix):
    producer_flags={'fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed','full_integer_domain_exhausted','economic_winner_selected','target_weights_changed','holdings_sold','runtime_binary_closure_verified','continuous_source_monitoring_claimed','automatic_retry_allowed'}
    require(set(request)=={'context_sha256','max_new_shards','full_shard_count','full_task_count'}|producer_flags,'Exact frozen schemaless request fields')
    for k in producer_flags:require(request[k] is False,'Request limitations')
    exact(request['context_sha256'],result['context_sha256'],'Request/result context link')
    exact(request['full_shard_count'],324,'Request full shards');exact(request['full_task_count'],301657,'Request full tasks')
    require(type(result['new_completed_shard_count']) is int and result['new_completed_shard_count']>=0,'Exact newly completed count')
    exact(result['new_completed_shard_count'],len(result['completed_shard_references'])-prior_prefix,'New count versus prior prefix')
    limit=request['max_new_shards'];require(limit is None or type(limit) is int and 1<=limit<=324,'Exact request bound')
    require(limit is None or result['new_completed_shard_count']<=limit,'New completions within request limit')

def aggregate(details,expected_counts):
    require(len(details)==324 and set(details)==set(range(324)),'All324 audits required')
    ids=set();counts=dict(FEASIBLE=0,INFEASIBLE=0,EVALUATION_EXCEPTION=0,VALIDATION_FAILURE=0,EXTERNALLY_REFERENCED=0);total=0;new=0
    for i in range(324):
        d=details[i];total+=integer(d['task_count']);new+=integer(d['new_arithmetic_checked_count'])
        require(len(d['task_results'])==d['task_count'],'Full audit identities')
        for t in d['task_results']:require(t['task_id'] not in ids,'No cross-shard repeated task');ids.add(t['task_id'])
        for k in counts:counts[k]+=integer(d['outcome_counts'][k])
    exact(total,301657,'Full distinct declared neighborhood');exact(new,301656,'First old point excluded from arithmetic');exact(len(ids),total,'Unique task total')
    exact({**counts,'UNRESOLVED_DISPATCH':0,'UNDISPATCHED':0},expected_counts,'Whole independently reconciled outcomes')
    return dict(task_count=total,new_arithmetic_checked_total_including_previously_audited_first=new,previously_audited_new_task_count=531,new_tasks_independently_checked_by_this_entry=301125,external_original_single_task_count=1,outcome_counts=counts,ordered_shard_count=324)
def run(*,result_reference,completed_audit_references=(),max_shards=None,execute=False):
    require(execute is True and RESULT_PATH is not None and RESULT_SHA is not None and REQUEST_SHA is not None,'Future actual anchors pending')
    exact(result_reference,reference(RESULT_PATH,RESULT_SHA),'Explicit final result anchor')
    require(max_shards is None or type(max_shards) is int and 1<=max_shards<=323,'Audit engineering limit')
    helper=fresh_helper();base={str(SOURCE):LOADED,str(HELPER):HELPER_SHA,**helper.producer_sources()};guard(base)
    refs={k:reference(p,h) for k,(p,h) in helper.BOUND.items()};sources=dict(base)
    # Hash-bound existing evidence is consumed, not its producer or old audit entrypoint.
    prep=decode(read(refs['preparation'],sources));pub=decode(read(refs['publication'],sources));pa=decode(read(refs['audit'],sources))
    require(pub['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_PUBLICATION_V1' and pub['status']=='PUBLISHED_UNEVALUATED_CANDIDATES_ONLY','Preparation published')
    require(pa['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_INDEPENDENT_READBACK_V1' and pa['status']=='PASS' and pa['reader_sha256']==helper.PINS['preparation_reader'][1],'Preparation independently read back')
    for d in (pub,pa):exact(d['preparation_reference'],refs['preparation'],'Preparation link')
    exact(pa['publication_reference'],refs['publication'],'Audit receipt');exact(pub['source_hashes'],prep['source_hashes'],'Original preparation sources')
    require(not (helper.PREP/'failure.json').exists(),'Failed preparation')
    queue=helper.queue_from_preparation(prep);result=decode(read(result_reference,sources));request_dir=Path(result_reference['path']).parent
    require(request_dir.parent==BATCH and request_dir.name.startswith('request-') and Path(result_reference['path']).name=='result.json','Fixed batch request path')
    require({p.name for p in request_dir.iterdir()}=={'started.json','result.json'},'Successful final request')
    rr=reference(request_dir/'started.json',REQUEST_SHA);exact(result['request_started_reference'],rr,'External request-start anchor');request=decode(read(rr,sources))
    br=result['batch_started_reference'];require(Path(br['path'])==BATCH/'started.json','Batch start path');batch=decode(read(br,sources));ctx=batch['context']
    require(type(ctx['runtime']) is dict and set(ctx['runtime'])=={'python','implementation','executable','platform'} and all(type(v) is str and v for v in ctx['runtime'].values()),'Recorded runtime only')
    expected=dict(schema='CASH_NEIGHBOR_SHARD_EXECUTION_CONTEXT_V1',input_references=refs,source_hashes=helper.producer_sources(),scenario_count=40,shard_count=324,task_count=301657,new_call_count=301656,externally_referenced_task_id=helper.FIRST_ID,runtime=ctx['runtime'],rule='ORIGINAL_PREPARATION_ORDER_ONE_EXPLICIT_CALL_PER_NEW_TASK',minimum_free_bytes=5*1024**3,**dict.fromkeys(helper.FALSE,False))
    ch=validate_partition(result,request,batch,queue,expected)
    first_ref=reference(FIRST_REPORT,FIRST_REPORT_SHA);first=decode(read(first_ref,sources));validate_first(first,queue,result['completed_shard_references'][0],helper)
    require(first['source_hashes'].get(str(HELPER))==HELPER_SHA,'First audited reader source')
    # Follow immutable request ancestry once; never infer the number of new shards from a claim.
    current=result;current_request=request;current_ref=result_reference;seen={result_reference['path']};prior_prefix=324
    while current['prior_run_reference'] is not None:
        pr=current['prior_run_reference'];require(pr['path'] not in seen,'Cyclic request ancestry');seen.add(pr['path'])
        prior=decode(read(pr,sources));pd=Path(pr['path']).parent
        require(pd.parent==BATCH and pd.name.startswith('request-') and Path(pr['path']).name=='result.json' and {x.name for x in pd.iterdir()}=={'started.json','result.json'},'Successful prior request namespace')
        require(prior['schema']=='CASH_NEIGHBOR_SHARD_BATCH_RUN_V1' and prior['context_sha256']==ch and prior['partial_shard_recovery'] is None,'Prior same execution context')
        require(prior['status']=='STOPPED' and prior['failure']['status'] in ('ENGINEERING_RUN_BOUND_BEFORE_DISPATCH','RESOURCE_STOP_BEFORE_DISPATCH'),'Only before-dispatch prior stop')
        n=len(prior['completed_shard_references']);require(n<=prior_prefix,'Monotone complete prefix')
        exact(prior['completed_shard_references'],result['completed_shard_references'][:n],'Same complete prefix ancestry')
        exact(prior['remaining_shard_descriptors'],queue[n:],'Prior whole remaining domain')
        validate_request_link(current,current_request,n)
        exact(prior['batch_started_reference'],result['batch_started_reference'],'Same batch-start reference through ancestry')
        prq=prior['request_started_reference'];require(Path(prq['path'])==pd/'started.json','Prior request start path');prqs=decode(read(prq,sources))
        require(prqs['context_sha256']==ch,'Prior request context')
        for obj in (prior,prqs):
            helper.flags(obj);exact(obj['full_shard_count'],324,'Prior full shards');exact(obj['full_task_count'],301657,'Prior full tasks')
        if pr==first['result_reference']:exact(prq,first['request_started_reference'],'First independently audited request anchor')
        current=prior;current_request=prqs;current_ref=pr;prior_prefix=n
    validate_request_link(current,current_request,0)
    exact(current_ref,first['result_reference'],'Initial request is externally audited first run')
    # Anchor the first completion only; do not open/recompute its journal.
    first_completion=decode(read(result['completed_shard_references'][0],sources));exact(first_completion['descriptor'],queue[0],'First completion descriptor');exact(first_completion['journal_reference'],first['journal_reference'],'First saved journal reference');exact(first_completion['started_reference'],first['started_reference'],'First saved start reference')
    exact(first_completion['context_sha256'],ch,'First belongs to same execution context');exact(first_completion['outcome_counts'],first['outcome_counts'],'First externally audited outcomes')
    context=dict(schema='CASH_NEIGHBOR_FULL_AUDIT_CONTEXT_V1',reader_sha256=LOADED,helper_reference=reference(HELPER,HELPER_SHA),result_reference=result_reference,request_started_reference=rr,preparation_reference=refs['preparation'],preparation_audit_reference=refs['audit'],existing_first_shard_audit_reference=first_ref,execution_context_sha256=ch,task_count=301657,shard_count=324,new_arithmetic_scope=301125,**FLAGS)
    audit_hash=digest(context);directory=OUTPUT/RESULT_SHA;details={0:compact_detail(first)};audits={0:first_ref};all_sources=dict(sources)
    require(type(completed_audit_references) in (list,tuple),'Explicit prior audit references')
    if not directory.exists():
        require(not completed_audit_references,'No supplied audits in absent namespace');directory.mkdir(parents=True,exist_ok=False);save(directory/'started.json',context)
    else:
        require(not (directory/'independent_readback.json').exists(),'Final audit already sealed; no repeat')
        exact(decode((directory/'started.json').read_bytes()),context,'Existing audit immutable context')
    # Do not autodiscover successful reports as authority. Every prior report is externally named.
    named=set()
    for ar in completed_audit_references:
        local={};report=decode(read(ar,local));i=integer(report['global_shard_index']);require(1<=i<324 and i not in details,'Unique explicitly resumed shard')
        folder=directory/f'shard-{i:05d}';require(Path(ar['path'])==folder/'independent_readback.json' and {p.name for p in folder.iterdir()}=={'started.json','independent_readback.json'},'No failed/partial prior shard')
        exact(decode((folder/'started.json').read_bytes()),dict(audit_context_sha256=audit_hash,global_shard_index=i,descriptor=queue[i],retry_allowed=False),'Prior audit attempt')
        d=validate_reused(report,i,audit_hash,result_reference,queue[i],result['completed_shard_references'][i])
        # Reconstruct the exact source closure independently, including ordered original tasks.
        expected_local=dict(sources);descriptor=queue[i];cr=result['completed_shard_references'][i]
        completion=decode(read(cr,expected_local));production=Path(cr['path']).parent
        require({p.name for p in production.iterdir()}=={'started.json','journal.jsonl','completion.json'},'Reused complete producer directory')
        sr=completion['started_reference'];jr=completion['journal_reference']
        require(Path(sr['path'])==production/'started.json' and Path(jr['path'])==production/'journal.jsonl','Reused fixed source paths')
        started=decode(read(sr,expected_local));prepared=decode(read(descriptor['contract_reference'],expected_local))
        tr=reference(descriptor['shard']['path'],descriptor['shard']['sha256']);tasks=[decode(line) for line in read(tr,expected_local).splitlines()]
        for r in (tr,descriptor['contract_reference']):require(pa['source_hashes'].get(r['path'])==r['sha256'],'Reused preparation audit pointer')
        require(prepared['contract_sha256']==prep['rows'][descriptor['scenario_index']]['contract_sha256'],'Reused scenario hash')
        require(set(jr)=={'path','sha256'} and type(jr['sha256']) is str and re.fullmatch('[a-f0-9]{64}',jr['sha256']),'Reused journal hash')
        require(jr['path'] not in expected_local or expected_local[jr['path']]==jr['sha256'],'Reused journal source conflict');expected_local[jr['path']]=jr['sha256']
        validate_reused_metadata(report,completion=completion,started=started,prepared=prepared,tasks=tasks,descriptor=descriptor,expected_sources=expected_local,execution_context_sha256=ch)
        # Hash guard reads bytes but never decodes the saved journal or reruns arithmetic here.
        guard(expected_local);details[i]=d;audits[i]=ar;named.add(folder.name)
        del tasks,prepared,started,completion
        for p,h in {**report['source_hashes'],**local}.items():require(p not in all_sources or all_sources[p]==h,'Cross audit source conflict');all_sources[p]=h
    existing={p.name for p in directory.iterdir() if p.is_dir()}
    require(existing==named,'Unacknowledged completed/partial/failed audit: no automatic replay')
    require(all(p.name=='started.json' or p.name in named for p in directory.iterdir()),'Unexpected audit namespace contents')
    oracle=helper.fresh_oracle();done=0
    for i in range(1,324):
        if i in details:continue
        if max_shards is not None and done>=max_shards:break
        descriptor=queue[i];folder=directory/f'shard-{i:05d}';folder.mkdir(exist_ok=False)
        save(folder/'started.json',dict(audit_context_sha256=audit_hash,global_shard_index=i,descriptor=descriptor,retry_allowed=False))
        try:
            local=dict(sources);cr=result['completed_shard_references'][i];completion=decode(read(cr,local));production=Path(cr['path']).parent
            require({p.name for p in production.iterdir()}=={'started.json','journal.jsonl','completion.json'},'Complete source shard only')
            sr=completion['started_reference'];jr=completion['journal_reference'];require(Path(sr['path'])==production/'started.json' and Path(jr['path'])==production/'journal.jsonl','Source shard paths')
            started=decode(read(sr,local));raw=read(jr,local);prepared=decode(read(descriptor['contract_reference'],local))
            require(prepared['contract_sha256']==prep['rows'][descriptor['scenario_index']]['contract_sha256'],'Original scenario contract')
            tr=reference(descriptor['shard']['path'],descriptor['shard']['sha256']);tasks=[decode(line) for line in read(tr,local).splitlines()]
            for r in (tr,descriptor['contract_reference']):require(pa['source_hashes'].get(r['path'])==r['sha256'],'Preparation audit pointer')
            require(all(t['task_id']!=helper.FIRST_ID for t in tasks),'External first never repeated')
            guard(local)
            detail=helper.inspect_complete_shard(started=started,completion=completion,journal_bytes=raw,tasks=tasks,prepared=prepared,descriptor=descriptor,context_sha256=ch,external_references={k:refs[k] for k in ('first_started','first_raw','first_postcheck','first_audit')},independent_result=oracle)
            guard(local)
            report=dict(schema='CASH_NEIGHBOR_FULL_AUDIT_SHARD_V1',status='PASS',reader_sha256=LOADED,audit_context_sha256=audit_hash,result_reference=result_reference,global_shard_index=i,descriptor=descriptor,completion_reference=cr,journal_reference=jr,started_reference=sr,source_hashes=local,detail=compact_detail(detail),**FLAGS)
            ar=save(folder/'independent_readback.json',report);guard(local);require({p.name for p in folder.iterdir()}=={'started.json','independent_readback.json'},'Exact success audit shard');require(sha(Path(ar['path']).read_bytes())==ar['sha256'],'Final report drift')
            details[i]=report['detail'];audits[i]=ar;done+=1
            for p,h in local.items():require(p not in all_sources or all_sources[p]==h,'Audited source collision');all_sources[p]=h
            all_sources[ar['path']]=ar['sha256']
            del raw,tasks,prepared,report,detail
        except Exception as error:
            save(folder/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(error),retry_allowed=False));raise
    if len(details)<324:
        return dict(status='AUDIT_ENGINEERING_BOUND_ONLY',audited_shard_references=[audits[i] for i in sorted(audits) if i],existing_first_shard_audit_reference=first_ref,remaining_shard_indexes=[i for i in range(1,324) if i not in details],whole_batch_audit_passed=False,**FLAGS)
    totals=aggregate(details,result['outcome_counts']);guard(all_sources)
    final=dict(schema='CASH_NEIGHBOR_FULL_BATCH_INDEPENDENT_READBACK_V1',status='PASS',reader_sha256=LOADED,audit_context_sha256=audit_hash,result_reference=result_reference,request_started_reference=rr,existing_first_shard_audit_reference=first_ref,shard_audit_references=[audits[i] for i in range(324)],source_hashes=all_sources,counts=totals,scope='DECLARED_SAVED_NEIGHBORHOOD_ONLY_NOT_GLOBAL_INTEGER_OPTIMUM_OR_PIT',request_source_shape='FROZEN_REQUEST_HAS_NO_SCHEMA_PRIOR_OR_BATCH_REFERENCE_FIELDS_RESULT_CHAIN_PROVIDES_LINKS',**FLAGS)
    try:
        result_ref=save(directory/'independent_readback.json',final);guard(all_sources)
        require(sha(Path(result_ref['path']).read_bytes())==result_ref['sha256'],'Final aggregate drift')
        require({p.name for p in directory.iterdir()}=={'started.json','independent_readback.json'}|{f'shard-{i:05d}' for i in range(1,324)},'Final exact namespace')
        return result_ref
    except Exception as error:
        save(directory/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(error),retry_allowed=False));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--max-shards',type=int);p.add_argument('--completed-audits-file');a=p.parse_args()
    refs=decode(Path(a.completed_audits_file).read_bytes()) if a.completed_audits_file else []
    print(json.dumps(run(result_reference=reference(RESULT_PATH,RESULT_SHA),completed_audit_references=refs,max_shards=a.max_shards,execute=a.execute)))
