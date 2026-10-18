"""Read-only, one-batch adapter for the authenticated full C double request.

Never imports a worker, evaluator, account or arithmetic inspector. Source/audit
manifests and every physical batch are rechecked through EOF on each traversal.
"""
import hashlib
import json
import os
import types
from pathlib import Path

TOTAL=52406569
SCENARIOS=40
PAIRS=4200
KINDS=('inspected_feasible','inspected_infeasible','evaluation_exception','supplied_not_evaluated_technical','supplied_not_evaluated_budget','validation_failure_returned','unresolved_dispatch_or_raw','undispatched')
ROLES={'preparation','request','publication','audit','reader','worker','registration','decoder'}
FILES={'started.json','raw_return.json.gz','raw_receipt.json','raw_byte_inspection.json','inspection.json','result.json','stream_result.json'}
FALSE=('account_executed','orders_executed','fit_executed','point_in_time_verified','promotion_allowed','future_independent_oos','cross_family_winner_selected','full_ndx_certified','automatic_retry_allowed')
# Bind only after the original C reader receives its final request/publication
# anchors. Its pending-source ancestor bf870 is not the final audit producer.
READER_SHA=None
WORKER_SHA='f7320731e3001029b2d8722ea05ac86eab941c55e4355f6174e04dc89983abb8'
DECODER_SHA='52a1013071018085b05ccf4905614c6986b3aa13bdb3c069a61703472e8624fd'
PREPARATION_SHA='fca04682cbda564a2f22d315894e7300c70d2f5d94d661adb16150cf5318c3f0'

def require(value,message):
    if not value:raise ValueError(message)
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def digest(value):return hashlib.sha256(encode(value)).hexdigest()
def exact(a,b,message):require(encode(a)==encode(b),message)
def valid(value):require(type(value)is str and len(value)==64 and not set(value)-set('0123456789abcdef'),'Pending or invalid external SHA')
def integer(value):
    require(type(value)is int and value>=0,'Exact nonnegative integer');return value
def safe(path):
    path=Path(path)
    for p in (path,*path.parents):require(not p.is_symlink()and not getattr(p,'is_junction',lambda:False)(),'No source/output link')
    return path
def filehash(path):
    h=hashlib.sha256()
    with safe(path).open('rb')as stream:
        for block in iter(lambda:stream.read(1024**2),b''):h.update(block)
    return h.hexdigest()
def ref(path):return dict(path=str(path),sha256=filehash(path))
def decode(raw):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda token:(_ for _ in()).throw(ValueError('Nonfinite JSON')))
def read(reference,limit=1024**2):
    valid(reference['sha256']);path=safe(reference['path']);require(path.stat().st_size<=limit,'Bounded metadata')
    raw=path.read_bytes();require(hashlib.sha256(raw).hexdigest()==reference['sha256'],'Original byte SHA')
    if 'byte_count'in reference:require(len(raw)==integer(reference['byte_count']),'Original byte length')
    return decode(raw)
def flags(value):
    for key in FALSE:require(value[key]is False,'No inherited authority '+key)
def exact_inventory(path,names):
    require({safe(p).name for p in safe(path).iterdir()}==set(names),'Exact namespace inventory')
def guard(sources):
    for path,sha in sources.items():require(filehash(path)==sha,'Immutable source closure')
def merge(sources,path,sha):
    valid(sha);require(path not in sources or sources[path]==sha,'Source SHA conflict');sources[path]=sha
def module(reference):
    valid(reference['sha256']);p=safe(reference['path']);raw=p.read_bytes();require(hashlib.sha256(raw).hexdigest()==reference['sha256'],'Module SHA')
    result=types.ModuleType('_double_selection_'+p.stem);result.__file__=str(p);exec(compile(raw,str(p),'exec'),result.__dict__);return result
def save(path,value):
    raw=encode(value)+b'\n'
    with safe(path).open('xb')as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())

def prepare(refs):
    require(set(refs)==ROLES,'Exact registered source roles')
    valid(READER_SHA)
    for r in refs.values():require(set(r)=={'path','sha256'},'Exact source reference');valid(r['sha256'])
    for key,sha in (('reader',READER_SHA),('worker',WORKER_SHA),('decoder',DECODER_SHA),('preparation',PREPARATION_SHA)):require(refs[key]['sha256']==sha,'Frozen source '+key)
    sources={r['path']:r['sha256']for r in refs.values()};guard(sources)
    request=read(refs['request']);publication=read(refs['publication']);audit=read(refs['audit']);registration=read(refs['registration']);prep=read(refs['preparation'],32*1024**2)
    require(request['schema']=='DOUBLE_REPLACEMENT_C_STREAM_REQUEST_RESULT_V1'and request['stopped']is None,'Full C request only')
    require(publication['schema']=='DOUBLE_REPLACEMENT_C_STREAM_EXECUTION_PUBLICATION_V1'and publication['full_domain_complete']is True,'Full publication')
    require(audit['schema']=='DOUBLE_REPLACEMENT_C_STREAM_INDEPENDENT_READBACK_V1'and audit['status']=='PASS_FULL_DOMAIN','Independent full-domain PASS required')
    for value in (request,publication,audit):flags(value)
    for value in (publication,audit):exact(value['registration_reference'],refs['registration'],'Original registration')
    exact(request['registration_reference'],refs['registration'],'Request registration')
    for value,key in ((publication,'result_reference'),(audit,'request_reference')):
        exact({k:value[key][k]for k in ('path','sha256')},refs['request'],'Original request bytes')
    exact(audit['publication_reference'],refs['publication'],'Audited publication');exact(audit['source_manifest_reference'],request['manifest_reference'],'Same source EOF');exact(publication['manifest_reference'],request['manifest_reference'],'Published EOF')
    exact(audit['inspection'],request['inspection'],'Independent full partition')
    summary=audit['inspection'];require(summary['full_domain_complete']is True and summary['status']=='FULL_NUMERIC_DOMAIN','Full numeric only')
    require(integer(summary['original_integer_count'])==TOTAL==integer(summary['next_undispatched_ordinal']),'All original 52M points')
    require(set(summary['counts'])==set(KINDS)and sum(integer(v)for v in summary['counts'].values())==TOTAL and all(summary['counts'][k]==0 for k in KINDS[2:]),'No partial/unknown/technical selection')
    prepared=prep['preparation'];d=prepared['document'];require(digest(d)==prepared['content_sha256'],'Prepared digest')
    exact([d['integer_count'],d['scenario_count'],d['pair_count']],[TOTAL,SCENARIOS,PAIRS],'Complete original denominator')
    exact(request['context']['document']['prepared_content_sha256'],prepared['content_sha256'],'Request original prepared identity')
    exact(registration['input_references']['preparation'],refs['preparation'],'Registered preparation')
    for value in (request,audit):
        for path,sha in value['source_hashes'].items():merge(sources,path,sha)
    require(sources.get(refs['worker']['path'])==WORKER_SHA and sources.get(refs['reader']['path'])==READER_SHA,'Fixed producer and independent checker closure')
    for r in (request['started_reference'],):merge(sources,r['path'],r['sha256'])
    request_folder=safe(refs['request']['path']).parent;root=request_folder.parent.parent;aroot=safe(refs['audit']['path']).parent
    exact(str(root/'requests/request-000000'),str(request_folder),'Original initial request only')
    exact(str(request_folder/'started.json'),request['started_reference']['path'],'Original request START position')
    exact(str(root/'publication.json'),refs['publication']['path'],'Physical root publication')
    exact(str(request_folder/'batch_manifest.jsonl'),request['manifest_reference']['path'],'Physical source manifest')
    exact(str(aroot/'batch_readback.jsonl'),audit['batch_readback_reference']['path'],'Physical audit manifest')
    # The audit format does not externally pin its own START. Freeze its actual
    # bytes for this consumption, without claiming an upstream external anchor.
    audit_start=ref(aroot/'started.json');merge(sources,audit_start['path'],audit_start['sha256'])
    state=dict(refs=refs,prepared=prepared,request=request,audit=audit,sources=sources,root=root,request_folder=request_folder,aroot=aroot,observed_audit_start_reference=audit_start)
    boundaries(state);guard(sources);return state

def boundaries(state):
    exact_inventory(state['root'],{'requests','publication.json','batches'})
    exact_inventory(state['root']/'requests',{'request-000000'})
    exact_inventory(state['request_folder'],{'started.json','batch_manifest.jsonl','result.json'})
    exact_inventory(state['aroot'],{'started.json','batch_readback.jsonl','independent_readback.json'})
    n=integer(state['request']['manifest_reference']['record_count'])
    require(integer(state['request']['batch_folder_count'])==n,'No unindexed final batch')
    base=state['root']/'batches';exact_inventory(base,{f'{i:03d}'for i in range((n+999)//1000)})
    for b in range((n+999)//1000):exact_inventory(base/f'{b:03d}',{f'{i:09d}'for i in range(b*1000,min((b+1)*1000,n))})

def lines(reference,limit,schema):
    whole=hashlib.sha256();previous=None;offset=count=0
    with safe(reference['path']).open('rb')as stream:
        while True:
            raw=stream.readline(limit+1)
            if not raw:break
            require(len(raw)<=limit and raw.endswith(b'\n'),'Bounded full canonical manifest line')
            value=decode(raw);exact(raw.decode(),(encode(value)+b'\n').decode(),'Canonical manifest bytes')
            record=value['record'];require(set(value)=={'record','record_sha256'}and digest(record)==value['record_sha256'],'Manifest content hash')
            require(record['schema']==schema and type(record['sequence'])is int and record['sequence']==count and record['previous_record_sha256']==previous,'Ordered chained manifest')
            locator=dict(reference=reference,line_index=count,byte_start=offset,byte_stop=offset+len(raw),record_sha256=value['record_sha256'])
            whole.update(raw);offset+=len(raw);count+=1;previous=value['record_sha256'];yield record,locator
    exact([whole.hexdigest(),offset,count,previous],[reference[k]for k in ('sha256','byte_count','record_count','last_record_sha256')],'Physical full EOF external anchor')

def records(state,*,metadata_only=False):
    """At most one decoded gzip and its small physical file dictionary are live."""
    boundaries(state);guard(state['sources']);decoder=None if metadata_only else module(state['refs']['decoder'])
    request=state['request'];audit=state['audit'];iterator=iter(lines(audit['batch_readback_reference'],8192,'DOUBLE_REPLACEMENT_STREAM_BATCH_READBACK_V1'));ordinal=0;counts=dict.fromkeys(KINDS,0)
    for record,mloc in lines(request['manifest_reference'],4096,'DOUBLE_REPLACEMENT_STREAM_BATCH_REFERENCE_V1'):
        try:checked,aloc=next(iterator)
        except StopIteration:raise ValueError('Missing independently audited batch')from None
        exact(checked['source_manifest_record_sha256'],mloc['record_sha256'],'Audited original manifest line')
        exact(checked['batch_reference'],record['batch_result_reference'],'Audited original batch evidence');flags(checked)
        span=record['descriptor'];require(integer(span['start'])==ordinal<integer(span['stop'])<=TOTAL and integer(span['point_count'])==span['stop']-ordinal,'Contiguous full batch interval')
        require(record['terminal_status']=='COMPLETE_NUMERIC_BATCH'and set(record['counts'])==set(KINDS)and not any(integer(record['counts'][k])for k in KINDS[2:]),'Numeric batch only')
        require(sum(integer(v)for v in record['counts'].values())==span['point_count'],'Batch numeric partition')
        require(record['context_sha256']==request['context']['content_sha256'],'Original request context')
        folder=state['root']/'batches'/f"{record['sequence']//1000:03d}"/f"{record['sequence']:09d}"
        exact_inventory(folder,FILES);exact(record['batch_result_reference']['path'],str(folder/'stream_result.json'),'Actual physical batch locator')
        envelope=read(record['batch_result_reference'],8192);descriptor=envelope['descriptor'];exact({k:descriptor[k]for k in span},span,'Batch descriptor');exact(checked['descriptor'],descriptor,'Audited full descriptor')
        files={}
        for item in envelope['files']:
            name=item['filename'];require(name in FILES-{'stream_result.json'}and name not in files,'Unique physical files')
            p=folder/name;require(p.stat().st_size==integer(item['byte_count'])and filehash(p)==item['sha256'],'Original complete batch bytes')
            files[name]=dict(path=str(p),sha256=item['sha256'],byte_count=item['byte_count'])
        require(set(files)==FILES-{'stream_result.json'},'All six original batch files')
        exact(envelope['terminal_reference'],files['result.json'],'Original successful terminal')
        report=checked['inspection'];require(report['inspection_error']is None and report['original_failure_preserved']is False,'Original independent arithmetic passed')
        require(report['arithmetic_inspection']['status']=='PASS_SAVED_RESULT_EVIDENCE'and report['arithmetic_inspection']['all_supplied_plans_numerically_checked']is True,'Complete independent numeric audit')
        receipt=read(files['raw_receipt.json'],8192);exact(receipt['raw_reference'],files['raw_return.json.gz'],'Original RAW role');exact(receipt['descriptor'],descriptor,'Original raw interval')
        if not metadata_only:
            with safe(files['raw_return.json.gz']['path']).open('rb')as stream:decoded=decoder.read_gzip_raw(stream,metadata=receipt['codec_metadata'],max_compressed_bytes=45050408,max_uncompressed_bytes=45036633)
            exact(decoded['inspection'],report['raw_byte_inspection'],'Independent audit bound to these decompressed bytes')
            raw=decoded['value'];require(raw['status']=='ALL_SUPPLIED_EVALUATED'and len(raw['results'])==span['point_count'],'Complete original return')
            local=dict.fromkeys(KINDS,0)
            for index,item in enumerate(raw['results']):
                require(type(item['supplied_index'])is int and item['supplied_index']==index and type(item['plan']['global_ordinal'])is int and item['plan']['global_ordinal']==ordinal+index,'Original results array position')
                require(item['status']in ('FEASIBLE','INFEASIBLE'),'Numeric return only');local['inspected_feasible'if item['status']=='FEASIBLE'else'inspected_infeasible']+=1
                yield dict(raw=item,locator=dict(raw_reference=files['raw_return.json.gz'],json_tokens=['results',index],manifest=mloc,independent_audit=aloc))
            exact(local,record['counts'],'Original per-batch outcome count');del decoded,raw
        for key in KINDS:counts[key]+=record['counts'][key]
        ordinal=span['stop']
    try:next(iterator)
    except StopIteration:pass
    else:raise ValueError('Extra independent audit line')
    require(ordinal==TOTAL,'No truncated selection domain');exact(counts,audit['inspection']['counts'],'All original outcome counts');boundaries(state);guard(state['sources'])
