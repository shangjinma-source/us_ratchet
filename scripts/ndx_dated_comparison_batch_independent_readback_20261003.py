"""Metadata-only comparison batch verification; no engine, fitter or numerical replay."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib,json,os
from pathlib import Path

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
RESULT_PATH=ROOT/'data/cache/research/dated_comparison_batch_20261003_v1/result.json'
RESULT_SHA='3a8c1ef0b3cd388586928f6c1b9674c4855b6c7c3c52b9c4ea1ced83ea7a09b2'
OUTPUT=ROOT/'data/cache/research/dated_comparison_batch_independent_readback_20261003_v1'
FULL=6222659648236112670
STAGES=('comparison','independent_readback')
FIRST='89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
INITIAL_IDS={FIRST,'530200b2ffe3b841c27f62dc68c5440c9b0f1cab7e7249592eaebae304713a68','046b0ad4dc7a207abf15e72ac1786848ad3a2a339515edc3b98e479bfb3678b9'}
BOUND={
 'summary':('data/cache/research/dated_batch_summary_20261003_v1/summary.json','406922de9ffc292417d4b495af30691833f5bb8c2b5b60449c010d5178acb378'),
 'economic_initial':('research_contracts/dated_initial_economic_completed_20261003_v1.json','1b5f549979e82653f2448d75ff48a6fa8a79497af1fcbe5066b77a2bcb48ffec'),
 'economic_result':('data/cache/research/dated_economic_batch_20261003_v1/result.json','6aaa8963043b54ad5de9a380302b3a7ae2007830a41de870a7947ce236d74218'),
 'economic_audit':('data/cache/research/dated_economic_batch_independent_readback_20261003_v1/independent_readback.json','322cec25f0a4deed92eeb98fa323d3cbbaece814e5544ad7026ceace958c15c7'),
 'initial':('research_contracts/dated_initial_comparisons_20261003_v1.json','2c03cb138ccc3c5af8e9f21a93cdb57322318f4d9e04b4a4dbca407b878d7ef2'),
 'driver':('scripts/ndx_dated_comparison_batch_20261003.py','5741d28f08189c04347291c9b2db439bce855de7eb8580cd9ad7e298e4116290')}
READER_SHA='6067301133e1662e6021c53e25d1c79c72e91e2b91b71cd5b8b874db035532ad'
FIRST_READER_SHA='155eab023c9ba22da72a7668d5d1df0f840051a1d8f398b5550aa6cdf9130739'
BATCH_FALSE=('fit_performed','account_executed','continuous_recomputed','retry_allowed','promotion_allowed','point_in_time_verified','formal_comparison_passed','winner_selected','all_plan_tasks_completed')
FLAGS=dict.fromkeys((*BATCH_FALSE,'economic_arithmetic_recomputed','old_audit_repeated','full_transitive_source_closure_reverified'),False)
PREPARATION_REFERENCE=dict(path=str(ROOT/'data/cache/research/dated_fixed_task_preparation_20261003_v1/preparation.json'),sha256='ff24a6b732bc55ea6dbb7b453a41ff58d0f2ee316e3f2120aa4006f3b82d3d0e')

def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def integer(v,n,msg):require(type(v) is int and v==n,msg)
def ref(role):p,h=BOUND[role];return dict(path=str(ROOT/p),sha256=h)
def reference(r):require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'] and type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Exact reference')
def merge(s,p,h):require(p not in s or s[p]==h,'Conflicting bytes');s[p]=h
def read(r,s):
    reference(r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Referenced bytes drift');merge(s,r['path'],r['sha256'])
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate key');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=invalid)
def guard(s):
    merged=dict(s);merge(merged,str(SOURCE),LOADED_SHA)
    for p,h in merged.items():require(sha(Path(p).read_bytes())==h,'Source drift')
def false(obj,keys):
    for k in keys:require(obj[k] is False,'Authority '+k)

def partition(summary,initial,batch):
    require(summary['schema']=='DATED_BATCH_SAVED_READBACK_SUMMARY_V1' and initial['schema']=='DATED_INITIAL_COMPARISONS_V1' and batch['schema']=='DATED_COMPARISON_BATCH_RESULT_V1','Source schemas')
    ids=[r['numerical_task_id'] for r in summary['rows']];require(len(ids)==len(set(ids))==1632,'Complete unique queue')
    integer(summary['full_new_cutoff_task_denominator'],FULL,'Full domain');integer(summary['old_different_cutoff_completed_count_deducted'],0,'No old cutoff deduction')
    context=batch['context'];integer(context['full_task_count'],1632,'Context materialized domain');integer(context['full_new_cutoff_task_denominator'],FULL,'Context full dated domain')
    exact(context['input_references'],{k:ref(k) for k in ('summary','economic_initial','economic_result','economic_audit','initial')},'Original batch source context')
    require(context['source_hashes'].get(ref('driver')['path'])==ref('driver')['sha256'],'Actual frozen batch driver')
    for r in context['input_references'].values():require(context['source_hashes'].get(r['path'])==r['sha256'],'Context source map reference')
    require(context['resource_gate_does_not_reduce_domain'] is True,'No economic completion or domain truncation')
    integer(context['minimum_free_disk_bytes'],5*1024**3,'Original resource gate')
    require(len(initial['rows'])==3 and {r['numerical_task_id'] for r in initial['rows']}==INITIAL_IDS,'Explicit initial three')
    exact(batch['initial_rows_preserved'],initial['rows'],'Initial references preserved')
    remaining=[t for t in ids if t not in INITIAL_IDS];new=batch['new_completed_rows']
    require([r['numerical_task_id'] for r in new]==remaining[:len(new)],'Original queue prefix, no selection/retry')
    for row in new:require(set(row['stage_references'])==set(STAGES),'Six completed stage references')
    integer(batch['planned_remaining_count'],1629,'Remaining dispatch denominator');integer(batch['new_completed_count'],len(new),'Completed count')
    u=batch['unresolved_task_ids'];n=batch['undispatched_task_ids'];require(type(u) is list and type(n) is list and len(u)<=1,'Failure partition lists')
    exact([r['numerical_task_id'] for r in new]+u+n,remaining,'Complete ordered partition')
    failure=batch['failure']
    if failure is None:require(batch['status']=='REQUESTED_COMPARISONS_FINISHED' and not u and not n,'Finished covers remaining queue')
    else:
        require(batch['status']=='STOPPED_WITH_EVIDENCE','Stopped status');integer(failure['ordinal'],len(new),'Failure ordinal')
        require(failure['numerical_task_id']==remaining[len(new)],'Failure at next task')
        for k in ('task_stage_invoked','current_stage_invoked','stage_may_have_written_evidence'):require(type(failure[k]) is bool,'Exact invocation flags')
        require(failure['task_stage_invoked']==failure['stage_may_have_written_evidence']==bool(u),'Invoked vs undispatched partition')
        require(not failure['current_stage_invoked'] or failure['task_stage_invoked'],'Current invocation implies task invocation')
        require(failure['retry_allowed'] is False,'No retry')
        refs=failure['completed_stage_references'];require(type(refs) is dict and set(refs)==set(STAGES[:len(refs)]),'Partial stage prefix')
        stage=failure['stage'];require(stage is None or stage in STAGES,'Failure stage')
        if stage is None:require(not refs and not u,'Pre-stage failure')
        else:require(len(refs) in (STAGES.index(stage),STAGES.index(stage)+1),'Last attempted stage position')
        if refs:require(failure['task_stage_invoked'],'Returned stages cannot be undispatched')
    false(batch,BATCH_FALSE);false(context,BATCH_FALSE)
    return ids,new,failure

def economic_map(ids,initial,result):
    require(initial['schema']=='DATED_INITIAL_ECONOMIC_COMPLETED_V1' and result['schema']=='DATED_ECONOMIC_BATCH_RESULT_V1','Economic source schemas')
    exact(initial['preparation_reference'],PREPARATION_REFERENCE,'Same dated preparation')
    require(len(initial['rows'])==3 and {r['numerical_task_id'] for r in initial['rows']}==INITIAL_IDS,'Three economic ancestors')
    exact(result['initial_rows_preserved'],initial['rows'],'Economic initial copy')
    require(result['status']=='REQUESTED_ECONOMIC_STAGES_FINISHED' and result['failure'] is None and result['unresolved_task_ids']==[] and result['undispatched_task_ids']==[],'Economic parent complete')
    integer(result['planned_remaining_count'],1629,'Economic planned');integer(result['new_completed_count'],1629,'Economic completed')
    exact([r['numerical_task_id'] for r in result['new_completed_rows']],[t for t in ids if t not in INITIAL_IDS],'Original economic order')
    roles={'inputs','input_readback','account_postcheck','account_readback','continuous','continuous_readback'}
    out={r['numerical_task_id']:{k:r[k] for k in roles} for r in initial['rows']}
    for row in result['new_completed_rows']:
        require(set(row['stage_references'])==roles,'Economic complete stage references');out[row['numerical_task_id']]=row['stage_references']
    for refs in out.values():
        for value in refs.values():reference(value)
    return out

def validate_comparison(tid,d,pub,a,refs,economic_refs,*,complete=True):
    first=tid==FIRST
    require(d['schema']==('SOURCE_BOUND_DATED_FIRST_ECONOMIC_COMPARISON_V1' if first else 'SOURCE_BOUND_DATED_PER_TASK_ECONOMIC_COMPARISON_V1'),'Comparison schema')
    false(d,('fit_performed','account_executed','point_in_time_verified','promotion_allowed','formal_comparison_passed','winner_selected','future_independent_oos','untouched_holdout'))
    c=d['comparison'];missing=False
    if not first:
        require(d['numerical_task_id']==tid and d['original_task_preserved']['numerical_task_id']==tid,'Exact comparison task')
        require(sha(enc(d['original_task_preserved']['numerical_identity']))==tid,'Numerical identity digest')
        require(d['original_task_preserved']['numerical_identity']['cutoff']=='2026-03-20' and d['original_task_preserved']['numerical_identity']['requested_previous_target_weights'] is None,'Dated None prior')
        for key,role in [('account_audit','account_readback'),('continuous_audit','continuous_readback'),('inputs','inputs'),('continuous','continuous')]:exact(d['input_references'][key],economic_refs[role],'Economic source binding')
        require(len(d['original_provenance_and_missing'])==101 and len(d['preserved_evidence_sidecars'])==7,'Evidence denominator retained')
        require(c['schema']=='DATED_PER_TASK_PARTIAL_ECONOMIC_DIAGNOSTIC_V1','Per-task result')
        status=c['candidate_integer_status_preserved']['status'];require(status in ('AVAILABLE','NOT_EXECUTED_NONPOSITIVE_TARGET'),'No technical absence as completed comparison');missing=status!='AVAILABLE'
        require(c['status']==('PARTIAL_CANDIDATE_INTEGER_UNAVAILABLE' if missing else 'ALL_FOUR_SAVED_TRACKS_DIAGNOSTIC_ONLY'),'Completeness explicit')
        if missing:
            track=c['tracks']['candidate_integer'];require(track['metrics'] is None and track['stored_values_exact'] is None and track['original_account_preserved'] is None,'Absent is not cash')
    if pub is not None:
        require(pub['schema']==('DATED_FIRST_ECONOMIC_COMPARISON_PUBLICATION_V1' if first else 'DATED_PER_TASK_ECONOMIC_COMPARISON_PUBLICATION_V1') and pub['status']=='PUBLISHED_SINGLE_PATH_DIAGNOSTIC_ONLY','Successful comparison receipt')
        exact(pub['comparison_reference'],refs['comparison'],'Publication target');exact(pub['source_hashes'],d['source_hashes'],'Publication source copy');false(pub,('fit_performed','account_executed','point_in_time_verified','promotion_allowed','formal_comparison_passed'))
    if complete:require(pub is not None and a is not None,'Every accepted comparison needs receipt and audit')
    if a is not None:
        require(a['schema']==('DATED_COMPARISON_INDEPENDENT_READBACK_V1' if first else 'DATED_PER_TASK_COMPARISON_INDEPENDENT_READBACK_V1') and a['status']=='PASS','Accepted comparison audit')
        if not first:require(a['numerical_task_id']==tid,'Audit task')
        require(a['reader_sha256']==(FIRST_READER_SHA if first else READER_SHA),'Frozen reader')
        exact(a['comparison_reference'],refs['comparison'],'Audit result');exact(a['publication_reference'],refs['publication'],'Audit receipt')
        false(a,('fit_performed','account_executed','point_in_time_verified','promotion_allowed','formal_comparison_passed','future_independent_oos'))
        counts=a if first else a['counts'];integer(counts['path_count'],5 if missing else 6,'Audited saved path count');integer(counts['observation_count'],635 if missing else 762,'Full points')
        integer(counts['distance_cell_count' if first else 'available_distance_cell_count'],4 if missing else 8,'Audited available distance count')
    return dict(numerical_task_id=tid,pipeline_complete=complete,stage_references=deepcopy(refs),integer_account_available=not missing,comparison_status=c.get('status'),economic_parent_references=deepcopy(economic_refs))

def readback(result_reference,*,execute=False):
    require(execute is True and RESULT_SHA is not None and all(h is not None for p,h in BOUND.values()),'Final result and economic anchors pending');reference(result_reference)
    exact(result_reference,dict(path=str(RESULT_PATH),sha256=RESULT_SHA),'Actual fixed result');require(not OUTPUT.exists(),'Create-only readback')
    base={str(SOURCE):LOADED_SHA};docs={k:read(ref(k),base) for k in BOUND if k!='driver'};merge(base,ref('driver')['path'],ref('driver')['sha256']);batch=read(result_reference,base)
    audit=docs['economic_audit'];require(audit['schema']=='DATED_ECONOMIC_BATCH_INDEPENDENT_READBACK_V1' and audit['status']=='PASS','Accepted economic audit');exact(audit['result_reference'],ref('economic_result'),'Economic audit target')
    ids,new,failure=partition(docs['summary'],docs['initial'],batch);exact(docs['initial']['preparation_reference'],PREPARATION_REFERENCE,'Initial dated preparation')
    parents=economic_map(ids,docs['economic_initial'],docs['economic_result'])
    path=RESULT_PATH.with_name('started.json');b=path.read_bytes();sr=dict(path=str(path),sha256=sha(b));started=read(sr,base)
    require(started['schema']=='DATED_COMPARISON_BATCH_STARTED_V1','Started schema');exact(started['ordered_remaining_task_ids'],[t for t in ids if t not in INITIAL_IDS],'Started order');exact(started['initial_rows'],docs['initial']['rows'],'Started initial');exact(started['context'],batch['context'],'Started context');false(started,BATCH_FALSE)
    for p,h in batch['context']['source_hashes'].items():merge(base,p,h)
    guard(base);sources=dict(base);rows=[]
    work=[(r['numerical_task_id'],dict(comparison=r['comparison_reference'],independent_readback=r['independent_readback_reference'],publication=r['publication_reference']),True) for r in docs['initial']['rows']]+[(r['numerical_task_id'],r['stage_references'],True) for r in new]
    if failure and failure['completed_stage_references']:work.append((failure['numerical_task_id'],failure['completed_stage_references'],False))
    for tid,stage_refs,complete in work:
        local={};refs=deepcopy(stage_refs);d=read(refs['comparison'],local);a=read(refs['independent_readback'],local) if 'independent_readback' in refs else None;pub=None
        if tid!=FIRST:
            for key,role in [('account_audit','account_readback'),('continuous_audit','continuous_readback')]:
                parent_audit=read(parents[tid][role],local)
                exact(d['independent_audits_preserved'][key],parent_audit,'Complete parent audit copy')
        if a is not None:
            if 'publication' in refs:exact(refs['publication'],a['publication_reference'],'Initial receipt anchor')
            else:refs['publication']=a['publication_reference']
            pub=read(refs['publication'],local)
        elif 'publication' in refs:pub=read(refs['publication'],local)
        rows.append(validate_comparison(tid,d,pub,a,refs,parents[tid],complete=complete));guard(local)
        for p,h in local.items():merge(sources,p,h)
        del d,pub,a
    guard(base);report=dict(schema='DATED_COMPARISON_BATCH_INDEPENDENT_READBACK_V1',status='PASS',result_reference=result_reference,reader_sha256=LOADED_SHA,rows=rows,input_references={k:ref(k) for k in BOUND},source_hashes=sources,batch_started_reference=sr,batch_started_reference_scope='CURRENT_BYTES_MATCH_EXTERNAL_RESULT_CONTEXT_NOT_EXTERNAL_START_ANCHOR',batch_context_preserved=batch['context'],initial_completed_count=3,new_completed_count=len(new),completed_pipeline_count=3+len(new),planned_task_count=1632,full_new_cutoff_task_denominator=FULL,remaining_without_completed_pipeline_count=FULL-3-len(new),batch_failure_preserved=failure,unresolved_task_ids=batch['unresolved_task_ids'],undispatched_task_ids=batch['undispatched_task_ids'],source_verification_scope='EACH_DIRECT_TASK_REFERENCE_READ_AND_FINAL_LOCAL_CHECK;BASE_FINAL_CHECK;NO_TRANSITIVE_REAUDIT',progress_dispatch_log_reverified=False,**FLAGS)
    OUTPUT.mkdir(parents=True,exist_ok=False);out=OUTPUT/'independent_readback.json';blob=enc(report)
    with out.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    guard(base);require(out.read_bytes()==blob and {p.name for p in OUTPUT.iterdir()}=={out.name},'Durable exact output');return dict(path=str(out),sha256=sha(blob))
