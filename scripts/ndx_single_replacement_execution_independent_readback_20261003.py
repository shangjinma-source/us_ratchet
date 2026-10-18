"""Independent saved single replacement execution evidence, never evaluation."""
from pathlib import Path
from types import ModuleType
import hashlib
import json
import os

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/single_replacement_evaluation_20261003_v1'
PREP=ROOT/'data/cache/research/single_replacement_preparation_20261003_v1'
AUDIT=ROOT/'data/cache/research/single_replacement_preparation_independent_readback_20261003_v1'
OUTPUT=ROOT/'data/cache/research/single_replacement_execution_independent_readback_20261003_v1'
REQUEST_PATH=PARENT/'request-0000'/'result.json'
REQUEST_SHA='d99dfe374103ca8f3396c2d5a7a71c2e46b7b97a66c50ae461628fa025dae869'
EXPECTED_INTEGER_COUNT=126541
INSPECTOR=ROOT/'backtest/ndx_single_replacement_result_inspection_research.py'
INSPECTOR_SHA='71c1b8edab94da4e5c8d19a6cecb62255a3755c59d260b1a03471ed1963d1242'
WORKER=ROOT/'scripts/ndx_single_replacement_shard_worker_20261003.py'
WORKER_SHA='94b082a66cbe5d34d57b2ac839d05adf284bca25ad165795033c73338f5fdb0f'
CODE={
 'registration':('backtest/ndx_single_replacement_execution_registration_research.py','3b4addb89fd9c7dc7494c873df3e4c50662852cc4aab61f4f7b1c7dbcd5cab89'),
 'journal':('backtest/ndx_single_replacement_journal_research.py','da86254528484bdac2945faa4a8625add03769f1295339ba8f5a2ac10713aa7d'),
 'evaluator':('backtest/ndx_single_replacement_evaluation_research.py','4303ead0a9d57d1bb95a4b6c563c707894a71eadec3c881bd082be3be5f1d767'),
 'domain':('backtest/ndx_single_replacement_domain_research.py','8df88963158ba8d3787c61705ca04f4a41ab481759701a291ccdbe75ae7505d7'),
 'risk':('backtest/ndx_conditional_new_cash_fork_research.py','5bb17d621b42707cfe312676279d59b565c3e97900bf3bdd6f9335df65aa0c5f')}
BOUND={
 'preparation':(str(PREP/'preparation.json'),'510a150834c82a9d68b2979d43c57c808d47800d0f1fc7258896fe7010ecedf6'),
 'publication':(str(PREP/'publication.json'),'e7a16bafeb236dd3e023c6c8f983041ac7a4236fb898124c20142d9bf4484c4c'),
 'audit':(str(AUDIT/'independent_readback.json'),'d5d5426406a4be38fd2f01285ab9a68cc36e48e54880f33eb46933e0edb001d9'),
 'reader':('scripts/ndx_single_replacement_preparation_independent_readback_20261003.py','0b4654ec4530eea382c948cae4eede99b2ced433757fae2557dfe89c8f3df48d')}
WORKER_FALSE=('point_in_time_verified','full_ndx_certified','economic_winner_selected','account_executed','fit_executed','orders_executed','automatic_retry_allowed')
FLAGS=dict.fromkeys(WORKER_FALSE+('producer_called','evaluator_called','old_account_reopened'),False)


def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def ref(p,h):return dict(path=str(p),sha256=h)
def reference(r):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'],'Exact reference')
    h=r['sha256'];require(type(h) is str and len(h)==64 and all(c in '0123456789abcdef' for c in h),'Bound SHA before IO');return r
def decode(b):
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'Duplicate key');d[k]=v
        return d
    return json.loads(b.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def take(r,sources):
    reference(r);require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Source collision')
    b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Authenticated same consumed bytes');sources[r['path']]=r['sha256'];return b
def flags(v):require(all(v[k] is False for k in WORKER_FALSE),'False authority exact')
def guard(sources,dirs):
    require(sha(SOURCE.read_bytes())==LOADED,'Loaded reader identity')
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Final source bytes drift')
    for p,names in dirs.items():require({v.name for v in Path(p).iterdir()}==set(names),'Exact source directory')
def save(name,value):
    b=enc(value);p=OUTPUT/name
    with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Saved reader bytes');return ref(p,sha(b))
def private(raw):
    require(sha(raw)==INSPECTOR_SHA,'Same inspector bytes');m=ModuleType('_independent_single_replacement_inspection');m.__file__=str(INSPECTOR);exec(compile(raw,str(INSPECTOR),'exec'),m.__dict__);return m


def load_inputs():
    request_ref=reference(ref(REQUEST_PATH,REQUEST_SHA));refs={k:reference(ref(ROOT/p,h)) for k,(p,h) in BOUND.items()}
    sources={str(SOURCE):LOADED};take(ref(WORKER,WORKER_SHA),sources);code=take(ref(INSPECTOR,INSPECTOR_SHA),sources)
    worker_sources={str(WORKER):WORKER_SHA,**{str(ROOT/p):h for p,h in CODE.values()}}
    for p,h in worker_sources.items():take(ref(p,h),sources)
    docs={}
    for k,r in refs.items():
        raw=take(r,sources);worker_sources[r['path']]=r['sha256']
        if k!='reader':docs[k]=decode(raw)
    audit=docs['audit'];out=docs['preparation'];pub=docs['publication']
    require(audit['schema']=='SINGLE_REPLACEMENT_PREPARATION_INDEPENDENT_READBACK_V1' and audit['status']=='PASS' and audit['reader_sha256']==refs['reader']['sha256'],'Prepared independent evidence')
    exact(audit['preparation_reference'],refs['preparation'],'Audit prepared parent');exact(audit['publication_reference'],refs['publication'],'Audit publication')
    require(out['schema']=='SOURCE_BOUND_SINGLE_REPLACEMENT_PREPARATION_V1' and pub['schema']=='SINGLE_REPLACEMENT_PREPARATION_PUBLICATION_V1','Prepared source roles');exact(pub['preparation_reference'],refs['preparation'],'Preparation publication')
    for p,h in audit['source_hashes'].items():
        require(p not in worker_sources or worker_sources[p]==h,'Fixed parent source collision');take(ref(p,h),sources);worker_sources[p]=h
    dirs={str(PREP):{'started.json','raw_preparation.json','preparation.json','publication.json'},str(AUDIT):{'started.json','independent_readback.json'}}
    for role,names in [('inputs',{'inputs.json','publication.json'}),('inventory',{'inventory.json','publication.json'}),('scenarios',{'scenarios.json'})]:dirs[str(Path(audit['input_references'][role]['path']).parent)]=names
    request=decode(take(request_ref,sources));flags(request)
    require(request['schema']=='SINGLE_REPLACEMENT_BATCH_RESULT_V1' and request['status'] in ('REQUEST_COMPLETE_PENDING_INDEPENDENT_READBACK','STOPPED_NO_RETRY'),'Saved bounded execution request')
    n=request['request_number'];require(type(n) is int and n>=0 and request_ref['path']==str(PARENT/('request-'+str(n).zfill(4))/'result.json'),'Fixed request coordinate')
    exact(request['input_references'],refs,'Exact four parent roles');exact(request['source_hashes'],worker_sources,'Independently constructed worker closure')
    regref=request['registration_reference'];require(regref['path']==str(PARENT/'registration.json'),'Registration path');registration=decode(take(regref,sources))
    require(sha(enc(registration['document']))==registration['content_sha256'],'Registration hash');plan=registration['document'];prepared=out['preparation']
    require(plan['schema']=='SINGLE_REPLACEMENT_EXECUTION_REGISTRATION_V1' and plan['prepared_content_sha256']==prepared['content_sha256'] and type(plan['shard_size']) is int and plan['shard_size']==512,'Fixed engineering registration')
    require(plan['status']=='STRUCTURAL_FULL_DOMAIN_PLAN_NOT_DISPATCH_PERMISSION' and plan['evaluation_api']=='PRIVATE_VALIDATED_PROJECT_THEN_EVALUATE_ONE' and plan['scope']==prepared['document']['scope'],'Registered semantic scope')
    exact(plan['references'],dict(preparation=refs['preparation'],audit=refs['audit'],evaluator=ref(ROOT/CODE['evaluator'][0],CODE['evaluator'][1])),'Registration bound roles')
    require(all(plan[k] is False for k in ('source_bytes_authenticated','dispatch_authorized','risk_evaluated','point_in_time_verified','economic_winner_selected','account_executed','automatic_retry_allowed','public_batch_evaluation_called')),'Registration permissions')
    for k in ('scenario_count','pair_count','integer_count','financial_integer_count_before_issuer','structurally_excluded_integer_count'):exact(plan[k],audit['inspection'][k],'Full denominator from audit')
    require(plan['scenario_count']==40 and plan['integer_count']==EXPECTED_INTEGER_COUNT,'Actual fixed full domain')
    expected=[]
    for i,start in enumerate(range(0,plan['integer_count'],512)):
        identity=dict(schema='SINGLE_REPLACEMENT_SHARD_V1',preparation_sha256=prepared['content_sha256'],ordinal=i,start=start,stop=min(start+512,plan['integer_count']))
        expected.append(dict(identity=identity,shard_id=sha(enc(identity))))
    exact(plan['shards'],expected,'All original contiguous shards');require(type(plan['shard_count']) is int and plan['shard_count']==len(expected),'Full shard count')
    expected_cases=[dict(scenario_index=v['scenario_index'],scenario_id=v['scenario_id'],start=v['first_global_ordinal'],stop=v['first_global_ordinal']+v['integer_count'],pair_count=v['pair_count'],financial_count=v['financial_integer_count_before_issuer'],structurally_excluded_count=v['structurally_excluded_integer_count']) for v in prepared['document']['cases']]
    exact(plan['cases'],expected_cases,'Original full case intervals')
    requests=request['prior_request_references']+[request_ref];require(len(requests)==n+1,'Full prior request chain')
    request_docs=[];saved_shards=[]
    for i,r in enumerate(requests):
        folder=PARENT/('request-'+str(i).zfill(4));require(r['path']==str(folder/'result.json'),'Original request order')
        v=decode(take(r,sources));flags(v);require(v['schema']=='SINGLE_REPLACEMENT_BATCH_RESULT_V1' and type(v['request_number']) is int and v['request_number']==i,'Prior request role')
        if i<n:require(v['status']=='REQUEST_COMPLETE_PENDING_INDEPENDENT_READBACK','Cannot resume failed request')
        exact(v['prior_request_references'],requests[:i],'Prior request chain');exact(v['input_references'],refs,'Request input roles');exact(v['source_hashes'],worker_sources,'Request fixed sources');exact(v['registration_reference'],regref,'One registration')
        sr=v['started_reference'];require(sr['path']==str(folder/'started.json'),'Started fixed path');s=decode(take(sr,sources));flags(s)
        require(s['schema']=='SINGLE_REPLACEMENT_BATCH_STARTED_V1' and type(s['request_number']) is int and s['request_number']==i and type(s['max_shards']) is int and 1<=s['max_shards']<=248,'Actual bounded request')
        exact(s['prior_result_reference'],requests[i-1] if i else None,'Prior explicit external anchor');exact(s['source_hashes'],worker_sources,'Started closure');exact(s['input_references'],refs,'Started inputs');exact(s['registration_reference'],regref,'Started registration')
        require(v['saved_references'][0]==sr,'First durable request START');saved_shards.extend(v['saved_references'][1:])
        require(0<len(v['saved_references'])-1<=s['max_shards'],'No undeclared or empty saved shard request')
        dirs[str(folder)]={'started.json','result.json'}|({'failure.json'} if v['status']=='STOPPED_NO_RETRY' else set())
        if v['status']=='STOPPED_NO_RETRY':
            b=(folder/'failure.json').read_bytes();sources[str(folder/'failure.json')]=sha(b)
        request_docs.append(v)
    require(len({r['path'] for r in saved_shards})==len(saved_shards),'No repeated shard evidence')
    guard(sources,dirs)
    return dict(refs=refs,sources=sources,dirs=dirs,worker_sources=worker_sources,inspector_bytes=code,prepared=prepared,plan=plan,registration=registration,requests=request_docs,request_reference=request_ref,shard_references=saved_shards)


def readback(*,execute=False):
    require(execute is True,'Explicit independent readback');c=load_inputs();require(not OUTPUT.exists(),'No retry or overwrite')
    OUTPUT.mkdir(parents=True,exist_ok=False);saved=[]
    try:
        saved.append(save('started.json',dict(schema='SINGLE_REPLACEMENT_EXECUTION_INDEPENDENT_STARTED_V1',request_reference=c['request_reference'],input_references=c['refs'],source_hashes=c['sources'],**FLAGS)))
        oracle=private(c['inspector_bytes']);oracle.catalogue(c['prepared']);checks=[];terminals=[];completed=[];unresolved=None
        for i,r in enumerate(c['shard_references']):
            require(i<len(c['plan']['shards']),'Bounded full domain');descriptor=c['plan']['shards'][i];folder=PARENT/('shard-'+str(i).zfill(4));require(r['path']==str(folder/'result.json'),'Original shard order')
            v=decode(take(r,c['sources']));flags(v);require(v['schema']=='SINGLE_REPLACEMENT_SHARD_RESULT_V1' and v['status'] in ('COMPLETE_PENDING_INDEPENDENT_READBACK','STOPPED_NO_RETRY'),'Shard saved role')
            exact(v['descriptor'],descriptor,'Exact original shard descriptor');context=sha(enc(dict(plan_sha256=c['registration']['content_sha256'],descriptor=descriptor,source_hashes=c['worker_sources'])))
            require(v['context_sha256']==context,'Fixed complete context');sr=v['started_reference'];jr=v['journal_reference'];require(sr['path']==str(folder/'started.json') and jr['path']==str(folder/'journal.jsonl'),'Shard fixed sources')
            start=decode(take(sr,c['sources']));flags(start);require(start['schema']=='SINGLE_REPLACEMENT_SHARD_STARTED_V1' and start['context_sha256']==context,'Shard START context');exact(start['source_hashes'],c['worker_sources'],'Shard START sources');exact(start['descriptor'],descriptor,'Shard START identity')
            report=oracle.inspect_saved_journal(prepared=c['prepared'],journal_bytes=take(jr,c['sources']),descriptor=descriptor,context_sha256=context)
            intervals=oracle.catalogue(c['prepared']);ordered=[dict(global_ordinal=k,task_id=oracle.reconstruct_task(intervals,k)[1]['task_id']) for k in range(descriptor['identity']['start'],descriptor['identity']['stop'])];exact(start['ordered_tasks'],ordered,'Independent complete START IDs')
            scan={k:report[k] for k in ('complete','terminal_rows','unresolved_ordinal','undispatched_ordinals','records','partial_tail_present','journal_sha256','terminal_record_sha256','automatic_retry_allowed')};exact(v['inspection'],scan,'Producer journal claims independently checked')
            if v['status']=='COMPLETE_PENDING_INDEPENDENT_READBACK':
                require(report['complete'] and all(t['outcome'] in ('FEASIBLE','INFEASIBLE') for t in report['terminal_rows']) and v['error'] is None,'Complete accepted shard');completed.append(r)
            else:require(i==len(c['shard_references'])-1,'No dispatch after failed shard')
            c['dirs'][str(folder)]={'started.json','journal.jsonl','result.json'}|({'failure.json'} if v['status']=='STOPPED_NO_RETRY' else set())
            if v['status']=='STOPPED_NO_RETRY':
                b=(folder/'failure.json').read_bytes();c['sources'][str(folder/'failure.json')]=sha(b)
            terminals.extend(report['terminal_rows']);unresolved=report['unresolved_ordinal'];checks.append(dict(shard_result_reference=r,inspection=report))
        latest=c['requests'][-1];exact(latest['completed_shard_references'],completed,'Full completed prefix')
        counts={k:sum(t['outcome']==k for t in terminals) for k in ('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE')};n=len(terminals);total=c['plan']['integer_count'];pending=n+int(unresolved is not None)
        partition=dict(full_integer_count=total,terminal_count=n,outcome_counts=counts,unresolved_ordinal=unresolved,undispatched_start=pending,undispatched_stop=total,undispatched_count=total-pending,automatic_retry_allowed=False,source_bytes_authenticated=False,dispatch_authorized=False,risk_evaluated=False,point_in_time_verified=False,economic_winner_selected=False,account_executed=False)
        exact(latest['partition'],partition,'Exact full domain partition');require(latest['full_queue_completed'] is (n==total and latest['status']!='STOPPED_NO_RETRY'),'No full completion inflation')
        offset=0;prior_terminals=[];prior_completed=[]
        for request in c['requests']:
            count=len(request['saved_references'])-1;subset=checks[offset:offset+count];offset+=count
            require(len(subset)==count,'All requested saved shard sources')
            for check in subset:
                prior_terminals.extend(check['inspection']['terminal_rows'])
                if check['shard_result_reference'] in completed:prior_completed.append(check['shard_result_reference'])
            exact(request['completed_shard_references'],prior_completed,'Each request exact completed refs')
            if request['status']=='REQUEST_COMPLETE_PENDING_INDEPENDENT_READBACK':
                require(all(check['shard_result_reference'] in completed for check in subset),'Success cannot hide stopped shard')
            last=subset[-1]['inspection'];unknown=last['unresolved_ordinal'];prefix=len(prior_terminals);begin=prefix+int(unknown is not None)
            expected_partition={**partition,'terminal_count':prefix,'outcome_counts':{k:sum(t['outcome']==k for t in prior_terminals) for k in counts},'unresolved_ordinal':unknown,'undispatched_start':begin,'undispatched_count':total-begin}
            exact(request['partition'],expected_partition,'Each original request full partition')
            require(request['full_queue_completed'] is (prefix==total and request['status']!='STOPPED_NO_RETRY'),'Each request exact full completion status')
        c['dirs'][str(PARENT)]={'registration.json'}|{'request-'+str(i).zfill(4) for i in range(len(c['requests']))}|{'shard-'+str(i).zfill(4) for i in range(len(checks))}
        guard(c['sources'],c['dirs'])
        report=save('independent_readback.json',dict(schema='SINGLE_REPLACEMENT_EXECUTION_INDEPENDENT_READBACK_V1',status='PASS_SAVED_PREFIX',request_reference=c['request_reference'],reader_sha256=LOADED,input_references=c['refs'],source_hashes=c['sources'],partition=partition,shards=checks,full_domain_evaluated=n==total and counts['EVALUATION_EXCEPTION']==counts['VALIDATION_FAILURE']==0,scope='SAVED_FRACTION_ARITHMETIC_AND_SOURCE_PREFIX_NOT_FULL_NDX_OR_ACCOUNT_EXECUTION',**FLAGS));saved.append(report)
        guard(c['sources'],c['dirs'])
        for r in saved:require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final reader bytes')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Reader exact namespace');return report
    except BaseException as e:
        save('failure.json',dict(error_type=type(e).__name__,error=str(e),saved_references=saved,**FLAGS));raise


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=parser.parse_args().execute)))
