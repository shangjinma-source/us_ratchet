"""Bounded scoring journal encoding/recovery only; never execute or truncate."""
import hashlib,json,re
ZERO='0'*64
STAGES=('TASK_STARTED','INPUTS','FIT_DISPATCH','RAW_FIT','SCORE_DISPATCH','RAW_SCORE','INSPECTION','POSTCHECK','EXTERNAL_REFERENCE')
TRANSITIONS={None:('TASK_STARTED','EXTERNAL_REFERENCE'),'TASK_STARTED':('INPUTS','POSTCHECK'),'INPUTS':('FIT_DISPATCH','POSTCHECK'),'FIT_DISPATCH':('RAW_FIT','POSTCHECK'),'RAW_FIT':('SCORE_DISPATCH','POSTCHECK'),'SCORE_DISPATCH':('RAW_SCORE','POSTCHECK'),'RAW_SCORE':('INSPECTION','POSTCHECK'),'INSPECTION':('POSTCHECK',)}
OUTCOMES=('SCORED_PENDING_INDEPENDENT_READBACK','NUMERICAL_EXCEPTION','VALIDATION_FAILURE','RESOURCE_STOP_AFTER_START','SOURCE_BLOCKED')


def require(ok,msg):
    if not ok:raise ValueError(msg)
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(encode(v)).hexdigest()
def make_record(*,sequence,previous_hash,context_sha256,task_id,task_position,stage,payload):
    require(type(sequence) is int and sequence>=0 and type(task_position) is int and task_position>=0,'Exact sequence and position')
    for v in (previous_hash,context_sha256,task_id):require(type(v) is str and re.fullmatch('[a-f0-9]{64}',v),'Explicit SHA')
    require(stage in STAGES and type(payload) is dict,'Known stage/payload')
    row=dict(schema='REGISTERED_SCORING_JOURNAL_RECORD_V1',sequence=sequence,previous_record_sha256=previous_hash,context_sha256=context_sha256,task_id=task_id,task_position=task_position,stage=stage,payload=payload)
    return dict(row,record_sha256=digest(row))


def inspect_journal(raw,*,context_sha256,ordered_task_ids):
    require(type(raw) is bytes and type(ordered_task_ids) is list and 0<len(ordered_task_ids)<=32 and len(set(ordered_task_ids))==len(ordered_task_ids),'Bounded32 original task order')
    previous=ZERO;offset=0;records=[];tasks=[];active=None;tail=None
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b'\n'):
            tail=dict(byte_start=offset,byte_count=len(line),sha256=hashlib.sha256(line).hexdigest(),reason='INCOMPLETE_RECORD_NOT_TRUNCATED');break
        def pairs(items):
            result={}
            for k,v in items:require(k not in result,'Duplicate key');result[k]=v
            return result
        row=json.loads(line,object_pairs_hook=pairs)
        expected=make_record(sequence=len(records),previous_hash=previous,context_sha256=context_sha256,task_id=row['task_id'],task_position=row['task_position'],stage=row['stage'],payload=row['payload'])
        require(encode(expected)+b'\n'==line,'Canonical exact typed hash chain')
        position=len(tasks);require(position<len(ordered_task_ids) and row['task_position']==position and row['task_id']==ordered_task_ids[position],'Full task prefix order')
        stage=row['stage'];prior=None if active is None else active['last_stage'];require(stage in TRANSITIONS[prior],'No skipped/repeated dispatch phase')
        if active is None:active=dict(task_id=row['task_id'],task_position=position,record_indexes=[],status='UNRESOLVED_DISPATCH',fit_dispatch_observed=False,score_dispatch_observed=False)
        active['record_indexes'].append(len(records));active['last_stage']=stage
        if stage=='FIT_DISPATCH':active['fit_dispatch_observed']=True
        if stage=='SCORE_DISPATCH':
            require(active.get('fit_returned') is True,'Score cannot run without returned fit');active['score_dispatch_observed']=True
        if stage in ('RAW_FIT','RAW_SCORE'):
            value=row['payload'];require(value['call_invoked'] is True and type(value['returned']) is bool and type(value['returned_call_count']) is int and value['returned_call_count']==int(value['returned']),'Actual call/return evidence')
            require(value['internal_optimizer_call_count'] is None,'Unknown internal optimizer calls')
            active['fit_returned' if stage=='RAW_FIT' else 'score_returned']=value['returned']
        if stage=='INSPECTION':
            require(active.get('score_returned') is True,'Inspection follows returned score')
            active['inspection_passed']=row['payload']['inspection'].get('status')=='PASS'
        if stage=='POSTCHECK':
            outcome=row['payload']['outcome'];require(outcome in OUTCOMES,'Known terminal outcome')
            if outcome=='SCORED_PENDING_INDEPENDENT_READBACK':require(prior=='INSPECTION' and active.get('fit_returned') is True and active.get('score_returned') is True and active.get('inspection_passed') is True,'Only complete independently checked lifecycle is scored')
            active['status']=outcome;tasks.append(active);active=None
        elif stage=='EXTERNAL_REFERENCE':active['status']='EXTERNALLY_REFERENCED';tasks.append(active);active=None
        records.append(dict(sequence=len(records),byte_start=offset,byte_stop=offset+len(line),record_sha256=row['record_sha256'],task_id=row['task_id'],stage=stage));previous=row['record_sha256'];offset+=len(line)
    completed=len(tasks)
    if active is not None:tasks.append(active)
    elif tail is not None and completed<len(ordered_task_ids):tasks.append(dict(task_id=ordered_task_ids[completed],task_position=completed,status='UNRESOLVED_DISPATCH',record_indexes=[],reason='UNKNOWN_PARTIAL_RECORD'))
    return dict(schema='REGISTERED_SCORING_JOURNAL_RECOVERY_V1',journal_sha256=hashlib.sha256(raw).hexdigest(),byte_count=len(raw),valid_prefix_byte_count=offset,record_count=len(records),records=records,tasks=tasks,tail=tail,last_record_sha256=previous,complete=active is None and tail is None and completed==len(ordered_task_ids),undispatched_task_ids=ordered_task_ids[len(tasks):],unresolved_task_ids=[t['task_id'] for t in tasks if t['status']=='UNRESOLVED_DISPATCH'],automatic_retry_allowed=False,bytes_truncated=False,executor_called=False)
