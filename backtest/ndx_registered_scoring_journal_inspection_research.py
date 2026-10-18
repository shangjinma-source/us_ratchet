"""Independent bounded scoring journal evidence inspection; no execution or repair."""
from collections import Counter
from datetime import datetime
import base64,hashlib,json,re

FIRST='75ad5a6a98d6056d4f13962d31b43debc809d9d663f719639fd1ea5e80fd4598'
SUCCESS='SCORED_PENDING_INDEPENDENT_READBACK'
FAILURES=('NUMERICAL_EXCEPTION','VALIDATION_FAILURE','RESOURCE_STOP_AFTER_START','SOURCE_BLOCKED')
TRANSITIONS={None:('TASK_STARTED','EXTERNAL_REFERENCE'),'TASK_STARTED':('INPUTS','POSTCHECK'),'INPUTS':('FIT_DISPATCH','POSTCHECK'),'FIT_DISPATCH':('RAW_FIT','POSTCHECK'),'RAW_FIT':('SCORE_DISPATCH','POSTCHECK'),'SCORE_DISPATCH':('RAW_SCORE','POSTCHECK'),'RAW_SCORE':('INSPECTION','POSTCHECK'),'INSPECTION':('POSTCHECK',)}
FALSE=('automatic_retry_allowed','point_in_time_verified','promotion_allowed','account_executed','winner_selected','outer_lane_prior_applied','whole_lot_gate_evaluated','formal_benchmark_passed','full_transitive_source_closure_reverified','runtime_binary_closure_verified','continuous_source_monitoring_claimed')


def require(ok,m):
    if not ok:raise ValueError(m)
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,m):require(encode(a)==encode(b),m)
def hashtext(v):require(type(v) is str and re.fullmatch('[a-f0-9]{64}',v) is not None,'Canonical hash')
def loads(b):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def error_value(v):
    require(type(v) is dict and set(v)=={'type','message','traceback'} and all(type(x) is str for x in v.values()) and bool(v['type']),'Complete original error evidence')
def ref(r):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'] and r['path']==r['path'].strip(),'Exact external reference');hashtext(r['sha256'])


def inspect_scoring_journal(*,journal_bytes,context_sha256,expected_jobs,shard_index,expected_runtime,external_first_evidence):
    require(type(journal_bytes) is bytes,'Original journal bytes');hashtext(context_sha256)
    require(type(shard_index) is int and 0<=shard_index<306,'Registered shard index')
    require(type(expected_jobs) is list and 0<len(expected_jobs)<=32,'Full supplied shard slots')
    ids=[j['job_id'] for j in expected_jobs];require(len(set(ids))==len(ids),'Unique shard job IDs')
    for j in expected_jobs:
        hashtext(j['job_id']);require(j['registered_status']=='PLANNED_NOT_ATTEMPTED' and j['fx_mode']=='BACKWARD_LATEST_VALID_FX','Blocked strict jobs never dispatched')
    require(type(expected_runtime) is dict and set(expected_runtime)=={'python','numpy','pandas','scipy'} and all(type(v) is str and v for v in expected_runtime.values()),'Explicit runtime version contract')
    require(type(external_first_evidence) is dict and set(external_first_evidence)=={'postcheck','started','inputs','raw_fit','raw_score','score_inspection','independent_readback'},'Complete first external audit evidence')
    for r in external_first_evidence.values():ref(r)
    if FIRST in ids:require(shard_index==0 and ids[0]==FIRST,'Only first slot external reuse')
    metadata=dict(runtime=expected_runtime,environment=dict(PYTHONHASHSEED='0',sys_flags_hash_randomization=0))
    offset=0;previous='0'*64;records=[];tasks=[];active=None;tail=None;failure_seen=False
    for line in journal_bytes.splitlines(keepends=True):
        if not line.endswith(b'\n'):
            tail=dict(byte_start=offset,byte_count=len(line),sha256=sha(line),reason='INCOMPLETE_RECORD_NOT_TRUNCATED');break
        require(not failure_seen,'No task may follow a failed terminal in stopped shard')
        row=loads(line);require(type(row) is dict and set(row)=={'schema','sequence','previous_record_sha256','context_sha256','task_id','task_position','stage','payload','record_sha256'},'Exact journal envelope')
        require(row['schema']=='REGISTERED_SCORING_JOURNAL_RECORD_V1' and type(row['sequence']) is int and row['sequence']==len(records),'Contiguous exact sequence')
        require(type(row['task_position']) is int and row['task_position']==len(tasks)<len(ids) and row['task_id']==ids[len(tasks)],'Complete original task prefix')
        require(row['previous_record_sha256']==previous and row['context_sha256']==context_sha256,'Previous chain/context')
        hashtext(row['record_sha256']);require(row['record_sha256']==sha(encode({k:v for k,v in row.items() if k!='record_sha256'})) and line==encode(row)+b'\n','Canonical authenticated record bytes')
        stage=row['stage'];payload=row['payload'];prior=None if active is None else active['last_stage']
        require(type(stage) is str and stage in TRANSITIONS[prior] and type(payload) is dict,'Allowed evidence transition and body')
        if active is None:
            active=dict(task_id=row['task_id'],task_position=len(tasks),last_stage=None,record_indexes=[],record_references=[],fit_dispatch_observed=False,score_dispatch_observed=False,payloads={})
        if row['task_id']==FIRST:require(stage=='EXTERNAL_REFERENCE','Never reexecute already independently audited first job')
        if stage=='EXTERNAL_REFERENCE':
            require(row['task_id']==FIRST and shard_index==0 and row['task_position']==0,'Only known external first')
            exact(payload,external_first_evidence,'Original first seven external refs')
        elif stage=='TASK_STARTED':
            require(set(payload)=={'descriptor','started_at_utc','fit_call_invoked','score_call_invoked'},'Original task start')
            exact(payload['descriptor'],expected_jobs[len(tasks)],'Whole registered descriptor')
            require(payload['fit_call_invoked'] is False and payload['score_call_invoked'] is False,'Not yet dispatched')
            require(type(payload['started_at_utc']) is str and datetime.fromisoformat(payload['started_at_utc']).utcoffset().total_seconds()==0,'UTC attempt time declaration')
        elif stage=='INPUTS':
            # Worker persists returned input before validating it. Invalid JSON
            # bodies remain technical-failure evidence; dispatch gates below stay strict.
            require(set(payload)=={'assembled'},'Original assembler returned body retained')
        elif stage in ('FIT_DISPATCH','SCORE_DISPATCH'):
            exact(payload,metadata,'Original process runtime and hash seed')
            a=active['payloads']['INPUTS']['assembled']
            require(type(a) is dict and a.get('schema')=='REGISTERED_MULTIDECISION_SCORING_JOB_INPUTS_V1' and a.get('job_id')==row['task_id'] and a.get('status')=='ASSEMBLED_NOT_DISPATCHED','Dispatch only valid available inputs')
            require(a.get('content_sha256')==sha(encode({k:v for k,v in a.items() if k!='content_sha256'})),'Dispatched input content hash')
            for flag in ('source_bytes_authenticated','fit_performed','score_computed','dispatch_authorized','execution_authorized','point_in_time_verified','promotion_allowed'):require(a[flag] is False,'Inputs do not authorize execution')
            if stage=='SCORE_DISPATCH':
                fit=active['payloads']['RAW_FIT'];require(fit['returned'] is True and fit['result_preserved_as_json'] is True and type(fit['result']) is dict,'Score cannot follow exception or invalid fit body')
            active['fit_dispatch_observed' if stage=='FIT_DISPATCH' else 'score_dispatch_observed']=True
        elif stage in ('RAW_FIT','RAW_SCORE'):
            keys={'call_invoked','returned','returned_call_count','internal_optimizer_call_count','result','error','result_preserved_as_json','dispatch_metadata'}
            require(type(payload.get('result_preserved_as_json')) is bool,'Original JSON representation flag')
            if payload['result_preserved_as_json'] is False:keys|={'representation_utf8_base64','representation_sha256','serialization_error'}
            require(set(payload)==keys,'Complete raw returned body')
            require(payload['call_invoked'] is True and type(payload['returned']) is bool and type(payload['returned_call_count']) is int and payload['returned_call_count']==int(payload['returned']),'Exact call/return evidence')
            require(payload['internal_optimizer_call_count'] is None,'Unknown optimizer count remains unknown')
            exact(payload['dispatch_metadata'],active['payloads']['FIT_DISPATCH' if stage=='RAW_FIT' else 'SCORE_DISPATCH'],'Raw dispatch metadata')
            if payload['returned']:
                require(payload['error'] is None,'Returned value cannot also claim caught exception')
            else:
                require(payload['result'] is None,'Exception cannot invent returned value');error_value(payload['error'])
            if payload['result_preserved_as_json'] is False:
                require(payload['result'] is None and payload['returned'] is True,'Unserializable returned value retained separately')
                blob=base64.b64decode(payload['representation_utf8_base64'],validate=True);require(sha(blob)==payload['representation_sha256'],'Opaque failed JSON representation hash')
                require(type(payload['serialization_error']) is dict and set(payload['serialization_error'])=={'type','message'} and all(type(v) is str for v in payload['serialization_error'].values()),'Serialization error retained')
        elif stage=='INSPECTION':
            score=active['payloads']['RAW_SCORE'];require(score['returned'] is True and score['result_preserved_as_json'] is True and type(score['result']) is dict,'Inspection only after saved valid score body')
            require(set(payload)=={'inspection'},'Complete original inspection returned body')
        elif stage=='POSTCHECK':
            outcome=payload['outcome'];require(outcome==SUCCESS or outcome in FAILURES,'Explicit terminal category')
            exact(payload['record_references'],active['record_references'],'All prior task records in exact order')
            require(payload['whole_queue_completed'] is False,'One task cannot complete whole queue')
            for flag in FALSE:require(payload[flag] is False,'No post authority')
            if outcome==SUCCESS:
                require(set(payload)=={'outcome','record_references','whole_queue_completed',*FALSE} and prior=='INSPECTION','Full success lifecycle only')
                report=active['payloads']['INSPECTION']['inspection'];require(type(report) is dict and report.get('status')=='PASS','Only independently accepted score can claim success')
            else:
                require(set(payload)=={'outcome','failed_stage','error','record_references','whole_queue_completed',*FALSE},'Failure original evidence');error_value(payload['error'])
                require(payload['failed_stage'] in ('START','FIT','SCORE','INSPECTION'),'Explicit worker stage')
                if outcome=='NUMERICAL_EXCEPTION':require(prior in ('RAW_FIT','RAW_SCORE') and active['payloads'][prior]['returned'] is False,'Numerical exception requires actual failed call evidence')
                if outcome=='SOURCE_BLOCKED':require(prior=='INPUTS' and active['payloads']['INPUTS']['assembled']['status']=='SOURCE_BLOCKED','Source blocked is not numerical failure')
                failure_seen=True
        active['record_indexes'].append(len(records));active['last_stage']=stage
        active['payloads'][stage]=payload
        records.append(dict(sequence=len(records),byte_start=offset,byte_stop=offset+len(line),record_sha256=row['record_sha256'],task_id=row['task_id'],stage=stage))
        active['record_references'].append(dict(sequence=row['sequence'],record_sha256=row['record_sha256']))
        previous=row['record_sha256'];offset+=len(line)
        if stage in ('POSTCHECK','EXTERNAL_REFERENCE'):
            tasks.append(dict(task_id=active['task_id'],task_position=active['task_position'],status='EXTERNALLY_REFERENCED' if stage=='EXTERNAL_REFERENCE' else payload['outcome'],record_indexes=active['record_indexes'],fit_dispatch_observed=active['fit_dispatch_observed'],score_dispatch_observed=active['score_dispatch_observed'],numerical_arithmetic_independently_verified=False))
            active=None
    if active is not None:
        tasks.append(dict(task_id=active['task_id'],task_position=active['task_position'],status='UNRESOLVED_DISPATCH',record_indexes=active['record_indexes'],fit_dispatch_observed=active['fit_dispatch_observed'],score_dispatch_observed=active['score_dispatch_observed'],last_stage=active['last_stage'],numerical_arithmetic_independently_verified=False))
    elif tail is not None:
        require(len(tasks)<len(ids) and not failure_seen,'Unexpected tail after full or failed terminal')
        tasks.append(dict(task_id=ids[len(tasks)],task_position=len(tasks),status='UNRESOLVED_DISPATCH',record_indexes=[],reason='UNKNOWN_PARTIAL_RECORD',fit_dispatch_observed=False,score_dispatch_observed=False,numerical_arithmetic_independently_verified=False))
    counts=dict(Counter(t['status'] for t in tasks));undispatched=ids[len(tasks):];unresolved=[t['task_id'] for t in tasks if t['status']=='UNRESOLVED_DISPATCH']
    terminal=len(tasks)-len(unresolved)
    return dict(schema='REGISTERED_SCORING_JOURNAL_INDEPENDENT_INSPECTION_V1',journal_sha256=sha(journal_bytes),byte_count=len(journal_bytes),valid_prefix_byte_count=offset,record_count=len(records),last_record_sha256=previous,records=records,tasks=tasks,tail=tail,status_counts=counts,terminal_evidence_count=terminal,numerical_success_claim_count=counts.get(SUCCESS,0),external_reference_count=counts.get('EXTERNALLY_REFERENCED',0),undispatched_task_ids=undispatched,unresolved_task_ids=unresolved,whole_shard_terminal_evidence_complete=terminal==len(ids) and tail is None,whole_shard_numeric_success_claims_complete=terminal==len(ids) and tail is None and not failure_seen,numerical_arithmetic_independently_verified=False,source_bytes_authenticated=False,fit_performed=False,score_worker_called=False,automatic_retry_allowed=False,bytes_truncated=False,promotion_allowed=False)


def inspect_saved_success_numeric(*,journal_bytes,inspection,task_id,numerical_sources):
    """Optional second stage: original source bindings supplied by source wrapper.

    No producer is called; only frozen independent fit-evidence and score arithmetic.
    This does not authenticate caller-supplied source documents or optimization.
    """
    from backtest.ndx_registered_scoring_result_inspection_research import inspect_registered_scoring_result
    require(sha(journal_bytes)==inspection['journal_sha256'],'Same inspected journal bytes')
    matches=[t for t in inspection['tasks'] if t['task_id']==task_id]
    require(len(matches)==1 and matches[0]['status']==SUCCESS,'Only complete successful new job')
    values={}
    for number in matches[0]['record_indexes']:
        r=inspection['records'][number];row=loads(journal_bytes[r['byte_start']:r['byte_stop']]);require(row['record_sha256']==r['record_sha256'],'Saved byte locator')
        values[row['stage']]=row['payload']
    return inspect_registered_scoring_result(assembled=values['INPUTS']['assembled'],saved_fit=values['RAW_FIT']['result'],saved_score=values['RAW_SCORE']['result'],saved_score_inspection=values['INSPECTION']['inspection'],**numerical_sources)
