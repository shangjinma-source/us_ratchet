"""Stream display-only saved chain additions. No economics or source-audit replay."""
import shutil
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import types

STORAGE=Path('D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714')
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=STORAGE/'dated_path_risk_display_20261003_v1'
OUTPUT=STORAGE/'dated_risk_chain_display_20261003_v1'
BOUND={
 'index':(str(PARENT/'index.json'),'4fca462ffc0c45c2bc0fc248a37bfd6ea926b5b3c00d1f24b09984d652cda3f8'),
 'publication':(str(PARENT/'publication.json'),'fcebd238aa5d8351ac24c7cb26adf4320f714ca7217c6cb960477853b855b5be'),
 'audit':(str(STORAGE/'dated_path_risk_display_independent_readback_20261003_v1/independent_readback.json'),'36a392c9a459140f7f5657aba5f373d33affb9956d947cf9c9eda6e7e58070fe'),
 'reader':(str(ROOT/'scripts/ndx_dated_path_risk_display_independent_readback_20261003.py'),'ebb843119024fb6a29808625be5e07f980e84a811e0f9c4f2f91b5bafa242913'),
 'producer':(str(ROOT/'scripts/ndx_dated_path_risk_display_20261003.py'),'7f4395264f9e5d8715b7014d57c47f0ec3fbb928bf656677a5cabaf2280fd854'),
 'projection_core':(str(ROOT/'backtest/ndx_dated_path_risk_display_research.py'),'afb909618ba50ce22d9491587957e350b7f37675dd14be046f97a502f18a26b3'),
 'core':(str(ROOT/'backtest/ndx_saved_risk_chain_display_research.py'),'428a1b1f2d391dcc24694b02df9213ae08dc9e61459a47c229bf9d1ba90df9bc')}
FALSE=('economics_recomputed','risk_gate_recomputed','account_executed','fit_performed','audit_reexecuted','point_in_time_verified','promotion_allowed','future_independent_oos','formal_comparison_passed','winner_selected','cohort_statistics_computed','original_targets_changed','full_transitive_source_closure_reverified')
ROLES=('incumbent_integer','incumbent_continuous','STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')

def require(ok,message):
    if not ok:raise ValueError(message)

def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,message):require(enc(a)==enc(b),message)
def integer(v,n,message):require(type(v) is int and v==n,message)
def ref(p,h):return dict(path=str(p),sha256=h)
def validref(r):require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'].strip()==r['path'] and bool(r['path']) and type(r['sha256']) is str and len(r['sha256'])==64 and set(r['sha256'])<=set('0123456789abcdef'),'Exact path/SHA')
def merge(s,p,h):require(p not in s or s[p]==h,'Source conflict');s[p]=h

def loads(b):
    def pairs(items):
        result={}
        for k,v in items:require(k not in result,'Duplicate key');result[k]=v
        return result
    return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))

def guard(sources):
    require(sources.get(str(SOURCE))==LOADED,'Loaded wrapper identity')
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Source drift '+p)

def read(r,sources):
    validref(r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed bytes');merge(sources,r['path'],r['sha256']);return b

def validate_parents(index,pub,audit,refs):
    require(index['schema']=='SOURCE_BOUND_DATED_PATH_RISK_DISPLAY_V1','Projection index schema')
    require(pub['schema']=='DATED_PATH_RISK_DISPLAY_PUBLICATION_V1' and pub['status']=='PUBLISHED_SAVED_PATH_DISPLAY_ONLY','Projection publication')
    exact(pub['index_reference'],refs['index'],'Published index');exact(pub['source_hashes'],index['source_hashes'],'Source claims preserved')
    require(audit['schema']=='DATED_PATH_RISK_DISPLAY_INDEPENDENT_READBACK_V1' and audit['status']=='PASS','Saved projection audit')
    exact(audit['index_reference'],refs['index'],'Audited index');exact(audit['publication_reference'],refs['publication'],'Audited publication')
    require(audit['reader_sha256']==refs['reader']['sha256'],'Audited reader SHA')
    for role in ('reader','producer','projection_core','index','publication'):
        require(audit['source_hashes'].get(refs[role]['path'])==refs[role]['sha256'],'Saved audit code/input closure')
    for role in ('producer','projection_core'):require(index['source_hashes'].get(refs[role]['path'])==refs[role]['sha256'],'Projection producer closure')
    for obj in (index,pub):
        for flag in ('formal_comparison_passed','point_in_time_verified','promotion_allowed','risk_recomputed','chain_totals_computed','weights_normalized','account_executed','fit_performed','winner_selected'):require(obj[flag] is False,'Original conditional authority')
    for flag in ('producer_called','projection_core_called','economics_recomputed','risk_recomputed','formal_comparison_passed','point_in_time_verified','promotion_allowed'):require(audit[flag] is False,'Audit scope')
    for key in ('planned_task_count','projected_task_count','not_supplied_task_count'):exact(audit[key],index[key],'Audited counts')
    integer(index['planned_task_count'],1632,'Full task denominator')
    for key in ('task_jsonl_reference','shared_paths_reference'):exact(pub[key],index[key],'Published payload reference')
    require(audit['verified_jsonl_sha256']==index['task_jsonl_reference']['sha256'],'Audited JSONL')
    exact(audit['verified_jsonl_bytes'],index['task_jsonl_reference']['byte_count'],'Audited byte count')

def restore_projection(row,shared):
    restored=deepcopy(row);used=[]
    require(type(shared) is dict and len(shared)==4,'Four immutable shared roles')
    for role in ROLES:
        container=restored['tracks'] if role.startswith('incumbent_') else restored['nav_modes']
        link=container[role];require(set(link)=={'shared_path_id','value_encoding_preserved'},'Exact compact link')
        key=link['shared_path_id'];require(key in shared,'Missing shared path')
        item=shared[key];identity=item['identity'];require(identity['role']==role and key==sha(enc(identity)),'Shared role and identity hash')
        exact(identity['source_reference'],item['payload']['source_reference'],'Shared source identity')
        container[role]=deepcopy(item['payload'])
        if link['value_encoding_preserved'] is not None:container[role]['value_encoding']=deepcopy(link['value_encoding_preserved'])
        used.append(key)
    require(set(used)==set(shared),'Every shared path referenced exactly once')
    return restored

def project_stream(stream,index,shared,core,emit):
    entries=index['task_index'];require(len(entries)==1632 and len({e['numerical_task_id'] for e in entries})==1632,'Complete ordered index')
    strata=Counter();specs_by_k={}
    for entry in entries:
        require(type(entry['k']) is int and 4<=entry['k']<=20,'Exact cardinality4..20')
        spec=enc(entry['weight_spec']).decode();strata[(entry['k'],spec)]+=1;specs_by_k.setdefault(entry['k'],set()).add(spec)
    require(set(specs_by_k)==set(range(4,21)) and len(strata)==51 and set(strata.values())=={32},'Complete51 strata of32')
    require(all(len(v)==3 and v==specs_by_k[4] for v in specs_by_k.values()),'Same three original specifications per cardinality')
    if index['projected_task_count']:
        require(type(index['calendar']) is list and len(index['calendar'])==127,'Full projection calendar')
    digest=hashlib.sha256();offset=count=0;output=[];common={};roles={};coverage=Counter()
    for ordinal,entry in enumerate(entries):
        integer(entry['task_ordinal'],ordinal,'Exact task ordinal')
        item=deepcopy(entry);item['jsonl_record']=None
        if entry['status']=='COMPARISON_NOT_SUPPLIED':
            require(entry['jsonl_record'] is None,'Missing comparison has no path');output.append(item);continue
        require(entry['status']=='AUDITED_SAVED_PATHS_PROJECTED','Known projection status')
        line=stream.readline();require(line.endswith(b'\n'),'Whole JSONL record')
        location=entry['jsonl_record'];exact(location,dict(record_index=count,byte_start=offset,byte_stop=offset+len(line),row_sha256=sha(line)),'Original JSONL index')
        digest.update(line);offset+=len(line);count+=1;row=loads(line)
        require(enc(row)+b'\n'==line,'Canonical input JSONL');require(row['numerical_task_id']==entry['numerical_task_id'],'Exact indexed task')
        for key in ('numerical_task_id','k','weight_spec'):exact(row['original_task_summary_row'][key],entry[key],'Original task summary coordinate')
        exact(row['calendar'],index['calendar'],'Exact full index calendar')
        restored=restore_projection(row,shared);result=core.project_chain_display(restored)
        require(result['numerical_task_id']==entry['numerical_task_id'],'Exact aggregate task')
        for flag in ('source_bytes_authenticated','economics_recomputed','risk_gate_recomputed','original_targets_changed','point_in_time_verified','promotion_allowed','future_independent_oos'):require(result[flag] is False,'Aggregate authority')
        require(result['chain_display_addition_performed'] is True,'Display addition only')
        for role in ('incumbent_integer','incumbent_continuous'):
            key=row['tracks'][role]['shared_path_id'];aggregate=result['tracks'][role]
            value=dict(identity=deepcopy(shared[key]['identity']),aggregation=deepcopy(aggregate))
            if role in roles:require(roles[role]==key,'One shared control identity per role')
            roles[role]=key
            if key in common:exact(common[key],value,'Shared aggregation cannot drift')
            else:common[key]=value
            result['tracks'][role]=dict(shared_aggregate_id=key)
        result.update(original_task_summary_row=deepcopy(row['original_task_summary_row']),preserved_evidence_sidecars=deepcopy(row['preserved_evidence_sidecars']),projection_input_references=deepcopy(row['input_references']))
        item['jsonl_record']=emit(result);item['status']='SAVED_CHAIN_DISPLAY_ADDED';output.append(item)
        coverage[(entry['k'],enc(entry['weight_spec']).decode())]+=1
    require(stream.read(1)==b'','No extra input records')
    descriptor=index['task_jsonl_reference']
    exact(descriptor['sha256'],digest.hexdigest(),'Input JSONL hash');integer(descriptor['byte_count'],offset,'Input byte count');integer(descriptor['record_count'],count,'Input record count')
    integer(index['projected_task_count'],count,'Projected denominator');integer(index['not_supplied_task_count'],1632-count,'Missing denominator')
    require(len(common)==(2 if count else 0),'Exactly two control aggregates')
    groups={}
    for e in output:
        k=(e['k'],enc(e['weight_spec']).decode());groups[k]=groups.get(k,0)+1
    return dict(task_index=output,shared_control_aggregates=common,planned_task_count=1632,projected_task_count=count,not_supplied_task_count=1632-count,
        k_spec_coverage=[dict(k=k,weight_spec=json.loads(s),planned_task_count=n,projected_task_count=coverage[(k,s)],not_supplied_task_count=n-coverage[(k,s)]) for (k,s),n in sorted(groups.items())],
        full_new_cutoff_task_denominator=index['full_new_cutoff_task_denominator'],calendar=deepcopy(index['calendar']))

MIN_FREE_BYTES=5*1024**3

def resource_gate(reserve_bytes=0):
    require(type(reserve_bytes) is int and reserve_bytes>=0,'Exact output byte reserve')
    # OUTPUT may not exist yet; its volume root does. Never check the source ROOT.
    require(shutil.disk_usage(Path(OUTPUT.anchor)).free>=MIN_FREE_BYTES+reserve_bytes,'RESOURCE_STOP_BEFORE_WRITE: preserve five GiB on output volume')

def save(path,value):
    b=enc(value)
    if path.name!='failure.json':resource_gate(len(b))
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Saved bytes');return ref(path,sha(b))

def run(*,execute=False):
    require(execute is True,'Explicit execute');require(not OUTPUT.exists(),'Create-only namespace; no retry')
    refs={k:ref(p,h) for k,(p,h) in BOUND.items()}
    for r in refs.values():validref(r)
    sources={str(SOURCE):LOADED};blobs={k:read(r,sources) for k,r in refs.items()};guard(sources)
    index,pub,audit=(loads(blobs[k]) for k in ('index','publication','audit'));validate_parents(index,pub,audit,refs)
    require({p.name for p in PARENT.iterdir()}=={'started.json','tasks.jsonl','shared_paths.json','index.json','publication.json'},'Successful projection namespace')
    sharedref=index['shared_paths_reference'];validref(sharedref);require(Path(sharedref['path'])==PARENT/'shared_paths.json','Fixed shared file')
    sd=loads(read(sharedref,sources));require(sd['schema']=='DATED_PATH_RISK_SHARED_PATHS_V1','Shared schema')
    jr=index['task_jsonl_reference'];require(Path(jr['path'])==PARENT/'tasks.jsonl','Fixed JSONL path')
    core=types.ModuleType('_private_chain_display');core.__file__=refs['core']['path'];exec(compile(blobs['core'],core.__file__,'exec'),core.__dict__);guard(sources)
    resource_gate();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(schema='DATED_CHAIN_DISPLAY_STARTED_V1',input_references=refs,source_hashes=sources,retry_allowed=False,**dict.fromkeys(FALSE,False)))
        offset=count=0;digest=hashlib.sha256()
        with Path(jr['path']).open('rb') as input_stream,(OUTPUT/'tasks.jsonl').open('xb') as output_stream:
            def emit(row):
                nonlocal count,offset
                b=enc(row)+b'\n';resource_gate(len(b));out=dict(record_index=count,byte_start=offset,byte_stop=offset+len(b),row_sha256=sha(b));count+=1;offset+=len(b);digest.update(b);output_stream.write(b);return out
            result=project_stream(input_stream,index,sd['shared_paths'],core,emit)
            output_stream.flush();os.fsync(output_stream.fileno())
        # Full input JSONL was authenticated during its sole streamed consumption.
        merge(sources,jr['path'],jr['sha256'])
        fixed={p:h for p,h in sources.items() if p!=jr['path']};guard(fixed)
        shared=save(OUTPUT/'shared_control_aggregates.json',dict(schema='DATED_CHAIN_SHARED_CONTROL_AGGREGATES_V1',aggregates=result.pop('shared_control_aggregates'),**dict.fromkeys(FALSE,False)))
        output_jsonl=dict(path=str(OUTPUT/'tasks.jsonl'),sha256=digest.hexdigest(),byte_count=offset,record_count=count)
        doc=dict(schema='SOURCE_BOUND_DATED_CHAIN_DISPLAY_V1',**result,task_jsonl_reference=output_jsonl,shared_control_aggregates_reference=shared,
            input_references=refs,original_projection_index_reference=refs['index'],original_projection_source_hashes_preserved=index['source_hashes'],source_hashes=sources,
            original_batch_failure_preserved=index['batch_failure_preserved'],original_unresolved_task_ids=index['unresolved_task_ids'],original_undispatched_task_ids=index['undispatched_task_ids'],
            source_verification_scope='INPUT_JSONL_HASH_VERIFIED_ONCE_DURING_STREAM_OTHER_DIRECT_BYTES_RECHECKED_AT_PUBLICATION_NO_PARENT_AUDIT_REPLAY',chain_display_addition_performed=True,**dict.fromkeys(FALSE,False))
        out=save(OUTPUT/'index.json',doc);receipt=save(OUTPUT/'publication.json',dict(schema='DATED_CHAIN_DISPLAY_PUBLICATION_V1',status='PUBLISHED_DISPLAY_ADDITION_NOT_RISK_REEVALUATION',index_reference=out,task_jsonl_reference=output_jsonl,shared_control_aggregates_reference=shared,source_hashes=sources,**dict.fromkeys(FALSE,False)))
        guard(fixed)
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','tasks.jsonl','shared_control_aggregates.json','index.json','publication.json'},'Exact successful namespace')
        final=hashlib.sha256()
        with (OUTPUT/'tasks.jsonl').open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):final.update(block)
        require(final.hexdigest()==digest.hexdigest(),'Final output JSONL bytes')
        for r in (out,receipt,shared):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final metadata bytes')
        return out
    except Exception as error:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(error),retry_allowed=False));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
