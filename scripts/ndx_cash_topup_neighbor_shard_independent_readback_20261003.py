"""Independent complete-shard journal, task, source and saved arithmetic readback."""
import argparse,hashlib,json,os,re,types
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PREP=ROOT/'data/cache/research/cash_topup_neighbor_preparation_20261003_v1'
BATCH=ROOT/'data/cache/research/cash_topup_neighbor_shard_evaluation_20261003_v1'
OUTPUT=ROOT/'data/cache/research/cash_topup_neighbor_shard_independent_readback_20261003_v1'
RESULT_PATH=BATCH/'request-dc2686d5a18447f5837e70f5936731ee/result.json';RESULT_SHA='15d9742bec44074dc09d8c23fee12bff0b9a096618f86c9cf809abb96fc138ff';REQUEST_SHA='622c9a2bcc4ce65cefcc9c39cfb54c2457fb245a993c6458953cc738c282eb6a'
FIRST_ID='8b5320eb5ac613ddf6a69478f7e2360811688d1951b38c9e1d7b4ff34678febd'
FIRST_ROOT=ROOT/'data/cache/research/cash_topup_neighbor_evaluation_20261003_v1'/FIRST_ID
WORKER=ROOT/'scripts/ndx_cash_topup_neighbor_shard_worker_20261003.py';WORKER_SHA='f61148cb64e28460055b8284c8e4cc976637394228600783b9cc9fdfd7f2515e'
ADAPTER=ROOT/'scripts/ndx_cash_topup_neighbor_single_evaluation_20261003.py';ADAPTER_SHA='6328a40a4c07f90b10b120ef348f924cf7cfa0dda9b12e63a80939e183c651ba'
JOURNAL=ROOT/'backtest/ndx_cash_topup_neighbor_journal_research.py';JOURNAL_SHA='d04eb2772432ed1fea291d699a25d4eeaac49b12aa228ee560d5d5613de8f637'
ORACLE=ROOT/'scripts/ndx_cash_topup_neighbor_single_evaluation_independent_readback_20261003.py';ORACLE_SHA='0106433db9e123a3786a1656e495387b8c58a0c42019be50a113b4c311176140'
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
 'first_reader':('scripts/ndx_cash_topup_neighbor_single_evaluation_independent_readback_20261003.py',ORACLE_SHA)}
FALSE=('fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed','full_integer_domain_exhausted','economic_winner_selected','target_weights_changed','holdings_sold','runtime_binary_closure_verified','continuous_source_monitoring_claimed','automatic_retry_allowed')
RULE='ALL_SAVED_FEASIBLE_SEEDS_SINGLE_PM1_AND_PAIR_PM1_NONNEGATIVE_SAVED_CAPS_V1'

def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(v):return sha(enc(v))
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def integer(v):require(type(v) is int and v>=0,'Exact nonnegative integer');return v
def ref(path,h):return dict(path=str(path),sha256=h)
def decode(b):
    def pairs(items):
        result={}
        for k,v in items:require(k not in result,'Duplicate JSON');result[k]=v
        return result
    def bad(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=bad)
def flags(v):require(all(v[k] is False for k in FALSE),'False authority scope')
def producer_sources():
    return {str(WORKER):WORKER_SHA,str(ADAPTER):ADAPTER_SHA,str(JOURNAL):JOURNAL_SHA,
        **{str(ROOT/p):h for p,h in PINS.values()},**{p:h for p,h in BOUND.values()}}

def queue_from_preparation(p):
    require(p['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_V1' and integer(p['scenario_count'])==40 and len(p['rows'])==40,'All40 scenarios')
    require(integer(p['task_evaluation_count'])==0 and p['declared_local_neighborhood_complete'] is True,'Complete unevaluated preparation')
    queue=[];position=0;names=set()
    for i,row in enumerate(p['rows']):
        require(row['scenario_id'] not in names,'Unique scenario');names.add(row['scenario_id'])
        require(Path(row['contract_reference']['path'])==PREP/f'scenario-{i:02d}'/'contract.json','Fixed original contract')
        start=0
        for j,s in enumerate(row['shards']):
            require(integer(s['start'])==start and 1<=integer(s['stop'])-start<=1000,'Complete original intervals')
            require(Path(s['path'])==PREP/f'scenario-{i:02d}'/f'tasks-{j:05d}.jsonl','Original stable shard path')
            count=s['stop']-start
            queue.append(dict(scenario_index=i,shard_index=j,global_shard_index=len(queue),global_task_start=position,global_task_stop=position+count,shard=deepcopy(s),contract_reference=deepcopy(row['contract_reference'])))
            position+=count;start=s['stop']
        exact(start,row['statistics']['new_candidate_count'],'Original scenario count')
    require(len(queue)==324 and position==301657,'Whole declared preparation denominator')
    exact(p['statistics']['new_candidate_count'],position,'Original total count')
    return queue

def task_arguments(prepared,task,ordinal):
    c=prepared['contract'];require(digest(c)==prepared['contract_sha256'],'Entire contract digest')
    require(c['schema']=='CONDITIONAL_TOPUP_NEIGHBOR_SCENARIO_CONTRACT_V1' and c['rule']==RULE,'Original conditional neighborhood')
    require(task['task_id']==digest(task['identity']) and task['scenario_id']==c['scenario_id'],'Full task/scenario identity')
    exact(task['scenario_candidate_ordinal'],ordinal,'Original shard position')
    require(task['evaluation_status']=='NOT_EVALUATED','Only prepared new point')
    for obj in (c,task):
        require(all(obj[k] is False for k in ('risk_evaluated','financial_feasibility_evaluated','old_evaluations_repeated','fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed','target_weights_changed','holdings_sold','new_candidates_selected')),'Prepared authority')
    buy=task['identity']['buy_shares'];ids=c['conditional_research_buy_ids'];caps=c['saved_buy_limits'];r=c['original_input_row']
    exact(task['identity'],dict(schema='CONDITIONAL_TOPUP_NEIGHBOR_TASK_IDENTITY_V1',rule=RULE,scenario_contract_sha256=prepared['contract_sha256'],buy_shares=buy),'Complete numeric point identity')
    require(ids==sorted(set(ids)) and set(ids)==set(caps)==set(buy),'Full zero-preserving vector')
    require(set(ids)==set(r['target_weights'])|{s for s,q in r['holdings'].items() if integer(q)>0},'Full old plus target domain')
    require(r['branch_role']=='MAIN_LANE' and r['target_l1_applicable'] is True and r['zero_buy_only'] is False,'Original main research role')
    require(all(r[k] is False for k in ('point_in_time_verified','orders_executed','promotion_allowed','fork_executable')),'Original input not certified')
    for s in ids:require(integer(buy[s])<=integer(caps[s]),'Saved cap')
    points=c['old_evaluated_points'];require(all(buy!=p['buy_shares'] for p in points),'Old evaluated vectors never repeated')
    origin=task['first_origin'];index=integer(origin['seed_candidate_index']);require(index<len(points) and points[index]['saved_feasible'] is True and index in c['all_feasible_seed_indexes'],'Original feasible seed')
    exact(origin['seed_reference'],points[index]['reference'],'Full seed pointer');moves=origin['moves']
    require(type(moves) is list and len(moves) in (1,2) and [m['security_id'] for m in moves]==sorted({m['security_id'] for m in moves}),'Declared distinct move coordinates')
    changed=deepcopy(points[index]['buy_shares'])
    for m in moves:
        require(set(m)=={'security_id','delta'} and m['security_id'] in ids and type(m['delta']) is int and m['delta'] in (-1,1),'Unit signed move')
        changed[m['security_id']]+=m['delta']
    exact(changed,buy,'Seed-to-task movement')
    a={k:deepcopy(r[k]) for k in ('cash_event','starting_cash_usd','holdings','execution_prices','risk_parameters','transaction_cost_bps','minimum_cash_buffer_usd')}
    a['securities']={s:{k:v[k] for k in ('issuer_id','risk_chain')} for s,v in r['securities'].items()}
    a.update(branches=[dict(branch_id=r['scenario_id'],buy_limits=deepcopy(caps))],max_evaluations=1)
    return dict(evaluation_inputs=a,plans_by_branch={r['scenario_id']:[deepcopy(buy)]})

def expected_detail(prepared,result):
    p=result['branches'][0]['evaluated_plans'][0];score=None
    if p['feasible']:
        r=prepared['contract']['original_input_row'];weights={s:Fraction(v) for s,v in r['target_weights'].items()};total=sum(weights.values(),Fraction())
        require(total>0,'Original positive target sum');values={s:q*Fraction(r['execution_prices'][s]) for s,q in p['proposed_holdings'].items()};stocks=sum(values.values(),Fraction());require(stocks>0,'Positive stock denominator')
        d=sum((abs(values.get(s,0)/stocks-weights.get(s,0)/total) for s in set(values)|set(weights)),Fraction());f=Fraction(p['fees_usd'])
        score=dict(distance=dict(numerator=d.numerator,denominator=d.denominator),fees_usd=dict(numerator=f.numerator,denominator=f.denominator))
    return dict(outcome='FEASIBLE' if p['feasible'] else 'INFEASIBLE',original_target_stock_weight_l1=score,score_absence_reason=None if score is not None else 'ORIGINAL_POLICY_SCORES_ONLY_FEASIBLE_PLANS',evaluation_error=None,validation_error=None)

def inspect_complete_shard(*,started,completion,journal_bytes,tasks,prepared,descriptor,context_sha256,external_references,independent_result):
    """Whole bounded shard only. Partial/technical capture is never a PASS here."""
    ids=[t['task_id'] for t in tasks]
    require(len(ids)==len(set(ids))==descriptor['shard']['stop']-descriptor['shard']['start'],'Exact full original task set')
    flags(started);flags(completion)
    require(started['schema']=='CASH_NEIGHBOR_SHARD_STARTED_V1' and completion['schema']=='CASH_NEIGHBOR_SHARD_COMPLETION_V1' and completion['status']=='COMPLETE_SAVED_DIAGNOSTICS_NOT_INDEPENDENTLY_AUDITED','Complete producer schemas')
    for obj in (started,completion):
        exact(obj['descriptor'],descriptor,'Independent original descriptor');require(obj['context_sha256']==context_sha256,'Batch context')
    exact(started['ordered_task_ids'],ids,'All ordered task IDs');exact(started['contract_sha256'],prepared['contract_sha256'],'Started contract identity')
    require(type(journal_bytes) is bytes and journal_bytes.endswith(b'\n'),'No incomplete journal tail')
    records=[];indexes=[];offset=0;previous='0'*64
    for line in journal_bytes.splitlines(keepends=True):
        require(line.endswith(b'\n'),'Complete persisted record');r=decode(line)
        require(set(r)=={'schema','sequence','previous_record_sha256','context_sha256','task_id','task_position','stage','payload','record_sha256'},'Exact journal record fields')
        require(r['schema']=='CASH_NEIGHBOR_JOURNAL_RECORD_V1' and type(r['sequence']) is int and r['sequence']==len(records),'Record schema/order')
        require(r['previous_record_sha256']==previous and r['context_sha256']==context_sha256,'Independent chained context')
        require(type(r['task_position']) is int and 0<=r['task_position']<len(ids) and r['task_id']==ids[r['task_position']],'Record original task attribution')
        body={k:v for k,v in r.items() if k!='record_sha256'};require(digest(body)==r['record_sha256'] and enc(r)+b'\n'==line,'Exact canonical record/hash')
        indexes.append(dict(sequence=len(records),byte_start=offset,byte_stop=offset+len(line),record_sha256=r['record_sha256'],task_id=r['task_id'],stage=r['stage']))
        records.append(r);previous=r['record_sha256'];offset+=len(line)
    cursor=0;counts=dict.fromkeys(('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE','EXTERNALLY_REFERENCED'),0);details=[]
    for pos,t in enumerate(tasks):
        args=task_arguments(prepared,t,descriptor['shard']['start']+pos)
        require(cursor<len(records),'Missing task records')
        if t['task_id']==FIRST_ID:
            require(descriptor['global_task_start']==0 and pos==0,'Unique first position')
            r=records[cursor];require(r['task_position']==pos and r['stage']=='EXTERNAL_REFERENCE','Existing first may only be referenced')
            exact(r['payload'],external_references,'Four exact external first references');counts['EXTERNALLY_REFERENCED']+=1;cursor+=1
            details.append(dict(task_id=t['task_id'],outcome='EXTERNALLY_REFERENCED',new_arithmetic_checked=False));continue
        group=records[cursor:cursor+3];require(len(group)==3 and [r['stage'] for r in group]==['TASK_STARTED','RAW_RETURNED','POSTCHECK'],'Complete successful return sequence; technical/partial is blocked')
        require(all(r['task_position']==pos and r['task_id']==t['task_id'] for r in group),'No interleaved task records')
        expected_start=dict(task_reference=dict(ref(descriptor['shard']['path'],descriptor['shard']['sha256']),jsonl_line_index=pos,scenario_candidate_ordinal=t['scenario_candidate_ordinal']),global_task_position=descriptor['global_task_start']+pos,evaluation_argument_sha256=digest(args))
        exact(group[0]['payload'],expected_start,'Original argument identity and full source pointer')
        raw=group[1]['payload'];require(set(raw)=={'result','error','explicit_evaluator_call_attempt_count','returned_evaluation_count'},'Full raw envelope')
        exact(raw['explicit_evaluator_call_attempt_count'],1,'Single dispatch');exact(raw['returned_evaluation_count'],1,'One saved return');require(raw['error'] is None,'No invented arithmetic after exception')
        result=independent_result(args);exact(raw['result'],result,'Independent complete finance/five-risk/zero-search arithmetic')
        detail=expected_detail(prepared,result);exact(group[2]['payload'],detail,'Independent score and outcome')
        counts[detail['outcome']]+=1;details.append(dict(task_id=t['task_id'],outcome=detail['outcome'],new_arithmetic_checked=True,original_target_stock_weight_l1=detail['original_target_stock_weight_l1']));cursor+=3
    require(cursor==len(records),'No extra record/task')
    exact(completion['record_index'],indexes,'Complete independent byte index');exact(completion['record_count'],len(records),'Record denominator')
    require(completion['terminal_record_sha256']==previous,'Final chain digest');exact(completion['task_count'],len(tasks),'Full task denominator')
    exact(completion['outcome_counts'],counts,'Full independent outcome partition');exact(completion['new_evaluator_call_count'],len(tasks)-counts['EXTERNALLY_REFERENCED'],'New call count')
    exact(completion['unresolved_dispatch_count'],0,'No unresolved complete shard');exact(completion['undispatched_count'],0,'No missing complete shard')
    return dict(task_count=len(tasks),new_arithmetic_checked_count=len(tasks)-counts['EXTERNALLY_REFERENCED'],outcome_counts=counts,task_results=details,record_count=len(records),journal_sha256=sha(journal_bytes))

def fresh_oracle():
    b=ORACLE.read_bytes();require(sha(b)==ORACLE_SHA,'Frozen independent arithmetic source')
    module=types.ModuleType('_independent_cash_arithmetic');module.__file__=str(ORACLE)
    exec(compile(b,str(ORACLE),'exec'),module.__dict__)
    return module.independent_result

def readback(result_reference,*,global_shard_index=0,execute=False):
    require(execute is True and type(execute) is bool and RESULT_PATH is not None and RESULT_SHA is not None and REQUEST_SHA is not None,'Actual run anchors pending or explicit action missing')
    exact(result_reference,ref(RESULT_PATH,RESULT_SHA),'External fixed batch result')
    out=OUTPUT/RESULT_SHA/f'shard-{integer(global_shard_index):05d}';require(not out.exists(),'Unique readback namespace')
    sources={str(SOURCE):LOADED,**producer_sources()};loaded={}
    def read(r):
        require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and type(r['sha256']) is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Exact external reference')
        require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Source collision')
        b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed bytes');sources[r['path']]=r['sha256'];return b
    def guard():
        for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Readback source drift')
    refs={k:ref(p,h) for k,(p,h) in BOUND.items()};loaded={k:decode(read(r)) for k,r in refs.items()};p=loaded['preparation'];queue=queue_from_preparation(p)
    for key in ('publication','audit'):exact(loaded[key]['preparation_reference'],refs['preparation'],'Sealed preparation link')
    require(loaded['publication']['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_PUBLICATION_V1' and loaded['publication']['status']=='PUBLISHED_UNEVALUATED_CANDIDATES_ONLY','Preparation publication')
    require(loaded['audit']['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_INDEPENDENT_READBACK_V1' and loaded['audit']['status']=='PASS' and loaded['audit']['reader_sha256']==PINS['preparation_reader'][1],'Existing preparation audit only referenced')
    exact(loaded['audit']['publication_reference'],refs['publication'],'Preparation audit receipt');exact(loaded['publication']['source_hashes'],p['source_hashes'],'Parent source map')
    require(not (PREP/'failure.json').exists(),'No failed preparation')
    first=loaded['first_audit'];require(first['schema']=='CASH_TOPUP_SINGLE_EVALUATION_INDEPENDENT_READBACK_V1' and first['status']=='PASS' and first['task_id']==FIRST_ID and first['reader_sha256']==ORACLE_SHA and first['returned_arithmetic_independently_verified'] is True and first['attempt_outcome'] in ('FEASIBLE','INFEASIBLE'),'First audited result reference')
    for key in ('started','raw','postcheck'):exact(first[key+'_reference'],refs['first_'+key],'External first evidence chain')
    result=decode(read(result_reference));request_dir=Path(result_reference['path']).parent
    require(request_dir.parent==BATCH and request_dir.name.startswith('request-') and Path(result_reference['path']).name=='result.json','Fixed request result path')
    require({x.name for x in request_dir.iterdir()}=={'started.json','result.json'},'No failed request consumption')
    request_ref=ref(request_dir/'started.json',REQUEST_SHA);exact(result['request_started_reference'],request_ref,'Explicit request anchor');request=decode(read(request_ref))
    batch_ref=result['batch_started_reference'];require(Path(batch_ref['path'])==BATCH/'started.json','Original batch context path');batch=decode(read(batch_ref));ctx=batch['context']
    require(type(ctx['runtime']) is dict and set(ctx['runtime'])=={'python','implementation','executable','platform'} and all(type(v) is str and v for v in ctx['runtime'].values()),'Saved runtime metadata, not independent binary proof')
    expected=dict(schema='CASH_NEIGHBOR_SHARD_EXECUTION_CONTEXT_V1',input_references=refs,source_hashes=producer_sources(),scenario_count=40,shard_count=324,task_count=301657,new_call_count=301656,externally_referenced_task_id=FIRST_ID,runtime=ctx['runtime'],rule='ORIGINAL_PREPARATION_ORDER_ONE_EXPLICIT_CALL_PER_NEW_TASK',minimum_free_bytes=5*1024**3,**dict.fromkeys(FALSE,False))
    exact(ctx,expected,'Independent entire producer source context');ch=digest(ctx);exact(batch['context_sha256'],ch,'Batch context hash')
    require(result['schema']=='CASH_NEIGHBOR_SHARD_BATCH_RUN_V1' and result['context_sha256']==request['context_sha256']==ch,'Run/request context')
    flags(request);flags(result)
    for obj in (result,request):exact(obj['full_shard_count'],324,'Whole shard denominator');exact(obj['full_task_count'],301657,'Whole task denominator')
    limit=request['max_new_shards'];require(limit is None or type(limit) is int and 1<=limit<=324,'Exact engineering request bound')
    completion_refs=result['completed_shard_references'];require(type(completion_refs) is list and global_shard_index<len(completion_refs)<=324,'Requested completed prefix shard exists')
    require(len({r['path'] for r in completion_refs})==len(completion_refs),'Unique completed references')
    for i,r in enumerate(completion_refs):
        d=queue[i];require(Path(r['path'])==BATCH/f'scenario-{d["scenario_index"]:02d}-shard-{d["shard_index"]:05d}'/'completion.json','Stable complete prefix references')
    exact(result['remaining_shard_descriptors'],queue[len(completion_refs):],'No truncated remaining domain')
    exact(result['accepted_task_count'],sum(d['global_task_stop']-d['global_task_start'] for d in queue[:len(completion_refs)]),'Accepted prefix count')
    require(result['failure'] is None or result['failure']['status'] in ('ENGINEERING_RUN_BOUND_BEFORE_DISPATCH','RESOURCE_STOP_BEFORE_DISPATCH'),'Technical/partial batch cannot receive complete PASS')
    require(result['partial_shard_recovery'] is None,'No partial evidence accepted as complete')
    require(result['status']==('COMPLETE' if len(completion_refs)==324 and result['failure'] is None else 'STOPPED'),'Exact run status')
    counts=result['outcome_counts'];require(set(counts)=={'FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE','EXTERNALLY_REFERENCED','UNRESOLVED_DISPATCH','UNDISPATCHED'},'Complete partition labels')
    require(sum(integer(v) for v in counts.values())==301657 and counts['EXTERNALLY_REFERENCED']==1 and counts['EVALUATION_EXCEPTION']==counts['VALIDATION_FAILURE']==counts['UNRESOLVED_DISPATCH']==0,'Complete accepted run partition')
    exact(counts['FEASIBLE']+counts['INFEASIBLE']+1,result['accepted_task_count'],'Accepted arithmetic prefix partition')
    descriptor=queue[global_shard_index];scenario=p['rows'][descriptor['scenario_index']];folder=Path(completion_refs[global_shard_index]['path']).parent
    require({x.name for x in folder.iterdir()}=={'started.json','journal.jsonl','completion.json'},'Exact successful shard directory')
    completion=decode(read(completion_refs[global_shard_index]));startref=completion['started_reference'];require(Path(startref['path'])==folder/'started.json','Shard started path');started=decode(read(startref))
    jr=completion['journal_reference'];require(Path(jr['path'])==folder/'journal.jsonl','Raw journal path');raw=read(jr)
    prepared=decode(read(descriptor['contract_reference']));require(prepared['contract_sha256']==scenario['contract_sha256'],'Original scenario contract')
    sr=ref(descriptor['shard']['path'],descriptor['shard']['sha256']);tasks=[decode(line) for line in read(sr).splitlines()]
    for r in (sr,descriptor['contract_reference']):require(loaded['audit']['source_hashes'][r['path']]==r['sha256'],'Existing preparation audit covers chosen bytes')
    external={k:refs[k] for k in ('first_started','first_raw','first_postcheck','first_audit')}
    if global_shard_index==0:
        exact(loaded['first_started']['task'],tasks[0],'Exact external task, not repeated arithmetic');exact(loaded['first_started']['original_contract'],prepared,'Same first contract')
    guard();detail=inspect_complete_shard(started=started,completion=completion,journal_bytes=raw,tasks=tasks,prepared=prepared,descriptor=descriptor,context_sha256=ch,external_references=external,independent_result=fresh_oracle());guard()
    for key,value in detail['outcome_counts'].items():require(value<=counts[key],'This independently checked shard cannot exceed run totals')
    if len(completion_refs)==1:
        exact({k:counts[k] for k in detail['outcome_counts']},detail['outcome_counts'],'First request complete outcome totals independently reconciled')
    out.mkdir(parents=True,exist_ok=False)
    def save(path,value):
        b=enc(value)
        with path.open('xb') as stream:stream.write(b);stream.flush();os.fsync(stream.fileno())
        require(path.read_bytes()==b,'Durable report');return ref(path,sha(b))
    try:
        report=dict(schema='CASH_NEIGHBOR_SHARD_INDEPENDENT_READBACK_V1',status='PASS',result_reference=result_reference,request_started_reference=request_ref,completion_reference=completion_refs[global_shard_index],journal_reference=jr,started_reference=startref,global_shard_index=global_shard_index,descriptor=descriptor,preparation_reference=refs['preparation'],preparation_audit_reference=refs['audit'],source_hashes=sources,reader_sha256=LOADED,
            verification_scope='ONE_COMPLETE_ORIGINAL_SHARD_FULL_SAVED_ARITHMETIC_NOT_WHOLE_BATCH_AUDIT',whole_batch_arithmetic_independently_verified=False,all_completed_prefix_arithmetic_checked_in_this_report=len(completion_refs)==1,producer_called=False,evaluator_called=False,old_audits_reexecuted=False,existing_first_arithmetic_recomputed=False,**detail,**dict.fromkeys(FALSE,False))
        answer=save(out/'independent_readback.json',report);guard();require((out/'independent_readback.json').read_bytes()==enc(report),'Final report bytes');require({x.name for x in out.iterdir()}=={'independent_readback.json'},'Exact audit directory');return answer
    except Exception as error:save(out/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(error),retry_allowed=False));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--global-shard-index',type=int,default=0);parser.add_argument('--execute',action='store_true');a=parser.parse_args()
    print(json.dumps(readback(ref(RESULT_PATH,RESULT_SHA),global_shard_index=a.global_shard_index,execute=a.execute)))
