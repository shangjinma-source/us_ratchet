"""Full saved cash recovery source readback; numerical evaluation is never dispatched.

Publication requires final external registration and independent inspector pins.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
HELPER = ROOT / 'scripts/ndx_cash_topup_neighbor_shard_independent_readback_20261003.py'
HELPER_SHA = '39a7194291584195eed09d2b1e2d83f97cd9b53a20bd4858e192fd4ba4d728ad'
PURE = ROOT / 'backtest/ndx_cash_neighbor_combined_inspection_research.py'
PURE_SHA = 'fc4dc4d5b54d8084fb6591d134a773ba3285635ee640f2368383197d1c375c50'
REGISTRATION_SHA = '5a495c0bc5ae54068cbfa736aee7ccb779d066de90661b872455343823af7c37'
FULL_SOURCE_GRAPH_IMPLEMENTED = True
OUTPUT = ROOT/'data/cache/research/cash_neighbor_combined_independent_readback_20261008_v1'
RECOVERY = ROOT/'data/cache/research/cash_neighbor_recovery_20261008_v1'
PARTITION = ROOT/'data/cache/research/cash_neighbor_interrupted_partition_20261008_v1/partition.json'
PARTITION_SHA = '3f88cd70bd62bcac4ccf9e756031e8353b788ef6575b23a4d6565d6a4a06f120'
SIDECAR = ROOT/'data/cache/research/cash_neighbor_saved_raw_postcheck_20261008_v1/independent_postcheck.json'
SIDECAR_SHA = 'ebe5a186043d4878ee3a7c3b0c570d8e1d876a072b1e3742372b39c56c63ede6'
WORKER = ROOT/'scripts/ndx_cash_neighbor_recovery_worker_20261008.py'
WORKER_SHA = 'e528088ee3f355f5d8c95d4b3b12a9f05003e7fdcddab3ca6996a054ebd7fb16'
RECOVERY_PURE = ROOT/'backtest/ndx_cash_neighbor_recovery_partition_research.py'
RECOVERY_PURE_SHA = 'b0265f556cdfdc5765ed69d0b52528d5470ce66f38bf80edded9c68dcd2a7b31'
FIRST = ROOT/'data/cache/research/cash_topup_neighbor_shard_independent_readback_20261003_v1/15d9742bec44074dc09d8c23fee12bff0b9a096618f86c9cf809abb96fc138ff/shard-00000/independent_readback.json'
FIRST_SHA = '9a17d90a72406a56313d5d6cab4d1cf807f65a80dd492cec17bf196879a34ba5'
FLAGS = dict.fromkeys(('evaluator_called','producer_called','old_tasks_redispatched','account_executed','orders_executed','point_in_time_verified','promotion_allowed','economic_winner_selected','full_integer_domain_exhausted','future_independent_oos','automatic_retry_allowed','runtime_binary_closure_verified'),False)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def valid(reference):
    require(type(reference) is dict and set(reference) == {'path', 'sha256'}, 'Exact reference')
    path, digest = reference['path'], reference['sha256']
    require(type(path) is str and Path(path).is_absolute() and str(Path(path)) == path and '..' not in Path(path).parts, 'Canonical absolute path')
    require(type(digest) is str and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest), 'Pending source anchor')


def memory_available():
    class Status(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(k, ctypes.c_ulonglong) for k in ('total', 'available', 'page_total', 'page_available', 'virtual_total', 'virtual_available', 'extended')]
    value = Status(); value.length = ctypes.sizeof(value)
    require(os.name == 'nt' and ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)), 'Measured available memory')
    return value.available


def load_bytes(reference, *, maximum_bytes, available=None):
    """Reserve before reading; same actual bounded bytes are authenticated."""
    valid(reference)
    require(type(maximum_bytes) is int and maximum_bytes > 0, 'Explicit read bound')
    path = Path(reference['path'])
    size = path.stat().st_size
    require(size <= maximum_bytes, 'Saved span exceeds registered resource bound')
    require((memory_available() if available is None else available) >= 2 * 1024**3 + 32 * size, 'Single span memory reserve')
    with path.open('rb') as stream:
        raw = stream.read(size + 1)
    require(len(raw) == size and hashlib.sha256(raw).hexdigest() == reference['sha256'], 'Bounded same consumed bytes')
    return raw


def private(path, digest):
    raw = load_bytes(dict(path=str(path), sha256=digest), maximum_bytes=1024**2)
    module = ModuleType('_combined_independent_' + path.stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def inspect_bound_span(*, journal_reference, maximum_journal_bytes, inputs):
    """Internal adapter; callers must first authenticate the full input graph.

No files are published and no dispatch function is loaded. This helper alone
cannot confer source-authenticated or whole-domain PASS status.
"""
    valid(dict(path=str(PURE), sha256=PURE_SHA))
    helper = private(HELPER, HELPER_SHA)
    pure = private(PURE, PURE_SHA)
    raw = load_bytes(journal_reference, maximum_bytes=maximum_journal_bytes)
    oracle = helper.fresh_oracle()
    return pure.inspect_span(raw=raw, arguments=helper.task_arguments,
                             independent_result=oracle, expected_detail=helper.expected_detail, **inputs)


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def sha(raw):return hashlib.sha256(raw).hexdigest()
def exact(left,right,message):require(encode(left)==encode(right),message)
def ref(path,digest):return dict(path=str(path),sha256=digest)
def file_sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()
def merge_bindings(target,values):
    for path,digest in values.items():
        valid(ref(path,digest));require(path not in target or target[path]==digest,'Source closure conflict');target[path]=digest

def guard(bindings):
    for path,digest in bindings.items():require(file_sha(path)==digest,'Source drift: '+path)

def inventory(root):return sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())

def save(path,value):
    raw=encode(value)
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Durable exact audit bytes');return ref(path,sha(raw))

def verify_saved_outputs(references):
    for value in references:
        valid(value);require(file_sha(value['path'])==value['sha256'],'Saved audit report drift')


def expected_domain(queue,ids_by_shard,partition,sidecar):
    ordered=[task for ids in ids_by_shard for task in ids]
    require(len(ordered)==len(set(ordered))==301657 and len(queue)==len(ids_by_shard)==324,'Entire original unique domain')
    groups=partition['task_ids_by_saved_status']
    require(set(groups)=={'FEASIBLE','INFEASIBLE','EXTERNALLY_REFERENCED','RAW_SAVED_POSTCHECK_MISSING','UNRESOLVED_DISPATCH','UNDISPATCHED'},'All saved categories')
    observed=[task for group in groups.values() for task in group]
    require(len(observed)==len(set(observed))==len(ordered) and set(observed)==set(ordered),'Full saved ID partition')
    exact(partition['counts'],{key:len(value) for key,value in groups.items()},'Saved category counts')
    exact(groups['UNDISPATCHED'],ordered[259356:],'Original untouched suffix')
    exact(groups['RAW_SAVED_POSTCHECK_MISSING'],[ordered[259355]],'Unique raw-only point')
    exact(groups['UNRESOLVED_DISPATCH'],[],'No unresolved original dispatch')
    exact(sidecar['task_id'],ordered[259355],'Sidecar original task')
    segments=[]
    for descriptor,ids in zip(queue,ids_by_shard):
        start=max(259356,descriptor['global_task_start']);stop=descriptor['global_task_stop']
        if start>=stop:continue
        local=start-descriptor['global_task_start']
        segments.append(dict(recovery_segment_index=len(segments),original_descriptor=descriptor,original_task_start=local,original_task_stop=len(ids),original_global_start=start,original_global_stop=stop,task_ids=ids[local:]))
    require(len(segments)==45 and len(segments[0]['task_ids'])==837,'Exact45 source segments')
    return dict(schema='CASH_NEIGHBOR_RECOVERY_DOMAIN_V1',original_task_count=301657,excluded_previously_dispatched_count=259356,recovery_task_count=42301,segments=segments,ordered_recovery_task_ids_sha256=sha(encode(groups['UNDISPATCHED'])),dispatch_authorized=False)

def consume_block(rows,expected_ids,counts):
    exact([row['task_id'] for row in rows],expected_ids,'Complete ordered logical shard')
    for row in rows:
        require(row['outcome'] in counts,'Only saved economic terminal or external reference')
        counts[row['outcome']]+=1

def validate_recovery_result(result,registration_reference,segments):
    require(result['schema']=='CASH_NEIGHBOR_RECOVERY_REQUEST_V1' and result['status']=='COMPLETE_PENDING_INDEPENDENT_READBACK','Complete entire new recovery')
    exact(result['registration_reference'],registration_reference,'New recovery registration link')
    exact(result['stopped'],None,'No technical/resource stop')
    exact(result['remaining_segment_descriptors'],[],'No truncated suffix')
    exact(result['full_recovery_task_count'],42301,'Full new domain')
    refs=result['completed_segment_references'];require(len(refs)==45,'All45 physical segments')
    for index,value in enumerate(refs):
        valid(value);require(Path(value['path'])==RECOVERY/('segment-%04d'%index)/'completion.json','Ordered original recovery segment path')
    groups=result['partition']['task_ids_by_status']
    require(set(groups)=={'FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE','RAW_SAVED_POSTCHECK_MISSING','UNRESOLVED_DISPATCH','UNDISPATCHED'},'Full new status categories')
    for key in groups:
        if key not in ('FEASIBLE','INFEASIBLE'):exact(groups[key],[],'No non-economic missing scope')
    exact(result['partition']['counts'],{key:len(values) for key,values in groups.items()},'New full counts')
    exact(result['partition']['old_task_dispatch_count'],0,'Never redispatched old domain')
    ids=[task for segment in segments for task in segment['task_ids']]
    got=groups['FEASIBLE']+groups['INFEASIBLE']
    require(len(got)==len(set(got))==42301 and set(got)==set(ids),'Exact complete new ID set')
    for key in ('account_executed','orders_executed','point_in_time_verified','promotion_allowed','economic_winner_selected','automatic_retry_allowed','old_tasks_reevaluated','runtime_binary_closure_verified','continuous_source_monitoring_claimed'):
        require(result[key] is False,'Recovery scope remains research')

def validate_first(first,completion,started,tasks,descriptor,context,raw,helper,pure,external):
    require(first['schema']=='CASH_NEIGHBOR_SHARD_INDEPENDENT_READBACK_V1' and first['status']=='PASS' and first['reader_sha256']==HELPER_SHA,'Previously independent first report')
    exact(first['descriptor'],descriptor,'First original descriptor');exact(first['task_count'],532,'First532');exact(first['new_arithmetic_checked_count'],531,'Prior531 arithmetic')
    exact(first['outcome_counts'],dict(FEASIBLE=98,INFEASIBLE=433,EVALUATION_EXCEPTION=0,VALIDATION_FAILURE=0,EXTERNALLY_REFERENCED=1),'First outcomes')
    require(first['all_completed_prefix_arithmetic_checked_in_this_report'] is True and first['existing_first_arithmetic_recomputed'] is False,'Reused first scope')
    helper.flags(first);helper.flags(completion);helper.flags(started)
    exact(completion['descriptor'],descriptor,'First saved descriptor');exact(completion['context_sha256'],context,'First context')
    exact(started['descriptor'],descriptor,'First start descriptor');exact(started['context_sha256'],context,'First start context')
    exact(started['ordered_task_ids'],[task['task_id'] for task in tasks],'First ordered source tasks')
    exact([row['task_id'] for row in first['task_results']],started['ordered_task_ids'],'First audit ordered IDs')
    exact(completion['outcome_counts'],first['outcome_counts'],'Saved first outcome counts')
    exact(completion['journal_reference']['sha256'],sha(raw),'First original journal hash')
    rows=pure.records(raw,recovery=False,context=context)
    exact(completion['record_index'],[locator for row,locator in rows],'First complete byte index')
    exact(completion['record_count'],len(rows),'First record count')
    require(rows[0][0]['task_id']==helper.FIRST_ID and rows[0][0]['stage']=='EXTERNAL_REFERENCE','First original external reference')
    exact(rows[0][0]['payload'],external,'First four independent evidence references')
    require(len(rows)==1+531*3,'First full journal stages')
    for position,row in enumerate(first['task_results']):
        require(row['new_arithmetic_checked'] is (position!=0),'Prior arithmetic role')
        if position==0:require(row['outcome']=='EXTERNALLY_REFERENCED','Single original first');continue
        group=rows[1+(position-1)*3:1+position*3]
        exact([item['stage'] for item,loc in group],['TASK_STARTED','RAW_RETURNED','POSTCHECK'],'First saved triplet')
        for item,loc in group:exact(item['task_position'],position,'First original position');exact(item['task_id'],row['task_id'],'First record identity')
        exact(group[2][0]['payload']['outcome'],row['outcome'],'Previously audited outcome')
        exact(group[2][0]['payload']['original_target_stock_weight_l1'],row['original_target_stock_weight_l1'],'Previously audited score')
    return [dict(row,source_kind='ORIGINAL_FIRST_AUDIT_REUSED',arithmetic_recomputed_in_this_run=False) for row in first['task_results']]

def run(*,registration_reference=None,execute=False):
    require(execute is True,'Explicit independent readback');valid(registration_reference)
    require(REGISTRATION_SHA is not None and registration_reference['sha256']==REGISTRATION_SHA,'Pending final external registration')
    valid(ref(PURE,PURE_SHA));require(not OUTPUT.exists(),'Create-only full audit namespace')
    helper=private(HELPER,HELPER_SHA);pure=private(PURE,PURE_SHA);oracle=helper.fresh_oracle()
    bindings={str(SOURCE):LOADED,str(HELPER):HELPER_SHA,str(PURE):PURE_SHA}
    def read(reference,maximum=128*1024**2):
        valid(reference);merge_bindings(bindings,{reference['path']:reference['sha256']})
        return load_bytes(reference,maximum_bytes=maximum)
    def document(reference,maximum=128*1024**2):return helper.decode(read(reference,maximum))
    external_registration=document(registration_reference)
    require(external_registration['schema']=='CASH_COMBINED_SOURCE_REGISTRATION_V1','External registration schema')
    exact(external_registration['domain'],dict(original_task_count=301657,logical_shard_count=324,recovery_task_count=42301,recovery_segment_count=45,old_candidate_count=2648,selection_union_candidate_count=304305),'Explicit full external registration domain')
    for key in FLAGS:require(external_registration[key] is False,'External research scope')
    refs=external_registration['references'];require(set(refs)=={'partition','sidecar','recovery_registration','recovery_result','first_audit'},'Exact external role set')
    exact(refs['partition'],ref(PARTITION,PARTITION_SHA),'Actual interrupted partition');exact(refs['sidecar'],ref(SIDECAR,SIDECAR_SHA),'Actual saved raw sidecar');exact(refs['first_audit'],ref(FIRST,FIRST_SHA),'Existing first audit')
    require(Path(refs['recovery_registration']['path'])==RECOVERY/'registration.json' and Path(refs['recovery_result']['path'])==RECOVERY/'request-0000/result.json','Fixed recovery attempt')
    partition=document(refs['partition']);sidecar=document(refs['sidecar']);recovery=document(refs['recovery_registration']);result=document(refs['recovery_result']);first=document(refs['first_audit'])
    require(partition['schema']=='CASH_NEIGHBOR_INTERRUPTED_PARTITION_V1' and partition['status']=='SAVED_STAGES_ONLY_NO_DISPATCH_AUTHORITY','Interrupted snapshot role')
    exact(sidecar['partition_reference'],refs['partition'],'Sidecar parent');exact(recovery['partition_reference'],refs['partition'],'Recovery partition');exact(recovery['sidecar_reference'],refs['sidecar'],'Recovery raw postcheck')
    require(recovery['schema']=='CASH_NEIGHBOR_RECOVERY_REGISTRATION_V1','Recovery registration schema')
    runtime=recovery['runtime_identity']
    require(set(runtime)=={'python_version','python_implementation','executable','platform','machine','runtime_binary_closure_verified'} and runtime['runtime_binary_closure_verified'] is False and all(type(v) is str and v for k,v in runtime.items() if k!='runtime_binary_closure_verified'),'Observed runtime identity only')
    for doc in (partition,sidecar,recovery,first):merge_bindings(bindings,doc['source_hashes'])
    require(recovery['source_hashes'].get(str(WORKER))==WORKER_SHA and recovery['source_hashes'].get(str(RECOVERY_PURE))==RECOVERY_PURE_SHA,'Actual worker and original domain code anchors')
    merge_bindings(bindings,helper.producer_sources());guard(bindings)
    parent_refs={key:ref(path,digest) for key,(path,digest) in helper.BOUND.items()}
    parents={key:document(value) for key,value in parent_refs.items()}
    prep=parents['preparation'];pub=parents['publication'];audit=parents['audit']
    require(pub['status']=='PUBLISHED_UNEVALUATED_CANDIDATES_ONLY' and audit['status']=='PASS','Prepared domain independently available')
    exact(pub['preparation_reference'],parent_refs['preparation'],'Preparation publication');exact(audit['preparation_reference'],parent_refs['preparation'],'Preparation audit');exact(audit['publication_reference'],parent_refs['publication'],'Preparation publication audit')
    for value in prep['input_references'].values():read(value)
    merge_bindings(bindings,prep['source_hashes']);guard(bindings)
    queue=helper.queue_from_preparation(prep);ids_by_shard=[]
    for descriptor in queue:
        tasks=[helper.decode(line) for line in read(ref(descriptor['shard']['path'],descriptor['shard']['sha256'])).splitlines()]
        require(len(tasks)==descriptor['global_task_stop']-descriptor['global_task_start'],'Complete task source file')
        ids_by_shard.append([task['task_id'] for task in tasks])
    domain=expected_domain(queue,ids_by_shard,partition,sidecar);exact(recovery['domain'],domain,'Independent complete recovery domain')
    validate_recovery_result(result,refs['recovery_registration'],domain['segments'])
    recovery_inventory=inventory(RECOVERY)
    require(recovery_inventory==sorted(['registration.json','request-0000/started.json','request-0000/result.json']+[f'segment-{i:04d}/{name}' for i in range(45) for name in ('started.json','journal.jsonl','completion.json')]),'Exact successful recovery namespace')
    request=document(result['started_reference']);exact(result['started_reference']['path'],str(RECOVERY/'request-0000/started.json'),'Request-start path');exact(request['registration_reference'],refs['recovery_registration'],'Original recovery request')
    for saved in (recovery,request):
        for key in ('account_executed','orders_executed','point_in_time_verified','promotion_allowed','economic_winner_selected','automatic_retry_allowed','old_tasks_reevaluated','continuous_source_monitoring_claimed','runtime_binary_closure_verified'):require(saved[key] is False,'Recovery registration and request scope')
    batch_path=helper.BATCH/'started.json';batch=document(ref(batch_path,partition['source_hashes'][str(batch_path)]));context=batch['context_sha256'];exact(sha(encode(batch['context'])),context,'Original saved execution context')
    exact(batch['context']['input_references'],parent_refs,'Original input context')
    runtime=batch['context']['runtime']
    require(type(runtime) is dict and set(runtime)=={'python','implementation','executable','platform'} and all(type(value) is str and value for value in runtime.values()),'Saved runtime identity only')
    expected_context=dict(schema='CASH_NEIGHBOR_SHARD_EXECUTION_CONTEXT_V1',input_references=parent_refs,source_hashes=helper.producer_sources(),scenario_count=40,shard_count=324,task_count=301657,new_call_count=301656,externally_referenced_task_id=helper.FIRST_ID,runtime=runtime,rule='ORIGINAL_PREPARATION_ORDER_ONE_EXPLICIT_CALL_PER_NEW_TASK',minimum_free_bytes=5*1024**3,**dict.fromkeys(helper.FALSE,False))
    exact(batch['context'],expected_context,'Independent original context source graph')
    original_inventory=inventory(helper.BATCH);exact(original_inventory,recovery['original_inventory'],'Unchanged original namespace')
    expected_old=sorted(Path(path).relative_to(helper.BATCH).as_posix() for path in partition['source_hashes'] if Path(path).is_relative_to(helper.BATCH));exact(original_inventory,expected_old,'Complete original namespace snapshot')
    old_refs=[];old_total=0
    for row in prep['rows']:
        contract=document(row['contract_reference']);points=contract['contract']['old_evaluated_points'];exact(len(points),row['old_evaluated_point_count'],'Original candidate count')
        old_refs.append(dict(scenario_id=row['scenario_id'],contract_reference=row['contract_reference'],old_points=[dict(candidate_index=index,reference=point['reference']) for index,point in enumerate(points)]));old_total+=len(points)
    exact(old_total,2648,'Preserved old candidates excluded from new domain')
    guard(bindings);OUTPUT.mkdir(parents=True,exist_ok=False)
    own_started=save(OUTPUT/'started.json',dict(schema='CASH_COMBINED_AUDIT_STARTED_V1',registration_reference=registration_reference,reader_sha256=LOADED,**FLAGS))
    reports=[];counts=dict(FEASIBLE=0,INFEASIBLE=0,EXTERNALLY_REFERENCED=0);new_groups={key:[] for key in result['partition']['task_ids_by_status']}
    old_groups={key:[] for key in partition['task_ids_by_saved_status']}
    old_groups['UNDISPATCHED']=[task for segment in domain['segments'] for task in segment['task_ids']]
    try:
        for index,descriptor in enumerate(queue):
            prepared=document(descriptor['contract_reference']);tasks=[helper.decode(line) for line in read(ref(descriptor['shard']['path'],descriptor['shard']['sha256'])).splitlines()]
            require(sha(encode(prepared['contract']))==prepared['contract_sha256'],'Full original contract')
            rows=[];evidence={}
            if index<279:
                folder=helper.BATCH/f'scenario-{descriptor["scenario_index"]:02d}-shard-{descriptor["shard_index"]:05d}'
                cp=ref(folder/'completion.json',partition['source_hashes'][str(folder/'completion.json')]);completion=document(cp)
                started=document(completion['started_reference']);raw=read(completion['journal_reference'])
                require(Path(completion['started_reference']['path'])==folder/'started.json' and Path(completion['journal_reference']['path'])==folder/'journal.jsonl','Original artifact paths')
                external={key:parent_refs[key] for key in ('first_started','first_raw','first_postcheck','first_audit')}
                if index==0:
                    exact(first['completion_reference'],cp,'First completion external anchor');exact(first['journal_reference'],completion['journal_reference'],'First journal audit');exact(first['started_reference'],completion['started_reference'],'First start audit')
                    rows=validate_first(first,completion,started,tasks,descriptor,context,raw,helper,pure,external)
                else:
                    detail=helper.inspect_complete_shard(started=started,completion=completion,journal_bytes=raw,tasks=tasks,prepared=prepared,descriptor=descriptor,context_sha256=context,external_references=external,independent_result=oracle)
                    rows=[dict(row,source_kind='ORIGINAL_COMPLETE_JOURNAL',raw_record_locator=completion['record_index'][3*position+1]) for position,row in enumerate(detail['task_results'])]
                for row in rows:old_groups[row['outcome']].append(row['task_id'])
                evidence=dict(completion_reference=cp,started_reference=completion['started_reference'],journal_reference=completion['journal_reference'])
            if index==279:
                folder=helper.BATCH/f'scenario-{descriptor["scenario_index"]:02d}-shard-{descriptor["shard_index"]:05d}'
                rawref=ref(folder/'journal.jsonl',partition['source_hashes'][str(folder/'journal.jsonl')]);raw=read(rawref)
                prefix=pure.inspect_span(raw=raw,tasks=tasks,prepared=prepared,descriptor=descriptor,start=0,stop=163,context=context,recovery=False,arguments=helper.task_arguments,independent_result=oracle,expected_detail=helper.expected_detail,sidecar=sidecar)
                rows=prefix['task_results']
                for row in rows[:-1]:old_groups[row['outcome']].append(row['task_id'])
                old_groups['RAW_SAVED_POSTCHECK_MISSING'].append(rows[-1]['task_id'])
                evidence=dict(original_partial_journal_reference=rawref,sidecar_reference=refs['sidecar'])
            if index>=279:
                segment=domain['segments'][index-279];cp=result['completed_segment_references'][index-279];completion=document(cp)
                require(completion['schema']=='CASH_NEIGHBOR_RECOVERY_SEGMENT_V1' and completion['status']=='COMPLETE_PENDING_INDEPENDENT_READBACK','Complete segment only');exact(completion['segment'],segment,'Full original segment');exact(completion['registration_sha256'],refs['recovery_registration']['sha256'],'Registered segment');exact(completion['error'],None,'No segment error')
                folder=RECOVERY/f'segment-{index-279:04d}';require(Path(completion['started_reference']['path'])==folder/'started.json' and Path(completion['journal_reference']['path'])==folder/'journal.jsonl','Original segment files')
                started=document(completion['started_reference']);exact(started['segment'],segment,'Saved segment start');exact(started['registration_sha256'],refs['recovery_registration']['sha256'],'Saved segment registration')
                raw=read(completion['journal_reference']);checked=pure.inspect_span(raw=raw,tasks=tasks,prepared=prepared,descriptor=descriptor,start=segment['original_task_start'],stop=segment['original_task_stop'],context=refs['recovery_registration']['sha256'],recovery=True,arguments=helper.task_arguments,independent_result=oracle,expected_detail=helper.expected_detail)
                expected_inspection=dict(terminal_rows=[dict(task_id=row['task_id'],original_task_position=segment['original_task_start']+offset,status=row['outcome'],raw_stage='RAW_RETURNED') for offset,row in enumerate(checked['task_results'])],active=None,tail=None,record_count=3*len(checked['task_results']),byte_count=len(raw),undispatched_task_ids=[],complete=True,journal_sha256=sha(raw),evaluator_called=False)
                exact(completion['inspection'],expected_inspection,'Independent complete saved segment partition')
                for saved in (completion,started):
                    for flag in ('account_executed','orders_executed','point_in_time_verified','promotion_allowed','economic_winner_selected','automatic_retry_allowed','old_tasks_reevaluated','continuous_source_monitoring_claimed','runtime_binary_closure_verified'):
                        require(saved[flag] is False,'Saved recovery authority')
                for row in checked['task_results']:new_groups[row['outcome']].append(row['task_id'])
                rows.extend(checked['task_results']);evidence['recovery_completion_reference']=cp;evidence['recovery_journal_reference']=completion['journal_reference']
            consume_block(rows,ids_by_shard[index],counts)
            reports.append(save(OUTPUT/f'shard-{index:05d}.json',dict(schema='CASH_COMBINED_LOGICAL_SHARD_AUDIT_V1',status='PASS',original_shard_index=index,descriptor=descriptor,task_count=len(rows),task_results=rows,evidence=evidence,**FLAGS)))
        exact(old_groups,partition['task_ids_by_saved_status'],'Independent original saved categories')
        exact(new_groups,result['partition']['task_ids_by_status'],'Independent new point outcomes and original order')
        require(sum(counts.values())==301657 and counts['EXTERNALLY_REFERENCED']==1,'Complete original coverage')
        guard(bindings);exact(inventory(helper.BATCH),original_inventory,'Final original namespace');exact(inventory(RECOVERY),recovery_inventory,'Final recovery namespace');require(len(reports)==324,'Complete324 reports')
        final=dict(schema='CASH_NEIGHBOR_COMBINED_INDEPENDENT_READBACK_V1',status='PASS',reader_sha256=LOADED,registration_reference=registration_reference,source_hashes=bindings,logical_shard_reports=reports,task_count=301657,outcome_counts=counts,physical_recovery_segment_count=45,new_dispatch_count=42301,previously_audited_arithmetic_reused_count=531,existing_external_original_task_count=1,arithmetic_checked_in_this_run=301125,sidecar_raw_arithmetic_rechecked_count=1,old_candidate_count=2648,old_candidate_references=old_refs,selection_union_candidate_count=304305,**FLAGS)
        answer=save(OUTPUT/'independent_readback.json',final);guard(bindings)
        verify_saved_outputs([own_started,*reports,answer])
        exact(inventory(OUTPUT),sorted(['started.json','independent_readback.json']+[f'shard-{i:05d}.json' for i in range(324)]),'Exact successful audit namespace')
        return answer
    except BaseException as error:
        save(OUTPUT/'failure.json',dict(status='FAILED_COMBINED_AUDIT_DO_NOT_CONSUME',error_type=type(error).__name__,error=str(error),**FLAGS));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--registration-path');parser.add_argument('--registration-sha');args=parser.parse_args()
    print(json.dumps(run(registration_reference=ref(args.registration_path,args.registration_sha),execute=args.execute)))
