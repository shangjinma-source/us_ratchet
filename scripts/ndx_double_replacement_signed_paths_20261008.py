"""Explicitly registered forty saved-source signed paths; default performs no IO.

Full paired EOF precedes every account invocation. No controls, selection, risk
evaluation, fit or live state. Returned objects are durable before validation.
"""
from pathlib import Path
from types import ModuleType
from fractions import Fraction
import ctypes
import hashlib
import json
import os
import shutil

ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/double_replacement_signed_paths_20261008_v1'
TOTAL=52406569
CODE={
 'requests':('backtest/ndx_double_replacement_path_requests_research.py',None),
 'account':('backtest/ndx_signed_cash_flow_return_accounting_research.py','2fc9ff7c5c4a8ff086242d99d0c051ad13951e2e58f911d7cefdee9763cccebe'),
 'inspector':('backtest/ndx_signed_cash_flow_account_inspection_research.py','49697feb352c70c20dd344c81bcf62131a7d0041d2fdcfad2cf60cd9fef0dcbd'),
 'decoder':('backtest/ndx_double_replacement_compressed_raw_inspection_research.py','52a1013071018085b05ccf4905614c6986b3aa13bdb3c069a61703472e8624fd'),
 'stream':('backtest/ndx_research_json_rows_stream.py','b1a2ae63c68476dc952abf53bdd081e7f08cab3052ddc6fca5b61bd32091b86c')}
BOUND={
 'prepared':('data/cache/research/double_replacement_preparation_20261003_v1/preparation.json','fca04682cbda564a2f22d315894e7300c70d2f5d94d661adb16150cf5318c3f0'),
 'paired':('data/cache/research/old_holding_topup_paired_account_20261002_v1/accounts.json','7d5df8f295657497f3919aa3458dff31f0c175a40f391eb6b37ac9e5b7512d6f'),
 'paired_publication':('data/cache/research/old_holding_topup_paired_account_20261002_v1/publication.json','fb9db1ac77fffec7ec90141a7b431b3f34fb4bac0329deb07245c85b22325e7e'),
 'paired_readback_note':('DYNAMIC_OLD_HOLDING_TOPUP_PAIRED_INDEPENDENT_READBACK_20261002.md','706398b940313eb1fbe763f6cc625ac1e08bf8b56d513633b61bef6093e441b5'),
 'paired_reader':('scripts/ndx_old_holding_topup_paired_independent_review_20261002.py','4fe78e2f5133453b4da0bc8aca818cdca3cca6fd995a0a645bc7d2cc252948af')}
SELECTION_PATHS={k:str(ROOT/p)for k,p in {
 'selection':'data/cache/research/double_stream_selection_20261008_v1/selection.json',
 'selection_publication':'data/cache/research/double_stream_selection_20261008_v1/publication.json',
 'selection_audit':'data/cache/research/double_stream_selection_independent_readback_20261008_v1/independent_readback.json',
 'selection_reader':'scripts/ndx_double_stream_selection_independent_readback_20261008.py'}.items()}
SELECTION_READER_SHA=None
FLAGS=dict.fromkeys(('risk_recomputed','selection_reexecuted','controls_executed','fit_executed','orders_executed','point_in_time_verified','promotion_allowed','fresh_oos_claimed','cross_family_winner_selected','independent_source_readback_passed','full_transitive_source_closure_reverified','automatic_retry_allowed'),False)


def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def ref(p,h):return dict(path=str(p),sha256=h)
def reference(r):
    require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and r['path'],'Exact reference')
    p=Path(r['path']);require(p.is_absolute()and str(p)==r['path']and '..'not in p.parts,'Absolute canonical external reference path')
    h=r['sha256'];require(type(h)is str and len(h)==64 and set(h)<=set('0123456789abcdef'),'Explicit external SHA before IO');return r
def decode(raw):
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
        return d
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def filehash(p):
    for path in (Path(p),*Path(p).parents):require(not path.is_symlink()and not getattr(path,'is_junction',lambda:False)(),'No linked source or output')
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def merge(s,r):
    reference(r);require(r['path']not in s or s[r['path']]==r['sha256'],'Source collision');s[r['path']]=r['sha256']
def take(r,s):
    merge(s,r);require(filehash(r['path'])==r['sha256'],'Original source SHA');raw=Path(r['path']).read_bytes();require(sha(raw)==r['sha256'],'Same consumed source bytes');return raw
def flags(v):require(all(v[k]is False for k in FLAGS),'False authority exact')
def inventory(p):
    p=Path(p);items=list(p.rglob('*'));require(not any(v.name.casefold()=='failure.json'for v in items),'Failed source namespace')
    require(not any(v.is_symlink()or getattr(v,'is_junction',lambda:False)()for v in (p,*p.parents,*items)),'No linked namespace')
    return sorted(str(v.relative_to(p))for v in items)
def guard(c,*,small=False):
    require(filehash(SOURCE)==LOADED,'Loaded wrapper source drift')
    for p,h in (c['small']if small else c['sources']).items():require(filehash(p)==h,'Authenticated source drift')
    for p,n in c['dirs'].items():exact(inventory(p),n,'Source directory drift')
    for p in c.get('source_failure_paths',()):require(not Path(p).exists(),'Failed original full request or audit')
def resource(*,metadata_bytes=0,encoded_bytes=0):
    parent=OUTPUT
    while not parent.exists():parent=parent.parent
    require(shutil.disk_usage(parent).free>=5*1024**3+encoded_bytes,'5GiB plus encoded bytes')
    if metadata_bytes:
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong)for n in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        m=Memory();m.length=ctypes.sizeof(m)
        require(os.name=='nt'and ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)),'Measured Windows available memory')
        require(m.available>=2*1024**3+64*metadata_bytes,'Complete40 objects and deepcopy memory reserve')
def save(p,v,*,emergency=False):
    b=enc(v)
    if not emergency:resource(encoded_bytes=len(b))
    with Path(p).open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(Path(p).read_bytes()==b,'Durable output bytes');return ref(p,sha(b))
def diagnostic(e):
    try:message=str(e)
    except BaseException:message='<exception str failed>'
    return dict(type=type(e).__name__,message=message)
def preserve_call(path,function,kwargs):
    result=None;error=None
    try:result=function(**kwargs)
    except BaseException as e:error=diagnostic(e)
    raw=dict(call_invoked=True,call_count=1,returned=error is None,result=result,error=error,result_preserved_as_json=True)
    try:enc(raw)
    except BaseException as e:
        try:text=repr(result);repr_error=None
        except BaseException as re:text=None;repr_error=diagnostic(re)
        raw.update(result=None,result_preserved_as_json=False,result_type=type(result).__name__,representation=text,representation_error=repr_error,serialization_error=diagnostic(e))
    r=save(path,raw,emergency=True);return raw,r
def private(role,raw):
    p,h=CODE[role];require(sha(raw)==h,'Immediate compiled bytes identity');m=ModuleType('_private_signed_paths_'+role);m.__file__=str(ROOT/p);exec(compile(raw,str(ROOT/p),'exec'),m.__dict__);return m


def selected_raw(c):
    # Read at most one selected original gzip at a time. The selector's complete
    # audit remains mandatory; no 52M search or evaluator is called here.
    decoder=private('decoder',c['code_bytes']['decoder'])
    audit=c['docs']['selection_audit'];selection=c['docs']['selection']
    original_audit_reference=selection['input_references']['audit']
    require(audit['source_hashes'].get(original_audit_reference['path'])==original_audit_reference['sha256'],'Original complete execution audit consumed by selection reader')
    original=decode(take(original_audit_reference,c['sources']))
    require(original['schema']=='DOUBLE_REPLACEMENT_C_STREAM_INDEPENDENT_READBACK_V1'and original['status']=='PASS_FULL_DOMAIN','Complete native double audit')
    request_folder=Path(original['request_reference']['path']).parent
    c['source_failure_paths']=[str(request_folder/'failure.json'),str(request_folder.parent.parent/'failure.json'),str(Path(original_audit_reference['path']).parent/'failure.json')]
    for row in selection['selection']['rows']:
        chosen=row['selected']
        if chosen is None:continue
        locator=chosen['locator'];rawref=locator['raw_reference'];reference({k:rawref[k]for k in ('path','sha256')});merge(c['sources'],{k:rawref[k]for k in ('path','sha256')})
        parsed=[]
        for name,key,limit in (('manifest','source_manifest_reference',4096),('independent_audit','batch_readback_reference',8192)):
            loc=locator[name];exact(loc['reference'],original[key],'Original full-stream external anchor');r={k:loc['reference'][k]for k in ('path','sha256')};merge(c['sources'],r)
            begin,end=loc['byte_start'],loc['byte_stop'];require(type(begin)is int and type(end)is int and 0<=begin<end and end-begin<=limit,'Bounded original manifest span')
            with Path(r['path']).open('rb')as f:f.seek(begin);blob=f.read(end-begin)
            require(len(blob)==end-begin and blob.endswith(b'\n'),'Complete original manifest line');value=decode(blob);require(blob==enc(value)+b'\n'and sha(enc(value['record']))==value['record_sha256']==loc['record_sha256'],'Original canonical record SHA');exact(value['record']['sequence'],loc['line_index'],'Original line coordinate');parsed.append(value['record'])
        manifest,inspection=parsed;exact(inspection['source_manifest_record_sha256'],locator['manifest']['record_sha256'],'Audit actual manifest link');exact(inspection['batch_reference'],manifest['batch_result_reference'],'Audit physical batch')
        envelope=decode(take(manifest['batch_result_reference'],c['sources']));folder=Path(rawref['path']).parent
        require(manifest['batch_result_reference']['path']==str(folder/'stream_result.json'),'Original batch folder')
        require(set(inventory(folder))=={'started.json','raw_return.json.gz','raw_receipt.json','raw_byte_inspection.json','inspection.json','result.json','stream_result.json'},'Complete original successful batch')
        c['dirs'][str(folder)]=inventory(folder)
        filemap={}
        for item in envelope['files']:
            name=item['filename'];require(name not in filemap and name in {'started.json','raw_return.json.gz','raw_receipt.json','raw_byte_inspection.json','inspection.json','result.json'},'Original physical batch file')
            r=ref(folder/name,item['sha256']);require(Path(r['path']).stat().st_size==item['byte_count'],'Original file length');merge(c['sources'],r);filemap[name]=dict(r,byte_count=item['byte_count'])
        require(len(filemap)==6,'Complete original batch files');exact(rawref,filemap['raw_return.json.gz'],'Original gzip role')
        receipt=decode(take({k:filemap['raw_receipt.json'][k]for k in ('path','sha256')},c['sources']));exact(receipt['raw_reference'],rawref,'Receipt actual gzip')
        with Path(rawref['path']).open('rb')as f:decoded=decoder.read_gzip_raw(f,metadata=receipt['codec_metadata'],max_compressed_bytes=45050408,max_uncompressed_bytes=45036633)
        exact(decoded['inspection'],inspection['inspection']['raw_byte_inspection'],'Original independently audited gzip bytes')
        tokens=locator['json_tokens'];require(type(tokens)is list and len(tokens)==2 and tokens[0]=='results'and type(tokens[1])is int and 0<=tokens[1]<len(decoded['value']['results']),'Exact results index')
        exact(decoded['value']['results'][tokens[1]],chosen['raw'],'Selected original RAW without replay')
        del decoded


def load_inputs(registration_reference,*,compile_numerical=True):
    reference(registration_reference)
    require(type(SELECTION_READER_SHA)is str and len(SELECTION_READER_SHA)==64,'Pending final selection reader')
    for p,h in CODE.values():require(type(h)is str and len(h)==64,'Pending reviewed code')
    sources={str(SOURCE):LOADED};reg=decode(take(registration_reference,sources));flags(reg)
    require(reg['schema']=='DOUBLE_REPLACEMENT_SIGNED_PATH_SOURCE_REGISTRATION_V1'and reg['status']=='REGISTERED_SELECTED_SIGNED_PATHS_ONLY','Native double source registration')
    exact((reg['scenario_count'],reg['integer_count']),(40,TOTAL),'Complete double domain')
    refs=reg['input_references'];require(set(refs)==set(BOUND)|set(SELECTION_PATHS),'Exact nine source roles')
    for r in refs.values():reference(r)
    for k,(p,h)in BOUND.items():exact(refs[k],ref(ROOT/p,h),'Fixed sealed role')
    for k,p in SELECTION_PATHS.items():require(refs[k]['path']==p,'Fixed future selection role')
    require(refs['selection_reader']['sha256']==SELECTION_READER_SHA,'Final independent selection reader')
    resource(metadata_bytes=sum(Path(r['path']).stat().st_size for k,r in refs.items()if not k.endswith('reader')))
    docs={};modules={};code_bytes={}
    for k,r in refs.items():
        if k=='paired':continue
        raw=take(r,sources)
        if not k.endswith('reader')and k!='paired_readback_note':docs[k]=decode(raw)
    for k,(p,h)in CODE.items():
        code_bytes[k]=take(ref(ROOT/p,h),sources)
        if compile_numerical or k=='stream':modules[k]=private(k,code_bytes[k])
    prep=docs['prepared'];sel=docs['selection'];pub=docs['selection_publication'];audit=docs['selection_audit']
    require(sel['schema']=='DOUBLE_STREAM_SELECTION_DOCUMENT_V1'and pub['schema']=='DOUBLE_STREAM_SELECTION_PUBLICATION_V1'and audit['schema']=='DOUBLE_STREAM_SELECTION_INDEPENDENT_READBACK_V1'and audit['status']=='PASS_COMPLETE_DOMAIN','Native independently read double selection')
    exact(pub['selection_reference'],refs['selection'],'Published selection');exact(audit['selection_reference'],refs['selection'],'Audited selection');exact(audit['publication_reference'],refs['selection_publication'],'Audited publication')
    exact(audit['input_references'],sel['input_references'],'Same full execution anchors');exact(pub['input_references'],sel['input_references'],'Published execution anchors');exact(sel['input_references']['preparation'],refs['prepared'],'Original double preparation')
    require(audit['source_hashes'].get(refs['selection_reader']['path'])==SELECTION_READER_SHA,'Actual final reader closure')
    require(sel['selection']['full_domain_selected']is True and sel['selection']['integer_count']==TOTAL and sel['selection']['scenario_count']==40,'Entire original double domain')
    for value in (sel,pub,audit):
        for key in ('evaluation_reperformed','account_executed','orders_executed','fit_executed','future_returns_used','cross_family_winner_selected','point_in_time_verified','promotion_allowed','full_ndx_certified','execution_authorized'):require(value[key]is False,'Selection authority unchanged')
    for p,h in audit['source_hashes'].items():merge(sources,ref(p,h))
    for role in ('selection','selection_publication'):require(audit['source_hashes'].get(refs[role]['path'])==refs[role]['sha256'],'Actually consumed selected bytes')
    paired=docs['paired_publication'];require(paired['schema']=='OLD_HOLDING_TOPUP_PAIRED_ACCOUNT_PUBLICATION_V1'and paired['status']=='PUBLISHED_CONDITIONAL_PRICE_ONLY_PAIRED_PATHS','Saved old price template only');exact(paired['account_reference'],refs['paired'],'Original template SHA')
    dirs={}
    for role,names in (('prepared',{'started.json','raw_preparation.json','preparation.json','publication.json'}),('paired',{'accounts.json','publication.json','started.json'}),('selection',{'started.json','selection.json','publication.json'}),('selection_audit',{'started.json','independent_readback.json'})):
        folder=Path(refs[role]['path']).parent;require(set(inventory(folder))==names,'Exact original namespace');dirs[str(folder)]=sorted(names)
    c=dict(refs=refs,docs=docs,modules=modules,code_bytes=code_bytes,sources=sources,small={str(SOURCE):LOADED,**{str(ROOT/p):h for p,h in CODE.values()},registration_reference['path']:registration_reference['sha256']},dirs=dirs,registration_reference=registration_reference)
    selected_raw(c);guard(c);return c


def read_paired(c):
    r=c['refs'];old=[];locations=[]
    with Path(r['paired']['path']).open('rb')as f:
        stream=c['modules']['stream'].JsonRowsStream(f,max_row_bytes=8*1024**2)
        for token in stream:
            require(type(token['row_index'])is int and token['row_index']==len(old)<40,'Original40 paired order')
            old.append(token['value']);locations.append(dict(source_reference=r['paired'],**{k:token[k]for k in ('row_index','byte_start','byte_stop','sha256')}))
        summary=stream.summary
    require(summary['complete_document_consumed']is True and len(old)==40 and summary['sha256']==r['paired']['sha256'],'Complete paired EOF and exact bytes before any account')
    metadata=summary['metadata'];require(metadata['schema']=='OLD_HOLDING_TOPUP_PAIRED_PRICE_ONLY_ACCOUNT_V1'and type(metadata['scenario_count'])is int and metadata['scenario_count']==40 and type(metadata['new_account_path_count'])is int and metadata['new_account_path_count']==80,'Original80 path source')
    exact(metadata['source_hashes'],c['docs']['paired_publication']['source_hashes'],'Saved source declarations preserved not rerun');merge(c['sources'],r['paired']);guard(c)
    return old,locations,summary


def prepare_requests(c):
    r=c['refs'];old,locations,summary=read_paired(c)
    args=dict(prepared=c['docs']['prepared']['preparation'],selection=c['docs']['selection']['selection'],old_paired_rows=old,source_references={k:r[v]for k,v in [('prepared','prepared'),('selection','selection'),('selection_audit','selection_audit'),('old_paired','paired')]})
    raw,rr=preserve_call(OUTPUT/'raw_requests.json',c['modules']['requests'].prepare_double_replacement_path_requests,args)
    require(raw['returned']is True and raw['result_preserved_as_json']is True,'Complete request preparation return');value=raw['result']
    require(type(value)is dict and value['schema']=='DOUBLE_REPLACEMENT_SIGNED_PATH_REQUESTS_V1'and type(value['scenario_count'])is int and value['scenario_count']==40 and len(value['rows'])==40,'All forty original requests')
    guard(c);entries=[]
    for i,row in enumerate(value['rows']):
        require(type(row['scenario_index'])is int and row['scenario_index']==i and row['scenario_id']==old[i]['scenario_id'],'Prepared request coordinate')
        folder=OUTPUT/f'scenario-{i:02d}';folder.mkdir(exist_ok=False)
        request=save(folder/'request.json',dict(schema='DOUBLE_REPLACEMENT_SIGNED_PATH_REQUEST_V1',scenario_index=i,scenario_id=row['scenario_id'],prepared_request=row,paired_row_byte_reference=locations[i],raw_requests_reference=rr,input_references=r,source_hashes=c['sources'],**FLAGS))
        entries.append(dict(scenario_index=i,scenario_id=row['scenario_id'],input_status=row['status'],request_reference=request,outcome=row['status']if row['status']!='NEW_SIGNED_PATH_REQUIRED'else'UNDISPATCHED',account_call_invoked=False,account_call_returned=False,control_reference=row['control_path_reference']))
    ir=save(OUTPUT/'requests_index.json',dict(schema='DOUBLE_REPLACEMENT_SIGNED_PATH_REQUESTS_INDEX_V1',rows=entries,scenario_count=40,status_counts=value['status_counts'],raw_requests_reference=rr,paired_stream_summary=summary,registration_reference=c['registration_reference'],input_references=r,source_hashes=c['sources'],**FLAGS))
    return entries,ir,rr


def first_trade_check(row,result):
    require(result['schema']=='SIGNED_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1'and result['rows'],'Signed result schema')
    actual=result['rows'][0];evaluation=row['expected_first_trade'];task=row['selection_row']['selected']['raw']['plan']['task']
    for a,b in [('gross_buy_usd','gross_buy_usd'),('gross_sell_usd','gross_sell_usd'),('fees_usd','total_fee_usd'),('cash_after_usd','cash_after_usd'),('post_trade_open_equity_usd','equity_after_usd')]:require(Fraction(actual[a])==Fraction(evaluation[b]),'Exact first Open selected evaluation '+a)
    exact(actual['holdings_after'],task['proposed_holdings'],'First signed holdings');exact(actual['trade_shares'],task['signed_trade_quantities'],'First signed legs including zero')
    require(Fraction(actual['post_trade_open_equity_usd'])-Fraction(actual['post_flow_pre_fee_open_equity_usd'])==-Fraction(evaluation['total_fee_usd']),'Open fee conservation not Close PnL')


def output_guard(saved):
    for r in saved:require(filehash(r['path'])==r['sha256'],'Saved output drift')
    expected={str(Path(r['path']).relative_to(OUTPUT))for r in saved}
    actual={str(p.relative_to(OUTPUT))for p in OUTPUT.rglob('*')if p.is_file()};require(actual==expected,'Exact current output files')


def run(*,registration_reference=None,execute=False):
    require(execute is True,'Explicit new signed-path execution');reference(registration_reference);c=load_inputs(registration_reference)
    require(not OUTPUT.exists(),'Create-only no retry');resource();OUTPUT.mkdir(parents=True,exist_ok=False);saved=[];entries=[];failure=None
    try:
        saved.append(save(OUTPUT/'started.json',dict(schema='DOUBLE_REPLACEMENT_SIGNED_PATHS_STARTED_V1',registration_reference=registration_reference,input_references=c['refs'],source_hashes=c['sources'],paired_eof_required_before_dispatch=True,paired_readback_evidence_scope='WHOLE_MARKDOWN_REPORT',**FLAGS)))
        entries,index,raw_requests_ref=prepare_requests(c);saved.extend([raw_requests_ref,index]);saved.extend(r['request_reference']for r in entries)
        for entry in entries:
            if entry['input_status']!='NEW_SIGNED_PATH_REQUIRED':continue
            i=entry['scenario_index'];folder=OUTPUT/f'scenario-{i:02d}'
            try:
                resource();guard(c,small=True);request=decode(take(entry['request_reference'],{}));row=request['prepared_request']
                require(type(row['scenario_index'])is int and row['scenario_index']==i and row['scenario_id']==entry['scenario_id']and row['status']==entry['input_status'],'Exact dispatched request coordinates')
                started=save(folder/'started.json',dict(schema='DOUBLE_REPLACEMENT_SIGNED_PATH_STARTED_V1',scenario_index=i,scenario_id=entry['scenario_id'],request_reference=entry['request_reference'],registration_reference=registration_reference,numerical_id=sha(enc(dict(request=row['accounting_request'],task_id=row['selection_row']['selected']['raw']['plan']['task']['task_id'],account_source=ref(ROOT/CODE['account'][0],CODE['account'][1])))),**FLAGS));saved.append(started);entry['started_reference']=started
                entry.update(outcome='UNRESOLVED_DISPATCH',account_call_invoked=True,account_call_returned=None)
                raw,rawref=preserve_call(folder/'raw_result.json',c['modules']['account'].account_path,row['accounting_request']);saved.append(rawref);entry.update(raw_reference=rawref,account_call_returned=raw['returned'])
                error=None;inspection=None
                try:
                    require(raw['returned']is True and raw['result_preserved_as_json']is True and type(raw['result'])is dict,'Complete account return')
                    guard(c,small=True)
                    inspection=c['modules']['inspector'].inspect_saved_signed_account(**row['accounting_request'],saved_result=raw['result']);require(inspection['status']=='PASS','Independent saved arithmetic')
                    first_trade_check(row,raw['result'])
                except BaseException as e:error=diagnostic(e)
                if inspection is not None:
                    ir=save(folder/'inspection.json',inspection,emergency=True);saved.append(ir);entry['inspection_reference']=ir
                outcome='ACCOUNT_EXCEPTION'if raw['returned']is False else('VALIDATION_FAILURE'if error else'ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK')
                post=save(folder/'postcheck.json',dict(schema='DOUBLE_REPLACEMENT_SIGNED_PATH_POSTCHECK_V1',scenario_index=i,scenario_id=entry['scenario_id'],outcome=outcome,request_reference=entry['request_reference'],started_reference=started,raw_reference=rawref,inspection_reference=entry.get('inspection_reference'),validation_error=error,**FLAGS),emergency=True);saved.append(post);entry.update(outcome=outcome,postcheck_reference=post)
                if error:failure=dict(scenario_index=i,error=error);break
            except BaseException as e:
                failure=dict(scenario_index=i,error=diagnostic(e));break
        result=dict(schema='DOUBLE_REPLACEMENT_SIGNED_PATHS_RESULT_V1',status='COMPLETE_PENDING_INDEPENDENT_READBACK'if failure is None else'STOPPED_NO_RETRY',scenario_count=40,rows=entries,outcome_counts={k:sum(r['outcome']==k for r in entries)for k in ('ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK','NO_FEASIBLE','BLOCKED_TEMPLATE_PRICE_GAP','ACCOUNT_EXCEPTION','VALIDATION_FAILURE','UNRESOLVED_DISPATCH','UNDISPATCHED')},failure=failure,requests_index_reference=index,raw_requests_reference=raw_requests_ref,registration_reference=registration_reference,input_references=c['refs'],source_hashes=c['sources'],original_paired_source_claims_preserved=c['docs']['paired_publication']['source_hashes'],**FLAGS)
        rr=save(OUTPUT/'result.json',result,emergency=True);saved.append(rr)
        if failure is not None:raise RuntimeError('Stopped signed path request; original evidence in result')
        guard(c);output_guard(saved)
        pub=save(OUTPUT/'publication.json',dict(schema='DOUBLE_REPLACEMENT_SIGNED_PATHS_PUBLICATION_V1',status='PUBLISHED_PENDING_INDEPENDENT_SOURCE_READBACK',result_reference=rr,requests_index_reference=index,raw_requests_reference=result['raw_requests_reference'],started_reference=saved[0],registration_reference=registration_reference,input_references=c['refs'],source_hashes=c['sources'],**FLAGS));saved.append(pub)
        guard(c);output_guard(saved);return dict(result=rr,publication=pub)
    except BaseException as e:
        save(OUTPUT/'failure.json',dict(error=diagnostic(e),saved_references=saved,rows=entries,registration_reference=registration_reference,**FLAGS),emergency=True);raise


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--registration');p.add_argument('--sha256');a=p.parse_args();print(json.dumps(run(registration_reference=ref(a.registration,a.sha256),execute=a.execute)))
