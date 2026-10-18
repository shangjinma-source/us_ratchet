"""Create-only exact-domain single replacement evaluation. Never an account run."""
from pathlib import Path
from types import ModuleType
import builtins
import hashlib
import json
import os
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/single_replacement_evaluation_20261003_v1'
PARENT=ROOT/'data/cache/research/single_replacement_preparation_20261003_v1'
AUDIT_ROOT=ROOT/'data/cache/research/single_replacement_preparation_independent_readback_20261003_v1'
CODE={
 'registration':('backtest/ndx_single_replacement_execution_registration_research.py','3b4addb89fd9c7dc7494c873df3e4c50662852cc4aab61f4f7b1c7dbcd5cab89'),
 'journal':('backtest/ndx_single_replacement_journal_research.py','da86254528484bdac2945faa4a8625add03769f1295339ba8f5a2ac10713aa7d'),
 'evaluator':('backtest/ndx_single_replacement_evaluation_research.py','4303ead0a9d57d1bb95a4b6c563c707894a71eadec3c881bd082be3be5f1d767'),
 'domain':('backtest/ndx_single_replacement_domain_research.py','8df88963158ba8d3787c61705ca04f4a41ab481759701a291ccdbe75ae7505d7'),
 'risk':('backtest/ndx_conditional_new_cash_fork_research.py','5bb17d621b42707cfe312676279d59b565c3e97900bf3bdd6f9335df65aa0c5f')}
BOUND={
 'preparation':(str(PARENT/'preparation.json'),'510a150834c82a9d68b2979d43c57c808d47800d0f1fc7258896fe7010ecedf6'),
 'publication':(str(PARENT/'publication.json'),'e7a16bafeb236dd3e023c6c8f983041ac7a4236fb898124c20142d9bf4484c4c'),
 'audit':(str(AUDIT_ROOT/'independent_readback.json'),'d5d5426406a4be38fd2f01285ab9a68cc36e48e54880f33eb46933e0edb001d9'),
 'reader':('scripts/ndx_single_replacement_preparation_independent_readback_20261003.py','0b4654ec4530eea382c948cae4eede99b2ced433757fae2557dfe89c8f3df48d')}
FLAGS=dict.fromkeys(('point_in_time_verified','full_ndx_certified','economic_winner_selected',
 'account_executed','fit_executed','orders_executed','automatic_retry_allowed'),False)
RESERVE=5*1024**3


def require(ok,msg):
    if not ok: raise ValueError(msg)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def ref(p,h):return dict(path=str(p),sha256=h)
def reference(r):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'],'Exact external reference')
    require(type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Explicit SHA before IO')
    return r
def read(r):
    reference(r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed bytes SHA');return b
def resource(path,additional=0):
    p=Path(path)
    while not p.exists():p=p.parent
    require(shutil.disk_usage(p).free>=RESERVE+additional,'RESOURCE_STOP_BEFORE_DISPATCH')
def save(path,value,emergency=False):
    b=enc(value)
    if not emergency:resource(path,len(b))
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Saved bytes');return ref(path,sha(b))
def guard(sources,dirs):
    require(sha(SOURCE.read_bytes())==LOADED,'Loaded worker identity')
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Source drift')
    for p,names in dirs.items():require({v.name for v in Path(p).iterdir()}==set(names),'Parent exact inventory')
def private(role,domain=None):
    p,h=CODE[role];p=ROOT/p;b=read(ref(p,h));m=ModuleType('_private_single_replacement_'+role);m.__file__=str(p)
    builtin=dict(vars(builtins));original=builtins.__import__
    def imports(name,globals=None,locals=None,fromlist=(),level=0):
        if name=='backtest' and fromlist==('ndx_single_replacement_domain_research',):
            require(domain is not None,'Private domain binding');package=ModuleType('backtest');package.ndx_single_replacement_domain_research=domain;return package
        return original(name,globals,locals,fromlist,level)
    builtin['__import__']=imports;m.__dict__['__builtins__']=builtin;exec(compile(b,str(p),'exec'),m.__dict__);return m


def load_common():
    refs={k:reference(ref(ROOT/p,h)) for k,(p,h) in BOUND.items()}
    sources={str(SOURCE):LOADED,**{str(ROOT/p):h for p,h in CODE.values()}}
    for p,h in sources.items():read(ref(p,h))
    docs={}
    for k,r in refs.items():
        b=read(r);sources[r['path']]=r['sha256']
        if k!='reader':docs[k]=json.loads(b)
    a=docs['audit'];o=docs['preparation'];pub=docs['publication']
    require(a['schema']=='SINGLE_REPLACEMENT_PREPARATION_INDEPENDENT_READBACK_V1' and a['status']=='PASS','Independent prepared domain')
    exact(a['preparation_reference'],refs['preparation'],'Audit preparation');exact(a['publication_reference'],refs['publication'],'Audit publication')
    require(a['reader_sha256']==refs['reader']['sha256'],'Audit reader')
    require(o['schema']=='SOURCE_BOUND_SINGLE_REPLACEMENT_PREPARATION_V1' and pub['schema']=='SINGLE_REPLACEMENT_PREPARATION_PUBLICATION_V1','Parent roles')
    exact(pub['preparation_reference'],refs['preparation'],'Parent publication link')
    for p,h in a['source_hashes'].items():
        require(p not in sources or sources[p]==h,'Source claim collision');read(ref(p,h));sources[p]=h
    # Audit externally binds these direct source bytes; original-account parent claims are deliberately not opened.
    dirs={str(PARENT):{'started.json','raw_preparation.json','preparation.json','publication.json'},str(AUDIT_ROOT):{'started.json','independent_readback.json'}}
    for role in ('inputs','inventory','scenarios'):
        p=Path(a['input_references'][role]['path']);names={'inputs.json','publication.json'} if role=='inputs' else {'inventory.json','publication.json'} if role=='inventory' else {'scenarios.json'}
        dirs[str(p.parent)]=names
    domain=private('domain');evaluator=private('evaluator',domain);registration=private('registration');journal=private('journal')
    validated=evaluator.validate_prepared(o['preparation'])
    plan=registration.build_execution_registration(prepared=o['preparation'],preparation_reference=refs['preparation'],preparation_audit_reference=refs['audit'],evaluator_reference=ref(ROOT/CODE['evaluator'][0],CODE['evaluator'][1]),shard_size=512)
    require(plan['document']['scenario_count']==40 and plan['document']['integer_count']==126541,'Registered full actual domain')
    for k in ('scenario_count','pair_count','integer_count','financial_integer_count_before_issuer','structurally_excluded_integer_count'):
        exact(plan['document'][k],a['inspection'][k],'Audited full denominator')
    guard(sources,dirs)
    return dict(refs=refs,sources=sources,dirs=dirs,validated=validated,plan=plan,evaluator=evaluator,journal=journal,
                small_sources={str(SOURCE):LOADED,**{str(ROOT/p):h for p,h in CODE.values()}})


def diagnostic(error):
    try:message=str(error)
    except BaseException:message='<str failed>'
    return dict(type=type(error).__name__,message=message)


def process_shard(c,descriptor,folder):
    evaluator=c['evaluator'];journal=c['journal'];identity=descriptor['identity'];context=sha(enc(dict(plan_sha256=c['plan']['content_sha256'],descriptor=descriptor,source_hashes=c['sources'])))
    tasks=[evaluator.project_validated_task(c['validated'],i) for i in range(identity['start'],identity['stop'])]
    require(len({t['task_id'] for t in tasks})==len(tasks),'Unique task identities')
    resource(folder);folder.mkdir(parents=True,exist_ok=False)
    start=save(folder/'started.json',dict(schema='SINGLE_REPLACEMENT_SHARD_STARTED_V1',descriptor=descriptor,context_sha256=context,source_hashes=c['sources'],ordered_tasks=[dict(global_ordinal=t['global_ordinal'],task_id=t['task_id']) for t in tasks],**FLAGS))
    sequence=0;previous='0'*64;error=None;f=(folder/'journal.jsonl').open('xb')
    def append(task,stage,payload):
        nonlocal sequence,previous
        record=journal.make_record(context_sha256=context,sequence=sequence,previous_sha256=previous,global_ordinal=task['global_ordinal'],task_id=task['task_id'],stage=stage,payload=payload)
        b=enc(record)+b'\n';f.write(b);f.flush();os.fsync(f.fileno());sequence+=1;previous=record['record_sha256']
    try:
        for task in tasks:
            resource(folder);guard(c['small_sources'],{})
            append(task,'START',dict(task=task,dispatch_may_have_occurred=True))
            result=None;failure=None
            try:result=evaluator.evaluate_one(c['validated']['cases'][task['scenario_index']]['identity']['original_input_row'],task)
            except BaseException as e:failure=diagnostic(e)
            raw=dict(call_invoked=True,call_count=1,returned=failure is None,result=result,error=failure,result_preserved_as_json=True)
            try:enc(raw)
            except BaseException as e:
                try:representation=repr(result)
                except BaseException as other:representation='<repr failed: '+type(other).__name__+'>'
                raw.update(result=None,result_preserved_as_json=False,result_type=type(result).__name__,representation=representation,serialization_error=diagnostic(e))
            append(task,'RAW_EXCEPTION' if failure else 'RAW_RETURNED',raw)
            outcome='EVALUATION_EXCEPTION' if failure else 'VALIDATION_FAILURE';validation=None
            if failure is None:
                try:
                    guard(c['small_sources'],{})
                    require(raw['result_preserved_as_json'] is True and type(result) is dict,'Complete returned evaluation')
                    require(result['status'] in ('FEASIBLE','INFEASIBLE') and result['feasible'] is (result['status']=='FEASIBLE'),'Typed economic outcome')
                    require(set(result['risk']['checks'])==set(evaluator.CHECKS) and all(type(v) is bool for v in result['risk']['checks'].values()),'Complete five risk checks')
                    require(result['risk']['all_passed'] is all(result['risk']['checks'].values()),'Risk conjunction')
                    require(type(result['financial_checks']) is dict and set(result['financial_checks'])=={'NONNEGATIVE_CASH','CASH_BUFFER'} and all(type(v) is bool for v in result['financial_checks'].values()),'Financial checks')
                    require(result['feasible'] is (all(result['financial_checks'].values()) and result['risk']['all_passed'] and not result['issuer_conflicts']),'Outcome conjunction')
                    outcome=result['status']
                except BaseException as e:validation=diagnostic(e)
            append(task,'POSTCHECK',dict(outcome=outcome,validation_error=validation))
            if outcome not in ('FEASIBLE','INFEASIBLE'):raise RuntimeError('Technical terminal; no retry')
    except BaseException as e:error=diagnostic(e)
    finally:f.close()
    b=(folder/'journal.jsonl').read_bytes();scan=journal.inspect_journal(b,context_sha256=context,ordered_tasks=tasks)
    if error is None:
        try:guard(c['sources'],c['dirs']);require(scan['complete'],'Full shard evidence')
        except BaseException as e:error=diagnostic(e)
    report=dict(schema='SINGLE_REPLACEMENT_SHARD_RESULT_V1',status='STOPPED_NO_RETRY' if error else 'COMPLETE_PENDING_INDEPENDENT_READBACK',descriptor=descriptor,context_sha256=context,started_reference=start,journal_reference=ref(folder/'journal.jsonl',sha(b)),inspection=scan,error=error,
                source_check_scope='SMALL_CODE_BEFORE_EACH_CALL_AND_AFTER_RETURN_FULL_SOURCES_AT_SHARD_BOUNDARIES',**FLAGS)
    rr=save(folder/'result.json',report,emergency=True)
    if error:save(folder/'failure.json',dict(error=error,result_reference=rr,**FLAGS),emergency=True)
    else:
        try:
            guard(c['sources'],c['dirs']);read(start);read(rr);require(sha((folder/'journal.jsonl').read_bytes())==scan['journal_sha256'],'Final journal bytes')
            require({p.name for p in folder.iterdir()}=={'started.json','journal.jsonl','result.json'},'Exact shard output')
        except BaseException as e:
            save(folder/'failure.json',dict(error=diagnostic(e),result_reference=rr,**FLAGS),emergency=True);raise
    return rr


def verify_completed(c,r,descriptor):
    folder=OUTPUT/('shard-'+str(descriptor['identity']['ordinal']).zfill(4))
    require(r['path']==str(folder/'result.json'),'Fixed completed shard path')
    require({p.name for p in folder.iterdir()}=={'started.json','journal.jsonl','result.json'},'Completed shard has no failure/tail residue')
    out=json.loads(read(r));require(out['schema']=='SINGLE_REPLACEMENT_SHARD_RESULT_V1' and out['status']=='COMPLETE_PENDING_INDEPENDENT_READBACK' and out['error'] is None,'Only saved complete shard can resume')
    require(all(out[k] is False for k in FLAGS),'Saved authority flags')
    exact(out['descriptor'],descriptor,'Frozen descriptor')
    context=sha(enc(dict(plan_sha256=c['plan']['content_sha256'],descriptor=descriptor,source_hashes=c['sources'])))
    require(out['context_sha256']==context,'Resume full source context')
    require(out['started_reference']['path']==str(folder/'started.json') and out['journal_reference']['path']==str(folder/'journal.jsonl'),'Saved file positions')
    start=json.loads(read(out['started_reference']));tasks=[c['evaluator'].project_validated_task(c['validated'],i) for i in range(descriptor['identity']['start'],descriptor['identity']['stop'])]
    require(start['schema']=='SINGLE_REPLACEMENT_SHARD_STARTED_V1' and all(start[k] is False for k in FLAGS),'Started role/authority')
    exact(start['descriptor'],descriptor,'Started descriptor');exact(start['source_hashes'],c['sources'],'Started source context')
    exact(start['ordered_tasks'],[dict(global_ordinal=t['global_ordinal'],task_id=t['task_id']) for t in tasks],'Started ordered tasks')
    require(start['context_sha256']==context,'Started hash context')
    scan=c['journal'].inspect_journal(read(out['journal_reference']),context_sha256=context,ordered_tasks=tasks)
    exact(scan,out['inspection'],'Saved independent grammar scan');require(scan['complete'] and all(t['outcome'] in ('FEASIBLE','INFEASIBLE') for t in scan['terminal_rows']),'No failed evidence retry')
    return scan['terminal_rows']


def run(*,execute=False,max_shards=1,prior_result_reference=None):
    require(execute is True and type(max_shards) is int and 1<=max_shards<=248,'Explicit bounded request')
    if prior_result_reference is not None:reference(prior_result_reference)
    else:require(not OUTPUT.exists(),'Existing namespace needs explicit successful result anchor; never retry')
    c=load_common();resource(OUTPUT);terminals=[];completed=[];request_number=0;prior_requests=[];prior_files={};prior_dirs={}
    if prior_result_reference is None:
        OUTPUT.mkdir(parents=True,exist_ok=False);registration_ref=save(OUTPUT/'registration.json',c['plan'])
    else:
        prior=json.loads(read(prior_result_reference))
        require(prior['schema']=='SINGLE_REPLACEMENT_BATCH_RESULT_V1' and prior['status']=='REQUEST_COMPLETE_PENDING_INDEPENDENT_READBACK' and all(prior[k] is False for k in FLAGS),'Explicit successful prior request')
        require(type(prior['request_number']) is int and prior['request_number']>=0,'Prior request index')
        request_number=prior['request_number']+1
        require(prior_result_reference['path']==str(OUTPUT/('request-'+str(request_number-1).zfill(4))/'result.json'),'Fixed prior request result')
        registration_ref=prior['registration_reference'];require(registration_ref['path']==str(OUTPUT/'registration.json'),'Fixed registration')
        exact(json.loads(read(registration_ref)),c['plan'],'Same complete registered domain')
        exact(prior['input_references'],c['refs'],'Same external input refs');exact(prior['source_hashes'],c['sources'],'Same source closure')
        completed=prior['completed_shard_references'];require(type(completed) is list and len(completed)<=len(c['plan']['document']['shards']),'Completed prefix')
        for i,r in enumerate(completed):
            terminals.extend(verify_completed(c,r,c['plan']['document']['shards'][i]))
            old=json.loads(read(r))
            for oldref in (r,old['started_reference'],old['journal_reference']):prior_files[oldref['path']]=oldref['sha256']
            prior_dirs[str(Path(r['path']).parent)]={'started.json','journal.jsonl','result.json'}
        exact(prior['partition'],private('registration').summarize_execution_prefix(registration=c['plan'],terminal_rows=terminals),'Prior complete partition')
        prior_requests=prior['prior_request_references']+[prior_result_reference]
        require(len(prior_requests)==request_number,'Full prior request chain')
        for i,r in enumerate(prior_requests):
            folder=OUTPUT/('request-'+str(i).zfill(4));require(r['path']==str(folder/'result.json') and {p.name for p in folder.iterdir()}=={'started.json','result.json'},'Prior request exact files')
            v=json.loads(read(r));require(v['request_number']==i and v['status']=='REQUEST_COMPLETE_PENDING_INDEPENDENT_READBACK','No earlier failed request')
            sr=v['started_reference'];require(sr['path']==str(folder/'started.json'),'Prior request start path');read(sr)
            for oldref in (r,sr):prior_files[oldref['path']]=oldref['sha256']
            prior_dirs[str(folder)]={'started.json','result.json'}
        expected={'registration.json'}|{'request-'+str(i).zfill(4) for i in range(request_number)}|{'shard-'+str(i).zfill(4) for i in range(len(completed))}
        require({p.name for p in OUTPUT.iterdir()}==expected,'No unanchored attempts may resume')
    require(len(completed)<len(c['plan']['document']['shards']),'No repeat completed domain')
    request=OUTPUT/('request-'+str(request_number).zfill(4));request.mkdir(exist_ok=False);saved=[];unresolved=None;stopped=False;current_descriptor=None
    try:
        started=save(request/'started.json',dict(schema='SINGLE_REPLACEMENT_BATCH_STARTED_V1',request_number=request_number,max_shards=max_shards,input_references=c['refs'],source_hashes=c['sources'],prior_result_reference=prior_result_reference,registration_reference=registration_ref,**FLAGS));saved.append(started)
        for descriptor in c['plan']['document']['shards'][len(completed):len(completed)+max_shards]:
            resource(OUTPUT);guard(c['sources'],c['dirs']);current_descriptor=descriptor
            r=process_shard(c,descriptor,OUTPUT/('shard-'+str(descriptor['identity']['ordinal']).zfill(4)));saved.append(r)
            report=json.loads(read(r));terminals.extend(report['inspection']['terminal_rows']);unresolved=report['inspection']['unresolved_ordinal']
            if report['status']=='STOPPED_NO_RETRY':stopped=True;break
            completed.append(r);current_descriptor=None
        partition=private('registration').summarize_execution_prefix(registration=c['plan'],terminal_rows=terminals,unresolved_ordinal=unresolved)
        result=save(request/'result.json',dict(schema='SINGLE_REPLACEMENT_BATCH_RESULT_V1',status='STOPPED_NO_RETRY' if stopped else 'REQUEST_COMPLETE_PENDING_INDEPENDENT_READBACK',request_number=request_number,started_reference=started,registration_reference=registration_ref,input_references=c['refs'],source_hashes=c['sources'],prior_request_references=prior_requests,completed_shard_references=completed,partition=partition,saved_references=saved,full_queue_completed=partition['terminal_count']==c['plan']['document']['integer_count'] and not stopped,**FLAGS),emergency=True)
        guard(c['sources'],c['dirs']);guard(prior_files,prior_dirs);[read(r) for r in saved];read(result);read(registration_ref)
        for r in saved[1:]:
            shard=json.loads(read(r));read(shard['started_reference']);read(shard['journal_reference'])
            require({p.name for p in Path(r['path']).parent.iterdir()}==({'started.json','journal.jsonl','result.json','failure.json'} if shard['status']=='STOPPED_NO_RETRY' else {'started.json','journal.jsonl','result.json'}),'Final current shard inventory')
        total_shards=len(completed)+int(stopped)
        expected={'registration.json'}|{'request-'+str(i).zfill(4) for i in range(request_number+1)}|{'shard-'+str(i).zfill(4) for i in range(total_shards)}
        require({p.name for p in OUTPUT.iterdir()}==expected,'Final batch namespace')
        require({p.name for p in request.iterdir()}=={'started.json','result.json'},'Exact request output')
        if stopped:save(request/'failure.json',dict(result_reference=result,status='TECHNICAL_STOP_NO_RETRY',**FLAGS),emergency=True)
        return result
    except BaseException as e:
        # An interrupted current shard can have a partial record. Preserve its bytes;
        # never infer NOT_DISPATCHED from the absence of a complete START line.
        partial=None
        if current_descriptor is not None:
            folder=OUTPUT/('shard-'+str(current_descriptor['identity']['ordinal']).zfill(4));jp=folder/'journal.jsonl'
            if jp.exists():
                raw=jp.read_bytes();tasks=[c['evaluator'].project_validated_task(c['validated'],i) for i in range(current_descriptor['identity']['start'],current_descriptor['identity']['stop'])]
                context=sha(enc(dict(plan_sha256=c['plan']['content_sha256'],descriptor=current_descriptor,source_hashes=c['sources'])))
                try:partial=c['journal'].inspect_journal(raw,context_sha256=context,ordered_tasks=tasks)
                except BaseException as failure:partial=dict(journal_reference=ref(jp,sha(raw)),status='CORRUPT_EVIDENCE_PARTITION_UNKNOWN',error=diagnostic(failure))
        failure_terminals=terminals;failure_unresolved=None;partition=None
        if partial is not None and 'terminal_rows' in partial:
            failure_terminals=[t for t in terminals if t['global_ordinal']<current_descriptor['identity']['start']]+partial['terminal_rows'];failure_unresolved=partial['unresolved_ordinal']
        if partial is None or 'terminal_rows' in partial:
            partition=private('registration').summarize_execution_prefix(registration=c['plan'],terminal_rows=failure_terminals,unresolved_ordinal=failure_unresolved)
        save(request/'failure.json',dict(error=diagnostic(e),saved_references=saved,completed_shard_references=completed,completed_terminal_count=len(failure_terminals),full_domain_count=c['plan']['document']['integer_count'],current_descriptor=current_descriptor,partial_evidence=partial,partition=partition,partition_unknown=partition is None,remaining_partition_must_be_read_from_preserved_journals=partition is None,**FLAGS),emergency=True);raise


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--max-shards',type=int,default=1);parser.add_argument('--prior-result-path');parser.add_argument('--prior-result-sha256')
    args=parser.parse_args();prior=None if args.prior_result_path is None and args.prior_result_sha256 is None else ref(args.prior_result_path,args.prior_result_sha256)
    print(json.dumps(run(execute=args.execute,max_shards=args.max_shards,prior_result_reference=prior)))
