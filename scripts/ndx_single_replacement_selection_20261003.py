"""Registered, complete-domain saved-evidence selection. No evaluation or account.

The external registration is an authorization to consume exact completed saved
evidence, not a fabricated future anchor. No registration/default execute: no IO.
"""
from pathlib import Path
from types import ModuleType
import ctypes
import hashlib
import json
import os
import shutil

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_single_replacement_selection_research.py'
CORE_SHA='a70d86a25fa4b6a5e9680aadf3c64e007da91cdecd284a8eaacbce33d4876082'
OUTPUT=ROOT/'data/cache/research/single_replacement_selection_20261003_v1'
EXECUTION=ROOT/'data/cache/research/single_replacement_evaluation_20261003_v1'
AUDIT_ROOT=ROOT/'data/cache/research/single_replacement_execution_independent_readback_20261003_v1'
READER=ROOT/'scripts/ndx_single_replacement_execution_independent_readback_20261003.py'
PREP=ROOT/'data/cache/research/single_replacement_preparation_20261003_v1'
PREP_AUDIT=ROOT/'data/cache/research/single_replacement_preparation_independent_readback_20261003_v1'
BOUND={
 'preparation':(str(PREP/'preparation.json'),'510a150834c82a9d68b2979d43c57c808d47800d0f1fc7258896fe7010ecedf6'),
 'publication':(str(PREP/'publication.json'),'e7a16bafeb236dd3e023c6c8f983041ac7a4236fb898124c20142d9bf4484c4c'),
 'audit':(str(PREP_AUDIT/'independent_readback.json'),'d5d5426406a4be38fd2f01285ab9a68cc36e48e54880f33eb46933e0edb001d9'),
 'reader':(str(ROOT/'scripts/ndx_single_replacement_preparation_independent_readback_20261003.py'),'0b4654ec4530eea382c948cae4eede99b2ced433757fae2557dfe89c8f3df48d')}
TOTAL=126541
FLAGS=dict.fromkeys(('point_in_time_verified','full_ndx_certified','cross_family_winner_selected','account_executed','fit_executed','evaluation_reperformed','future_returns_used','execution_authorized','promotion_allowed','automatic_retry_allowed'),False)
ROLES={'preparation','preparation_publication','preparation_audit','preparation_reader','request','execution_audit','execution_reader'}


def require(ok,message):
    if not ok:raise ValueError(message)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,message):require(enc(a)==enc(b),message)
def reference(r):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'],'Exact reference')
    h=r['sha256'];require(type(h) is str and len(h)==64 and set(h)<=set('0123456789abcdef'),'Explicit SHA before IO');return r
def ref(p,h):return dict(path=str(p),sha256=h)
def decode(b):
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
        return d
    return json.loads(b.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def filehash(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def merge(s,r):
    reference(r);require(r['path'] not in s or s[r['path']]==r['sha256'],'Source hash collision');s[r['path']]=r['sha256']
def take(r,s):
    merge(s,r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Same consumed source bytes');return b
def flags(v):require(all(v[k] is False for k in FLAGS),'False permissions exact')
def inventory(folder):
    p=Path(folder);require(not any(v.name.casefold()=='failure.json' for v in p.rglob('*')),'Failed parent is not selectable')
    return sorted(str(v.relative_to(p)) for v in p.rglob('*'))
def guard(c):
    require(filehash(SOURCE)==LOADED,'Loaded publisher bytes')
    for p,h in c['sources'].items():require(filehash(p)==h,'Final source bytes drift')
    for p,names in c['dirs'].items():require(inventory(p)==names,'Source namespace drift')
def resource(encoded_bytes=0,metadata_bytes=0):
    # CPython JSON dicts + selector's isolated deepcopy: conservative 64x.
    ancestor=OUTPUT
    while not ancestor.exists():ancestor=ancestor.parent
    require(shutil.disk_usage(ancestor).free>=5*1024**3+encoded_bytes,'5GiB plus encoded output bytes')
    if metadata_bytes:
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        m=Memory();m.length=ctypes.sizeof(m)
        require(os.name=='nt' and ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)),'Measured Windows memory gate')
        require(m.available>=2*1024**3+64*metadata_bytes,'Audit metadata plus deepcopy memory reserve')
def save(name,value,*,emergency=False):
    b=enc(value)
    if not emergency:resource(len(b))
    p=OUTPUT/name
    with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Saved output exact');return ref(p,sha(b))


def load_inputs(registration_reference,*,compile_selector=True):
    reference(registration_reference)  # No filesystem access for an absent anchor.
    sources={str(SOURCE):LOADED};registration=decode(take(registration_reference,sources))
    require(registration['schema']=='SINGLE_REPLACEMENT_SELECTION_SOURCE_REGISTRATION_V1' and registration['status']=='REGISTERED_SAVED_COMPLETE_DOMAIN_SELECTION_ONLY','Explicit external registration')
    flags(registration);require(type(registration['integer_count']) is int and registration['integer_count']==TOTAL and type(registration['scenario_count']) is int and registration['scenario_count']==40,'Fixed original domain')
    refs=registration['input_references'];require(set(refs)==ROLES,'Seven fixed source roles')
    for r in refs.values():reference(r)
    original={k:ref(p,h) for k,(p,h) in BOUND.items()}
    for k,role in [('preparation','preparation'),('publication','preparation_publication'),('audit','preparation_audit'),('reader','preparation_reader')]:exact(refs[role],original[k],'Fixed sealed preparation role')
    require(refs['execution_reader']['path']==str(READER) and refs['execution_audit']['path']==str(AUDIT_ROOT/'independent_readback.json'),'Registered final reader/audit locations')
    require(Path(refs['request']['path']).parent.parent==EXECUTION and Path(refs['request']['path']).name=='result.json','Final request location')
    size=Path(refs['execution_audit']['path']).stat().st_size+Path(refs['preparation']['path']).stat().st_size
    resource(metadata_bytes=size)
    docs={k:decode(take(r,sources)) for k,r in refs.items() if not k.endswith('reader')}
    for k in ('preparation_reader','execution_reader'):take(refs[k],sources)
    audit=docs['execution_audit'];request=docs['request'];out=docs['preparation'];pa=docs['preparation_audit']
    require(audit['schema']=='SINGLE_REPLACEMENT_EXECUTION_INDEPENDENT_READBACK_V1' and audit['status']=='PASS_SAVED_PREFIX' and audit['full_domain_evaluated'] is True,'Only full audited domain')
    require(all(audit[k] is False for k in ('producer_called','evaluator_called','old_account_reopened','point_in_time_verified','full_ndx_certified','economic_winner_selected','account_executed','fit_executed','orders_executed','automatic_retry_allowed')),'Original independent evidence permissions')
    partition=audit['partition'];require(type(partition['full_integer_count']) is int and type(partition['terminal_count']) is int and partition['full_integer_count']==partition['terminal_count']==TOTAL and partition['unresolved_ordinal'] is None and type(partition['undispatched_count']) is int and partition['undispatched_count']==0,'Full independently inspected integer denominator')
    counts=partition['outcome_counts'];require(set(counts)=={'FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE'} and all(type(n) is int and n>=0 for n in counts.values()) and counts['EVALUATION_EXCEPTION']==counts['VALIDATION_FAILURE']==0 and sum(counts.values())==TOTAL,'No failed or unknown saved domain')
    require(audit['reader_sha256']==refs['execution_reader']['sha256'],'Final reader binding');exact(audit['request_reference'],refs['request'],'Actual terminal request')
    exact(audit['input_references'],original,'All prepared roles');exact(request['input_references'],original,'Request prepared roles')
    require(request['full_queue_completed'] is True and request['status']=='REQUEST_COMPLETE_PENDING_INDEPENDENT_READBACK','Complete request only')
    require(out['schema']=='SOURCE_BOUND_SINGLE_REPLACEMENT_PREPARATION_V1','Prepared document')
    exact(docs['preparation_publication']['preparation_reference'],refs['preparation'],'Prepared publication link')
    require(pa['status']=='PASS' and pa['reader_sha256']==refs['preparation_reader']['sha256'],'Original preparation audit')
    exact(pa['preparation_reference'],refs['preparation'],'Prepared audit link')
    for p,h in audit['source_hashes'].items():merge(sources,ref(p,h))
    # No old-account reopening: only the authenticated execution reader's actual
    # consumed map, not the preparation document's unverified parent claims.
    for k,r in refs.items():
        if k!='execution_audit':require(audit['source_hashes'].get(r['path'])==r['sha256'],'Execution audit consumed source role')
    raw=take(ref(CORE,CORE_SHA),sources)
    core=None
    if compile_selector:
        core=ModuleType('_registered_complete_replacement_selector');core.__file__=str(CORE);exec(compile(raw,str(CORE),'exec'),core.__dict__)
    dirs={str(EXECUTION):inventory(EXECUTION),str(AUDIT_ROOT):inventory(AUDIT_ROOT),str(PREP):inventory(PREP),str(PREP_AUDIT):inventory(PREP_AUDIT)}
    expected=['registration.json']
    require(type(request['request_number']) is int and request['request_number']>=0,'Original final request number')
    for kind,count,names in [('request',request['request_number']+1,('started.json','result.json')),('shard',len(audit['shards']),('started.json','result.json','journal.jsonl'))]:
        for i in range(count):
            folder=f'{kind}-{i:04d}';expected.append(folder);expected.extend(str(Path(folder)/n) for n in names)
    exact(dirs[str(EXECUTION)],sorted(expected),'Exact complete execution inventory')
    require(set(dirs[str(AUDIT_ROOT)])=={'started.json','independent_readback.json'},'Complete audit namespace')
    for role in ('inputs','inventory','scenarios'):
        p=Path(pa['input_references'][role]['path']).parent;dirs[str(p)]=inventory(p)
    c=dict(sources=sources,dirs=dirs,registration=registration,registration_reference=registration_reference,refs=refs,prepared=out['preparation'],audit=audit,core=core)
    guard(c);return c


def stream_records(c):
    """One bounded line at a time, same bytes hashed and decoded, strict EOF."""
    ordinal=0
    for si,s in enumerate(c['audit']['shards']):
        report=s['inspection'];result=decode(take(s['shard_result_reference'],c['sources']))
        jr=result['journal_reference'];require(jr['path']==str(EXECUTION/f'shard-{si:04d}'/'journal.jsonl') and jr['sha256']==report['journal_sha256'],'Fixed journal role')
        require(c['audit']['source_hashes'].get(jr['path'])==jr['sha256'],'Audited journal bytes');merge(c['sources'],jr)
        require(result['status']=='COMPLETE_PENDING_INDEPENDENT_READBACK','Complete shard')
        h=hashlib.sha256();offset=0;previous='0'*64;task=None;returned=None;rawloc=None
        with Path(jr['path']).open('rb') as f:
            for seq,loc in enumerate(report['records']):
                line=f.readline(4*1024*1024+1);require(0<len(line)<=4*1024*1024 and line.endswith(b'\n'),'Bounded complete record')
                h.update(line);v=decode(line);b=v['body'];require(set(v)=={'body','record_sha256'} and sha(enc(b))==v['record_sha256'],'Original record SHA')
                require(b['schema']=='SINGLE_REPLACEMENT_JOURNAL_RECORD_V1' and type(b['sequence']) is int and b['sequence']==seq and b['previous_sha256']==previous and b['context_sha256']==result['context_sha256'],'Record chain/context')
                observed=dict(sequence=seq,byte_start=offset,byte_stop=offset+len(line),record_sha256=v['record_sha256'],stage=b['stage'],global_ordinal=b['global_ordinal'])
                exact(observed,loc,'Exact audited byte locator');require(type(b['global_ordinal']) is int and b['global_ordinal']==ordinal,'Original global order')
                p=b['payload'];stage=('START','RAW_RETURNED','POSTCHECK')[seq%3];require(b['stage']==stage,'Three-stage complete task')
                if stage=='START':
                    require(p['dispatch_may_have_occurred'] is True,'Original actual dispatch fact');task=p['task'];require(task['task_id']==b['task_id'],'START identity')
                elif stage=='RAW_RETURNED':
                    require(b['task_id']==task['task_id'] and p['call_invoked'] is True and type(p['call_count']) is int and p['call_count']==1 and p['returned'] is True and p['error'] is None and p['result_preserved_as_json'] is True,'Original returned JSON and task');returned=p['result'];rawloc=loc
                else:
                    terminal=report['terminal_rows'][seq//3];require(p['outcome'] in ('FEASIBLE','INFEASIBLE'),'No technical prefix winner');exact(terminal,dict(global_ordinal=ordinal,task_id=b['task_id'],outcome=p['outcome']),'Audited terminal')
                    require(task['task_id']==b['task_id']==report['terminal_rows'][seq//3]['task_id'],'Task unchanged')
                    yield dict(global_ordinal=ordinal,task=task,evaluation=returned,source_reference=dict(journal_reference=jr,record_locator=rawloc,json_pointer='/body/payload/result'),inspection_reference=dict(reference=c['refs']['execution_audit'],json_pointer=f'/shards/{si}/inspection/terminal_rows/{seq//3}'))
                    ordinal+=1
                offset+=len(line);previous=v['record_sha256']
            require(f.read(1)==b'','Full journal EOF, no extra records')
        require(h.hexdigest()==jr['sha256'] and previous==report['terminal_record_sha256'],'Entire consumed journal hash')
    require(ordinal==TOTAL,'Full original domain EOF')


def run(*,registration_reference=None,execute=False):
    require(execute is True,'Explicit saved selection only');reference(registration_reference)
    c=load_inputs(registration_reference);require(not OUTPUT.exists(),'Create-only no retry');resource();OUTPUT.mkdir(parents=True,exist_ok=False);saved=[]
    try:
        saved.append(save('started.json',dict(schema='SINGLE_REPLACEMENT_SELECTION_STARTED_V1',registration_reference=registration_reference,input_references=c['refs'],source_hashes=c['sources'],**FLAGS)))
        result=c['core'].select_complete_single_replacements(prepared=c['prepared'],preparation_reference=c['refs']['preparation'],readback=c['audit'],readback_reference=c['refs']['execution_audit'],records=stream_records(c))
        raw=dict(returned=True,result=result)
        try:enc(raw)
        except BaseException as serialization_error:
            try:representation=repr(result);representation_error=None
            except BaseException as e:representation=None;representation_error=dict(type=type(e).__name__,message=str(e))
            saved.append(save('raw_selection.json',dict(returned=True,result=None,result_preserved_as_json=False,result_type=type(result).__name__,representation=representation,representation_error=representation_error,serialization_error=dict(type=type(serialization_error).__name__,message=str(serialization_error))),emergency=True))
            raise
        saved.append(save('raw_selection.json',raw,emergency=True))
        require(type(result) is dict and sha(enc(result['document']))==result['content_sha256'],'Returned complete selection envelope')
        require(result['document']['integer_count']==TOTAL and result['document']['scenario_count']==40 and result['document']['all_registered_points_consumed'] is True,'Full selection before publication')
        guard(c)
        selected=save('selection.json',dict(schema='SOURCE_BOUND_SINGLE_REPLACEMENT_SELECTION_V1',selection=result,registration_reference=registration_reference,input_references=c['refs'],source_hashes=c['sources'],raw_reference=saved[-1],scope='FULL_SAVED_WITHIN_FAMILY_SELECTION_NOT_ACCOUNTS_OR_FORMAL_WINNER',**FLAGS));saved.append(selected)
        publication=save('publication.json',dict(schema='SINGLE_REPLACEMENT_SELECTION_PUBLICATION_V1',status='PUBLISHED_PENDING_INDEPENDENT_READBACK',selection_reference=selected,started_reference=saved[0],raw_reference=saved[1],registration_reference=registration_reference,input_references=c['refs'],source_hashes=c['sources'],**FLAGS));saved.append(publication)
        guard(c)
        for r in saved:require(filehash(r['path'])==r['sha256'],'Final saved output bytes')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','raw_selection.json','selection.json','publication.json'},'Exact output inventory')
        return dict(selection=selected,publication=publication)
    except BaseException as e:
        save('failure.json',dict(error_type=type(e).__name__,error=str(e),saved_references=saved,registration_reference=registration_reference,**FLAGS),emergency=True);raise


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--registration');p.add_argument('--sha256');a=p.parse_args()
    print(json.dumps(run(registration_reference=ref(a.registration,a.sha256),execute=a.execute)))
