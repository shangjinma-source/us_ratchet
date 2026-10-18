"""Append-only journal encoding and read-only recovery classification. No evaluator."""
import hashlib,json
ZERO='0'*64
STAGES=('TASK_STARTED','RAW_RETURNED','RAW_EXCEPTION','POSTCHECK','EXTERNAL_REFERENCE')
OUTCOMES=('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE')
def require(ok,message):
    if not ok:raise ValueError(message)
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(encode(v)).hexdigest()
def make_record(*,sequence,previous_hash,context_sha256,task_id,task_position,stage,payload):
    require(type(sequence) is int and sequence>=0 and stage in STAGES,'Record sequence/stage')
    for h in (previous_hash,context_sha256,task_id):require(type(h) is str and len(h)==64 and all(c in '0123456789abcdef' for c in h),'Record SHA')
    require(type(task_position) is int and task_position>=0,'Exact task position')
    row=dict(schema='CASH_NEIGHBOR_JOURNAL_RECORD_V1',sequence=sequence,previous_record_sha256=previous_hash,context_sha256=context_sha256,task_id=task_id,task_position=task_position,stage=stage,payload=payload)
    return dict(row,record_sha256=digest(row))
def inspect_journal(raw,*,context_sha256,ordered_task_ids):
    require(type(raw) is bytes and type(ordered_task_ids) is list and len(set(ordered_task_ids))==len(ordered_task_ids),'Original bytes and unique task order')
    previous=ZERO;offset=0;records=[];tasks=[];active=None;tail=None
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b'\n'):
            tail=dict(byte_start=offset,byte_count=len(raw)-offset,sha256=hashlib.sha256(raw[offset:]).hexdigest(),reason='INCOMPLETE_FINAL_RECORD');break
        try:
            def pairs(items):
                d={}
                for k,v in items:require(k not in d,'Duplicate key');d[k]=v
                return d
            row=json.loads(line,object_pairs_hook=pairs);body={k:v for k,v in row.items() if k!='record_sha256'}
            require(row==make_record(sequence=len(records),previous_hash=previous,context_sha256=context_sha256,task_id=row['task_id'],task_position=row['task_position'],stage=row['stage'],payload=row['payload']),'Exact chained record')
            require(encode(row)+b'\n'==line and digest(body)==row['record_sha256'],'Canonical exact bytes/hash')
            position=len(tasks);require(position<len(ordered_task_ids) and row['task_position']==position and type(row['task_position']) is int and row['task_id']==ordered_task_ids[position],'Fixed full task order')
            stage=row['stage']
            if active is None:
                require(stage in ('TASK_STARTED','EXTERNAL_REFERENCE'),'Task begins explicitly')
                active=dict(task_id=row['task_id'],task_position=position,record_indexes=[],status='UNRESOLVED_DISPATCH')
            else:require(stage in (('RAW_RETURNED','RAW_EXCEPTION') if active['status']=='UNRESOLVED_DISPATCH' else ('POSTCHECK',)),'Exactly ordered task stages')
            active['record_indexes'].append(len(records))
            if stage in ('RAW_RETURNED','RAW_EXCEPTION'):active['status']='RAW_SAVED_POSTCHECK_MISSING';active['raw_stage']=stage
            elif stage=='POSTCHECK':
                outcome=row['payload']['outcome'];require(outcome in OUTCOMES,'Terminal outcome');require(active['raw_stage']!='RAW_EXCEPTION' or outcome in ('EVALUATION_EXCEPTION','VALIDATION_FAILURE'),'Exception is not infeasible');require(active['raw_stage']!='RAW_RETURNED' or outcome!='EVALUATION_EXCEPTION','Returned result is not evaluator exception');active['status']=outcome;tasks.append(active);active=None
            elif stage=='EXTERNAL_REFERENCE':active['status']='EXTERNALLY_REFERENCED';tasks.append(active);active=None
            records.append(dict(sequence=len(records),byte_start=offset,byte_stop=offset+len(line),record_sha256=row['record_sha256'],task_id=row['task_id'],stage=stage));previous=row['record_sha256'];offset+=len(line)
        except (ValueError,KeyError,TypeError) as error:
            raise ValueError('Corrupt complete journal record at byte '+str(offset)) from error
    if active is not None:tasks.append(active)
    elif tail is not None and len(tasks)<len(ordered_task_ids):
        tasks.append(dict(task_id=ordered_task_ids[len(tasks)],task_position=len(tasks),record_indexes=[],status='UNRESOLVED_DISPATCH',reason='UNKNOWN_PARTIAL_RECORD'))
    return dict(schema='CASH_NEIGHBOR_JOURNAL_RECOVERY_V1',journal_sha256=hashlib.sha256(raw).hexdigest(),byte_count=len(raw),valid_prefix_byte_count=offset,record_count=len(records),tail=tail,records=records,tasks=tasks,last_record_sha256=previous,undispatched_task_ids=ordered_task_ids[len(tasks):],complete=tail is None and active is None and len(tasks)==len(ordered_task_ids),recovery_calls_evaluator=False,tail_truncated_or_overwritten=False)
