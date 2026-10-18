"""Pending C-volume source-bound full-domain STREAM worker; no registered actual run.

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
OUTPUT = Path('C:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714/double_replacement_stream_evaluation_c_20261008_v1')
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
LIFECYCLE_SHA = '52498d79414fdf8eea89f61536fc42a66f8b01b50e58e797d1e9c2db0b0013e9'
STREAM_SHA = '6f42ccfbf4edf0376b453340202c69d4ed22eaa180e9332cff64f63ea5af75ff'
# Pending reviewed engineering contract, distinct from an allocator/RSS proof.
# External registration cannot fill these actual binding pins on its own.
RESOURCE_ENVELOPE = {'disk_bytes': 50331648, 'filesystem_reserve_bytes': 34359738368, 'initial_capacity_bytes': 233000000000, 'max_compressed_bytes': 45050408, 'max_uncompressed_bytes': 45036633, 'memory_bytes': 17179869184, 'per_remaining_batch_capacity_bytes': 50331648}
RESOURCE_PROOF_SHA = 'e15c74ded1847a4b27e7eda2d25da3cab72d934f0c31bb320a4c098c5efa77b2'
RESOURCE_CONTRACT_SHA = 'f7441ca45be77043959b93ce8d5b7296a115e6f4e8213801fcfde7de527cf09a'
RESOURCE_CONTRACT_PATH = ROOT/'research_contracts/double_stream_c_resources_20261008_v1.json'
EXPECTED_BATCH_SIZE = 10000
RESOURCE_CLAIMS = dict(normal_data_bound_proved=True, allocator_rss_bound_proved=False, ntfs_internal_metadata_bound_proved=False, whole_run_completion_guaranteed=False)
ENGINEERING_ENVELOPE = dict(max_uncompressed_bytes=45036633, max_compressed_bytes=45050408, memory_bytes=16*1024**3, disk_bytes=48*1024**2, initial_capacity_bytes=233000000000, per_remaining_batch_capacity_bytes=48*1024**2, filesystem_reserve_bytes=32*1024**3)
METADATA_LIMITS = dict(registration_path_json_bytes=1024, runtime_string_json_bytes=4096,
                       source_map_json_bytes=65536, request_file_bytes=1024**2,
                       batch_fixed_json_bytes=8192, manifest_line_bytes=4096,
                       independent_audit_line_bytes=8192)
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
    with safe(path).open('rb') as stream:
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


def expected_resource_contract():
    return dict(schema='DOUBLE_REPLACEMENT_C_STREAM_RESOURCE_CONTRACT_V1',
                domain_counts=COUNTS,batch_size=EXPECTED_BATCH_SIZE,
                complete_request_batch_count=(COUNTS['integer_count']+EXPECTED_BATCH_SIZE-1)//EXPECTED_BATCH_SIZE,
                envelope=ENGINEERING_ENVELOPE,claims=RESOURCE_CLAIMS,
                metadata_limits=METADATA_LIMITS,
                normal_data_bound=dict(full_normal_gzip_bytes_upper=228862454440,
                                       normal_runs_bytes_upper=3511240123,
                                       capped_normal_logical_bytes_upper=232700944483,
                                       file_data_with_cluster_slack_bytes_upper=232851206413,
                                       ntfs_cluster_bytes=4096,
                                       independent_reader_must_enforce_registered_metadata_limits=True),
                baseline_free_bytes=5*1024**3,
                normal_bound_reference=ref(ROOT/'tmp/double_stream_resource_v3_20261008_v3.json','bd7e6e996886743d4c7fa1513ed3985a47261d44264bf106d0bf5dde0e502603'),
                frozen_ancestor_sha256='cf6eacfd44756486216c6cf1d65fd512cd2198dcc1b164b41baba3e78c8bb002',
                scope='NORMAL_DATA_BOUND_WITH_EXPLICIT_ENGINEERING_RESERVES_NOT_FULL_RESOURCE_PROOF',
                insufficient_before_dispatch='STOP_WITH_COMPLETE_ORIGINAL_PARTITION',
                returned_value_policy='RAW_FIRST_PRESERVE_PARTIAL_OR_UNKNOWN_ON_FAILURE_NO_RETRY',
                hardware_failure_complete_return_preservation_guaranteed=False,
                automatic_retry_allowed=False,automatic_resume_allowed=False)


def normal_metadata_budget():
    batches=(COUNTS['integer_count']+EXPECTED_BATCH_SIZE-1)//EXPECTED_BATCH_SIZE
    # Normal success only. Six fixed JSON files (result with runs removed),
    # two bounded manifest lines, five bounded request/reader JSON documents.
    logical=228862454440+67*COUNTS['integer_count']+batches*(6*METADATA_LIMITS['batch_fixed_json_bytes']+METADATA_LIMITS['manifest_line_bytes']+METADATA_LIMITS['independent_audit_line_bytes'])+5*METADATA_LIMITS['request_file_bytes']
    allocated=logical+(7*batches+7)*(4096-1)
    return dict(logical_bytes=logical,data_cluster_bytes=allocated)


def resource_requirements(envelope,*,phase='batch',remaining_batches=None):
    keys={'max_uncompressed_bytes','max_compressed_bytes','memory_bytes','disk_bytes','initial_capacity_bytes','per_remaining_batch_capacity_bytes','filesystem_reserve_bytes'}
    require(type(envelope)is dict and set(envelope)==keys,'Reviewed complete stream resource envelope')
    for value in envelope.values():require(type(value)is int and value>0,'Exact resource bytes')
    require(phase in ('initial','remaining','batch'),'Explicit resource gate phase')
    reserve=envelope['disk_bytes']
    if phase=='initial':reserve=max(reserve,envelope['initial_capacity_bytes'])
    if phase=='remaining':
        require(type(remaining_batches)is int and remaining_batches>=0,'Full-domain remaining batch count')
        reserve=max(reserve,remaining_batches*envelope['per_remaining_batch_capacity_bytes'])
    return dict(memory_bytes=5*1024**3+envelope['memory_bytes'],
                disk_bytes=5*1024**3+envelope['filesystem_reserve_bytes']+reserve)


def available_resources(output):
    class Memory(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(key,ctypes.c_ulonglong)for key in ('physical','available','page','available_page','virtual','available_virtual','extended')]
    require(os.name=='nt','Registered Windows runtime only')
    memory=Memory();memory.length=ctypes.sizeof(memory)
    require(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)),'Available memory measurement')
    existing=output
    while not existing.exists():existing=existing.parent
    return dict(memory_bytes=memory.available,disk_bytes=shutil.disk_usage(existing).free)


def resource_gate(envelope,output,*,phase='batch',remaining_batches=None):
    wanted=resource_requirements(envelope,phase=phase,remaining_batches=remaining_batches)
    available=available_resources(output)
    require(available['memory_bytes']>=wanted['memory_bytes'],'RESOURCE_STOP_BEFORE_DISPATCH_MEMORY')
    require(available['disk_bytes']>=wanted['disk_bytes'],'RESOURCE_STOP_BEFORE_DISPATCH_DISK_'+phase.upper())


def append_durable(stream,line):
    require(stream.write(line)==len(line),'Full manifest record write')
    stream.flush();os.fsync(stream.fileno())


def batch_inventory(folder):
    rows=[]
    for path in sorted(folder.iterdir()):
        safe(path);require(path.is_file(),'No nested batch output')
        rows.append(dict(filename=path.name,sha256=filehash(path),byte_count=path.stat().st_size))
    require(len(rows)<=8,'Bounded original batch evidence set')
    return rows


def verify_stream_manifest(path,stream_module,context,expected,output):
    """One-batch final byte guard, no economic replay and no global inventory."""
    accumulator=stream_module.RequestAccumulator(context)
    with path.open('rb')as manifest:
        while True:
            line=manifest.readline(accumulator.max_line_bytes+1)
            if not line:break
            require(len(line)<=accumulator.max_line_bytes and line.endswith(b'\n'),'Complete bounded manifest at final guard')
            row=json.loads(line);record=row['record'];index=accumulator.sequence
            folder=output/f'batches/{index//1000:03d}/{index:09d}'
            evidence_ref=record['batch_result_reference']
            exact(evidence_ref['path'],str(folder/'stream_result.json'),'Derived batch evidence path')
            evidence=json.loads(read(evidence_ref,{}))
            require(evidence['schema']=='DOUBLE_REPLACEMENT_STREAM_BATCH_EVIDENCE_V1','Stream batch evidence role')
            wanted=evidence['files'];require(type(wanted)is list and len(wanted)<=8,'Bounded batch inventory')
            names=[item['filename']for item in wanted]
            require(len(names)==len(set(names)),'Unique physical batch files')
            require({p.name for p in folder.iterdir()}==set(names)|{'stream_result.json'},'Exact one-batch file inventory')
            for item in wanted:
                require(Path(item['filename']).name==item['filename'],'Local filename only')
                file=folder/item['filename'];require(filehash(file)==item['sha256']and file.stat().st_size==item['byte_count'],'Batch evidence final SHA/size')
            terminal_ref=evidence['terminal_reference'];require(terminal_ref['path']in(str(folder/'result.json'),str(folder/'failure.json')),'Original terminal role')
            terminal=json.loads(read(terminal_ref,{}))
            accumulator.consume(line,batch_result_reference=evidence_ref,verified_runs=iter(terminal['point_runs']))
    return accumulator.finish(eof_observed=True,expected_manifest_sha256=expected['sha256'],expected_byte_count=expected['byte_count'],expected_record_count=expected['record_count'],expected_last_record_sha256=expected['last_record_sha256'])


def namespace_guard_stream(output,request,*,batch_folder_count,publication=False):
    def names(folder):return {safe(p).name for p in safe(folder).iterdir()}
    require(names(output)==({'requests','batches','publication.json'}if publication else{'requests','batches'}),'Exact stream root namespace')
    require(names(output/'requests')=={'request-000000'},'Initial request namespace')
    bucket_count=(batch_folder_count+999)//1000
    require(names(output/'batches')=={f'{i:03d}'for i in range(bucket_count)},'Exact bounded bucket set')
    for bucket in range(bucket_count):
        folder=output/'batches'/f'{bucket:03d}'
        wanted={f'{i:09d}'for i in range(bucket*1000,min((bucket+1)*1000,batch_folder_count))}
        require(names(folder)==wanted,'Exact bucket batch set')




def execute(*,registration_path,registration_sha256,execute=False):
    require(execute is True,'Explicit research execution')
    # Future anchors and explicit engineering resource contract must be bound
    # before reading registration, importing dependencies or creating output.
    # External anchor avoids a cycle: registration binds the final worker,
    # while the worker must not embed that registration's content hash.
    for h in (registration_sha256,LIFECYCLE_SHA,STREAM_SHA,RESOURCE_PROOF_SHA,RESOURCE_CONTRACT_SHA): valid(h)
    require(RESOURCE_ENVELOPE is not None,'Pending reviewed engineering resource contract')
    exact(RESOURCE_ENVELOPE,ENGINEERING_ENVELOPE,'Fixed reviewed C engineering choices')
    require(normal_metadata_budget()['data_cluster_bytes']<=ENGINEERING_ENVELOPE['initial_capacity_bytes'],'Normal data bound fits registered initial budget')
    require(len(encode(str(Path(registration_path).resolve())))<=METADATA_LIMITS['registration_path_json_bytes'],'Bound registration path encoding')
    for value in (sys.version,zlib.ZLIB_VERSION,platform.platform()):
        require(len(encode(value))<=METADATA_LIMITS['runtime_string_json_bytes'],'Bound runtime text, not runtime authentication')
    safe(OUTPUT);require(not OUTPUT.exists(),'Create-only request: no automatic continuation')
    sources={str(SOURCE):LOADED}
    references={role:ref(ROOT/p,h) for role,(p,h) in BOUND.items()}
    references['lifecycle']=ref(ROOT/'backtest/ndx_double_replacement_batch_lifecycle_research.py',LIFECYCLE_SHA)
    references['stream']=ref(ROOT/'backtest/ndx_double_replacement_stream_request_research.py',STREAM_SHA)
    registration_ref=ref(Path(registration_path).resolve(),registration_sha256)
    registration=json.loads(read(registration_ref,sources))
    contract_ref=ref(RESOURCE_CONTRACT_PATH,RESOURCE_CONTRACT_SHA)
    exact(registration['resource_contract_reference'],contract_ref,'Fixed C resource contract')
    contract=json.loads(read(contract_ref,sources))
    exact(contract,expected_resource_contract(),'Exact normal-bound and engineering-reserve contract')
    read(contract['normal_bound_reference'],sources)
    exact(registration['resource_claims'],RESOURCE_CLAIMS,'No absolute resource guarantee')
    require(type(registration['batch_size'])is int and registration['batch_size']==EXPECTED_BATCH_SIZE,'Fixed complete C batch size')
    require(registration['schema']=='DOUBLE_REPLACEMENT_C_STREAM_BATCH_REGISTRATION_V1','External registration schema')
    exact(registration['input_references'],references,'Exact immutable role set')
    exact(registration['worker_reference'],ref(SOURCE,LOADED),'Registered worker')
    exact(registration['domain_counts'],COUNTS,'Full original domain')
    exact(registration['flags'],FLAGS,'Research-only false authority')
    exact(registration['output_directory'],str(OUTPUT),'Fixed independent namespace')
    exact(registration['resource_envelope'],RESOURCE_ENVELOPE,'Code-bound reviewed resource proof, not caller cap')
    valid(registration['resource_proof_reference']['sha256'])
    require(registration['resource_proof_reference']['sha256']==RESOURCE_PROOF_SHA,'External proof identity')
    read(registration['resource_proof_reference'],sources)
    require(type(registration['request_index'])is int and registration['request_index']==0 and registration['prior_request_reference'] is None,'Only initial request supported')
    resource_gate(RESOURCE_ENVELOPE,OUTPUT,phase='initial')
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
    for key in ('math','codec','decoder','lifecycle','stream'):
        modules[key]=private_module(key,blobs[key],references[key]['path'])
    modules['domain']=private_module('domain',blobs['domain'],references['domain']['path'],{'ndx_two_positive_integer_budget_domain_research':modules['math']})
    modules['evaluator']=private_module('evaluator',blobs['evaluator'],references['evaluator']['path'],{'ndx_double_replacement_domain_research':modules['domain']})
    # A separate domain instance for the independent inspector; no cached
    # evaluator objects or callable are supplied to the arithmetic inspector.
    independent_math=private_module('independent_math',blobs['math'],references['math']['path'])
    independent_domain=private_module('independent_domain',blobs['domain'],references['domain']['path'],{'ndx_two_positive_integer_budget_domain_research':independent_math})
    modules['inspector']=private_module('inspector',blobs['inspector'],references['inspector']['path'],{'ndx_double_replacement_domain_research':independent_domain})
    modules['raw_io']=private_module('raw_io',blobs['raw_io'],references['raw_io']['path'],{'ndx_double_replacement_compressed_batch_research':modules['codec']})
    codec=modules['codec'];original_save=modules['raw_io'].save_json
    def save(path,value):
        # Successful metadata is bounded independently of runtime string length.
        # Failed diagnostics retain original failure behavior and may be larger.
        if path.name!='failure.json':
            fixed=value
            if 'point_runs'in value:fixed={**value,'point_runs':[]}
            limit=METADATA_LIMITS['batch_fixed_json_bytes']if'batches'in path.parts else METADATA_LIMITS['request_file_bytes']
            require(len(encode(fixed))<=limit,'Normal metadata within registered byte bound')
        return original_save(path,value)
    plan=codec.build_plan(preparation_reference=references['preparation'],prepared_content_sha256=CONTENT,**COUNTS,batch_size=registration['batch_size'])
    require(type(registration['request_batch_limit']) is int and registration['request_batch_limit']==plan['document']['batch_count'],'Entire original request, no prefix cap')
    namespaces=((Path(references['preparation']['path']).parent,{'started.json','raw_preparation.json','preparation.json','publication.json'}),(Path(references['audit']['path']).parent,{'started.json','independent_readback.json'}))
    def namespace_guard():
        for folder,names in namespaces:
            require({p.name for p in folder.iterdir()}==names,'Exact original namespace')
    namespace_guard()
    require(len(encode(sources))<=METADATA_LIMITS['source_map_json_bytes'],'Bound exact source-map payload')
    guard(sources);OUTPUT.mkdir(parents=True,exist_ok=False)
    request=OUTPUT/'requests/request-000000';request.mkdir(parents=True,exist_ok=False)
    (OUTPUT/'batches').mkdir(exist_ok=False)
    stream_module=modules['stream']
    context=stream_module.context(registration_reference=registration_ref,preparation_reference=references['preparation'],prepared_content_sha256=CONTENT,domain_counts=COUNTS,batch_size=registration['batch_size'])
    accumulator=stream_module.RequestAccumulator(context)
    started=save(request/'started.json',dict(schema='DOUBLE_REPLACEMENT_C_STREAM_REQUEST_STARTED_V1',resource_contract_reference=contract_ref,resource_claims=RESOURCE_CLAIMS,registration_reference=registration_ref,context=context,plan=plan,source_hashes=sources,python=sys.version,zlib=zlib.ZLIB_VERSION,platform=platform.platform(),request_index=0,prior_request_reference=None,**FLAGS))
    small={p:h for p,h in sources.items()if Path(p).stat().st_size<=1024**2}
    def small_guard():guard(small)
    calls=0;returned=0;stopped=None;active=None;active_call_baseline=0;batch_folder_count=0;undispatched_terminal=None;undispatched_descriptor=None
    def uncalled_guard():
        if undispatched_terminal is not None:
            require(filehash(undispatched_terminal['path'])==undispatched_terminal['sha256'],'Uncalled terminal SHA')
            require({safe(p).name for p in Path(undispatched_terminal['path']).parent.iterdir()}=={'failure.json'},'Exact uncalled stop evidence')
    manifest_path=request/'batch_manifest.jsonl'
    # No global output-reference, report, inventory or point-runs list.
    committed_counts=dict.fromkeys(stream_module.KINDS,0);committed_end=0
    committed_records=0;last_record=None
    manifest=None
    try:
        manifest=manifest_path.open('xb')
        for batch_index in range(registration['request_batch_limit']):
            descriptor=codec.descriptor(plan,batch_index)
            try:
                resource_gate(RESOURCE_ENVELOPE,OUTPUT,phase='remaining',remaining_batches=plan['document']['batch_count']-batch_index)
                small_guard()
            except BaseException as error:
                stopped=dict(status='STOP_BEFORE_DISPATCH',descriptor=descriptor,error=modules['lifecycle'].error_record(error));break
            page=modules['domain'].task_page(prepared,start=descriptor['start'],limit=descriptor['point_count'])
            require(page['stop']==descriptor['stop']and page['domain_truncated']is False,'Whole original task batch')
            plans=[dict(global_ordinal=descriptor['start']+i,task=task)for i,task in enumerate(page['tasks'])]
            folder=OUTPUT/f'batches/{batch_index//1000:03d}/{batch_index:09d}'
            folder.mkdir(parents=True,exist_ok=False);batch_folder_count+=1
            active=descriptor;active_call_baseline=calls
            def start(items):
                return save(folder/'started.json',dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_STARTED_V1',descriptor=descriptor,registration_reference=registration_ref,request_started_reference=started,ordered_task_content_sha256=digest(items),dispatch_may_have_occurred=True,call_returned=False,**FLAGS))
            def evaluate(items):
                nonlocal calls,returned
                calls+=1
                value=modules['evaluator'].evaluate_explicit_double_replacement_plans_cached(prepared=prepared,registered_plans=items,max_evaluations=descriptor['point_count'])
                returned+=1;return value
            def preserve(value):
                return modules['raw_io'].preserve_return(directory=folder,descriptor=descriptor,value=value,max_compressed_bytes=RESOURCE_ENVELOPE['max_compressed_bytes'],max_uncompressed_bytes=RESOURCE_ENVELOPE['max_uncompressed_bytes'])
            def decode(receipt_ref):
                receipt=json.loads(read(receipt_ref,{}))
                with Path(receipt['raw_reference']['path']).open('rb')as raw:
                    decoded=modules['decoder'].read_gzip_raw(raw,metadata=receipt['codec_metadata'],max_compressed_bytes=RESOURCE_ENVELOPE['max_compressed_bytes'],max_uncompressed_bytes=RESOURCE_ENVELOPE['max_uncompressed_bytes'])
                save(folder/'raw_byte_inspection.json',dict(raw_receipt_reference=receipt_ref,inspection=decoded['inspection']))
                return decoded['value']
            def inspect(items,value):
                report=modules['inspector'].inspect_explicit_evaluations(prepared=prepared,registered_plans=items,max_evaluations=descriptor['point_count'],saved_result=value)
                reference=save(folder/'inspection.json',dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_INSPECTION_V1',descriptor=descriptor,started_reference=ref(folder/'started.json',filehash(folder/'started.json')),raw_receipt_reference=ref(folder/'raw_receipt.json',filehash(folder/'raw_receipt.json')),ordered_task_content_sha256=digest(items),inspection=report,**FLAGS))
                return report,reference
            hooks=dict(before_dispatch=lambda:(resource_gate(RESOURCE_ENVELOPE,OUTPUT,phase='batch'),small_guard()),start=start,evaluate=evaluate,preserve=preserve,decode=decode,inspect=inspect,guard=small_guard,
                       complete=lambda state:save(folder/'result.json',{'schema':'DOUBLE_REPLACEMENT_COMPRESSED_BATCH_RESULT_V1',**state,**FLAGS}),
                       failure=lambda state:save(folder/'failure.json',{'schema':'DOUBLE_REPLACEMENT_COMPRESSED_BATCH_FAILURE_V1',**state,**FLAGS}))
            state=modules['lifecycle'].run_once(descriptor=descriptor,plans=plans,hooks=hooks)
            terminal_ref=state['references'].get('completion',state['references'].get('failure'))
            require(terminal_ref is not None,'Durable terminal evidence before indexing')
            if state['point_runs']:
                # Existing raw/inspection/result bytes stay unchanged. A bounded
                # extra envelope binds the complete per-batch physical inventory.
                evidence=save(folder/'stream_result.json',dict(schema='DOUBLE_REPLACEMENT_STREAM_BATCH_EVIDENCE_V1',descriptor=descriptor,terminal_reference=terminal_ref,files=batch_inventory(folder),**FLAGS))
                evidence_ref=ref(evidence['path'],evidence['sha256'])
                row=stream_module.manifest_record(context_value=context,sequence=committed_records,previous_record_sha256=last_record,batch_reference=evidence_ref,verified_runs=iter(state['point_runs']))
                line=stream_module.manifest_line(row)
                require(len(line)<=METADATA_LIMITS['manifest_line_bytes'],'C registered manifest line bound')
                require(len(line)<=accumulator.max_line_bytes,'Bounded manifest metadata before append')
                append_durable(manifest,line)
                accumulator.consume(line,batch_result_reference=evidence_ref,verified_runs=iter(state['point_runs']))
                # These fixed-size values advance only after the physical line
                # and the full in-memory validation both succeeded.
                committed_counts=dict(accumulator.counts);committed_end=accumulator.end
                committed_records=accumulator.sequence;last_record=accumulator.previous
                active=None
            else:
                require(state['call_invoked']is False,'Unindexed return/START cannot become undispatched')
                require(not(folder/'started.json').exists(),'Unindexed START requires UNKNOWN failure reconciliation')
                undispatched_terminal=terminal_ref
                undispatched_descriptor=descriptor
                active=None
            if state['status']!='COMPLETE_SAVED_AND_INSPECTED':
                # Keep only a bounded terminal reference, not its full runs.
                stopped=dict(status=state['status'],descriptor=descriptor,terminal_reference=terminal_ref);break
            del state,plans,page
        manifest.flush();os.fsync(manifest.fileno());manifest.close();manifest=None
        manifest_ref=dict(path=str(manifest_path),sha256=filehash(manifest_path),byte_count=manifest_path.stat().st_size,record_count=committed_records,last_record_sha256=last_record)
        summary=accumulator.finish(eof_observed=True,expected_manifest_sha256=manifest_ref['sha256'],expected_byte_count=manifest_ref['byte_count'],expected_record_count=manifest_ref['record_count'],expected_last_record_sha256=manifest_ref['last_record_sha256'])
        # Reopen to physical EOF and re-hash every indexed batch, one at a time.
        rechecked=verify_stream_manifest(manifest_path,stream_module,context,manifest_ref,OUTPUT)
        exact(rechecked,summary,'Stream final byte/partition guard')
        guard(sources);namespace_guard()
        namespace_guard_stream(OUTPUT,request,batch_folder_count=batch_folder_count)
        require({p.name for p in request.iterdir()}=={'started.json','batch_manifest.jsonl'},'Exact pre-result request namespace')
        require(filehash(started['path'])==started['sha256'],'Original request START')
        uncalled_guard()
        result=save(request/'result.json',dict(schema='DOUBLE_REPLACEMENT_C_STREAM_REQUEST_RESULT_V1',resource_contract_reference=contract_ref,resource_claims=RESOURCE_CLAIMS,registration_reference=registration_ref,started_reference=started,context=context,manifest_reference=manifest_ref,inspection=summary,stopped=stopped,batch_folder_count=batch_folder_count,evaluator_call_count=calls,returned_batch_count=returned,risk_evaluation_compute_invoked=calls>0,source_hashes=sources,output_guard_scope='STREAM_MANIFEST_EOF_AND_EVERY_INDEXED_BATCH_FILE_SHA_RECHECKED_ONE_BATCH_AT_A_TIME',**FLAGS))
        publication=None
        if summary['full_domain_complete']:
            require(stopped is None,'Full domain has no stop')
            publication=save(OUTPUT/'publication.json',dict(schema='DOUBLE_REPLACEMENT_C_STREAM_EXECUTION_PUBLICATION_V1',resource_contract_reference=contract_ref,resource_claims=RESOURCE_CLAIMS,result_reference=result,registration_reference=registration_ref,manifest_reference=manifest_ref,full_domain_complete=True,independent_full_execution_readback_passed=False,**FLAGS))
        guard(sources);namespace_guard()
        exact(verify_stream_manifest(manifest_path,stream_module,context,manifest_ref,OUTPUT),summary,'Final streamed closure guard after result')
        namespace_guard_stream(OUTPUT,request,batch_folder_count=batch_folder_count,publication=publication is not None)
        require({p.name for p in request.iterdir()}=={'started.json','batch_manifest.jsonl','result.json'},'Exact final request namespace')
        for reference in (started,result,publication,undispatched_terminal):
            if reference is not None:require(filehash(reference['path'])==reference['sha256'],'Final bounded request output SHA')
        uncalled_guard()
        return result
    except BaseException as error:
        if manifest is not None:
            try:manifest.flush();os.fsync(manifest.fileno())
            except BaseException:pass
            try:manifest.close()
            except BaseException:pass
        unknown=None;counts=dict(committed_counts);end=committed_end
        uncertain=active if active is not None else undispatched_descriptor
        if uncertain is not None:
            # START or returned-but-unindexed data is conservatively UNKNOWN,
            # even when the diagnostic cannot establish a real invocation.
            folder=OUTPUT/f"batches/{uncertain['batch_index']//1000:03d}/{uncertain['batch_index']:09d}"
            has_dispatch_bytes=any((folder/name).exists()for name in ('started.json','raw_return.json.gz','raw_receipt.json','raw_diagnostic.json'))
            if(active is not None and calls>active_call_baseline)or has_dispatch_bytes:
                unknown=dict(start=uncertain['start'],stop=uncertain['stop'],status='unresolved_dispatch_or_raw')
                counts['unresolved_dispatch_or_raw']+=uncertain['point_count'];end=uncertain['stop']
        counts['undispatched']=COUNTS['integer_count']-end
        require(sum(counts.values())==COUNTS['integer_count'],'Failure retains complete original domain')
        actual_manifest=None
        if manifest_path.exists():actual_manifest=dict(path=str(manifest_path),sha256=filehash(manifest_path),byte_count=manifest_path.stat().st_size)
        save(request/'failure.json',dict(schema='DOUBLE_REPLACEMENT_C_STREAM_REQUEST_FAILURE_V1',resource_contract_reference=contract_ref,resource_claims=RESOURCE_CLAIMS,error=modules['lifecycle'].error_record(error),registration_reference=registration_ref,context=context,manifest_finalized=False,preserved_manifest_reference=actual_manifest,indexed_record_count=committed_records,indexed_next_ordinal=committed_end,indexed_last_record_sha256=last_record,unindexed_unknown_interval=unknown,counts=counts,full_domain_complete=False,evaluator_call_count=calls,returned_batch_count=returned,**FLAGS))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--registration',required=True);parser.add_argument('--registration-sha256',required=True);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();print(json.dumps(execute(registration_path=args.registration,registration_sha256=args.registration_sha256,execute=args.execute)))
