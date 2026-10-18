"""Pending independent saved-request reader. Never executes the worker/evaluator.

Failed request namespaces are rejected even if they contain result/publication.
Known batch stops are inspected as preservation evidence, never full coverage.
"""
import argparse
import builtins
import ctypes
import hashlib
import json
import os
import sys
from pathlib import Path
from types import ModuleType,SimpleNamespace

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1]
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
STORAGE=Path('D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714')
PARENT=STORAGE/'double_replacement_stream_evaluation_20261008_v1'
OUTPUT=STORAGE/'double_replacement_stream_independent_readback_20261008_v1'
REQUEST=PARENT/'requests/request-000000'
PURE=ROOT/'backtest/ndx_double_replacement_stream_request_research.py'
PURE_SHA=None
LIFECYCLE_SHA=None
WORKER=ROOT/'scripts/ndx_double_replacement_stream_worker_20261008.py'
WORKER_SHA=None
REQUEST_RESULT_SHA=None
PUBLICATION_SHA=None
COUNTS=dict(scenario_count=40,pair_count=4200,integer_count=52406569,financial_integer_count_before_issuer=57064580,structurally_excluded_integer_count=4658011)
CONTENT='11ae1bc652249682337a67b18d1cc2fecbdebee1c31b341f5565ee6c4430d819'
FLAGS=dict.fromkeys(('worker_called','evaluator_called','account_executed','orders_executed','fit_executed',
                    'point_in_time_verified','promotion_allowed','future_independent_oos','cross_family_winner_selected','full_ndx_certified','automatic_retry_allowed'),False)
WORKER_FLAGS=('account_executed','orders_executed','fit_executed','point_in_time_verified','promotion_allowed','future_independent_oos','cross_family_winner_selected','full_ndx_certified','automatic_retry_allowed','old_tasks_reevaluated','continuous_source_monitoring_claimed','runtime_binary_closure_verified')
RAW_FLAGS=('source_bytes_authenticated','call_event_authenticated','evaluation_called','economic_result_validated','resource_sufficiency_proved','execution_authorized','automatic_retry_allowed')
FIXED={
 'preparation':('data/cache/research/double_replacement_preparation_20261003_v1/preparation.json','fca04682cbda564a2f22d315894e7300c70d2f5d94d661adb16150cf5318c3f0'),
 'publication':('data/cache/research/double_replacement_preparation_20261003_v1/publication.json','fd21fc9f8aabbc6e8093b7c7ca61335d1cd8c8dce7ff8de8c2119e4d67802daf'),
 'audit':('data/cache/research/double_replacement_preparation_independent_readback_20261003_v1/independent_readback.json','c2aeeeb27fbe1ecb3a462436d76e37095faa32839ff65fb709c40bc7161c31c1'),
 'domain':('backtest/ndx_double_replacement_domain_research.py','334af655e4d30a928af9d965b1c63bfe664c5c9a633dca3591bfac7f8130d4b6'),
 'math':('backtest/ndx_two_positive_integer_budget_domain_research.py','081a1d3a72c78c3e4637fa25b3845853a610c33608bfd5b4b2ee8ccdca2dc5e1'),
 'inspector':('backtest/ndx_double_replacement_result_inspection_research.py','2642df64d98b171ecdb740ece74a13d0f5313ca782bea23a384ac0e1c2838f1c'),
 'decoder':('backtest/ndx_double_replacement_compressed_raw_inspection_research.py','52a1013071018085b05ccf4905614c6986b3aa13bdb3c069a61703472e8624fd'),
 'preparation_reader':('scripts/ndx_double_replacement_preparation_independent_readback_20261003.py','886bb528c841c89c80c8177856dbff4294c36a64d1d6a506e0580d5a6845234f'),
 'evaluator':('backtest/ndx_double_replacement_cached_evaluation_research.py','93da67c1f0011dc8b183a3085ccf96b114c6d9b14357a1cfeb292e0f3609ebfa'),
 'naive':('backtest/ndx_double_replacement_evaluation_research.py','42640b41f3b54ba827e47d90c4c200c31b03ac13c6d867e928dc9a5956f4d5a2'),
 'codec':('backtest/ndx_double_replacement_compressed_batch_research.py','6374b11882f5b898f19bb055f29c1c7fff695625c89c27068d9c63987d388c93'),
 'raw_io':('scripts/ndx_double_replacement_compressed_raw_io_20261003.py','b27260993d0e670270943486ac9d0539e23bb133e8203c67a609a85fb6a5a71f'),
}


def require(ok,message):
    if not ok:raise ValueError(message)
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def exact(a,b,message):require(encode(a)==encode(b),message)
def digest(value):return hashlib.sha256(encode(value)).hexdigest()
def valid(value):require(type(value)is str and len(value)==64 and set(value)<=set('0123456789abcdef'),'Bind actual immutable SHA before IO')
def ref(path,sha):return dict(path=str(path),sha256=sha)


def false_flags(value,keys=WORKER_FLAGS):
    for key in keys:require(value[key]is False,'Exact false authority: '+key)


def nonnegative_integer(value):
    require(type(value)is int and value>=0,'Exact nonnegative count without bool');return value


def check_terminal_status(state,failed):
    if failed:
        wanted='VALIDATION_FAILURE'if state['raw_preserved']else'UNKNOWN_RETURN_OR_PARTIAL_RAW'
    else:
        numeric=all(run['status']in('inspected_feasible','inspected_infeasible')for run in state['point_runs'])
        wanted='COMPLETE_SAVED_AND_INSPECTED'if numeric else'SAVED_TECHNICAL_STOP'
    require(state['status']==wanted,'Exact terminal status from preserved point runs')


def safe(path):
    path=Path(path)
    for ancestor in (path,*path.parents):require(not ancestor.is_symlink()and not getattr(ancestor,'is_junction',lambda:False)(),'No linked source or output')
    return path


def filehash(path):
    h=hashlib.sha256()
    with safe(path).open('rb')as stream:
        for chunk in iter(lambda:stream.read(1024**2),b''):h.update(chunk)
    return h.hexdigest()


def read(reference,sources):
    valid(reference['sha256']);path=safe(reference['path']);raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==reference['sha256'],'Source bytes')
    require(str(path)not in sources or sources[str(path)]==reference['sha256'],'Conflicting source SHA')
    sources[str(path)]=reference['sha256'];return raw


def decode(raw):
    def pairs(items):
        value={}
        for k,v in items:require(k not in value,'Duplicate JSON key');value[k]=v
        return value
    def constant(value):raise ValueError('Nonfinite JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)


def guard(sources):
    for path,sha in sources.items():require(filehash(path)==sha,'Source drift')


def load_module(name,blob,path,dependencies=None):
    dependencies=dependencies or {};original=builtins.__import__
    def local_import(module,globals=None,locals=None,fromlist=(),level=0):
        if module=='backtest':
            require(level==0 and set(fromlist)<=set(dependencies),'Fixed independent dependency graph')
            return SimpleNamespace(**{key:dependencies[key]for key in fromlist})
        return original(module,globals,locals,fromlist,level)
    instance=ModuleType('_independent_double_request_'+name);instance.__file__=str(path)
    instance.__dict__['__builtins__']={**vars(builtins),'__import__':local_import}
    exec(compile(blob,str(path),'exec'),instance.__dict__);return instance


def memory_gate(raw_bytes):
    require(type(raw_bytes)is int and raw_bytes>0,'Bound raw decoder input')
    require(os.name=='nt','Registered Windows reader')
    class Memory(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong)for name in ('physical','available','page','available_page','virtual','available_virtual','extended')]
    status=Memory();status.length=ctypes.sizeof(status)
    require(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)),'Available RAM')
    require(status.available>=5*1024**3+32*raw_bytes,'Independent bounded decoder RAM gate')


def namespace_check(batch_count,full):
    require(not(REQUEST/'failure.json').exists()and not(PARENT/'failure.json').exists(),'Failed request namespace cannot be consumed')
    def names(path):return {safe(p).name for p in safe(path).iterdir()}
    require(names(PARENT)==({'requests','batches','publication.json'}if full else{'requests','batches'}),'Exact stream source root')
    require(names(PARENT/'requests')=={'request-000000'},'Initial source request only')
    require(names(REQUEST)=={'started.json','batch_manifest.jsonl','result.json'},'Exact source request files')
    buckets=(batch_count+999)//1000
    require(names(PARENT/'batches')=={f'{i:03d}'for i in range(buckets)},'Exact bucket directory inventory')
    for bucket in range(buckets):
        require(names(PARENT/'batches'/f'{bucket:03d}')=={f'{i:09d}'for i in range(bucket*1000,min(batch_count,(bucket+1)*1000))},'Exact batch directory inventory')


def bounded_json(reference,limit):
    path=safe(reference['path']);require(path.stat().st_size<=limit,'Bounded one-batch JSON metadata')
    return decode(read(reference,{}))


def batch_evidence(reference,index,limit):
    folder=PARENT/f'batches/{index//1000:03d}/{index:09d}'
    exact(reference['path'],str(folder/'stream_result.json'),'Fixed physical stream batch envelope')
    envelope=bounded_json(reference,65536)
    require(envelope['schema']=='DOUBLE_REPLACEMENT_STREAM_BATCH_EVIDENCE_V1','Independent envelope role')
    false_flags(envelope)
    rows=envelope['files'];require(type(rows)is list and len(rows)<=8,'Bounded physical file inventory')
    local={}
    for row in rows:
        require(set(row)=={'filename','sha256','byte_count'},'Exact per-file physical evidence')
        name=row['filename'];require(type(name)is str and Path(name).name==name and name not in local,'Unique local file name')
        nonnegative_integer(row['byte_count']);file=safe(folder/name)
        require(file.is_file()and file.stat().st_size==row['byte_count']and filehash(file)==row['sha256'],'Original batch file SHA and size')
        local[name]=dict(path=str(file),sha256=row['sha256'],byte_count=row['byte_count'])
    require({safe(p).name for p in folder.iterdir()}==set(local)|{'stream_result.json'},'Exact authenticated batch directory')
    terminal=envelope['terminal_reference']
    name=Path(terminal['path']).name;require(name in ('result.json','failure.json'),'Actual original terminal role')
    exact(terminal,local[name],'Original terminal reference in physical inventory')
    state=bounded_json(terminal,limit)
    failure=name=='failure.json'
    success_files={'started.json','raw_return.json.gz','raw_receipt.json','raw_byte_inspection.json','inspection.json','result.json'}
    failure_files={'started.json','raw_return.json.gz','raw_receipt.json','raw_byte_inspection.json','inspection.json','failure.json','raw_diagnostic.json'}
    if failure:require({'started.json','failure.json'}<=set(local)<=failure_files,'Exact known technical evidence set')
    else:require(set(local)==success_files,'Complete original successful batch evidence')
    require(state['schema']==('DOUBLE_REPLACEMENT_COMPRESSED_BATCH_FAILURE_V1'if failure else'DOUBLE_REPLACEMENT_COMPRESSED_BATCH_RESULT_V1'),'Original terminal schema')
    false_flags(state);check_terminal_status(state,failure)
    return envelope,local,state,failure


def independent_runs(descriptor,plans,value,report):
    require(report['status']=='PASS_SAVED_RESULT_EVIDENCE'and report['supplied_plan_count']==len(plans),'Full independent numeric inspection')
    require(len(value['results'])==len(plans)==descriptor['point_count'],'Full raw task count')
    mapping={'FEASIBLE':'inspected_feasible','INFEASIBLE':'inspected_infeasible','EVALUATION_EXCEPTION':'evaluation_exception','NOT_EVALUATED_TECHNICAL_STOP':'supplied_not_evaluated_technical','NOT_EVALUATED_BUDGET':'supplied_not_evaluated_budget'}
    runs=[]
    for i,(plan,row)in enumerate(zip(plans,value['results'])):
        require(type(row['supplied_index'])is int and row['supplied_index']==i,'Exact supplied ordinal')
        exact(row['plan'],plan,'Original task plan')
        status=mapping[row['status']];ordinal=descriptor['start']+i
        if runs and runs[-1]['status']==status:runs[-1]['stop']=ordinal+1
        else:runs.append(dict(start=ordinal,stop=ordinal+1,status=status))
    return runs


def inspect_batch(envelope,files,state,failed,*,descriptor,prepared,domain,inspector,decoder,resource,registration_ref,started_ref,perform_arithmetic):
    limit=2*resource['max_uncompressed_bytes']+1024**2
    exact(envelope['descriptor'],descriptor,'Stream envelope original descriptor')
    exact(state['descriptor'],descriptor,'Terminal original descriptor')
    for key in ('started','call_invoked','returned','raw_preserved','independently_inspected'):require(type(state[key])is bool,'Exact lifecycle fact')
    require(state['started']is True and state['call_invoked']is True,'Indexed original call fact')
    exact(state['references']['started'],files['started.json'],'Original START reference')
    start=bounded_json(files['started.json'],limit);false_flags(start)
    require(start['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_STARTED_V1'and start['dispatch_may_have_occurred']is True and start['call_returned']is False,'Original uncertain START')
    exact(start['descriptor'],descriptor,'START full interval');exact(start['registration_reference'],registration_ref,'START registration')
    exact(start['request_started_reference'],started_ref,'START request identity')
    numeric=None;byte_report=None;inspection_error=None
    runs=state['point_runs']
    if perform_arithmetic:
        page=domain.task_page(prepared,start=descriptor['start'],limit=descriptor['point_count'])
        plans=[dict(global_ordinal=descriptor['start']+i,task=task)for i,task in enumerate(page['tasks'])]
        require(len(plans)==descriptor['point_count']and start['ordered_task_content_sha256']==digest(plans),'Complete independently projected original tasks')
    if state['raw_preserved']:
        require(state['returned']is True,'Original preserved return fact')
        exact(state['references']['raw_receipt'],files['raw_receipt.json'],'Original receipt reference')
        receipt=bounded_json(files['raw_receipt.json'],65536);false_flags(receipt,RAW_FLAGS)
        require(receipt['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_RAW_RECEIPT_V1'and receipt['status']=='COMPLETE_CANONICAL_JSON_GZIP_NOT_ECONOMICALLY_VALIDATED'and receipt['result_preserved_as_json']is True and receipt['returned_value_supplied_by_caller']is True,'Original raw utility scope')
        exact(receipt['descriptor'],descriptor,'Receipt exact original interval')
        require(receipt['descriptor_sha256']==digest(descriptor),'Receipt original descriptor content')
        exact(receipt['raw_reference'],files['raw_return.json.gz'],'Original gzip physical role')
        if perform_arithmetic:
            try:
                with safe(receipt['raw_reference']['path']).open('rb')as stream:
                    decoded=decoder.read_gzip_raw(stream,metadata=receipt['codec_metadata'],max_compressed_bytes=resource['max_compressed_bytes'],max_uncompressed_bytes=resource['max_uncompressed_bytes'])
                byte_report=decoded['inspection']
            except (ValueError,TypeError,KeyError)as error:
                require(failed and state['failure_stage']=='DECODE_SAVED_RAW','Unexpected raw byte validation failure')
                inspection_error=dict(stage='DECODE_SAVED_RAW',error_type=type(error).__name__)
            if byte_report is not None:
                try:
                    numeric=inspector.inspect_explicit_evaluations(prepared=prepared,registered_plans=plans,max_evaluations=descriptor['point_count'],saved_result=decoded['value'])
                    runs=independent_runs(descriptor,plans,decoded['value'],numeric)
                except (ValueError,TypeError,KeyError)as error:
                    require(failed and state['failure_stage']=='INDEPENDENT_INSPECTION','Unexpected rejected arithmetic')
                    inspection_error=dict(stage='INDEPENDENT_INSPECTION',error_type=type(error).__name__)
                del decoded
        if 'inspection.json'in files:
            inspection=bounded_json(files['inspection.json'],limit)
            require(set(inspection)=={'schema','descriptor','started_reference','raw_receipt_reference','ordered_task_content_sha256','inspection',*WORKER_FLAGS}and inspection['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_INSPECTION_V1','Arithmetic inspection role and complete fields')
            false_flags(inspection)
            if 'inspection'in state['references']:exact(state['references']['inspection'],files['inspection.json'],'Original inspection reference')
            elif not failed:raise ValueError('Successful terminal requires inspection reference')
            exact(inspection['descriptor'],descriptor,'Arithmetic full interval')
            exact(inspection['started_reference'],{k:files['started.json'][k]for k in ('path','sha256')},'Inspection START')
            exact(inspection['raw_receipt_reference'],{k:files['raw_receipt.json'][k]for k in ('path','sha256')},'Inspection receipt')
            require(inspection['ordered_task_content_sha256']==start['ordered_task_content_sha256'],'Inspection ordered tasks')
            if perform_arithmetic:
                require(numeric is not None,'Existing saved inspection requires independent arithmetic')
                exact(inspection['inspection'],numeric,'Independently reconstructed complete arithmetic')
        if 'raw_byte_inspection.json'in files:
            byte_saved=bounded_json(files['raw_byte_inspection.json'],limit)
            require(set(byte_saved)=={'raw_receipt_reference','inspection'},'Exact saved raw byte report wrapper')
            require(byte_saved['inspection']['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_RAW_BYTE_INSPECTION_V1','Saved raw byte inspection role')
            exact(byte_saved['raw_receipt_reference'],files['raw_receipt.json'],'Byte report receipt')
            if perform_arithmetic:
                require(byte_report is not None,'Existing byte inspection requires independent byte validation')
                exact(byte_saved['inspection'],byte_report,'Independent canonical gzip readback')
        if not failed:
            require(state['independently_inspected']is True,'Original complete arithmetic status')
            if perform_arithmetic:
                exact(state['point_runs'],runs,'Independent numeric/technical point partition')
    else:
        require('inspection.json'not in files and'raw_byte_inspection.json'not in files,'No postcheck reports without preserved raw')
        if not failed:raise ValueError('Successful batch lacks preserved raw')
    if failed:
        require(state['independently_inspected']is False,'Failed batch not promoted')
        category='validation_failure_returned'if state['raw_preserved']else'unresolved_dispatch_or_raw'
        runs=[dict(start=descriptor['start'],stop=descriptor['stop'],status=category)]
        exact(state['point_runs'],runs,'Conservative whole original failed interval')
    return runs,dict(arithmetic_inspection=numeric,raw_byte_inspection=byte_report,inspection_error=inspection_error,original_failure_preserved=failed)




def readback(*,registration_path,registration_sha256=None,execute=False):
    require(execute is True,'Explicit independent readback')
    for value in (registration_sha256,PURE_SHA,LIFECYCLE_SHA,WORKER_SHA,REQUEST_RESULT_SHA):valid(value)
    require(not(REQUEST/'failure.json').exists()and not(PARENT/'failure.json').exists(),'Failed request namespace cannot be consumed')
    require(not OUTPUT.exists(),'No reader overwrite or retry')
    sources={str(SOURCE):LOADED};refs={k:ref(ROOT/p,h)for k,(p,h)in FIXED.items()}
    pure=load_module('partition',read(ref(PURE,PURE_SHA),sources),PURE)
    registration_ref=ref(Path(registration_path).resolve(),registration_sha256)
    registration=decode(read(registration_ref,sources));request_ref=ref(REQUEST/'result.json',REQUEST_RESULT_SHA)
    exact(registration['input_references'],{**refs,'stream':ref(PURE,PURE_SHA),'lifecycle':ref(ROOT/'backtest/ndx_double_replacement_batch_lifecycle_research.py',LIFECYCLE_SHA)},'Exact fourteen source roles with independent frozen bindings')
    result=decode(read(request_ref,sources))
    require(result['schema']=='DOUBLE_REPLACEMENT_STREAM_REQUEST_RESULT_V1','Successful saved request record role')
    exact(result['registration_reference'],registration_ref,'Original external registration')
    require(registration['schema']=='DOUBLE_REPLACEMENT_STREAM_BATCH_REGISTRATION_V1','Original registration role')
    exact(registration['worker_reference'],ref(WORKER,WORKER_SHA),'Bound worker bytes without execution')
    exact(registration['domain_counts'],COUNTS,'Complete original domain')
    false_flags(registration['flags']);false_flags(result)
    require(nonnegative_integer(registration['request_batch_limit'])>0,'Positive engineering request batch count')
    nonnegative_integer(result['evaluator_call_count']);nonnegative_integer(result['returned_batch_count'])
    for name,value in registration['flags'].items():require(value is False,'Registration false research boundary')
    for name in ('account_executed','orders_executed','fit_executed','point_in_time_verified','promotion_allowed','future_independent_oos','cross_family_winner_selected','full_ndx_certified','automatic_retry_allowed'):
        require(registration['flags'][name]is False and result[name]is False,'No promoted execution authority')
    require(type(registration['request_index'])is int and registration['request_index']==0 and registration['prior_request_reference']is None,'Initial request only')
    exact(registration['output_directory'],str(PARENT),'Exact worker output')
    read(ref(WORKER,WORKER_SHA),sources)
    for key,r in refs.items():
        exact(registration['input_references'][key],r,'Fixed independently known source role')
    blobs={k:read(r,sources)for k,r in refs.items()}
    prep=decode(blobs['preparation']);audit=decode(blobs['audit'])
    require(audit['status']=='PASS'and audit['schema']=='DOUBLE_REPLACEMENT_PREPARATION_INDEPENDENT_READBACK_V1','Original preparation independent audit')
    exact(audit['preparation_reference'],refs['preparation'],'Audited full preparation')
    exact(audit['publication_reference'],refs['publication'],'Audited publication')
    prepared=prep['preparation'];require(prepared['content_sha256']==CONTENT,'Original prepared content')
    exact({k:prepared['document'][k]for k in COUNTS},COUNTS,'Original full domain counts')
    for path,sha in result['source_hashes'].items():read(ref(path,sha),sources)
    for r in registration['input_references'].values():read(r,sources)
    read(registration['resource_proof_reference'],sources)
    for path,sha in audit['consumed_authenticated_sources'].items():read(ref(path,sha),sources)
    for r in prep['input_references'].values():read(r,sources)
    read(prep['raw_preparation_reference'],sources);read(audit['producer_started_reference'],sources)
    source_claims={str(WORKER):WORKER_SHA,registration_ref['path']:registration_ref['sha256'],registration['resource_proof_reference']['path']:registration['resource_proof_reference']['sha256']}
    for r in registration['input_references'].values():source_claims[r['path']]=r['sha256']
    source_claims.update(audit['consumed_authenticated_sources'])
    for r in prep['input_references'].values():source_claims[r['path']]=r['sha256']
    for r in (prep['raw_preparation_reference'],audit['producer_started_reference']):source_claims[r['path']]=r['sha256']
    exact(result['source_hashes'],source_claims,'Complete exact worker source closure')
    exact(registration['input_references']['stream'],ref(PURE,PURE_SHA),'Registered frozen stream accounting source')
    context=pure.context(registration_reference=registration_ref,preparation_reference=refs['preparation'],prepared_content_sha256=CONTENT,domain_counts=COUNTS,batch_size=registration['batch_size'])
    exact(result['context'],context,'Original stream request context')
    manifest_ref=result['manifest_reference']
    require(set(manifest_ref)=={'path','sha256','byte_count','record_count','last_record_sha256'},'Complete manifest external anchor')
    exact(manifest_ref['path'],str(REQUEST/'batch_manifest.jsonl'),'Fixed physical manifest')
    for key in ('byte_count','record_count'):nonnegative_integer(manifest_ref[key])
    valid(manifest_ref['sha256'])
    nonnegative_integer(result['batch_folder_count'])
    require(manifest_ref['record_count']<=result['batch_folder_count']<=manifest_ref['record_count']+1,'At most one unindexed final uncalled batch')
    require(manifest_ref['record_count']<=registration['request_batch_limit'],'Original engineering request limit')
    batch_count=(COUNTS['integer_count']+registration['batch_size']-1)//registration['batch_size']
    require(registration['request_batch_limit']<=batch_count,'Request boundary within whole original domain')
    started_ref=result['started_reference'];exact(started_ref['path'],str(REQUEST/'started.json'),'Original physical request START')
    require(safe(started_ref['path']).stat().st_size==started_ref['byte_count'],'Original started byte count')
    started=decode(read(started_ref,sources));false_flags(started)
    require(started['schema']=='DOUBLE_REPLACEMENT_STREAM_REQUEST_STARTED_V1','Original stream START role')
    exact(started['registration_reference'],registration_ref,'Started registration')
    exact(started['context'],context,'Started complete stream context')
    require(type(started['request_index'])is int,'Exact started request index')
    exact(started['request_index'],registration['request_index'],'Started request ordinal')
    exact(started['prior_request_reference'],registration['prior_request_reference'],'Started prior request')
    exact(started['source_hashes'],result['source_hashes'],'Original source closure at START')
    plan_body=dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_PLAN_V1',preparation_reference=refs['preparation'],prepared_content_sha256=CONTENT,**COUNTS,batch_size=registration['batch_size'],batch_count=batch_count,source_bytes_authenticated=False,execution_authorized=False,evaluation_called=False,point_in_time_verified=False,promotion_allowed=False)
    plan=dict(document=plan_body,content_sha256=digest(plan_body));exact(started['plan'],plan,'Independent original complete engineering plan')
    def desc(index):
        span=pure.descriptor(context,index)
        return dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_DESCRIPTOR_V1',plan_sha256=plan['content_sha256'],**span)
    math=load_module('math',blobs['math'],refs['math']['path'])
    domain=load_module('domain',blobs['domain'],refs['domain']['path'],{'ndx_two_positive_integer_budget_domain_research':math})
    inspector=load_module('arithmetic',blobs['inspector'],refs['inspector']['path'],{'ndx_double_replacement_domain_research':domain})
    decoder=load_module('raw_decoder',blobs['decoder'],refs['decoder']['path'])
    resource=registration['resource_envelope']
    for key in ('max_uncompressed_bytes','max_compressed_bytes'):require(nonnegative_integer(resource[key])>0,'Registered raw engineering bounds')
    metadata_limit=2*resource['max_uncompressed_bytes']+1024**2
    claimed_full=result['inspection']['full_domain_complete'];require(type(claimed_full)is bool,'Exact full flag')
    namespace_check(result['batch_folder_count'],claimed_full)

    def sweep(*,perform_arithmetic,audit_stream=None):
        accumulator=pure.RequestAccumulator(context);calls=0;returned=0;last=None
        audit_hash=hashlib.sha256();audit_bytes=0;audit_last=None
        with safe(manifest_ref['path']).open('rb')as manifest:
            while True:
                line=manifest.readline(accumulator.max_line_bytes+1)
                if not line:break
                require(len(line)<=accumulator.max_line_bytes and line.endswith(b'\n'),'Complete bounded source manifest record')
                row=decode(line);index=accumulator.sequence;descriptor=desc(index)
                evidence_ref=row['record']['batch_result_reference']
                memory_gate(resource['max_uncompressed_bytes'])
                envelope,files,state,failed=batch_evidence(evidence_ref,index,metadata_limit)
                runs,report=inspect_batch(envelope,files,state,failed,descriptor=descriptor,prepared=prepared,domain=domain,inspector=inspector,decoder=decoder,resource=resource,registration_ref=registration_ref,started_ref=started_ref,perform_arithmetic=perform_arithmetic)
                accumulator.consume(line,batch_result_reference=evidence_ref,verified_runs=iter(runs))
                calls+=1;returned+=state['returned']
                last=dict(status=state['status'],descriptor=descriptor,terminal_reference=envelope['terminal_reference'])
                if audit_stream is not None:
                    entry=dict(schema='DOUBLE_REPLACEMENT_STREAM_BATCH_READBACK_V1',sequence=index,previous_record_sha256=audit_last,source_manifest_record_sha256=row['record_sha256'],batch_reference=evidence_ref,descriptor=descriptor,inspection=report,**FLAGS)
                    audit_last=digest(entry);encoded=encode(dict(record=entry,record_sha256=audit_last))+b'\n'
                    require(audit_stream.write(encoded)==len(encoded),'Complete independent audit line')
                    audit_stream.flush();os.fsync(audit_stream.fileno());audit_hash.update(encoded);audit_bytes+=len(encoded)
                # Only the last bounded terminal identity survives this iteration.
                del envelope,files,state,runs,report,row
        summary=accumulator.finish(eof_observed=True,expected_manifest_sha256=manifest_ref['sha256'],expected_byte_count=manifest_ref['byte_count'],expected_record_count=manifest_ref['record_count'],expected_last_record_sha256=manifest_ref['last_record_sha256'])
        exact(summary,result['inspection'],'Independent full stream partition and EOF')
        require(result['evaluator_call_count']==calls and result['returned_batch_count']==returned,'Exact original call/return counts')
        require(result['risk_evaluation_compute_invoked']is(calls>0),'Original runtime invocation fact')
        stop=result['stopped'];technical=any(summary['counts'][kind]for kind in pure.KINDS[2:-1])
        if summary['full_domain_complete']:require(stop is None,'Full domain has no stop')
        elif technical:exact(stop,last,'Actual last technical terminal reference')
        elif stop is not None:
            require(stop['status']=='STOP_BEFORE_DISPATCH','Only uncalled stop after numeric prefix')
            exact(stop['descriptor'],desc(accumulator.sequence),'Exact undispatched next interval')
            if result['batch_folder_count']==accumulator.sequence+1:
                folder=PARENT/f'batches/{accumulator.sequence//1000:03d}/{accumulator.sequence:09d}'
                require({safe(p).name for p in folder.iterdir()}=={'failure.json'},'Unindexed START/RAW cannot be called undispatched')
                reference=stop['terminal_reference'];exact(reference['path'],str(folder/'failure.json'),'Physical uncalled failure')
                failure=bounded_json(reference,metadata_limit);false_flags(failure)
                require(failure['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_FAILURE_V1'and failure['status']=='STOP_BEFORE_DISPATCH'and failure['call_invoked']is False and failure['returned']is False and failure['started']is False and failure['raw_preserved']is False and failure['independently_inspected']is False,'Original uncalled failure facts')
                exact(failure['descriptor'],stop['descriptor'],'Uncalled exact descriptor')
                exact(failure['point_runs'],[],'Uncalled no point results')
                exact(stop,dict(status='STOP_BEFORE_DISPATCH',descriptor=desc(accumulator.sequence),terminal_reference=reference),'Exact uncalled stop envelope')
                require(Path(reference['path']).stat().st_size==reference['byte_count'],'Uncalled terminal size')
            else:
                require(set(stop)=={'status','descriptor','error'},'Exact outer resource/source stop')
                require(type(stop['error'])is dict and set(stop['error'])=={'type','message'},'Explicit stop error')
        else:
            require(accumulator.sequence==registration['request_batch_limit'],'Only engineering boundary may end an unstopped prefix')
        require(result['batch_folder_count']==accumulator.sequence+(1 if stop is not None and'terminal_reference'in stop and stop['status']=='STOP_BEFORE_DISPATCH'else 0),'Exact indexed/uncalled folder count')
        namespace_check(result['batch_folder_count'],summary['full_domain_complete'])
        return summary,dict(sha256=audit_hash.hexdigest(),byte_count=audit_bytes,record_count=accumulator.sequence,last_record_sha256=audit_last)

    publication_ref=None
    if claimed_full:
        valid(PUBLICATION_SHA);publication_ref=ref(PARENT/'publication.json',PUBLICATION_SHA)
        publication=decode(read(publication_ref,sources));false_flags(publication)
        require(publication['schema']=='DOUBLE_REPLACEMENT_STREAM_EXECUTION_PUBLICATION_V1'and publication['full_domain_complete']is True and publication['independent_full_execution_readback_passed']is False,'Original full publication boundary')
        exact(publication['registration_reference'],registration_ref,'Published registered execution')
        exact(publication['result_reference'],{**request_ref,'byte_count':Path(request_ref['path']).stat().st_size},'Published original result')
        exact(publication['manifest_reference'],manifest_ref,'Published exact stream EOF')
    guard(sources)
    safe(OUTPUT);OUTPUT.mkdir(parents=True,exist_ok=False)
    def save(path,value):
        raw=encode(value)
        with path.open('xb')as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        require(filehash(path)==hashlib.sha256(raw).hexdigest(),'Independent output durable bytes')
        return ref(path,hashlib.sha256(raw).hexdigest())
    own_started=save(OUTPUT/'started.json',dict(schema='DOUBLE_REPLACEMENT_STREAM_READBACK_STARTED_V1',request_reference=request_ref,registration_reference=registration_ref,source_hashes=sources,**FLAGS))
    try:
        audit_path=OUTPUT/'batch_readback.jsonl'
        with audit_path.open('xb')as audit_stream:
            summary,audit_eof=sweep(perform_arithmetic=True,audit_stream=audit_stream)
        require(filehash(audit_path)==audit_eof['sha256']and audit_path.stat().st_size==audit_eof['byte_count'],'Complete bounded audit manifest output')
        guard(sources)
        second,_=sweep(perform_arithmetic=False);exact(second,summary,'Final source closure sweep without economic replay')
        report=save(OUTPUT/'independent_readback.json',dict(schema='DOUBLE_REPLACEMENT_STREAM_INDEPENDENT_READBACK_V1',status='PASS_FULL_DOMAIN'if summary['full_domain_complete']else'PASS_SAVED_PARTIAL_EVIDENCE_NOT_FULL_DOMAIN',request_reference=request_ref,registration_reference=registration_ref,publication_reference=publication_ref,source_manifest_reference=manifest_ref,batch_readback_reference=dict(path=str(audit_path),**audit_eof),inspection=summary,source_hashes=sources,source_guard_scope='FIXED_INPUT_CLOSURE_PLUS_ONE_BATCH_AT_A_TIME_MANIFEST_EOF_AND_ALL_BATCH_FILE_HASHES',**FLAGS))
        guard(sources)
        third,_=sweep(perform_arithmetic=False);exact(third,summary,'Final physical source guard after output')
        for reference in (own_started,report):require(filehash(reference['path'])==reference['sha256'],'Final independent metadata SHA')
        require(filehash(audit_path)==audit_eof['sha256'],'Final independent audit stream SHA')
        require({safe(p).name for p in OUTPUT.iterdir()}=={'started.json','batch_readback.jsonl','independent_readback.json'},'Exact independent output namespace')
        return report
    except BaseException as error:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,**FLAGS));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--registration',required=True);parser.add_argument('--registration-sha256',required=True);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();print(json.dumps(readback(registration_path=args.registration,registration_sha256=args.registration_sha256,execute=args.execute)))
