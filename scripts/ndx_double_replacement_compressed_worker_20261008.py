"""Pending source-bound full-domain serial worker; no registered actual run.

Only request 000000 is supported. Any stop requires a separately reviewed
continuation implementation; no existing output can be resumed or overwritten.
The unbound resource envelope is deliberately NOT a caller-selected byte cap.
"""
import argparse
import builtins
import ctypes
import hashlib
import json
import os
import platform
import shutil
import sys
import zlib
from pathlib import Path
from types import ModuleType, SimpleNamespace

SOURCE = Path(__file__).resolve()
ROOT = SOURCE.parents[1]
OUTPUT = Path('D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714/double_replacement_compressed_evaluation_20261008_v1')
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
LIFECYCLE_SHA = None
# Pending independently reviewed worst-case bound. An external registration
# cannot fill this on its own. No non-None candidate is supplied by this draft.
RESOURCE_ENVELOPE = None
RESOURCE_PROOF_SHA = None
COUNTS = dict(scenario_count=40, pair_count=4200, integer_count=52406569,
              financial_integer_count_before_issuer=57064580, structurally_excluded_integer_count=4658011)
CONTENT = '11ae1bc652249682337a67b18d1cc2fecbdebee1c31b341f5565ee6c4430d819'
FLAGS = dict.fromkeys(('account_executed','orders_executed','fit_executed','point_in_time_verified',
                      'promotion_allowed','future_independent_oos','cross_family_winner_selected',
                      'full_ndx_certified','automatic_retry_allowed','old_tasks_reevaluated',
                      'continuous_source_monitoring_claimed','runtime_binary_closure_verified'),False)
BOUND = {
 'preparation': ('data/cache/research/double_replacement_preparation_20261003_v1/preparation.json','fca04682cbda564a2f22d315894e7300c70d2f5d94d661adb16150cf5318c3f0'),
 'publication': ('data/cache/research/double_replacement_preparation_20261003_v1/publication.json','fd21fc9f8aabbc6e8093b7c7ca61335d1cd8c8dce7ff8de8c2119e4d67802daf'),
 'audit': ('data/cache/research/double_replacement_preparation_independent_readback_20261003_v1/independent_readback.json','c2aeeeb27fbe1ecb3a462436d76e37095faa32839ff65fb709c40bc7161c31c1'),
 'preparation_reader': ('scripts/ndx_double_replacement_preparation_independent_readback_20261003.py','886bb528c841c89c80c8177856dbff4294c36a64d1d6a506e0580d5a6845234f'),
 'domain': ('backtest/ndx_double_replacement_domain_research.py','334af655e4d30a928af9d965b1c63bfe664c5c9a633dca3591bfac7f8130d4b6'),
 'math': ('backtest/ndx_two_positive_integer_budget_domain_research.py','081a1d3a72c78c3e4637fa25b3845853a610c33608bfd5b4b2ee8ccdca2dc5e1'),
 'evaluator': ('backtest/ndx_double_replacement_cached_evaluation_research.py','93da67c1f0011dc8b183a3085ccf96b114c6d9b14357a1cfeb292e0f3609ebfa'),
 'naive': ('backtest/ndx_double_replacement_evaluation_research.py','42640b41f3b54ba827e47d90c4c200c31b03ac13c6d867e928dc9a5956f4d5a2'),
 'inspector': ('backtest/ndx_double_replacement_result_inspection_research.py','2642df64d98b171ecdb740ece74a13d0f5313ca782bea23a384ac0e1c2838f1c'),
 'codec': ('backtest/ndx_double_replacement_compressed_batch_research.py','6374b11882f5b898f19bb055f29c1c7fff695625c89c27068d9c63987d388c93'),
 'raw_io': ('scripts/ndx_double_replacement_compressed_raw_io_20261003.py','b27260993d0e670270943486ac9d0539e23bb133e8203c67a609a85fb6a5a71f'),
 'decoder': ('backtest/ndx_double_replacement_compressed_raw_inspection_research.py','52a1013071018085b05ccf4905614c6986b3aa13bdb3c069a61703472e8624fd'),
}


def require(ok, message):
    if not ok: raise ValueError(message)


def valid(value):
    require(type(value) is str and len(value)==64 and set(value)<=set('0123456789abcdef'), 'Pending immutable SHA anchor')


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def digest(value): return hashlib.sha256(encode(value)).hexdigest()
def exact(a,b,message): require(encode(a)==encode(b),message)
def ref(path,sha): return dict(path=str(path),sha256=sha)


def filehash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024**2),b''): h.update(chunk)
    return h.hexdigest()


def safe(path):
    path=Path(path)
    for p in (path,*path.parents):
        require(not p.is_symlink() and not getattr(p,'is_junction',lambda:False)(), 'No source/output link or junction')
    return path


def read(reference,sources):
    valid(reference['sha256']); path=safe(reference['path']); b=path.read_bytes()
    require(hashlib.sha256(b).hexdigest()==reference['sha256'],'Authenticated source bytes')
    require(str(path) not in sources or sources[str(path)]==reference['sha256'],'Conflicting source reference')
    sources[str(path)]=reference['sha256']; return b


def guard(sources):
    for p,h in sources.items(): require(filehash(safe(p))==h,'Source drift: '+p)


def private_module(name,blob,path,dependencies=None):
    dependencies=dependencies or {}
    original=builtins.__import__
    def local_import(module,globals=None,locals=None,fromlist=(),level=0):
        if module=='backtest':
            require(level==0 and set(fromlist)<=set(dependencies),'Exact private dependency injection')
            return SimpleNamespace(**{key:dependencies[key] for key in fromlist})
        return original(module,globals,locals,fromlist,level)
    module=ModuleType('_private_double_worker_'+name);module.__file__=str(path)
    module.__dict__['__builtins__']={**vars(builtins),'__import__':local_import}
    exec(compile(blob,str(path),'exec'),module.__dict__)
    return module


def resource_gate(envelope, output):
    require(type(envelope) is dict and set(envelope)=={'max_uncompressed_bytes','max_compressed_bytes','memory_bytes','disk_bytes'},'Reviewed resource envelope')
    for value in envelope.values(): require(type(value) is int and value>0,'Exact resource bytes')
    class Memory(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(key,ctypes.c_ulonglong) for key in ('physical','available','page','available_page','virtual','available_virtual','extended')]
    require(os.name=='nt','Registered Windows runtime only')
    memory=Memory();memory.length=ctypes.sizeof(memory)
    require(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)),'Available memory measurement')
    existing=output
    while not existing.exists(): existing=existing.parent
    require(memory.available>=5*1024**3+envelope['memory_bytes'],'RESOURCE_STOP_BEFORE_DISPATCH_MEMORY')
    require(shutil.disk_usage(existing).free>=5*1024**3+envelope['disk_bytes'],'RESOURCE_STOP_BEFORE_DISPATCH_DISK')


def execute(*,registration_path,registration_sha256,execute=False):
    require(execute is True,'Explicit research execution')
    # Future anchors and mathematical resource envelope must be reviewed/bound
    # before reading registration, importing dependencies or creating output.
    # External anchor avoids a cycle: registration binds the final worker,
    # while the worker must not embed that registration's content hash.
    for h in (registration_sha256,LIFECYCLE_SHA,RESOURCE_PROOF_SHA): valid(h)
    require(RESOURCE_ENVELOPE is not None,'Pending worst-case returned-object/resource proof')
    safe(OUTPUT);require(not OUTPUT.exists(),'Create-only request: no automatic continuation')
    sources={str(SOURCE):LOADED}
    references={role:ref(ROOT/p,h) for role,(p,h) in BOUND.items()}
    references['lifecycle']=ref(ROOT/'backtest/ndx_double_replacement_batch_lifecycle_research.py',LIFECYCLE_SHA)
    registration_ref=ref(Path(registration_path).resolve(),registration_sha256)
    registration=json.loads(read(registration_ref,sources))
    require(registration['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_REGISTRATION_V1','External registration schema')
    exact(registration['input_references'],references,'Exact immutable role set')
    exact(registration['worker_reference'],ref(SOURCE,LOADED),'Registered worker')
    exact(registration['domain_counts'],COUNTS,'Full original domain')
    exact(registration['flags'],FLAGS,'Research-only false authority')
    exact(registration['output_directory'],str(OUTPUT),'Fixed independent namespace')
    exact(registration['resource_envelope'],RESOURCE_ENVELOPE,'Code-bound reviewed resource proof, not caller cap')
    valid(registration['resource_proof_reference']['sha256'])
    require(registration['resource_proof_reference']['sha256']==RESOURCE_PROOF_SHA,'External proof identity')
    read(registration['resource_proof_reference'],sources)
    require(registration['request_index']==0 and registration['prior_request_reference'] is None,'Only initial request supported')
    resource_gate(RESOURCE_ENVELOPE,OUTPUT)
    blobs={k:read(r,sources) for k,r in references.items()}
    prep=json.loads(blobs['preparation']);pub=json.loads(blobs['publication']);audit=json.loads(blobs['audit'])
    require(prep['schema']=='SOURCE_BOUND_DOUBLE_REPLACEMENT_PREPARATION_V1','Preparation role')
    require(pub['schema']=='DOUBLE_REPLACEMENT_PREPARATION_PUBLICATION_V1' and pub['status']=='PUBLISHED_UNEVALUATED_DOMAIN_ONLY','Original publication')
    require(audit['schema']=='DOUBLE_REPLACEMENT_PREPARATION_INDEPENDENT_READBACK_V1' and audit['status']=='PASS','Independent preparation audit')
    exact(audit['preparation_reference'],references['preparation'],'Audited preparation')
    exact(audit['publication_reference'],references['publication'],'Audited publication')
    exact(pub['preparation_reference'],references['preparation'],'Published preparation')
    require(audit['reader_sha256']==references['preparation_reader']['sha256'],'Original reader code')
    for p,h in audit['consumed_authenticated_sources'].items(): read(ref(p,h),sources)
    for r in prep['input_references'].values(): read(r,sources)
    rawprep=json.loads(read(prep['raw_preparation_reference'],sources))
    exact(rawprep['result'],prep['preparation'],'Original raw preparation')
    read(audit['producer_started_reference'],sources)
    prepared=prep['preparation'];require(prepared['content_sha256']==CONTENT,'Original full prepared content')
    exact({k:prepared['document'][k] for k in COUNTS},COUNTS,'Original counts')
    modules={}
    for key in ('math','codec','decoder','lifecycle'):
        modules[key]=private_module(key,blobs[key],references[key]['path'])
    modules['domain']=private_module('domain',blobs['domain'],references['domain']['path'],{'ndx_two_positive_integer_budget_domain_research':modules['math']})
    modules['evaluator']=private_module('evaluator',blobs['evaluator'],references['evaluator']['path'],{'ndx_double_replacement_domain_research':modules['domain']})
    # A separate domain instance for the independent inspector; no cached
    # evaluator objects or callable are supplied to the arithmetic inspector.
    independent_math=private_module('independent_math',blobs['math'],references['math']['path'])
    independent_domain=private_module('independent_domain',blobs['domain'],references['domain']['path'],{'ndx_two_positive_integer_budget_domain_research':independent_math})
    modules['inspector']=private_module('inspector',blobs['inspector'],references['inspector']['path'],{'ndx_double_replacement_domain_research':independent_domain})
    modules['raw_io']=private_module('raw_io',blobs['raw_io'],references['raw_io']['path'],{'ndx_double_replacement_compressed_batch_research':modules['codec']})
    codec=modules['codec'];save=modules['raw_io'].save_json
    plan=codec.build_plan(preparation_reference=references['preparation'],prepared_content_sha256=CONTENT,**COUNTS,batch_size=registration['batch_size'])
    require(type(registration['request_batch_limit']) is int and 0<registration['request_batch_limit']<=plan['document']['batch_count'],'Explicit engineering request limit')
    namespaces=((Path(references['preparation']['path']).parent,{'started.json','raw_preparation.json','preparation.json','publication.json'}),(Path(references['audit']['path']).parent,{'started.json','independent_readback.json'}))
    def namespace_guard():
        for folder,names in namespaces:
            require({p.name for p in folder.iterdir()}==names,'Exact original namespace')
    namespace_guard()
    guard(sources);OUTPUT.mkdir(parents=True,exist_ok=False)
    request=OUTPUT/'requests/request-000000';request.mkdir(parents=True,exist_ok=False)
    output_refs=[];outcomes=[];calls=0;returned=0
    def saved(path,value):
        result=save(path,value);output_refs.append(result);return result
    started=saved(request/'started.json',dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_REQUEST_STARTED_V1',registration_reference=registration_ref,plan=plan,source_hashes=sources,python=sys.version,zlib=zlib.ZLIB_VERSION,platform=platform.platform(),request_index=0,prior_request_reference=None,**FLAGS))
    small={p:h for p,h in sources.items() if Path(p).stat().st_size<=1024**2}
    def small_guard(): guard(small)
    stopped=None;active_descriptor=None;active_call_baseline=0
    try:
        for batch_index in range(registration['request_batch_limit']):
            descriptor=codec.descriptor(plan,batch_index)
            try:
                resource_gate(RESOURCE_ENVELOPE,OUTPUT);small_guard()
            except BaseException as error:
                stopped=dict(status='STOP_BEFORE_DISPATCH',descriptor=descriptor,error=modules['lifecycle'].error_record(error));break
            page=modules['domain'].task_page(prepared,start=descriptor['start'],limit=descriptor['point_count'])
            require(page['stop']==descriptor['stop'] and page['domain_truncated'] is False,'Full original batch projection')
            plans=[dict(global_ordinal=descriptor['start']+i,task=t) for i,t in enumerate(page['tasks'])]
            active_descriptor=descriptor;active_call_baseline=calls
            folder=OUTPUT/f'batches/{batch_index//1000:03d}/{batch_index:09d}'
            folder.mkdir(parents=True,exist_ok=False)
            def start(items):
                return saved(folder/'started.json',dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_STARTED_V1',descriptor=descriptor,registration_reference=registration_ref,request_started_reference=started,ordered_task_content_sha256=digest(items),dispatch_may_have_occurred=True,call_returned=False,**FLAGS))
            def evaluate(items):
                nonlocal calls,returned
                calls+=1
                result=modules['evaluator'].evaluate_explicit_double_replacement_plans_cached(prepared=prepared,registered_plans=items,max_evaluations=descriptor['point_count'])
                returned+=1;return result
            def preserve(value):
                receipt_ref=modules['raw_io'].preserve_return(directory=folder,descriptor=descriptor,value=value,max_compressed_bytes=RESOURCE_ENVELOPE['max_compressed_bytes'],max_uncompressed_bytes=RESOURCE_ENVELOPE['max_uncompressed_bytes'])
                output_refs.append(receipt_ref)
                receipt=json.loads(read(receipt_ref,{}));output_refs.append(receipt['raw_reference'])
                return receipt_ref
            def decode(receipt_ref):
                receipt=json.loads(read(receipt_ref,{}))
                with Path(receipt['raw_reference']['path']).open('rb') as stream:
                    decoded=modules['decoder'].read_gzip_raw(stream,metadata=receipt['codec_metadata'],max_compressed_bytes=RESOURCE_ENVELOPE['max_compressed_bytes'],max_uncompressed_bytes=RESOURCE_ENVELOPE['max_uncompressed_bytes'])
                saved(folder/'raw_byte_inspection.json',dict(raw_receipt_reference=receipt_ref,inspection=decoded['inspection']))
                return decoded['value']
            def inspect(items,value):
                report=modules['inspector'].inspect_explicit_evaluations(prepared=prepared,registered_plans=items,max_evaluations=descriptor['point_count'],saved_result=value)
                reference=saved(folder/'inspection.json',dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_INSPECTION_V1',descriptor=descriptor,started_reference=ref(folder/'started.json',filehash(folder/'started.json')),raw_receipt_reference=ref(folder/'raw_receipt.json',filehash(folder/'raw_receipt.json')),ordered_task_content_sha256=digest(items),inspection=report,**FLAGS))
                return report,reference
            hooks=dict(before_dispatch=lambda:(resource_gate(RESOURCE_ENVELOPE,OUTPUT),small_guard()),start=start,evaluate=evaluate,preserve=preserve,decode=decode,inspect=inspect,guard=small_guard,
                       complete=lambda state:saved(folder/'result.json',{'schema':'DOUBLE_REPLACEMENT_COMPRESSED_BATCH_RESULT_V1',**state,**FLAGS}),
                       failure=lambda state:saved(folder/'failure.json',{'schema':'DOUBLE_REPLACEMENT_COMPRESSED_BATCH_FAILURE_V1',**state,**FLAGS}))
            state=modules['lifecycle'].run_once(descriptor=descriptor,plans=plans,hooks=hooks)
            if state['point_runs']:outcomes.append(dict(descriptor=descriptor,point_runs=state['point_runs']))
            active_descriptor=None
            if state['status']!='COMPLETE_SAVED_AND_INSPECTED':stopped=state;break
        partition=codec.partition(plan,outcomes)
        guard(sources);namespace_guard()
        for r in output_refs:require(filehash(r['path'])==r['sha256'],'Output drift')
        inventory=[]
        for path in sorted(OUTPUT.rglob('*')):
            safe(path)
            if path.is_file():inventory.append(dict(path=str(path.relative_to(OUTPUT)),sha256=filehash(path),byte_count=path.stat().st_size))
        result=saved(request/'result.json',dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_REQUEST_RESULT_V1',registration_reference=registration_ref,started_reference=started,plan=plan,partition=partition,batch_outcomes=outcomes,stopped=stopped,output_inventory_before_result=inventory,evaluator_call_count=calls,returned_batch_count=returned,risk_evaluation_compute_invoked=calls>0,source_hashes=sources,**FLAGS))
        if partition['full_domain_complete']:
            saved(OUTPUT/'publication.json',dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_EXECUTION_PUBLICATION_V1',result_reference=result,registration_reference=registration_ref,full_domain_complete=True,independent_full_execution_readback_passed=False,**FLAGS))
        guard(sources);namespace_guard()
        for r in output_refs:require(filehash(r['path'])==r['sha256'],'Final output drift')
        return result
    except BaseException as error:
        if active_descriptor is not None and calls>active_call_baseline:
            outcomes.append(dict(descriptor=active_descriptor,point_runs=[dict(start=active_descriptor['start'],stop=active_descriptor['stop'],status='unresolved_dispatch_or_raw')]))
        saved(request/'failure.json',dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_REQUEST_FAILURE_V1',error=modules['lifecycle'].error_record(error),completed_batch_outcomes=outcomes,partition=codec.partition(plan,outcomes),partition_scope='LIFECYCLE_EVIDENCE_PLUS_CONSERVATIVE_UNKNOWN_FOR_UNCOMPLETED_CALL; NO_REDISPATCH_AUTHORITY',evaluator_call_count=calls,returned_batch_count=returned,automatic_retry_allowed=False,**{k:v for k,v in FLAGS.items() if k!='automatic_retry_allowed'}))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--registration',required=True);parser.add_argument('--registration-sha256',required=True);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();print(json.dumps(execute(registration_path=args.registration,registration_sha256=args.registration_sha256,execute=args.execute)))
