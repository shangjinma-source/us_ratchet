"""Stream saved comparison files into compact tables; never replay economics."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib,json,os,types
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_dated_comparison_results_summary_research.py';CORE_SHA='2a2d2dc006f75092fe1b04d33abec9e2014e3ab1aa06906b419879466f9b0d42'
OUTPUT=ROOT/'data/cache/research/dated_comparison_results_summary_20261003_v1'
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
}
FLAGS=dict.fromkeys(('comparison_recomputed','account_executed','fit_performed','audit_reexecuted','full_transitive_source_closure_reverified','formal_comparison_passed','point_in_time_verified','promotion_allowed','winner_selected','cohort_statistics_computed','future_independent_oos'),False)

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
def save(path,value):
    b=enc(value)
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

def stream_summary(summary,summary_reference,index,load_item,core):
    """One denominator validation, then one compact projection per available task."""
    output=core.summarize_comparisons(task_summary=summary,task_summary_reference=summary_reference,comparisons_by_task={})
    require(set(index).issubset({r['numerical_task_id'] for r in summary['rows']}),'No foreign task in comparison index')
    present=0
    for i,task in enumerate(summary['rows']):
        tid=task['numerical_task_id']
        if tid not in index:continue
        envelope=load_item(tid,index[tid]);row=core.project_task(task,envelope)
        for key in ('document_reference','audit_reference'):
            r=envelope[key];merge(output['source_hash_claims'],r['path'],r['sha256'])
        output['rows'][i]=row;present+=1;del envelope
    output['supplied_comparison_count']=present;output['not_supplied_count']=1632-present;output['unrepresented_full_domain_count']=output['full_new_cutoff_task_denominator']-present
    # Compact rows only: no saved original account/path retained by project_task.
    groups={}
    for row in output['rows']:groups.setdefault((row['k'],row['weight_spec']),[]).append(row)
    strata=[]
    for k,spec in sorted(groups):
        rows=groups[k,spec];ok=[r for r in rows if r['status']=='AUDITED_COMPARISON_PRESENT']
        strata.append(dict(k=k,weight_spec=spec,planned_task_count=32,supplied_comparison_count=len(ok),not_supplied_count=32-len(ok),candidate_integer_status_counts=dict(Counter(r['tracks']['candidate_integer']['status'] for r in ok)),candidate_integer_decision_counts=dict(Counter(r['tracks']['candidate_integer']['decision_status'] for r in ok if r['tracks']['candidate_integer']['decision_status'] is not None)),candidate_integer_execution_counts=dict(Counter(s for r in ok for s in (r['tracks']['candidate_integer']['execution_statuses'] or [])))))
    output['k_spec_coverage']=strata;return output

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

def run(*,execute=False):
    require(type(execute) is bool and execute,'Explicit execute required');require(not OUTPUT.exists(),'Immutable summary namespace exists')
    docs,index,base,core=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(schema='DATED_COMPARISON_RESULTS_SUMMARY_STARTED_V1',input_references={k:ref(k) for k in BOUND},source_hashes=base,**FLAGS))
        all_sources=dict(base)
        def load_item(tid,refs):
            local={};envelope=extract_item(tid,refs,local);guard(local)
            for p,h in local.items():merge(all_sources,p,h)
            return envelope
        compact=stream_summary(docs['task_summary'],ref('task_summary'),index,load_item,core);guard(base)
        value=dict(schema='SOURCE_BOUND_DATED_COMPARISON_RESULTS_SUMMARY_V1',tables=compact,input_references={k:ref(k) for k in BOUND},batch_failure_preserved=deepcopy(docs['batch']['failure']),unresolved_task_ids=deepcopy(docs['batch']['unresolved_task_ids']),undispatched_task_ids=deepcopy(docs['batch']['undispatched_task_ids']),source_hashes=all_sources,source_verification_scope='DIRECT_COMPARISON_AUDIT_PUBLICATION_BYTES_AT_EACH_ITEM;BASE_RECHECKED_AT_END;NO_TRANSITIVE_REPLAY',streamed_full_documents_retained=False,**FLAGS)
        out=save(OUTPUT/'summary.json',value);guard(base);require({p.name for p in OUTPUT.iterdir()}=={'started.json','summary.json'},'Unexpected pre-publication file')
        pub=save(OUTPUT/'publication.json',dict(schema='DATED_COMPARISON_RESULTS_SUMMARY_PUBLICATION_V1',status='PUBLISHED_SAVED_DIAGNOSTIC_TABLES',summary_reference=out,source_hashes=all_sources,**FLAGS));guard(base)
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','summary.json','publication.json'},'Unexpected published file')
        for r in (out,pub):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Publication bytes changed')
        return out
    except Exception as e:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(e).__name__,error=str(e),retry_allowed=False));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
