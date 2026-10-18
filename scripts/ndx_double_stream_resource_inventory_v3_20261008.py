"""Read-only normal metadata census from pinned constructors; zero point calls."""
import ast
import hashlib
import json
import platform
import shutil
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace as NS
from backtest import ndx_double_stream_resource_v3_research as bound
from backtest import ndx_double_replacement_resource_bounds_v2_research as prior_bounds

ROOT=Path(__file__).resolve().parents[1]
H='f'*64
N=52406569
SIZE=10000  # frozen codec and stream accept only 512 or 10000
PARENT=Path('C:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714/double_replacement_stream_evaluation_c_20261008_v1')
READER=PARENT.parent/'double_replacement_stream_readback_c_20261008_v1'
PINS={
 'worker':('scripts/ndx_double_replacement_stream_worker_20261008.py','cf6eacfd44756486216c6cf1d65fd512cd2198dcc1b164b41baba3e78c8bb002'),
 'reader':('scripts/ndx_double_replacement_stream_independent_readback_20261008.py','1b2694d67b0680528c8d7db33b6e5a4fc3846a736978079fda28e0db52ef4358'),
 'stream':('backtest/ndx_double_replacement_stream_request_research.py','6f42ccfbf4edf0376b453340202c69d4ed22eaa180e9332cff64f63ea5af75ff'),
 'lifecycle':('backtest/ndx_double_replacement_batch_lifecycle_research.py','52498d79414fdf8eea89f61536fc42a66f8b01b50e58e797d1e9c2db0b0013e9'),
}


def declaration(source,name):
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
    return eval(compile(ast.Expression(node.value),'<constant>','eval'),{'dict':dict})


def run():
    sources={}; blobs={}
    algorithm_sources={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (Path(__file__).resolve(),Path(bound.__file__).resolve())}
    def read(path,sha):
        path=Path(path);raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==sha,str(path)
        sources[str(path)]=dict(sha256=sha,byte_count=len(raw));return raw
    for name,(path,sha) in PINS.items():blobs[name]=read(ROOT/path,sha)
    fixed=declaration(blobs['worker'],'BOUND')
    for name,(path,sha) in fixed.items():blobs[name]=read(ROOT/path,sha)
    prep=json.loads(blobs['preparation']); audit=json.loads(blobs['audit']);d=prep['preparation']['document']
    for path,sha in audit['consumed_authenticated_sources'].items():read(path,sha)
    for r in (*prep['input_references'].values(),prep['raw_preparation_reference'],audit['producer_started_reference']):read(r['path'],r['sha256'])
    # Future path/hash placeholders are length witnesses, NOT authenticated
    # registration/proof anchors. 16-digit byte-count witnesses exceed all
    # values in this normal census; final binding must stay within these paths.
    def ref(path,sha=H,bytes=False):
        result=dict(path=str(path),sha256=sha)
        if bytes:result['byte_count']=9999999999999999
        return result
    request=PARENT/'requests/request-000000';folder=PARENT/'batches/005/000005240'
    registration_ref=ref(PARENT.parent/'double_stream_c_registration_20261008_v1.json')
    refs={k:ref(ROOT/p,h) for k,(p,h) in fixed.items()}
    flags=declaration(blobs['worker'],'FLAGS');counts=declaration(blobs['worker'],'COUNTS')
    kinds=declaration(blobs['stream'],'KINDS');streamflags=declaration(blobs['stream'],'FLAGS')
    staticmap={p:r['sha256'] for p,r in sources.items()}
    staticmap[registration_ref['path']]=H
    staticmap[str(PARENT.parent/'double_stream_c_resource_proof_20261008_v1.json')]=H
    # Union bounds both worker and reader closures. Reader additionally retains
    # result, START and publication as authenticated sources.
    for path in (request/'result.json',request/'started.json',PARENT/'publication.json'):
        staticmap[str(path)]=H
    def make(module,role,**env):return bound.constructor(blobs[module],role,env)
    contextbody=make('stream','DOUBLE_REPLACEMENT_STREAM_REQUEST_CONTEXT_V1',registration_reference=registration_ref,preparation_reference=refs['preparation'],prepared_content_sha256=prep['preparation']['content_sha256'],domain_counts=counts,batch_size=SIZE,request_index=0,FLAGS=streamflags)
    context=dict(document=contextbody,content_sha256=H)
    planbody=make('codec','DOUBLE_REPLACEMENT_COMPRESSED_BATCH_PLAN_V1',preparation_reference=refs['preparation'],prepared_content_sha256=H,**counts,batch_size=SIZE,FLAGS=declaration(blobs['codec'],'FLAGS'))
    plan=dict(document=planbody,content_sha256=H)
    desc=dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_DESCRIPTOR_V1',plan_sha256=H,batch_index=5240,start=N,stop=N,point_count=SIZE)
    startedref=ref(request/'started.json',bytes=True)
    start=make('worker','DOUBLE_REPLACEMENT_COMPRESSED_BATCH_STARTED_V1',descriptor=desc,registration_ref=registration_ref,started=startedref,digest=lambda _:H,items=None,FLAGS=flags)
    encoding=declaration(blobs['codec'],'ENCODING')
    codecmeta=make('codec','DOUBLE_REPLACEMENT_CANONICAL_GZIP_V1',ENCODING=encoding,packed=NS(hash=NS(hexdigest=lambda:H),count=45050408),raw_hash=NS(hexdigest=lambda:H),raw_size=45036633)
    receipt=make('raw_io','DOUBLE_REPLACEMENT_COMPRESSED_RAW_RECEIPT_V1',frozen_descriptor=desc,codec=NS(digest=lambda _:H),raw_reference=ref(folder/'raw_return.json.gz',bytes=True),metadata=codecmeta,FLAGS=declaration(blobs['raw_io'],'FLAGS'))
    byte_report=make('decoder','DOUBLE_REPLACEMENT_COMPRESSED_RAW_BYTE_INSPECTION_V1',compressed_hash=NS(hexdigest=lambda:H),count=45050408,raw_hash=NS(hexdigest=lambda:H),output=range(45036633),value_type='object',max_compressed_bytes=45050408,max_uncompressed_bytes=45036633,max_json_depth=128)
    report=make('inspector','DOUBLE_REPLACEMENT_EXPLICIT_EVALUATION_INSPECTION_V1',expected_result={'status':'ALL_SUPPLIED_EVALUATED'},schema=declaration(blobs['inspector'],'SCHEMAS')[1],supplied=range(SIZE),d=d,counts={s:SIZE for s in ('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','NOT_EVALUATED_BUDGET','NOT_EVALUATED_TECHNICAL_STOP')},numeric=SIZE,DOMAIN_SHA256=H,MATH_SHA256=H,FLAGS=declaration(blobs['inspector'],'FLAGS'))
    receiptref=ref(folder/'raw_receipt.json',bytes=True)
    inspection=make('worker','DOUBLE_REPLACEMENT_COMPRESSED_BATCH_INSPECTION_V1',descriptor=desc,folder=folder,ref=lambda p,h:ref(p,h),filehash=lambda _:H,digest=lambda _:H,items=None,report=report,FLAGS=flags)
    # Lifecycle's initial state fields plus successful final fields. No actual
    # run/point list constructed; the 67*N term is added symbolically.
    state=dict(descriptor=desc,started=True,call_invoked=True,returned=True,raw_preserved=True,independently_inspected=True,references={k:ref(folder/f,bytes=True) for k,f in (('started','started.json'),('raw_receipt','raw_receipt.json'),('inspection','inspection.json'))},point_runs=[],automatic_retry_allowed=False,status='COMPLETE_SAVED_AND_INSPECTED')
    terminal=dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_RESULT_V1',**state,**{k:v for k,v in flags.items() if k not in state})
    lengths={name:len(bound.encode(value)) for name,value in [('started.json',start),('raw_receipt.json',receipt),('raw_byte_inspection.json',dict(raw_receipt_reference=receiptref,inspection=byte_report)),('inspection.json',inspection),('result.json',terminal)]}
    files=[dict(filename=name,sha256=H,byte_count=9999999999999999) for name in (*lengths,'raw_return.json.gz')]
    evidence=make('worker','DOUBLE_REPLACEMENT_STREAM_BATCH_EVIDENCE_V1',descriptor=desc,terminal_ref=ref(folder/'result.json',bytes=True),batch_inventory=lambda _:files,folder=folder,FLAGS=flags)
    lengths['stream_result.json']=len(bound.encode(evidence))
    row=make('stream','DOUBLE_REPLACEMENT_STREAM_BATCH_REFERENCE_V1',__function__='manifest_record',context_value=context,sequence=5240,previous_record_sha256=H,span={k:desc[k] for k in ('batch_index','start','stop','point_count')},batch_reference=ref(folder/'stream_result.json'),summary=dict(counts=dict.fromkeys(kinds,SIZE),terminal_status='COMPLETE_NUMERIC_BATCH'))
    manifest_line=len(bound.encode(dict(record=row,record_sha256=H)))+1
    auditentry=make('reader','DOUBLE_REPLACEMENT_STREAM_BATCH_READBACK_V1',index=5240,audit_last=H,row={'record_sha256':H},evidence_ref=ref(folder/'stream_result.json'),descriptor=desc,report=dict(arithmetic_inspection=report,raw_byte_inspection=byte_report,inspection_error=None,original_failure_preserved=False),FLAGS=declaration(blobs['reader'],'FLAGS'))
    audit_line=len(bound.encode(dict(record=auditentry,record_sha256=H)))+1
    summary=make('stream','DOUBLE_REPLACEMENT_STREAM_REQUEST_INSPECTION_V1',self=NS(context_sha256=H,hash=NS(hexdigest=lambda:H),byte_count=9999999999999999,sequence=5241,previous=H,end=N,stopped=False),total=N,counts=dict.fromkeys(kinds,N),full=True,FLAGS=streamflags)
    manifest_ref=dict(path=str(request/'batch_manifest.jsonl'),sha256=H,byte_count=9999999999999999,record_count=5241,last_record_sha256=H)
    reqstart=make('worker','DOUBLE_REPLACEMENT_STREAM_REQUEST_STARTED_V1',registration_ref=registration_ref,context=context,plan=plan,sources=staticmap,sys=sys,zlib=zlib,platform=platform,FLAGS=flags)
    reqresult=make('worker','DOUBLE_REPLACEMENT_STREAM_REQUEST_RESULT_V1',registration_ref=registration_ref,started=startedref,context=context,manifest_ref=manifest_ref,summary=summary,stopped=None,batch_folder_count=5241,calls=5241,returned=5241,sources=staticmap,FLAGS=flags)
    pub=make('worker','DOUBLE_REPLACEMENT_STREAM_EXECUTION_PUBLICATION_V1',result=ref(request/'result.json',bytes=True),registration_ref=registration_ref,manifest_ref=manifest_ref,FLAGS=flags)
    readerflags=declaration(blobs['reader'],'FLAGS')
    readerstart=make('reader','DOUBLE_REPLACEMENT_STREAM_READBACK_STARTED_V1',request_ref=ref(request/'result.json'),registration_ref=registration_ref,sources=staticmap,FLAGS=readerflags)
    readerresult=make('reader','DOUBLE_REPLACEMENT_STREAM_INDEPENDENT_READBACK_V1',summary=summary,request_ref=ref(request/'result.json'),registration_ref=registration_ref,publication_ref=ref(PARENT/'publication.json'),manifest_ref=manifest_ref,audit_path=READER/'batch_readback.jsonl',audit_eof=dict(sha256=H,byte_count=9999999999999999,record_count=5241,last_record_sha256=H),sources=staticmap,FLAGS=readerflags)
    requestlengths={k:len(bound.encode(v)) for k,v in dict(worker_started=reqstart,worker_result=reqresult,publication=pub,reader_started=readerstart,reader_result=readerresult).items()}
    result=bound.totals(count=N,batch_size=SIZE,gzip_total=228862454440,gzip_batch=45050408,raw_batch=45036633,file_lengths=lengths,manifest_line=manifest_line,audit_line=audit_line,request_lengths=requestlengths)
    # Extract ONLY the earlier symbolic bounding-row constructor. No original
    # task is projected: both quantity maxima can be infeasible simultaneously.
    # Stop before its optional integer-digit counting loop.
    prior_source=read(Path(prior_bounds.__file__),'51f7dc80a7c18709702abb3b07934a8409562acc23899051ca761ffe867af8ca')
    fn=next(n for n in ast.parse(prior_source).body if isinstance(n,ast.FunctionDef) and n.name=='pair_bound')
    end=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='result' for t in n.targets))
    fn.body=fn.body[:end+1]+[ast.Return(ast.Name(id='result',ctx=ast.Load()))]
    tree=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]));env=dict(prior_bounds.__dict__)
    exec(compile(tree,'<symbolic-bound-row-only>','exec'),env)
    maximum_row_tree=0;maximum_row_json=0;pair_count=0
    rule=declaration(blobs['domain'],'RULE');taskflags=declaration(blobs['domain'],'FLAGS');checks=declaration(blobs['inspector'],'CHECKS')
    for case in d['cases']:
        for pair in case['pairs']:
            if not pair['enumerable_integer_count']:continue
            row=env['pair_bound'](case,pair,rule=rule,flags=taskflags,checks=checks,full_count=N)
            maximum_row_tree=max(maximum_row_tree,bound.retained_tree_bytes(row))
            maximum_row_json=max(maximum_row_json,len(bound.encode(row)));pair_count+=1
    prepared_payload=bound.retained_tree_bytes(prep['preparation'])
    # Union of named lifetimes, deliberately charging aliases and mutually
    # exclusive phases twice. These are payload charges, not allocator proof.
    batch_charges=dict(page_tasks=1,outer_plans=1,hook_deepcopy=1,supplied_deepcopy=1,
                       returned_or_decoded_rows=1,verified_tasks=1,expected_rows=1,
                       current_projection_or_row=1,worker_runs=1,completion_runs_copy=1,
                       reader_saved_runs=1,reader_reconstructed_runs=1)
    domain_charges=dict(prepared=1,rawprep=1,reconstructed=1,validated_domain_copy=1,
                        original_rows_and_contract=1,domain_build_temporary=1)
    raw_charges=dict(decoder_bytearray_with_growth=2,last_inflated_block=1,utf8_unicode=1,
                     exact_two_sides_str_and_bytes=4,save_str_bytes_readback=3,
                     codec_piece_and_block=2,filehash_chunk=1,domain_hash_str_and_bytes=2)
    payload_model=sum(batch_charges.values())*SIZE*maximum_row_tree+sum(domain_charges.values())*prepared_payload+sum(raw_charges.values())*45036633+sum(map(len,blobs.values()))
    result.update(schema='DOUBLE_STREAM_NORMAL_METADATA_RESOURCE_RESEARCH_V3',source_hashes=sources,algorithm_sources=algorithm_sources,
                  prepared_file_bytes=len(blobs['preparation']),prepared_canonical_bytes=len(bound.encode(prep['preparation'])),
                  prepared_tree_payload_model=bound.retained_tree_bytes(prep['preparation']),
                  static_source_map_entries=len(staticmap),static_source_map_json_bytes=len(bound.encode(staticmap)),
                  fixed_blobs_bytes=sum(map(len,blobs.values())),max_single_source_bytes=max(r['byte_count'] for r in sources.values()),
                  symbolic_nonempty_pairs=pair_count,symbolic_max_row_tree_bytes=maximum_row_tree,symbolic_max_row_json_bytes=maximum_row_json,
                  normal_live_json_payload_model_bytes=payload_model,
                  payload_lifetime_charges=dict(batch_tree=batch_charges,domain_tree=domain_charges,raw_bytes=raw_charges),
                  payload_model_excludes_allocator_and_non_json_fraction_intermediates=True,
                  platform=dict(python=sys.version,machine=platform.machine(),pointer_bits=64 if sys.maxsize>2**32 else 32),
                  candidate_paths_are_length_witnesses_not_actual_anchors=True,resource_proof_sha256=None,
                  free_c_bytes=shutil.disk_usage('C:/').free,evaluator_calls=0,inspector_calls=0)
    for path,info in sources.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==info['sha256'],path
    for path,sha in algorithm_sources.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha,path
    return result


if __name__=='__main__':print(json.dumps(run(),indent=2))
