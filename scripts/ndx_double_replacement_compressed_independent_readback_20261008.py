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
PARENT=STORAGE/'double_replacement_compressed_evaluation_20261008_v1'
OUTPUT=STORAGE/'double_replacement_compressed_independent_readback_20261008_v1'
REQUEST=PARENT/'requests/request-000000'
PURE=ROOT/'backtest/ndx_double_replacement_request_inspection_research.py'
PURE_SHA=None
WORKER=ROOT/'scripts/ndx_double_replacement_compressed_worker_20261008.py'
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


def lifecycle_state_from_disk(state,reference,failed):
    """Worker returns the pre-save state plus its new self reference.

    The disk record additionally carries schema and worker boundary flags. Those
    flags were not lifecycle fields, except automatic_retry_allowed.
    """
    false_flags(state)
    actual={key:value for key,value in state.items()if key!='schema' and(key not in WORKER_FLAGS or key=='automatic_retry_allowed')}
    actual['references']=dict(state['references'])
    actual['references']['failure'if failed else'completion']=reference
    return actual


def check_terminal_status(state,failed):
    if failed:
        wanted='VALIDATION_FAILURE'if state['raw_preserved']else'UNKNOWN_RETURN_OR_PARTIAL_RAW'
    else:
        numeric=all(run['status']in('inspected_feasible','inspected_infeasible')for run in state['point_runs'])
        wanted='COMPLETE_SAVED_AND_INSPECTED'if numeric else'SAVED_TECHNICAL_STOP'
    require(state['status']==wanted,'Exact terminal status from preserved point runs')


def check_stop(summary,saved_stop,last_state,predispatch_state=None):
    if summary['full_domain_complete']:
        require(saved_stop is None,'Full domain requires stopped=None');return
    technical=any(summary['counts'][key]for key in ('evaluation_exception','supplied_not_evaluated_technical','supplied_not_evaluated_budget','validation_failure_returned','unresolved_dispatch_or_raw'))
    if technical:exact(saved_stop,last_state,'Actual technical terminal state including self reference')
    elif saved_stop is not None:
        require(saved_stop['status']=='STOP_BEFORE_DISPATCH','Only explicit pre-dispatch stop after numeric prefix')
        if predispatch_state is not None:exact(saved_stop,predispatch_state,'Actual undispatched lifecycle failure state')
        else:
            require(set(saved_stop)=={'status','descriptor','error'},'Exact outer pre-dispatch stop shape')
            require(type(saved_stop['error'])is dict and set(saved_stop['error'])=={'type','message'},'Saved resource/source stop error')


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


def inventory(root):
    rows=[]
    for path in sorted(root.rglob('*')):
        safe(path)
        if path.is_file():rows.append(dict(path=str(path.relative_to(root)),sha256=filehash(path),byte_count=path.stat().st_size))
    return rows


def namespace_gate(parent,request,saved_result):
    require(not (request/'failure.json').exists(),'Failed request namespace cannot be consumed')
    require(not (parent/'failure.json').exists(),'Failed worker namespace cannot be consumed')
    expected=list(saved_result['output_inventory_before_result'])
    expected_names=[row['path']for row in expected]
    require(len(expected_names)==len(set(expected_names)),'Unique exact saved file inventory')
    actual=inventory(parent)
    extras={str((request/'result.json').relative_to(parent))}
    if saved_result['partition']['full_domain_complete']:extras.add('publication.json')
    require({r['path']for r in actual}==set(expected_names)|extras,'Exact request output file namespace')
    exact([r for r in actual if r['path']not in extras],expected,'Exact pre-result inventory bytes')
    return actual


def memory_gate(raw_bytes):
    require(type(raw_bytes)is int and raw_bytes>0,'Bound raw decoder input')
    require(os.name=='nt','Registered Windows reader')
    class Memory(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong)for name in ('physical','available','page','available_page','virtual','available_virtual','extended')]
    status=Memory();status.length=ctypes.sizeof(status)
    require(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)),'Available RAM')
    require(status.available>=5*1024**3+32*raw_bytes,'Independent bounded decoder RAM gate')


def readback(*,registration_path,registration_sha256=None,execute=False):
    require(execute is True,'Explicit independent readback')
    for value in (registration_sha256,PURE_SHA,WORKER_SHA,REQUEST_RESULT_SHA):valid(value)
    require(not OUTPUT.exists(),'No reader overwrite or retry')
    sources={str(SOURCE):LOADED};refs={k:ref(ROOT/p,h)for k,(p,h)in FIXED.items()}
    pure=load_module('partition',read(ref(PURE,PURE_SHA),sources),PURE)
    registration_ref=ref(Path(registration_path).resolve(),registration_sha256)
    registration=decode(read(registration_ref,sources));request_ref=ref(REQUEST/'result.json',REQUEST_RESULT_SHA)
    result=decode(read(request_ref,sources))
    require(result['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_REQUEST_RESULT_V1','Successful saved request record role')
    exact(result['registration_reference'],registration_ref,'Original external registration')
    require(registration['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_REGISTRATION_V1','Original registration role')
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
    actual_inventory=namespace_gate(PARENT,REQUEST,result)
    file_refs={row['path']:ref(PARENT/row['path'],row['sha256'])for row in actual_inventory}
    def saved_json(path):
        key=str(path.relative_to(PARENT));require(key in file_refs,'File belongs to exact authenticated inventory')
        return decode(read(file_refs[key],sources))
    def saved_reference(path):
        key=str(path.relative_to(PARENT));require(key in file_refs,'Bound physical reference')
        return {**file_refs[key],'byte_count':path.stat().st_size}
    started=saved_json(REQUEST/'started.json')
    require(started['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_REQUEST_STARTED_V1','Request started role')
    false_flags(started)
    require(type(started['request_index'])is int,'Exact request index')
    exact(started['request_index'],registration['request_index'],'Original started request index')
    exact(started['prior_request_reference'],registration['prior_request_reference'],'Original started prior request')
    exact(result['started_reference'],{**file_refs[str((REQUEST/'started.json').relative_to(PARENT))],'byte_count':(REQUEST/'started.json').stat().st_size},'Started reference')
    exact(started['source_hashes'],result['source_hashes'],'Started original source set')
    exact(started['registration_reference'],registration_ref,'Started registration')
    plan=result['plan'];document=pure.checked_plan(plan)
    exact(started['plan'],plan,'Original request full plan')
    exact({k:document[k]for k in COUNTS},COUNTS,'Full plan domain')
    exact(document['preparation_reference'],refs['preparation'],'Plan source role')
    require(document['prepared_content_sha256']==CONTENT,'Plan prepared identity')
    require(document['batch_size']==registration['batch_size'],'Registered engineering partition')
    math=load_module('math',blobs['math'],refs['math']['path'])
    domain=load_module('domain',blobs['domain'],refs['domain']['path'],{'ndx_two_positive_integer_budget_domain_research':math})
    inspector=load_module('arithmetic',blobs['inspector'],refs['inspector']['path'],{'ndx_double_replacement_domain_research':domain})
    decoder=load_module('raw_decoder',blobs['decoder'],refs['decoder']['path'])
    envelope=registration['resource_envelope'];verified=[];reports=[];calls=0;returns=0;last_returned_state=None;predispatch_state=None
    allowed_files={str((REQUEST/name).relative_to(PARENT))for name in ('started.json','result.json')}
    for index,item in enumerate(result['batch_outcomes']):
        desc=pure.expected_descriptor(plan,index);exact(item['descriptor'],desc,'Full original batch descriptor')
        folder=PARENT/f'batches/{index//1000:03d}/{index:09d}'
        start=saved_json(folder/'started.json')
        require(start['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_STARTED_V1','Batch START role')
        false_flags(start)
        exact(start['descriptor'],desc,'START original interval')
        exact(start['registration_reference'],registration_ref,'Batch registration')
        exact(start['request_started_reference'],result['started_reference'],'Batch request context')
        require(start['dispatch_may_have_occurred']is True and start['call_returned']is False,'START uncertainty retained')
        page=domain.task_page(prepared,start=desc['start'],limit=desc['point_count'])
        plans=[dict(global_ordinal=desc['start']+i,task=t)for i,t in enumerate(page['tasks'])]
        require(start['ordered_task_content_sha256']==digest(plans),'Independent original task projection')
        failed=(folder/'failure.json').exists()
        names={p.name for p in folder.iterdir()}
        success_names={'started.json','raw_return.json.gz','raw_receipt.json','raw_byte_inspection.json','inspection.json','result.json'}
        failure_names={'started.json','raw_return.json.gz','raw_receipt.json','raw_byte_inspection.json','inspection.json','failure.json','raw_diagnostic.json'}
        if failed:require({'started.json','failure.json'}<=names<=failure_names,'Exact known batch failure evidence files')
        else:require(names==success_names,'Exact complete batch evidence files')
        allowed_files.update(str((folder/name).relative_to(PARENT))for name in names)
        state=saved_json(folder/('failure.json'if failed else'result.json'))
        require(state['schema']==('DOUBLE_REPLACEMENT_COMPRESSED_BATCH_FAILURE_V1'if failed else'DOUBLE_REPLACEMENT_COMPRESSED_BATCH_RESULT_V1'),'Saved batch terminal role')
        false_flags(state);check_terminal_status(state,failed)
        last_returned_state=lifecycle_state_from_disk(state,saved_reference(folder/('failure.json'if failed else'result.json')),failed)
        exact(state['descriptor'],desc,'Terminal batch descriptor')
        for name in ('started','call_invoked','returned','raw_preserved','independently_inspected'):
            require(type(state[name])is bool,'Exact lifecycle fact type')
        require(state['automatic_retry_allowed']is False,'No saved retry authority')
        exact(state['references']['started'],saved_reference(folder/'started.json'),'Terminal original START reference')
        require(state['call_invoked']is True and state['started']is True,'A classified supplied batch was invoked')
        calls+=1;require(type(state['returned'])is bool,'Exact return fact');returns+=state['returned']
        numerical=None;byte_report=None;inspection_error=None
        if state['raw_preserved']:
            require(state['returned']is True,'Saved return fact')
            receipt=saved_json(folder/'raw_receipt.json')
            exact(state['references']['raw_receipt'],saved_reference(folder/'raw_receipt.json'),'Terminal original receipt reference')
            require(receipt['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_RAW_RECEIPT_V1' and receipt['result_preserved_as_json']is True,'Preserved original raw receipt')
            false_flags(receipt,RAW_FLAGS)
            require(receipt['status']=='COMPLETE_CANONICAL_JSON_GZIP_NOT_ECONOMICALLY_VALIDATED'and receipt['returned_value_supplied_by_caller']is True,'Original raw utility scope')
            exact(receipt['descriptor'],desc,'Receipt original batch')
            require(receipt['descriptor_sha256']==digest(desc),'Receipt descriptor hash')
            raw_ref=receipt['raw_reference'];raw_path=folder/'raw_return.json.gz'
            exact(raw_ref,dict(path=str(raw_path),sha256=file_refs[str(raw_path.relative_to(PARENT))]['sha256'],byte_count=raw_path.stat().st_size),'Raw physical role and bytes')
            memory_gate(receipt['codec_metadata']['uncompressed_byte_count'])
            try:
                with raw_path.open('rb')as stream:
                    decoded=decoder.read_gzip_raw(stream,metadata=receipt['codec_metadata'],max_compressed_bytes=envelope['max_compressed_bytes'],max_uncompressed_bytes=envelope['max_uncompressed_bytes'])
                byte_report=decoded['inspection']
            except (ValueError,TypeError,KeyError) as error:
                require(failed and state['failure_stage']=='DECODE_SAVED_RAW','Unexpected invalid durable raw')
                inspection_error=dict(type=type(error).__name__,message=str(error),stage='DECODE_SAVED_RAW')
            if byte_report is not None:
                try:
                    numerical=inspector.inspect_explicit_evaluations(prepared=prepared,registered_plans=plans,max_evaluations=desc['point_count'],saved_result=decoded['value'])
                    runs=pure.numeric_runs(desc,plans,decoded['value'],numerical)
                except (ValueError,TypeError,KeyError) as error:
                    require(failed and state['failure_stage']=='INDEPENDENT_INSPECTION','Unexpected rejected saved economic result')
                    inspection_error=dict(type=type(error).__name__,message=str(error),stage='INDEPENDENT_INSPECTION')
            if not failed:
                saved_byte=saved_json(folder/'raw_byte_inspection.json')
                exact(saved_byte['raw_receipt_reference'],saved_reference(folder/'raw_receipt.json'),'Byte inspection receipt identity')
                exact(saved_byte['inspection'],byte_report,'Independent raw byte report')
                saved_inspection=saved_json(folder/'inspection.json')
                false_flags(saved_inspection)
                require(saved_inspection['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_INSPECTION_V1','Saved independent batch inspection role')
                exact(saved_inspection['descriptor'],desc,'Inspection original descriptor')
                exact(state['references']['inspection'],saved_reference(folder/'inspection.json'),'Terminal original inspection reference')
                exact(saved_inspection['started_reference'],file_refs[str((folder/'started.json').relative_to(PARENT))],'Inspection START identity')
                exact(saved_inspection['raw_receipt_reference'],file_refs[str((folder/'raw_receipt.json').relative_to(PARENT))],'Inspection raw receipt identity')
                require(saved_inspection['ordered_task_content_sha256']==digest(plans),'Inspection full task content')
                exact(saved_inspection['inspection'],numerical,'Independent complete arithmetic result')
                require(state['independently_inspected']is True,'Saved arithmetic status')
                exact(state['point_runs'],runs,'Original independently checked point partition')
            if byte_report is not None:del decoded
        if failed:
            require(state['independently_inspected']is False,'Failed batch cannot claim inspected completion')
            category='validation_failure_returned'if state['raw_preserved']else'unresolved_dispatch_or_raw'
            runs=[dict(start=desc['start'],stop=desc['stop'],status=category)]
            exact(state['point_runs'],runs,'Conservative saved failure interval')
        else:
            require(numerical is not None,'Successful batch needs complete independently decoded raw')
            require(state['status']in ('COMPLETE_SAVED_AND_INSPECTED','SAVED_TECHNICAL_STOP'),'Saved successful raw lifecycle role')
        exact(item['point_runs'],runs,'Request original saved batch classification')
        verified.append(dict(descriptor=desc,point_runs=runs))
        reports.append(dict(batch_index=index,descriptor=desc,raw_byte_inspection=byte_report,arithmetic_inspection=numerical,inspection_error=inspection_error,original_failure_preserved=failed))
    summary=pure.inspect_request_partition(plan=plan,verified_batch_outcomes=verified,saved_request=result)
    require(result['evaluator_call_count']==calls and result['returned_batch_count']==returns,'Saved call and returned batch denominator')
    require(result['risk_evaluation_compute_invoked']is (calls>0),'Actual evaluator invocation fact')
    require(len(verified)<=registration['request_batch_limit'],'Explicit engineering request boundary')
    if len(verified)<registration['request_batch_limit'] and not summary['full_domain_complete']:
        require(type(result['stopped'])is dict,'Incomplete request requires explicit technical/resource stop')
    if result['stopped']is not None and result['stopped']['status']=='STOP_BEFORE_DISPATCH':
        require(summary['counts']['unresolved_dispatch_or_raw']==0 and summary['counts']['validation_failure_returned']==0,'Pre-dispatch stop has no supplied unknown batch')
        exact(result['stopped']['descriptor'],pure.expected_descriptor(plan,len(verified)),'Unconsumed stop begins at exact undispatched suffix')
        index=len(verified);folder=PARENT/f'batches/{index//1000:03d}/{index:09d}'
        if folder.exists():
            names={p.name for p in folder.iterdir()}
            require(names<= {'started.json','failure.json'},'No RAW or completed result for undispatched batch')
            allowed_files.update(str((folder/name).relative_to(PARENT))for name in names)
            if 'failure.json'in names:
                failure=saved_json(folder/'failure.json')
                false_flags(failure)
                require(failure['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_FAILURE_V1','Undispatched failure role')
                require(failure['status']=='STOP_BEFORE_DISPATCH'and failure['call_invoked']is False and failure['returned']is False,'Explicit uncalled batch')
                exact(failure['descriptor'],result['stopped']['descriptor'],'Undispatched failure interval')
                predispatch_state=lifecycle_state_from_disk(failure,saved_reference(folder/'failure.json'),True)
    check_stop(summary,result['stopped'],last_returned_state,predispatch_state)
    if summary['full_domain_complete']:
        allowed_files.add('publication.json')
        valid(PUBLICATION_SHA)
        publication=decode(read(ref(PARENT/'publication.json',PUBLICATION_SHA),sources))
        require(publication['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_EXECUTION_PUBLICATION_V1'and publication['full_domain_complete']is True,'Full-domain publication')
        false_flags(publication)
        exact(publication['registration_reference'],registration_ref,'Published registered execution')
        exact(publication['result_reference'],{**request_ref,'byte_count':(REQUEST/'result.json').stat().st_size},'Published actual request')
        require(publication['independent_full_execution_readback_passed']is False,'Original worker could not attest this reader')
    else:require(not(PARENT/'publication.json').exists(),'Partial domain never published full')
    require(set(file_refs)==allowed_files,'Independently derived complete file inventory, no self-declared extra evidence')
    guard(sources);exact(inventory(PARENT),actual_inventory,'Final exact original output inventory')
    OUTPUT.mkdir(parents=True,exist_ok=False)
    output=OUTPUT/'independent_readback.json'
    report=dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_INDEPENDENT_READBACK_V1',status='PASS_FULL_DOMAIN'if summary['full_domain_complete']else'PASS_SAVED_PARTIAL_EVIDENCE_NOT_FULL_DOMAIN',request_reference=request_ref,registration_reference=registration_ref,inspection=summary,batch_reports=reports,source_hashes=sources,original_output_inventory=actual_inventory,**FLAGS)
    try:
        with output.open('xb')as stream:stream.write(encode(report));stream.flush();os.fsync(stream.fileno())
        guard(sources);exact(inventory(PARENT),actual_inventory,'Final guard after saved report')
    except BaseException as error:
        with(OUTPUT/'failure.json').open('xb')as stream:
            stream.write(encode(dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,**FLAGS)));stream.flush();os.fsync(stream.fileno())
        raise
    return ref(output,filehash(output))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--registration',required=True);parser.add_argument('--registration-sha256',required=True);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();print(json.dumps(readback(registration_path=args.registration,registration_sha256=args.registration_sha256,execute=args.execute)))
