"""Exact original-position recovery domain and append-only journal, no economics."""
import hashlib
import json

STAGES = ('TASK_STARTED','RAW_RETURNED','RAW_EXCEPTION','POSTCHECK')
TERMINAL = ('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE')
SAVED = ('FEASIBLE','INFEASIBLE','EXTERNALLY_REFERENCED','RAW_SAVED_POSTCHECK_MISSING','UNRESOLVED_DISPATCH','UNDISPATCHED')

def require(ok,message):
    if not ok:
        raise ValueError(message)

def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()

def exact(left,right,message):
    require(encode(left)==encode(right),message)

def build_recovery_segments(queue, task_ids_by_shard, partition, sidecar):
    require(type(queue) is list and len(queue)==324 and type(task_ids_by_shard) is list and len(task_ids_by_shard)==324,'All original shards')
    original=[];position=0
    for index,(descriptor,ids) in enumerate(zip(queue,task_ids_by_shard)):
        exact(descriptor['global_shard_index'],index,'Original shard index')
        exact(descriptor['global_task_start'],position,'Original global start')
        require(type(ids) is list and ids,'Full task shard')
        position+=len(ids)
        exact(descriptor['global_task_stop'],position,'Original global stop')
        require(type(descriptor['shard']['start']) is int and type(descriptor['shard']['stop']) is int and 0<=descriptor['shard']['start']<descriptor['shard']['stop'],'Exact nonnegative original ordinals')
        exact(descriptor['shard']['stop']-descriptor['shard']['start'],len(ids),'Original ordinal range')
        require(all(type(i) is str and len(i)==64 and all(c in '0123456789abcdef' for c in i) for i in ids),'SHA task ids')
        original.extend(ids)
    require(position==301657 and len(set(original))==position,'Unique complete original domain')
    groups=partition['task_ids_by_saved_status']
    require(set(groups)==set(SAVED) and all(type(v) is list for v in groups.values()),'All saved status categories')
    combined=[i for values in groups.values() for i in values]
    require(len(combined)==len(set(combined))==len(original) and set(combined)==set(original),'Disjoint exhaustive full ID partition')
    exact(partition['counts'],{k:len(v) for k,v in groups.items()},'Exact partition counts')
    require(groups['UNRESOLVED_DISPATCH']==[] and len(groups['RAW_SAVED_POSTCHECK_MISSING'])==1,'Only saved raw pending')
    pending=groups['RAW_SAVED_POSTCHECK_MISSING'][0]
    require(sidecar['status']=='PASS_SAVED_RAW_ARITHMETIC_ONLY' and sidecar['saved_arithmetic_independently_verified'] is True and sidecar['task_id']==pending,'Independent saved raw sidecar')
    require(sidecar['independent_postcheck']['outcome'] in ('FEASIBLE','INFEASIBLE'),'Resolved arithmetic outcome')
    require(sidecar['evaluator_called'] is False and sidecar['dispatch_authorized'] is False and partition['dispatch_authorized'] is False,'No inherited dispatch authority')
    exact(sidecar['global_task_position'],259355,'Original pending position')
    require(original[259355]==pending,'Actual pending ID at original position')
    exact(groups['UNDISPATCHED'],original[259356:],'Exact untouched suffix order')
    require(len(groups['UNDISPATCHED'])==42301,'Full recovery denominator')
    segments=[]
    for descriptor,ids in zip(queue,task_ids_by_shard):
        start=max(259356,descriptor['global_task_start'])
        stop=descriptor['global_task_stop']
        if start>=stop:
            continue
        local=start-descriptor['global_task_start']
        segments.append(dict(recovery_segment_index=len(segments),original_descriptor=descriptor,original_task_start=local,original_task_stop=len(ids),original_global_start=start,original_global_stop=stop,task_ids=ids[local:]))
    require(len(segments)==45 and segments[0]['original_descriptor']['global_shard_index']==279 and segments[0]['original_task_start']==163 and len(segments[0]['task_ids'])==837,'Original tail and 44 remaining shards')
    return dict(schema='CASH_NEIGHBOR_RECOVERY_DOMAIN_V1',original_task_count=len(original),excluded_previously_dispatched_count=259356,recovery_task_count=42301,segments=segments,ordered_recovery_task_ids_sha256=digest(groups['UNDISPATCHED']),dispatch_authorized=False)

def validate_segment(segment):
    require(type(segment) is dict and {'original_task_start','original_task_stop','task_ids','original_descriptor'} <= set(segment),'Segment object')
    begin=segment['original_task_start'];end=segment['original_task_stop']
    require(type(begin) is int and type(end) is int and 0<=begin<end,'Exact original positions')
    ids=segment['task_ids']
    require(type(ids) is list and len(ids)==len(set(ids))==end-begin,'Exact unique suffix IDs')
    require(all(type(i) is str and len(i)==64 and all(c in '0123456789abcdef' for c in i) for i in ids),'Exact SHA task IDs')
    descriptor=segment['original_descriptor']
    require(type(descriptor) is dict and {'global_task_start','global_task_stop','shard'} <= set(descriptor),'Full descriptor fields')
    require(type(descriptor['shard']) is dict and {'start','stop'} <= set(descriptor['shard']),'Full source ordinal fields')
    for value in (descriptor['global_task_start'],descriptor['global_task_stop'],descriptor['shard']['start'],descriptor['shard']['stop']):
        require(type(value) is int and value>=0,'Exact nonnegative source coordinates')
    require(descriptor['global_task_stop']-descriptor['global_task_start']==end and descriptor['shard']['stop']-descriptor['shard']['start']==end,'Full original descriptor range')

def hash_string(value):
    require(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),'Exact SHA256')

def make_record(*, sequence, previous_hash, registration_sha256, segment, task_position, stage, payload):
    validate_segment(segment);hash_string(previous_hash);hash_string(registration_sha256)
    require(type(sequence) is int and sequence>=0 and stage in STAGES,'Journal sequence and stage')
    require(type(task_position) is int and segment['original_task_start']<=task_position<segment['original_task_stop'],'Original task position')
    descriptor=segment['original_descriptor'];local=task_position-segment['original_task_start']
    value=dict(schema='CASH_NEIGHBOR_RECOVERY_RECORD_V1',record_sequence=sequence,previous_record_sha256=previous_hash,registration_sha256=registration_sha256,task_id=segment['task_ids'][local],original_shard_task_position=task_position,original_global_task_position=descriptor['global_task_start']+task_position,scenario_candidate_ordinal=descriptor['shard']['start']+task_position,stage=stage,payload=payload)
    return dict(value,record_sha256=digest(value))

def inspect_recovery_journal(raw, *, segment, registration_sha256):
    validate_segment(segment);hash_string(registration_sha256)
    require(type(raw) is bytes,'Original bytes')
    previous='0'*64;sequence=0;offset=0;completed=[];active=None;tail=None
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b'\n'):
            tail=dict(byte_start=offset,byte_count=len(raw)-offset,sha256=hashlib.sha256(raw[offset:]).hexdigest());break
        def pairs(items):
            out={}
            for k,v in items:
                require(k not in out,'Duplicate key');out[k]=v
            return out
        value=json.loads(line,object_pairs_hook=pairs)
        position=segment['original_task_start']+len(completed)
        require(position<segment['original_task_stop'],'No surplus task')
        expected=make_record(sequence=sequence,previous_hash=previous,registration_sha256=registration_sha256,segment=segment,task_position=position,stage=value['stage'],payload=value['payload'])
        require(encode(expected)+b'\n'==line,'Exact chained original-position record')
        stage=value['stage']
        if active is None:
            require(stage=='TASK_STARTED','One explicit dispatch before return')
            active=dict(task_id=value['task_id'],original_task_position=position,status='UNRESOLVED_DISPATCH')
        elif active['status']=='UNRESOLVED_DISPATCH':
            require(stage in ('RAW_RETURNED','RAW_EXCEPTION'),'Durable raw before validation')
            active.update(status='RAW_SAVED_POSTCHECK_MISSING',raw_stage=stage)
        else:
            require(stage=='POSTCHECK' and value['payload']['outcome'] in TERMINAL,'Exactly one terminal postcheck')
            outcome=value['payload']['outcome']
            require(active['raw_stage']!='RAW_EXCEPTION' or outcome=='EVALUATION_EXCEPTION','Exception never economic infeasible')
            require(active['raw_stage']!='RAW_RETURNED' or outcome!='EVALUATION_EXCEPTION','Returned raw not evaluator exception')
            active['status']=outcome;completed.append(active);active=None
            if outcome in ('EVALUATION_EXCEPTION','VALIDATION_FAILURE'):
                require(offset+len(line)==len(raw),'Technical stop cannot continue')
        previous=value['record_sha256'];sequence+=1;offset+=len(line)
    if tail is not None and active is None:
        position=segment['original_task_start']+len(completed)
        require(position<segment['original_task_stop'],'Unknown bytes after full segment')
        active=dict(task_id=segment['task_ids'][len(completed)],original_task_position=position,status='UNRESOLVED_DISPATCH')
    consumed=len(completed)+int(active is not None)
    return dict(terminal_rows=completed,active=active,tail=tail,record_count=sequence,byte_count=len(raw),undispatched_task_ids=segment['task_ids'][consumed:],complete=active is None and tail is None and len(completed)==len(segment['task_ids']),journal_sha256=hashlib.sha256(raw).hexdigest(),evaluator_called=False)
