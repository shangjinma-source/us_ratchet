"""Explicit new-namespace suffix recovery. No old task may be dispatched again."""
import argparse
import ctypes
import hashlib
import json
import os
import platform
import sys
import shutil
from pathlib import Path
from types import ModuleType

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1]
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/cash_neighbor_recovery_20261008_v1'
PARTITION=ROOT/'data/cache/research/cash_neighbor_interrupted_partition_20261008_v1/partition.json'
PARTITION_SHA='3f88cd70bd62bcac4ccf9e756031e8353b788ef6575b23a4d6565d6a4a06f120'
SIDECAR=ROOT/'data/cache/research/cash_neighbor_saved_raw_postcheck_20261008_v1/independent_postcheck.json'
SIDECAR_SHA='ebe5a186043d4878ee3a7c3b0c570d8e1d876a072b1e3742372b39c56c63ede6'
PURE=ROOT/'backtest/ndx_cash_neighbor_recovery_partition_research.py'
PURE_SHA='b0265f556cdfdc5765ed69d0b52528d5470ce66f38bf80edded9c68dcd2a7b31'
ADAPTER=ROOT/'scripts/ndx_cash_topup_neighbor_single_evaluation_20261003.py'
ADAPTER_SHA='6328a40a4c07f90b10b120ef348f924cf7cfa0dda9b12e63a80939e183c651ba'
READER=ROOT/'scripts/ndx_cash_topup_neighbor_shard_independent_readback_20261003.py'
READER_SHA='39a7194291584195eed09d2b1e2d83f97cd9b53a20bd4858e192fd4ba4d728ad'
MIN_DISK=5*1024**3
MIN_RAM=2*1024**3
FLAGS=dict.fromkeys(('account_executed','orders_executed','point_in_time_verified','promotion_allowed','economic_winner_selected','automatic_retry_allowed','old_tasks_reevaluated','continuous_source_monitoring_claimed','runtime_binary_closure_verified'),False)

def require(ok,message):
    if not ok:raise ValueError(message)
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def exact(left,right,message):require(encode(left)==encode(right),message)
def reference(path,digest):return dict(path=str(path),sha256=digest)
def valid(digest):require(type(digest) is str and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'Bind SHA before IO')
def decode(raw):
    def pairs(items):
        result={}
        for k,v in items:require(k not in result,'Duplicate key');result[k]=v
        return result
    def reject(value):raise ValueError('Nonfinite JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=reject)
def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def guard(bindings):
    for path,digest in bindings.items():require(file_sha(path)==digest,'Source drift: '+path)
def merge_bindings(*maps):
    result={}
    for mapping in maps:
        require(type(mapping) is dict,'Source map object')
        for path,digest in mapping.items():
            require(type(path) is str and path,'Source path');valid(digest)
            require(path not in result or result[path]==digest,'Conflicting source binding: '+path)
            result[path]=digest
    return result

def runtime_identity():
    return dict(python_version=sys.version,python_implementation=platform.python_implementation(),executable=str(Path(sys.executable).resolve()),platform=platform.platform(),machine=platform.machine(),runtime_binary_closure_verified=False)

def read(path,digest):
    valid(digest);raw=Path(path).read_bytes();require(sha(raw)==digest,'Bound source');return raw
def load(path,digest):
    module=ModuleType('_cash_recovery_'+path.stem);module.__file__=str(path)
    exec(compile(read(path,digest),str(path),'exec'),module.__dict__);return module
def save(path,value):
    raw=encode(value)
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Durable exact bytes');return reference(path,sha(raw))
def available_memory():
    class Status(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in ('total','available','total_page','available_page','total_virtual','available_virtual','extended')]
    status=Status();status.length=ctypes.sizeof(status)
    require(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))!=0,'Available memory measurement')
    return status.available
def resource_gate(folder,input_bytes,*,disk_free=None,memory_free=None):
    disk=shutil.disk_usage(folder).free if disk_free is None else disk_free
    memory=available_memory() if memory_free is None else memory_free
    require(type(disk) is int and type(memory) is int and type(input_bytes) is int and input_bytes>=0,'Exact measured resource values')
    require(disk>=MIN_DISK and memory>=MIN_RAM+32*input_bytes,'RESOURCE_STOP_BEFORE_DISPATCH')
    return dict(disk_free=disk,memory_available=memory,minimum_disk=MIN_DISK,required_memory=MIN_RAM+32*input_bytes)

class Journal:
    def __init__(self,path,pure,segment,registration_sha):
        self.stream=path.open('xb');self.path=path;self.pure=pure;self.segment=segment;self.registration_sha=registration_sha;self.sequence=0;self.previous='0'*64
    def append(self,position,stage,payload):
        record=self.pure.make_record(sequence=self.sequence,previous_hash=self.previous,registration_sha256=self.registration_sha,segment=self.segment,task_position=position,stage=stage,payload=payload)
        # Chunked write retains any partial original return; never rewrite/truncate on failure.
        encoder=json.JSONEncoder(sort_keys=True,separators=(',',':'),allow_nan=False)
        buffer=bytearray()
        def write_chunk(chunk):
            require(shutil.disk_usage(self.path.parent).free>=len(chunk)+1024*1024,'RAW_WRITE_RESOURCE_FAILURE')
            self.stream.write(chunk)
        for part in encoder.iterencode(record):
            raw=part.encode()
            for start in range(0,len(raw),65536):
                buffer.extend(raw[start:start+65536])
                if len(buffer)>=65536:
                    write_chunk(buffer);buffer.clear()
        buffer.extend(b'\n')
        if buffer:write_chunk(buffer)
        self.stream.flush();os.fsync(self.stream.fileno())
        self.sequence+=1;self.previous=record['record_sha256']
    def close(self):self.stream.close()

def process_segment(*,folder,segment,tasks,prepared,registration_sha,pure,adapter,evaluate,verify,input_bytes):
    require(not folder.exists(),'Existing attempt cannot be repeated')
    folder.mkdir();save(folder/'started.json',dict(segment=segment,registration_sha256=registration_sha,**FLAGS))
    journal=Journal(folder/'journal.jsonl',pure,segment,registration_sha)
    error=None
    try:
        for position in range(segment['original_task_start'],segment['original_task_stop']):
            verify();resource_gate(folder,input_bytes)
            task=tasks[position];require(task['task_id']==segment['task_ids'][position-segment['original_task_start']],'Exact registered original task')
            arguments=adapter.evaluation_arguments(prepared,task)
            descriptor=segment['original_descriptor']
            journal.append(position,'TASK_STARTED',dict(task_reference=dict(path=descriptor['shard']['path'],sha256=descriptor['shard']['sha256'],jsonl_line_index=position),evaluation_argument_sha256=sha(encode(arguments))))
            result=None;failure=None
            try:result=evaluate(**arguments)
            except Exception as caught:failure=dict(type=type(caught).__name__,message=str(caught))
            journal.append(position,'RAW_EXCEPTION' if failure else 'RAW_RETURNED',dict(result=result,error=failure,explicit_evaluator_call_attempt_count=1,returned_evaluation_count=int(failure is None)))
            if failure:detail=dict(outcome='EVALUATION_EXCEPTION',original_target_stock_weight_l1=None,score_absence_reason='NO_RETURNED_EVALUATION',evaluation_error=failure,validation_error=None)
            else:
                try:detail=dict(**adapter.inspect_return(prepared,task,result),evaluation_error=None,validation_error=None)
                except Exception as caught:detail=dict(outcome='VALIDATION_FAILURE',original_target_stock_weight_l1=None,score_absence_reason='UNACCEPTED_RETURNED_EVALUATION',evaluation_error=None,validation_error=dict(type=type(caught).__name__,message=str(caught)))
            journal.append(position,'POSTCHECK',detail)
            verify()
            require(detail['outcome'] in ('FEASIBLE','INFEASIBLE'),'TECHNICAL_STOP_NO_RETRY')
    except BaseException as caught:
        error=dict(type=type(caught).__name__,message=str(caught))
    finally:journal.close()
    raw=(folder/'journal.jsonl').read_bytes()
    inspection=pure.inspect_recovery_journal(raw,segment=segment,registration_sha256=registration_sha)
    complete=error is None and inspection['complete']
    report=dict(schema='CASH_NEIGHBOR_RECOVERY_SEGMENT_V1',status='COMPLETE_PENDING_INDEPENDENT_READBACK' if complete else 'STOPPED_NO_AUTOMATIC_RETRY',segment=segment,registration_sha256=registration_sha,started_reference=reference(folder/'started.json',file_sha(folder/'started.json')),journal_reference=reference(folder/'journal.jsonl',sha(raw)),inspection=inspection,error=error,**FLAGS)
    return save(folder/('completion.json' if complete else 'failure.json'),report),report

def request_partition(domain,reports):
    categories=('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE','RAW_SAVED_POSTCHECK_MISSING','UNRESOLVED_DISPATCH','UNDISPATCHED')
    groups={key:[] for key in categories}
    require(len(reports)<=len(domain['segments']),'Bounded segment reports')
    for index,segment in enumerate(domain['segments']):
        if index>=len(reports):groups['UNDISPATCHED'].extend(segment['task_ids']);continue
        report=reports[index];exact(report['segment'],segment,'Exact original segment')
        inspected=report['inspection']
        sequence=[row['task_id'] for row in inspected['terminal_rows']]
        if inspected['active'] is not None:sequence.append(inspected['active']['task_id'])
        sequence.extend(inspected['undispatched_task_ids'])
        exact(sequence,segment['task_ids'],'Exact per-segment ordered task partition')
        for row in inspected['terminal_rows']:groups[row['status']].append(row['task_id'])
        if inspected['active'] is not None:
            row=inspected['active'];groups[row['status']].append(row['task_id'])
        groups['UNDISPATCHED'].extend(inspected['undispatched_task_ids'])
        technical=any(row['status'] in ('EVALUATION_EXCEPTION','VALIDATION_FAILURE') for row in inspected['terminal_rows'])
        require((inspected['complete'] and not technical and report['status']=='COMPLETE_PENDING_INDEPENDENT_READBACK') or index==len(reports)-1,'Incomplete or technical segment cannot be followed')
    expected=[task for segment in domain['segments'] for task in segment['task_ids']]
    actual=[task for tasks in groups.values() for task in tasks]
    require(len(actual)==len(set(actual))==len(expected) and set(actual)==set(expected),'Full exact recovery ID partition')
    return dict(counts={key:len(tasks) for key,tasks in groups.items()},task_ids_by_status=groups,old_task_dispatch_count=0)

def run(*,execute=False,max_new_segments=None):
    require(execute is True,'Explicit new recovery action')
    for digest in (PURE_SHA,PARTITION_SHA,SIDECAR_SHA,ADAPTER_SHA,READER_SHA):valid(digest)
    require(max_new_segments is None or type(max_new_segments) is int and 1<=max_new_segments<=45,'Engineering segment bound')
    require(not OUTPUT.exists(),'New namespace only; stopped requests need separately audited continuation')
    resource_gate(OUTPUT.parent,PARTITION.stat().st_size+SIDECAR.stat().st_size)
    pure=load(PURE,PURE_SHA);adapter=load(ADAPTER,ADAPTER_SHA);reader=load(READER,READER_SHA)
    partition=decode(read(PARTITION,PARTITION_SHA));sidecar=decode(read(SIDECAR,SIDECAR_SHA))
    require(set(p.name for p in SIDECAR.parent.iterdir())=={'independent_postcheck.json'},'No failed sidecar namespace')
    exact(sidecar['partition_reference'],reference(PARTITION,PARTITION_SHA),'Exact sidecar parent')
    bindings=merge_bindings(partition['source_hashes'],sidecar['source_hashes'],{str(SOURCE):LOADED,str(PURE):PURE_SHA,str(ADAPTER):ADAPTER_SHA,str(READER):READER_SHA,str(PARTITION):PARTITION_SHA,str(SIDECAR):SIDECAR_SHA})
    guard(bindings)
    prep_path=reader.PREP/'preparation.json';prep=decode(read(prep_path,bindings[str(prep_path)]))
    queue=reader.queue_from_preparation(prep);task_ids=[]
    for descriptor in queue:
        ref=descriptor['shard'];tasks=[decode(line) for line in read(ref['path'],ref['sha256']).splitlines()];task_ids.append([task['task_id'] for task in tasks])
    domain=pure.build_recovery_segments(queue,task_ids,partition,sidecar)
    original_root=reader.BATCH
    original_inventory=sorted(p.relative_to(original_root).as_posix() for p in original_root.rglob('*') if p.is_file())
    expected_inventory=sorted(Path(p).relative_to(original_root).as_posix() for p in partition['source_hashes'] if Path(p).is_relative_to(original_root))
    exact(original_inventory,expected_inventory,'Original namespace unchanged')
    OUTPUT.mkdir(parents=True,exist_ok=False)
    registration=save(OUTPUT/'registration.json',dict(schema='CASH_NEIGHBOR_RECOVERY_REGISTRATION_V1',runtime_identity=runtime_identity(),domain=domain,source_hashes=bindings,original_inventory=original_inventory,partition_reference=reference(PARTITION,PARTITION_SHA),sidecar_reference=reference(SIDECAR,SIDECAR_SHA),**FLAGS))
    request=OUTPUT/'request-0000';request.mkdir();started=save(request/'started.json',dict(registration_reference=registration,max_new_segments=max_new_segments,**FLAGS))
    accepted=[];stopped=None;segment_reports=[]
    try:
        evaluate=adapter.fresh_evaluator()
        for segment in domain['segments']:
            if max_new_segments is not None and len(accepted)>=max_new_segments:stopped=dict(status='ENGINEERING_STOP_BEFORE_DISPATCH');break
            descriptor=segment['original_descriptor'];contract_ref=descriptor['contract_reference'];task_ref=descriptor['shard']
            inputs=Path(contract_ref['path']).stat().st_size+Path(task_ref['path']).stat().st_size
            try:resource_gate(OUTPUT,inputs)
            except ValueError as caught:stopped=dict(status='RESOURCE_STOP_BEFORE_DISPATCH',error=str(caught));break
            prepared=decode(read(contract_ref['path'],contract_ref['sha256']));tasks=[decode(line) for line in read(task_ref['path'],task_ref['sha256']).splitlines()]
            local=merge_bindings({str(SOURCE):LOADED,str(PURE):PURE_SHA,str(ADAPTER):ADAPTER_SHA,contract_ref['path']:contract_ref['sha256'],task_ref['path']:task_ref['sha256']},adapter.source_map())
            ref,report=process_segment(folder=OUTPUT/('segment-%04d'%segment['recovery_segment_index']),segment=segment,tasks=tasks,prepared=prepared,registration_sha=registration['sha256'],pure=pure,adapter=adapter,evaluate=evaluate,verify=lambda:guard(local),input_bytes=inputs)
            segment_reports.append(report)
            if report['status']!='COMPLETE_PENDING_INDEPENDENT_READBACK':stopped=dict(status='TECHNICAL_STOP_NO_RETRY',partial_reference=ref);break
            accepted.append(ref)
        guard(bindings);exact(original_inventory,sorted(p.relative_to(original_root).as_posix() for p in original_root.rglob('*') if p.is_file()),'Final original inventory')
        partition_result=request_partition(domain,segment_reports)
        result=save(request/'result.json',dict(schema='CASH_NEIGHBOR_RECOVERY_REQUEST_V1',status='COMPLETE_PENDING_INDEPENDENT_READBACK' if len(accepted)==45 and stopped is None else 'STOPPED',registration_reference=registration,started_reference=started,completed_segment_references=accepted,stopped=stopped,full_recovery_task_count=42301,partition=partition_result,remaining_segment_descriptors=domain['segments'][len(accepted):],**FLAGS))
        guard(bindings)
        return result
    except BaseException as caught:
        save(request/'failure.json',dict(status='FAILED_REQUEST_DO_NOT_CONSUME',error_type=type(caught).__name__,**FLAGS));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--max-new-segments',type=int);args=parser.parse_args()
    print(json.dumps(run(execute=args.execute,max_new_segments=args.max_new_segments)))
