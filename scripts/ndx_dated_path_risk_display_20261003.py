"""Stream audited saved paths and conditional security labels; no economics replay."""
import shutil
import argparse
from collections import Counter
from copy import deepcopy
import hashlib,json,os,types
from pathlib import Path

STORAGE=Path('D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714')
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_dated_path_risk_display_research.py';CORE_SHA='afb909618ba50ce22d9491587957e350b7f37675dd14be046f97a502f18a26b3'
OUTPUT=STORAGE/'dated_path_risk_display_20261003_v1'
FIRST='89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
INITIAL_IDS={FIRST,'530200b2ffe3b841c27f62dc68c5440c9b0f1cab7e7249592eaebae304713a68','046b0ad4dc7a207abf15e72ac1786848ad3a2a339515edc3b98e479bfb3678b9'}
COMPARISON_ROOT=ROOT/'data/cache/research/dated_per_task_economic_comparison_20261003_v1'
BOUND={
 'task_summary':('data/cache/research/dated_batch_summary_20261003_v1/summary.json','406922de9ffc292417d4b495af30691833f5bb8c2b5b60449c010d5178acb378'),
 'task_summary_publication':('data/cache/research/dated_batch_summary_20261003_v1/publication.json','23480ca1d99000206344d0176e555b2f16ba12542f2784002854652b7720782b'),
 'task_summary_audit':('DYNAMIC_DATED_BATCH_SUMMARY_INDEPENDENT_READBACK_20261003.json','d60fefc9121db9a14667d0994cd8e4ee58e1d6c62135f042234396d2212b555a'),
 'initial':('research_contracts/dated_initial_comparisons_20261003_v1.json','2c03cb138ccc3c5af8e9f21a93cdb57322318f4d9e04b4a4dbca407b878d7ef2'),
 'batch':('data/cache/research/dated_comparison_batch_20261003_v1/result.json','3a8c1ef0b3cd388586928f6c1b9674c4855b6c7c3c52b9c4ea1ced83ea7a09b2'),
 'batch_audit':('data/cache/research/dated_comparison_batch_independent_readback_20261003_v1/independent_readback.json','2592eeea99f3ab319d39a2c2bacdc85d684af2a3838ce57d543a5a2ec7aedcf9'),
}
READERS={
 'task_summary':('scripts/ndx_dated_batch_summary_independent_readback_20261003.py','1e7ef358ec186aac0997a2f34ed3d690f89fb907b557e08befa2dd67e9235c11'),
 'first_comparison':('scripts/ndx_dated_comparison_independent_readback_20261003.py','155eab023c9ba22da72a7668d5d1df0f840051a1d8f398b5550aa6cdf9130739'),
 'comparison':('scripts/ndx_dated_per_task_comparison_independent_readback_20261003.py','6067301133e1662e6021c53e25d1c79c72e91e2b91b71cd5b8b874db035532ad'),
 'batch':('scripts/ndx_dated_comparison_batch_independent_readback_20261003.py','ade3e78135fc4473f02c3b8c8de8e34151a8189aaf5ee2b685a08fe6d9d23e0b'),
 'inputs':('scripts/ndx_dated_account_input_independent_readback_20261003.py','688685ffffad650b30647cf2be5205aacf819b1aed5215867b0d4c565ed22295'),
}
FLAGS=dict.fromkeys(('comparison_recomputed','account_executed','fit_performed','audit_reexecuted','full_transitive_source_closure_reverified','formal_comparison_passed','point_in_time_verified','promotion_allowed','winner_selected','cohort_statistics_computed','future_independent_oos','risk_recomputed','chain_totals_computed','weights_normalized'),False)

def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def integer(v,n,msg):require(type(v) is int and v==n,msg)
def ref(role):p,h=BOUND[role];return dict(path=str(ROOT/p),sha256=h)
def reference(r):require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'] and type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Exact externally anchored reference')
def merge(s,p,h):require(p not in s or s[p]==h,'Conflicting referenced bytes');s[p]=h
def read(r,s):
    reference(r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Referenced bytes changed');merge(s,r['path'],r['sha256'])
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def guard(s):
    values=dict(s);merge(values,str(SOURCE),LOADED_SHA);merge(values,str(CORE),CORE_SHA)
    for p,h in values.items():require(type(h) is str and sha(Path(p).read_bytes())==h,'Source drift or pending')
MIN_FREE_BYTES=5*1024**3

def resource_gate(reserve_bytes=0):
    require(type(reserve_bytes) is int and reserve_bytes>=0,'Exact output byte reserve')
    # OUTPUT may not exist yet; its volume root does. Never check the source ROOT.
    require(shutil.disk_usage(Path(OUTPUT.anchor)).free>=MIN_FREE_BYTES+reserve_bytes,'RESOURCE_STOP_BEFORE_WRITE: preserve five GiB on output volume')

def save(path,value):
    b=enc(value)
    if path.name!='failure.json':resource_gate(len(b))
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Output drift');return dict(path=str(path),sha256=sha(b))

def index_comparisons(summary,initial,batch):
    ids=[r['numerical_task_id'] for r in summary['rows']];require(len(ids)==len(set(ids))==1632,'Complete original order')
    require(initial['schema']=='DATED_INITIAL_COMPARISONS_V1' and batch['schema']=='DATED_COMPARISON_BATCH_RESULT_V1','Saved manifest/result schemas')
    require(len(initial['rows'])==3 and {r['numerical_task_id'] for r in initial['rows']}==INITIAL_IDS,'Exact explicit initial three')
    exact(batch['initial_rows_preserved'],initial['rows'],'Initial comparisons preserved')
    remaining=[t for t in ids if t not in INITIAL_IDS];new=batch['new_completed_rows'];integer(batch['planned_remaining_count'],1629,'Remaining batch denominator');integer(batch['new_completed_count'],len(new),'Accepted comparisons count')
    require([r['numerical_task_id'] for r in new]==remaining[:len(new)],'Comparison queue prefix not reranked')
    u=batch['unresolved_task_ids'];n=batch['undispatched_task_ids'];require(type(u) is list and type(n) is list and len(u)<=1,'Missing task partition')
    exact([r['numerical_task_id'] for r in new]+u+n,remaining,'No omitted task')
    failure=batch['failure']
    if failure is None:require(batch['status']=='REQUESTED_COMPARISONS_FINISHED' and not u and not n,'Complete comparison terminal')
    else:
        require(batch['status']=='STOPPED_WITH_EVIDENCE' and failure['numerical_task_id']==remaining[len(new)],'Failed comparison position')
        require(type(failure['stage_may_have_written_evidence']) is bool and failure['stage_may_have_written_evidence']==bool(u),'Explicit unresolved dispatch')
    result={}
    for row in initial['rows']:
        require(set(row)=={'numerical_task_id','comparison_reference','publication_reference','independent_readback_reference'},'Initial exact refs')
        result[row['numerical_task_id']]=deepcopy({k:v for k,v in row.items() if k!='numerical_task_id'})
    for row in new:
        require(set(row)=={'numerical_task_id','stage_references'} and set(row['stage_references'])=={'comparison','independent_readback'},'Completed stage pair')
        result[row['numerical_task_id']]=dict(comparison_reference=deepcopy(row['stage_references']['comparison']),independent_readback_reference=deepcopy(row['stage_references']['independent_readback']))
    for refs in result.values():
        for r in refs.values():reference(r)
    return result

def extract_item(tid,refs,sources):
    audit=read(refs['independent_readback_reference'],sources);doc=read(refs['comparison_reference'],sources)
    require(audit['status']=='PASS','Accepted saved comparison audit');exact(audit['comparison_reference'],refs['comparison_reference'],'Audited comparison')
    publication_reference=audit['publication_reference'];reference(publication_reference)
    if 'publication_reference' in refs:exact(publication_reference,refs['publication_reference'],'Initial publication anchor')
    pub=read(publication_reference,sources);exact(pub['comparison_reference'],refs['comparison_reference'],'Published comparison');exact(pub['source_hashes'],doc['source_hashes'],'Saved publication source map');require(pub['status']=='PUBLISHED_SINGLE_PATH_DIAGNOSTIC_ONLY','Published conditional diagnostic')
    first=tid==FIRST;role='first_comparison' if first else 'comparison';p,h=READERS[role]
    require(audit['reader_sha256']==h and audit['source_hashes'].get(str(ROOT/p))==h,'Frozen independent reader binding')
    folder=Path(refs['comparison_reference']['path']).parent
    if first:
        require(folder==ROOT/'data/cache/research/dated_first_economic_comparison_20261003_v1','First fixed namespace');require({p.name for p in folder.iterdir()}=={'started.json','comparison.json','publication.json'},'First comparison immutable')
        positions=doc['comparison']['saved_paths_preserved']['candidate']['continuous_track']['positions_preserved']
    else:
        require(folder==COMPARISON_ROOT/tid and Path(refs['independent_readback_reference']['path'])==folder/'independent_readback.json','Per-task fixed namespace');require({p.name for p in folder.iterdir()}=={'started.json','comparison.json','publication.json','independent_readback.json'},'Audited comparison complete')
        positions=doc['comparison']['tracks']['candidate_continuous']['original_track_preserved']['positions_preserved']
    require(Path(publication_reference['path'])==folder/'publication.json','Fixed receipt path')
    return dict(document=doc,document_reference=deepcopy(refs['comparison_reference']),audit=audit,audit_reference=deepcopy(refs['independent_readback_reference']),original_targets=deepcopy(positions))

def load_inputs():
    for role in BOUND:reference(ref(role))
    for path,h in READERS.values():require(type(h) is str and len(h)==64,'Reader pin pending')
    sources={str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA};docs={k:read(ref(k),sources) for k in BOUND}
    for p,h in READERS.values():require(sha((ROOT/p).read_bytes())==h,'Reader source changed');merge(sources,str(ROOT/p),h)
    a=docs['task_summary_audit'];require(a['schema']=='DATED_BATCH_SUMMARY_INDEPENDENT_READBACK_V1' and a['status']=='PASS' and a['reader_sha256']==READERS['task_summary'][1],'Audited original task summary');exact(a['summary_reference'],ref('task_summary'),'Task summary audit');exact(a['publication_reference'],ref('task_summary_publication'),'Task summary receipt audit');exact(docs['task_summary_publication']['summary_reference'],ref('task_summary'),'Task summary published')
    a=docs['batch_audit'];require(a['schema']=='DATED_COMPARISON_BATCH_INDEPENDENT_READBACK_V1' and a['status']=='PASS' and a['reader_sha256']==READERS['batch'][1],'Audited comparison batch');exact(a['result_reference'],ref('batch'),'Exact batch audited')
    index=index_comparisons(docs['task_summary'],docs['initial'],docs['batch']);guard(sources)
    blob=CORE.read_bytes();require(sha(blob)==CORE_SHA,'Fresh frozen projection core');core=types.ModuleType('_stream_projection');core.__file__=str(CORE);exec(compile(blob,str(CORE),'exec'),core.__dict__);guard(sources)
    return docs,index,sources,core

FIRST_INPUT = dict(path=str(ROOT/'data/cache/research/dated_account_inputs_20261003_v1'/FIRST/'inputs.json'),sha256='ac0201e24925dff189d25e4fb5f0a8c741d567c31060f2aa48e3e2232fd90409')
FIRST_INPUT_AUDIT = dict(path=str(ROOT/'data/cache/research/dated_account_inputs_20261003_v1'/FIRST/'independent_readback.json'),sha256='396b45c1eec5a3fa0f2441744d409c0642eb21d2f6719da33725360707e114a3')

def load_projection_inputs(tid, refs, sources):
    envelope=extract_item(tid,refs,sources)
    envelope.pop('original_targets')
    document=envelope['document']
    if tid==FIRST:
        ir, ar=deepcopy(FIRST_INPUT),deepcopy(FIRST_INPUT_AUDIT)
    else:
        account_audit=document['independent_audits_preserved']['account_audit']
        saved_audit=read(document['input_references']['account_audit'],sources)
        exact(saved_audit,account_audit,'Preserved account audit bytes')
        ir=deepcopy(document['input_references']['inputs'])
        exact(account_audit['inputs_reference'],ir,'Account original input link')
        ar=deepcopy(account_audit['input_readback_reference'])
    folder=ROOT/'data/cache/research/dated_account_inputs_20261003_v1'/tid
    require(Path(ir['path'])==folder/'inputs.json' and Path(ar['path'])==folder/'independent_readback.json','Exact task input paths')
    require({p.name for p in folder.iterdir()}=={'started.json','inputs.json','publication.json','independent_readback.json'},'Complete immutable input namespace')
    inputs=read(ir,sources);audit=read(ar,sources)
    require(audit['schema']=='DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1' and audit['status']=='PASS','Accepted input audit')
    exact(audit['inputs_reference'],ir,'Input audit bytes link')
    p,h=READERS['inputs'];require(audit['reader_sha256']==h and audit['source_hashes'].get(str(ROOT/p))==h,'Frozen input reader link')
    pr=audit['publication_reference'];require(Path(pr['path'])==folder/'publication.json','Input receipt path')
    pub=read(pr,sources)
    require(pub['schema']=='DATED_ACCOUNT_INPUT_PUBLICATION_V1' and pub['status']=='PUBLISHED_CONDITIONAL_INPUT_NOT_EXECUTED','Input publication schema/status')
    exact(pub['inputs_reference'],ir,'Input receipt bytes link');exact(pub['source_hashes'],inputs['source_hashes'],'Input receipt source claims')
    return dict(task_id=tid,**envelope,inputs_document=inputs,inputs_reference=ir,input_audit=audit,input_audit_reference=ar)

def stream_paths(summary,index,load_item,core,write_row):
    """Keep one task envelope plus four immutable shared paths in memory."""
    ids=[row['numerical_task_id'] for row in summary['rows']]
    require(len(ids)==len(set(ids))==1632 and set(index).issubset(ids),'Full ordered task denominator')
    shared,identities,entries,claims={},{},[],{}
    calendar=None
    for ordinal,task in enumerate(summary['rows']):
        tid=task['numerical_task_id']
        entry=dict(task_ordinal=ordinal,numerical_task_id=tid,k=task['k'],weight_spec=deepcopy(task['weight_spec']),status='COMPARISON_NOT_SUPPLIED',jsonl_record=None)
        if tid in index:
            args=load_item(tid,index[tid])
            require(args['task_id']==tid,'Loaded task matches original index')
            projection=core.project_saved_comparison(**args)
            if calendar is None:calendar=deepcopy(projection['calendar'])
            else:exact(calendar,projection['calendar'],'Same full observation calendar')
            collection=core.collect_projections([projection])
            for key,value in collection['shared_paths'].items():
                role=value['identity']['role']
                if role in identities:exact(identities[role],value['identity'],'One immutable shared source per role')
                identities[role]=deepcopy(value['identity'])
                if key in shared:exact(shared[key],value,'Same shared path bytes and labels')
                else:shared[key]=deepcopy(value)
            for path,h in collection['source_hash_claims'].items():merge(claims,path,h)
            row=collection['tasks'][0]
            row['original_task_summary_row']=deepcopy(task)
            location=write_row(row)
            entry.update(status='AUDITED_SAVED_PATHS_PROJECTED',jsonl_record=location,
                candidate_integer_status=row['tracks']['candidate_integer']['status'],input_references=deepcopy(row['input_references']))
            del args,projection,collection,row
        entries.append(entry)
    present=sum(e['status']=='AUDITED_SAVED_PATHS_PROJECTED' for e in entries)
    require(len(shared)==(4 if present else 0),'Exactly four shared roles; both FX retained')
    groups={}
    for entry in entries:
        key=(entry['k'],enc(entry['weight_spec']).decode())
        groups.setdefault(key,[]).append(entry)
    coverage=[]
    for (k,spec),rows in sorted(groups.items()):
        available=[r for r in rows if r['status']=='AUDITED_SAVED_PATHS_PROJECTED']
        coverage.append(dict(k=k,weight_spec=json.loads(spec),planned_task_count=len(rows),projected_task_count=len(available),
            not_supplied_task_count=len(rows)-len(available),candidate_integer_status_counts=dict(Counter(r['candidate_integer_status'] for r in available))))
    return dict(task_index=entries,shared_paths=shared,calendar=calendar,planned_task_count=1632,
        projected_task_count=present,not_supplied_task_count=1632-present,
        k_spec_coverage=coverage,
        full_new_cutoff_task_denominator=summary['full_new_cutoff_task_denominator'],source_hash_claims=claims,
        full_documents_retained=False,evaluation_interval_previously_used_for_fitting=True,**FLAGS)

def run(*,execute=False):
    require(type(execute) is bool and execute,'Explicit execute required')
    require(not OUTPUT.exists(),'Immutable path display namespace exists')
    docs,index,base,core=load_inputs()
    resource_gate();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(schema='DATED_PATH_RISK_DISPLAY_STARTED_V1',input_references={k:ref(k) for k in BOUND},source_hashes=base,**FLAGS))
        sources=dict(base)
        def load_item(tid,refs):
            local={};value=load_projection_inputs(tid,refs,local);guard(local)
            for p,h in local.items():merge(sources,p,h)
            return value
        records=0;offset=0;digest=hashlib.sha256()
        with (OUTPUT/'tasks.jsonl').open('xb') as stream:
            def write_row(row):
                nonlocal records,offset
                blob=enc(row)+b'\n';resource_gate(len(blob));start=offset;stream.write(blob);digest.update(blob);offset+=len(blob)
                result=dict(record_index=records,byte_start=start,byte_stop=offset,row_sha256=sha(blob));records+=1
                return result
            result=stream_paths(docs['task_summary'],index,load_item,core,write_row)
            stream.flush();os.fsync(stream.fileno())
        guard(base)
        jsonl=dict(path=str(OUTPUT/'tasks.jsonl'),sha256=digest.hexdigest(),byte_count=offset,record_count=records)
        shared=save(OUTPUT/'shared_paths.json',dict(schema='DATED_PATH_RISK_SHARED_PATHS_V1',shared_paths=result.pop('shared_paths'),**FLAGS))
        value=dict(schema='SOURCE_BOUND_DATED_PATH_RISK_DISPLAY_V1',**result,
            task_jsonl_reference=jsonl,shared_paths_reference=shared,input_references={k:ref(k) for k in BOUND},
            batch_failure_preserved=deepcopy(docs['batch']['failure']),unresolved_task_ids=deepcopy(docs['batch']['unresolved_task_ids']),
            undispatched_task_ids=deepcopy(docs['batch']['undispatched_task_ids']),source_hashes=sources,
            source_verification_scope='DIRECT_ITEM_BYTES_CHECKED_AND_RECHECKED_BEFORE_RELEASE;BASE_RECHECKED_AT_PUBLICATION;TRANSITIVE_CLAIMS_NOT_REPLAYED')
        out=save(OUTPUT/'index.json',value);guard(base)
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','tasks.jsonl','shared_paths.json','index.json'},'Unexpected pre-publication files')
        pub=save(OUTPUT/'publication.json',dict(schema='DATED_PATH_RISK_DISPLAY_PUBLICATION_V1',status='PUBLISHED_SAVED_PATH_DISPLAY_ONLY',index_reference=out,task_jsonl_reference=jsonl,shared_paths_reference=shared,source_hashes=sources,**FLAGS))
        guard(base)
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','tasks.jsonl','shared_paths.json','index.json','publication.json'},'Unexpected final files')
        # Stream a final byte verification without retaining the whole JSONL.
        check=hashlib.sha256()
        with (OUTPUT/'tasks.jsonl').open('rb') as stream:
            for blob in iter(lambda:stream.read(1024*1024),b''):check.update(blob)
        require(check.hexdigest()==digest.hexdigest(),'JSONL persisted bytes')
        for r in (out,pub,shared):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Published metadata bytes changed')
        return out
    except Exception as error:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,error=str(error),retry_allowed=False));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
