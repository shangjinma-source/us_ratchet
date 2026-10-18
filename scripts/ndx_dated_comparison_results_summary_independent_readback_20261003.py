"""Stream saved comparison files into compact tables; never replay economics."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib,json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PRODUCER=ROOT/'scripts/ndx_dated_comparison_results_summary_20261003.py'
PRODUCER_SHA='50aa1e9c4f47f114af3ad6c1ada0e3bb572f06acc5166be7b834644d7aabebe9'
CORE=ROOT/'backtest/ndx_dated_comparison_results_summary_research.py'
CORE_SHA='2a2d2dc006f75092fe1b04d33abec9e2014e3ab1aa06906b419879466f9b0d42'
SUMMARY_PATH=ROOT/'data/cache/research/dated_comparison_results_summary_20261003_v1/summary.json'
SUMMARY_SHA='33f7063589b085300f26823d46b2e96c078fbf55144c8ad075269e45417440e9';PUBLICATION_SHA='c66bf1a809c27328eb51dfd542811e6e3d090d5de0154ee5e07f0426ad0f355f'
OUTPUT=ROOT/'data/cache/research/dated_comparison_results_summary_independent_readback_20261003_v1'
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
    values=dict(s);merge(values,str(SOURCE),LOADED_SHA);merge(values,str(PRODUCER),PRODUCER_SHA)
    for p,h in values.items():require(type(h) is str and sha(Path(p).read_bytes())==h,'Source drift or pending')
def save(path,value):
    b=enc(value)
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Output drift');return dict(path=str(path),sha256=sha(b))

def expected_producer_sources():
    """Fixed external anchors, never a producer-supplied source table."""
    result={}
    entries=[(str(PRODUCER),PRODUCER_SHA),(str(CORE),CORE_SHA)]
    entries.extend((str(ROOT/p),h) for p,h in BOUND.values())
    entries.extend((str(ROOT/p),h) for p,h in READERS.values())
    for p,h in entries:
        reference(dict(path=p,sha256=h));merge(result,p,h)
    return result

def verify_source_tables(start,document,publication,expected_base,expected_all):
    exact(start['source_hashes'],expected_base,'Exact independently bound producer base')
    exact(document['source_hashes'],expected_all,'Exact direct source union, no missing or extra claims')
    exact(publication['source_hashes'],expected_all,'Exact published direct source union')

FULL=6222659648236112670
SPECS=('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
TRACKS=('candidate_integer','incumbent_integer','candidate_continuous','incumbent_continuous')
METRICS=('cumulative_return','annualized_return','maximum_drawdown')
TABLE_FALSE=('comparison_recomputed','account_executed','fit_performed','source_bytes_authenticated','audit_reexecuted','cohort_statistics_computed','formal_comparison_passed','formal_noninferiority_verified','point_in_time_verified','promotion_allowed','winner_selected','global_optimum_proved','future_independent_oos')
def missing_row(task):
    return dict(numerical_task_id=task['numerical_task_id'],k=task['k'],weight_spec=task['weight_spec'],status='NOT_SUPPLIED',original_targets=None,tracks=None,nav_modes=None,reason='No externally audited comparison supplied; not inferred failed or all cash')

def verify_row(row,task,document,audit,refs):
    tid=task['numerical_task_id'];first=tid==FIRST;c=document['comparison']
    require(document['schema']==('SOURCE_BOUND_DATED_FIRST_ECONOMIC_COMPARISON_V1' if first else 'SOURCE_BOUND_DATED_PER_TASK_ECONOMIC_COMPARISON_V1'),'Document schema')
    require(audit['schema']==('DATED_COMPARISON_INDEPENDENT_READBACK_V1' if first else 'DATED_PER_TASK_COMPARISON_INDEPENDENT_READBACK_V1') and audit['status']=='PASS','Accepted audit')
    if not first:require(document['numerical_task_id']==audit['numerical_task_id']==document['original_task_preserved']['numerical_task_id']==tid,'Same task')
    exact(audit['comparison_reference'],refs['comparison_reference'],'Audited comparison')
    positions=c['saved_paths_preserved']['candidate']['continuous_track']['positions_preserved'] if first else c['tracks']['candidate_continuous']['original_track_preserved']['positions_preserved']
    require(len(positions)==task['k'] and len({p['security_id'] for p in positions})==task['k'],'Uncompressed target coordinates')
    tracks={}
    for name in TRACKS:
        t=c['tracks'][name];available=first or t['status']=='AVAILABLE'
        if not available:
            require(name=='candidate_integer' and t['status'] in ('NOT_EXECUTED_NONPOSITIVE_TARGET','TECHNICAL_MISSING') and t['metrics'] is None and t['stored_values_exact'] is None and t['original_account_preserved'] is None,'Missing not cash')
            tracks[name]=dict(status=t['status'],metrics=None,decision_status=None,execution_statuses=None,source_reference=None,missing_evidence=t['missing_evidence']);continue
        decision=None;executions=None
        if name.endswith('_integer'):
            account=c['saved_paths_preserved'][name.split('_')[0]]['integer_account'] if first else t['original_account_preserved'];require(len(account['decisions'])==1,'One original decision');decision=account['decisions'][0]['status'];executions=[e['status'] for e in account['executions']]
        tracks[name]=dict(status='AVAILABLE',metrics={k:t['metrics'][k] for k in METRICS},decision_status=decision,execution_statuses=executions,source_reference=t['source_reference'],path_pointer=t.get('path_pointer'),value_encoding=t['value_encoding'])
    modes={mode:dict(nav_metrics={k:c['nav_modes'][mode]['metrics'][k] for k in METRICS},nav_source_reference=c['nav_modes'][mode]['source_reference'],absolute_distance_comparisons=c['absolute_distance_comparisons'][mode]) for mode in MODES}
    expected=dict(numerical_task_id=tid,k=task['k'],weight_spec=task['weight_spec'],status='AUDITED_COMPARISON_PRESENT',original_targets=positions,target_weights_normalized_by_summary=False,comparison_reference=refs['comparison_reference'],audit_reference=refs['independent_readback_reference'],calendar=c['calendar'],tracks=tracks,nav_modes=modes,original_candidate_integer_status=None if first else c['candidate_integer_status_preserved'],source_references_preserved=c['source_references_preserved'])
    exact(row,expected,'Every compact row field is an unchanged source projection')
    for obj in (document,c):
        for flag in ('formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','winner_selected'):require(obj[flag] is False,'Conditional source scope')
    for flag in ('formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos'):require(audit[flag] is False,'Audit scope')

def verify_tables(tables,summary,index):
    tasks=summary['rows'];require(summary['schema']=='DATED_BATCH_SAVED_READBACK_SUMMARY_V1' and len(tasks)==1632 and len({t['numerical_task_id'] for t in tasks})==1632,'Full queue')
    integer(summary['materialized_task_count'],1632,'Materialized queue');integer(summary['full_new_cutoff_task_denominator'],FULL,'Full domain')
    coverage=Counter((t['k'],t['weight_spec']) for t in tasks)
    require(coverage==Counter({(k,s):32 for k in range(4,21) for s in SPECS}),'51 complete strata')
    require(all(type(t['k']) is int for t in tasks),'Exact k integers');require(set(index)<= {t['numerical_task_id'] for t in tasks},'No foreign supplied task')
    require(tables['schema']=='DATED_COMPARISON_RESULTS_TABLES_V1','Tables schema');exact([r['numerical_task_id'] for r in tables['rows']],[t['numerical_task_id'] for t in tasks],'Original order')
    groups={}
    for task,row in zip(tasks,tables['rows']):
        require(row['k']==task['k'] and type(row['k']) is int and row['weight_spec']==task['weight_spec'],'Original coordinates')
        if task['numerical_task_id'] not in index:exact(row,missing_row(task),'Missing row explicit')
        else:require(row['status']=='AUDITED_COMPARISON_PRESENT','Supplied status')
        groups.setdefault((task['k'],task['weight_spec']),[]).append(row)
    strata=[]
    for (k,s),rows in sorted(groups.items()):
        ok=[r for r in rows if r['status']=='AUDITED_COMPARISON_PRESENT']
        strata.append(dict(k=k,weight_spec=s,planned_task_count=32,supplied_comparison_count=len(ok),not_supplied_count=32-len(ok),candidate_integer_status_counts=dict(Counter(r['tracks']['candidate_integer']['status'] for r in ok)),candidate_integer_decision_counts=dict(Counter(r['tracks']['candidate_integer']['decision_status'] for r in ok if r['tracks']['candidate_integer']['decision_status'] is not None)),candidate_integer_execution_counts=dict(Counter(e for r in ok for e in (r['tracks']['candidate_integer']['execution_statuses'] or [])))))
    exact(tables['k_spec_coverage'],strata,'Every stratum count')
    for key,n in [('materialized_task_count',1632),('supplied_comparison_count',len(index)),('not_supplied_count',1632-len(index)),('full_new_cutoff_task_denominator',FULL),('unrepresented_full_domain_count',FULL-len(index))]:integer(tables[key],n,'Count '+key)
    exact(tables['mode_order'],list(MODES),'Both FX modes');require(tables['modes_kept_separate'] is True and tables['original_order_preserved'] is True and tables['single_path_diagnostics_not_cohort_envelope'] is True,'Projection boundaries')
    exact(tables['task_summary_reference'],ref('task_summary'),'Task source');require(tables['aggregation_scope']=='SAVED_AUDITED_METRICS_PROJECTION_ONLY_NO_RETURN_DISTANCE_RECOMPUTATION','No new metrics')
    for k in TABLE_FALSE:require(tables[k] is False,'No promotion '+k)

def make_index(tasks,initial,batch):
    ids=[r['numerical_task_id'] for r in tasks['rows']];require(initial['schema']=='DATED_INITIAL_COMPARISONS_V1' and batch['schema']=='DATED_COMPARISON_BATCH_RESULT_V1','Parent schemas');require(len(initial['rows'])==3 and {r['numerical_task_id'] for r in initial['rows']}==INITIAL_IDS,'Initial3')
    exact(batch['initial_rows_preserved'],initial['rows'],'Initial copy');remaining=[t for t in ids if t not in INITIAL_IDS];new=batch['new_completed_rows'];integer(batch['planned_remaining_count'],1629,'Batch planned');integer(batch['new_completed_count'],len(new),'New count')
    exact([r['numerical_task_id'] for r in new]+batch['unresolved_task_ids']+batch['undispatched_task_ids'],remaining,'Entire dispatch partition')
    if batch['failure'] is None:require(batch['status']=='REQUESTED_COMPARISONS_FINISHED' and not batch['unresolved_task_ids'] and not batch['undispatched_task_ids'],'Complete batch')
    else:require(batch['status']=='STOPPED_WITH_EVIDENCE','Stopped scope')
    index={r['numerical_task_id']:{k:r[k] for k in ('comparison_reference','publication_reference','independent_readback_reference')} for r in initial['rows']}
    for row in new:
        require(set(row['stage_references'])=={'comparison','independent_readback'},'Both accepted stages');index[row['numerical_task_id']]=dict(comparison_reference=row['stage_references']['comparison'],independent_readback_reference=row['stage_references']['independent_readback'])
    return index

def readback(*,execute=False):
    require(execute is True and SUMMARY_SHA is not None and PUBLICATION_SHA is not None and PRODUCER_SHA is not None and all(h is not None for p,h in BOUND.values()) and all(h is not None for p,h in READERS.values()),'Actual anchors pending');require(not OUTPUT.exists(),'Exclusive readback')
    producer_base=expected_producer_sources();guard(producer_base)
    expected_all=dict(producer_base);base=dict(producer_base);merge(base,str(SOURCE),LOADED_SHA);sr=dict(path=str(SUMMARY_PATH),sha256=SUMMARY_SHA);pr=dict(path=str(SUMMARY_PATH.with_name('publication.json')),sha256=PUBLICATION_SHA)
    d=read(sr,base);pub=read(pr,base);docs={k:read(ref(k),base) for k in BOUND};folder=SUMMARY_PATH.parent
    require({p.name for p in folder.iterdir()}=={'started.json','summary.json','publication.json'},'No failed or foreign output')
    require(d['schema']=='SOURCE_BOUND_DATED_COMPARISON_RESULTS_SUMMARY_V1' and pub['schema']=='DATED_COMPARISON_RESULTS_SUMMARY_PUBLICATION_V1' and pub['status']=='PUBLISHED_SAVED_DIAGNOSTIC_TABLES','Published summary');exact(pub['summary_reference'],sr,'Publication target');exact(pub['source_hashes'],d['source_hashes'],'Publication source map')
    inputs={k:ref(k) for k in BOUND};exact(d['input_references'],inputs,'Hard parent refs')
    b=(folder/'started.json').read_bytes();startedref=dict(path=str(folder/'started.json'),sha256=sha(b));start=read(startedref,base);require(start['schema']=='DATED_COMPARISON_RESULTS_SUMMARY_STARTED_V1','Started schema');exact(start['input_references'],inputs,'Started context')
    exact(start['source_hashes'],producer_base,'Started independently reconstructed source base')
    for obj in (d,pub,start):
        for k in FLAGS:require(obj[k] is False,'No authority '+k)
    require(d['streamed_full_documents_retained'] is False,'Streaming scope')
    for k in ('failure','unresolved_task_ids','undispatched_task_ids'):exact(d['batch_failure_preserved' if k=='failure' else k],docs['batch'][k],'Batch partition copy')
    for role,key,source in [('task_summary_audit','summary_reference','task_summary'),('batch_audit','result_reference','batch')]:require(docs[role]['status']=='PASS','Accepted parent audit');exact(docs[role][key],ref(source),'Parent audited reference')
    require(docs['task_summary_audit']['schema']=='DATED_BATCH_SUMMARY_INDEPENDENT_READBACK_V1' and docs['batch_audit']['schema']=='DATED_COMPARISON_BATCH_INDEPENDENT_READBACK_V1','Parent audit schemas')
    require(docs['task_summary_audit']['reader_sha256']==READERS['task_summary'][1] and docs['batch_audit']['reader_sha256']==READERS['batch'][1],'Parent reader source pins')
    exact(docs['task_summary_audit']['publication_reference'],ref('task_summary_publication'),'Task audit publication');exact(docs['task_summary_publication']['summary_reference'],ref('task_summary'),'Task receipt')
    index=make_index(docs['task_summary'],docs['initial'],docs['batch']);verify_tables(d['tables'],docs['task_summary'],index)
    sources=dict(base);claims={ref('task_summary')['path']:ref('task_summary')['sha256']}
    for task,row in zip(docs['task_summary']['rows'],d['tables']['rows']):
        tid=task['numerical_task_id']
        if tid not in index:continue
        refs=index[tid];local={};doc=read(refs['comparison_reference'],local);audit=read(refs['independent_readback_reference'],local);receiptref=audit['publication_reference']
        if 'publication_reference' in refs:exact(receiptref,refs['publication_reference'],'Initial publication')
        receipt=read(receiptref,local);exact(receipt['comparison_reference'],refs['comparison_reference'],'Per-task receipt');exact(receipt['source_hashes'],doc['source_hashes'],'Per-task receipt source');require(receipt['status']=='PUBLISHED_SINGLE_PATH_DIAGNOSTIC_ONLY','Per-task publication status')
        role='first_comparison' if tid==FIRST else 'comparison';p,h=READERS[role];require(audit['reader_sha256']==h and audit['source_hashes'].get(str(ROOT/p))==h,'Frozen task audit')
        verify_row(row,task,doc,audit,refs);guard(local)
        for p,h in local.items():merge(sources,p,h);merge(expected_all,p,h)
        for k in ('comparison_reference','independent_readback_reference'):merge(claims,refs[k]['path'],refs[k]['sha256'])
        del doc,audit,receipt
    exact(d['tables']['source_hash_claims'],claims,'All compact source claims')
    verify_source_tables(start,d,pub,producer_base,expected_all)
    guard(base);report=dict(schema='DATED_COMPARISON_RESULTS_SUMMARY_INDEPENDENT_READBACK_V1',status='PASS',summary_reference=sr,publication_reference=pr,reader_sha256=LOADED_SHA,source_hashes=sources,verified_task_count=1632,verified_stratum_count=51,verified_supplied_count=len(index),batch_started_reference=startedref,started_reference_scope='CURRENT_BYTES_MATCH_EXTERNAL_SUMMARY_NOT_EXTERNAL_START_ANCHOR',source_verification_scope='DIRECT_PER_TASK_BYTES_ONCE_PLUS_LOCAL_FINAL_CHECK;BASE_FINAL;NO_TRANSITIVE_REAUDIT',**FLAGS)
    OUTPUT.mkdir(parents=True,exist_ok=False);out=save(OUTPUT/'independent_readback.json',report);guard(base);require(sha(Path(out['path']).read_bytes())==out['sha256'] and {p.name for p in OUTPUT.iterdir()}=={'independent_readback.json'},'Final report bytes and singleton namespace');return out

