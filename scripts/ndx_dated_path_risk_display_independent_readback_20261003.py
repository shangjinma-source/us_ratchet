"""Read saved display bytes and source copies; never run a projection or economics."""
import argparse,hashlib,json,os,re
from collections import Counter
from copy import deepcopy
from pathlib import Path
STORAGE=Path('D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714')
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=STORAGE/'dated_path_risk_display_20261003_v1'
OUTPUT=STORAGE/'dated_path_risk_display_independent_readback_20261003_v1'
INDEX_SHA='4fca462ffc0c45c2bc0fc248a37bfd6ea926b5b3c00d1f24b09984d652cda3f8';PUBLICATION_SHA='fcebd238aa5d8351ac24c7cb26adf4320f714ca7217c6cb960477853b855b5be';PRODUCER_SHA='7f4395264f9e5d8715b7014d57c47f0ec3fbb928bf656677a5cabaf2280fd854'
PRODUCER=ROOT/'scripts/ndx_dated_path_risk_display_20261003.py'
CORE=ROOT/'backtest/ndx_dated_path_risk_display_research.py';CORE_SHA='afb909618ba50ce22d9491587957e350b7f37675dd14be046f97a502f18a26b3'
FIRST='89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
SUMMARY=ROOT/'data/cache/research/dated_batch_summary_20261003_v1/summary.json';SUMMARY_SHA='406922de9ffc292417d4b495af30691833f5bb8c2b5b60449c010d5178acb378'
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
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
TRACKS=('candidate_integer','incumbent_integer','candidate_continuous','incumbent_continuous')
FALSE=('formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','risk_recomputed','chain_totals_computed','weights_normalized','account_executed','fit_performed','winner_selected')

def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def flags(v):require(all(v[k] is False for k in FALSE),'Unchanged conditional permissions')
def loads(b):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda s:(_ for _ in ()).throw(ValueError(s)))
def ref(p,h):return dict(path=str(p),sha256=h)
def merge(mapping,path,h):
    require(path not in mapping or mapping[path]==h,'Conflicting source identity');mapping[path]=h
def fixed_base():
    references={k:ref(ROOT/p,h) for k,(p,h) in BOUND.items()}
    base={str(PRODUCER):PRODUCER_SHA,str(CORE):CORE_SHA}
    for p,h in (*BOUND.values(),*READERS.values()):
        require(type(h) is str and re.fullmatch('[a-f0-9]{64}',h),'Pending fixed source/reader pin')
        merge(base,str(ROOT/p),h)
    return references,base
def check_reader(audit,role):
    p,h=READERS[role]
    require(audit['reader_sha256']==h and audit['source_hashes'].get(str(ROOT/p))==h,'Exact fixed audit reader')
def check_source_closure(claimed,base,item_refs):
    expected=dict(base)
    for r in item_refs:merge(expected,r['path'],r['sha256'])
    exact(claimed,expected,'Independently constructed complete direct source closure')
    return expected
def ptr(v,path):
    for part in path.split('/')[1:]:
        part=part.replace('~1','/').replace('~0','~');v=v[int(part)] if type(v) is list else v[part]
    return v

def inspect_row(row,shared,summary_row,comparison,inputs):
    """Check every displayed daily copy against saved source objects, no arithmetic."""
    tid=summary_row['numerical_task_id'];first=tid==FIRST;flags(row)
    require(row['source_bytes_authenticated'] is False,'Projection does not authenticate source bytes')
    require(row['economics_recomputed'] is False,'Projection does not recompute economics')
    require(row['scope']=='SAVED_PATH_AND_SECURITY_EXPOSURE_COPY_ONLY;LABELS_CONDITIONAL_NOT_OFFICIAL_PIT;NO_CHAIN_TOTAL_RECALCULATION','Exact projection scope')
    require(row['schema']=='DATED_SAVED_PATH_RISK_DISPLAY_PROJECTION_V1' and row['numerical_task_id']==tid,'Display task/schema')
    exact(row['original_task_summary_row'],summary_row,'Original summary row')
    c=comparison['comparison'];i=inputs['inputs'];calendar=c['calendar']
    require(len(calendar)==127 and calendar==sorted(set(calendar)) and calendar[:2]==['2026-03-20','2026-03-23'] and calendar[-1]=='2026-09-21','All fixed sessions')
    exact(row['calendar'],calendar,'Copied calendar');exact(i['calendar'],calendar,'Input calendar')
    require(row['evaluation_interval_previously_used_for_fitting'] is True,'Consumed historical interval')
    for k,key in [('original_provenance_and_missing','original_provenance_and_missing'),('preserved_evidence_sidecars','preserved_evidence_sidecars')]:exact(row[k],inputs[key],'All original evidence layers')
    exact(row['candidate_normalization_evidence'],i['candidate_engine_normalization_evidence'],'Original normalization evidence');exact(row['input_limitations'],i['limitations'],'Original limitations')
    require(set(row['tracks'])==set(TRACKS) and set(row['nav_modes'])==set(MODES),'All four tracks and two modes')
    used=set()
    claims={v['path']:v['sha256'] for v in row['input_references'].values()}
    def claim(value):
        require(value['path'] not in claims or claims[value['path']]==value['sha256'],'Path reference conflict')
        claims[value['path']]=value['sha256']
    def resolve(value,role):
        require(set(value)=={'shared_path_id','value_encoding_preserved'},'Shared task link')
        key=value['shared_path_id'];require(key in shared,'Shared object present');obj=shared[key]
        require(obj['identity']['role']==role and sha(enc(obj['identity']))==key,'Shared identity hash and role')
        exact(obj['identity']['source_reference'],obj['payload']['source_reference'],'Shared pointer identity');used.add(key)
        payload=deepcopy(obj['payload'])
        if value['value_encoding_preserved'] is not None:payload['value_encoding']=value['value_encoding_preserved']
        return payload
    for role in ('candidate','incumbent'):
        original=c['saved_paths_preserved'][role]['continuous_track'] if first else c['tracks'][role+'_continuous']['original_track_preserved']
        target=row['target_evidence'][role];labels=i[role]['risk_chains_by_decision'][calendar[0]]
        expected=[]
        for p in original['positions_preserved']:
            sid=p['security_id'];label=labels[sid]
            require(i[role]['original_ticker_by_security'][sid]==p['ticker'],'No engine alias as ticker')
            expected.append(dict(original_position=p,risk_chain=label,risk_chain_status='UNKNOWN' if label in (None,'unclassified') else 'SAVED_CONDITIONAL_LABEL',model_observation_date=calendar[0],observation_date_is_source_publication_date=False))
        exact(target,dict(rows=expected,original_schedule=i[role]['schedule'],label_mapping_preserved=labels,weights_changed=False,input_pointer='/inputs/'+role,source_reference=row['input_references']['inputs']),'Every original target and label')
    for name in TRACKS:
        integer=name.endswith('_integer');role=name.split('_')[0];track=c['tracks'][name]
        value=resolve(row['tracks'][name],name) if role=='incumbent' else row['tracks'][name]
        status='AVAILABLE' if first else track['status']
        if status!='AVAILABLE':
            exact(value,dict(status=status,source_reference=None,path=None,missing_evidence=track['missing_evidence'],calendar_slots=[dict(session=d,value=None) for d in calendar]),'Missing integer never fabricated')
            continue
        original=c['saved_paths_preserved'][role]['integer_account' if integer else 'continuous_track'] if first else track['original_account_preserved' if integer else 'original_track_preserved']
        path=original['daily' if integer else 'path'];require([r['session'] for r in path]==calendar,'Uncompressed saved path')
        expected_ref=deepcopy(track['source_reference']);expected_ref['json_pointer']=track['path_pointer'] if first else expected_ref['json_pointer']+('/daily' if integer else '/path')
        claim(expected_ref)
        risk=None
        if integer:
            risk=[]
            for day in path:
                exposures=[dict(security_id=s,ticker=i[role]['original_ticker_by_security'][s],saved_stock_weight=w,risk_chain=day['risk_chains'].get(s),model_observation_date=day['risk_chain_observation_dates'].get(s)) for s,w in day['risk'].get('actual_weights',{}).items()]
                risk.append(dict(session=day['session'],stock_denominator_status='POSITIVE_STOCK_ONLY' if any(q>0 for q in day['shares'].values()) else 'NO_POSITIVE_STOCK',saved_risk=day['risk'],security_exposures=exposures,risk_chains=day['risk_chains'],risk_chain_observation_dates=day['risk_chain_observation_dates']))
        expected=dict(status='AVAILABLE',source_reference=expected_ref,path=path,stored_values_exact=track['stored_values_exact'],saved_normalized_values_exact=track['metrics']['normalized_values_exact'],metrics=track['metrics'],value_encoding=track['value_encoding'],risk_rows=risk,decisions=original['decisions'] if integer else None,executions=original['executions'] if integer else None,continuous_security_contributions_preserved=not integer,missing_evidence=None)
        exact(value,expected,'Every stored daily value/risk/decision/execution copied')
    for mode in MODES:
        value=resolve(row['nav_modes'][mode],mode);original=c['nav_modes'][mode]
        expected_ref=deepcopy(original['source_reference']);expected_ref['json_pointer']=original['path_pointer']+'/observations' if first else expected_ref['json_pointer']+'/modes/'+mode+'/observations'
        claim(expected_ref)
        mode_value=original['original_mode' if first else 'original_mode_preserved']
        exact(value,dict(source_reference=expected_ref,observations=mode_value['observations'],metrics=original['metrics'],mode=mode),'All saved NAV/FX dates and values')
    exact(row['source_hash_claims'],claims,'Complete copied source claims')
    return used


def inspect_stream(stream,index,shared,summary,load_sources):
    """Verify byte ranges and source copies one task at a time; no whole JSONL load."""
    require(len(summary['rows'])==1632 and len(index['task_index'])==1632,'Complete original 1632 slots')
    require(set(shared)=={sha(enc(v['identity'])) for v in shared.values()},'Exact shared identity keys')
    require(len(shared)==4 and {v['identity']['role'] for v in shared.values()}=={'incumbent_integer','incumbent_continuous',*MODES},'Exactly four distinct shared roles')
    offset=0;number=0;digest=hashlib.sha256();used=set()
    for ordinal,(entry,original) in enumerate(zip(index['task_index'],summary['rows'])):
        exact(entry['task_ordinal'],ordinal,'Original task order index');require(entry['numerical_task_id']==original['numerical_task_id'],'Original task order ID')
        exact(entry['k'],original['k'],'Original k');exact(entry['weight_spec'],original['weight_spec'],'Original spec')
        if entry['status']=='COMPARISON_NOT_SUPPLIED':require(entry['jsonl_record'] is None,'Missing row has no fake record');continue
        require(entry['status']=='AUDITED_SAVED_PATHS_PROJECTED','Explicit task state')
        line=stream.readline();require(line.endswith(b'\n'),'Complete JSONL record');row=loads(line);require(enc(row)+b'\n'==line,'Canonical JSONL')
        exact(entry['jsonl_record'],dict(record_index=number,byte_start=offset,byte_stop=offset+len(line),row_sha256=sha(line)),'Exact byte index and digest')
        exact(entry['input_references'],row['input_references'],'Index provenance')
        exact(entry['candidate_integer_status'],row['tracks']['candidate_integer']['status'],'Integer availability')
        comparison,inputs=load_sources(row['numerical_task_id'],row['input_references'])
        used.update(inspect_row(row,shared,original,comparison,inputs));offset+=len(line);number+=1;digest.update(line)
    require(stream.read(1)==b'','No tail or extra task record')
    exact(index['projected_task_count'],number,'Projected denominator');exact(index['not_supplied_task_count'],1632-number,'Missing denominator');exact(index['planned_task_count'],1632,'Planned denominator')
    exact(index['full_new_cutoff_task_denominator'],summary['full_new_cutoff_task_denominator'],'Original full combinatorial denominator')
    r=index['task_jsonl_reference'];exact(r['byte_count'],offset,'Full byte count');exact(r['record_count'],number,'Full line count');require(r['sha256']==digest.hexdigest(),'Whole JSONL byte digest')
    require(used==set(shared),'No unused or omitted shared role')
    groups={}
    for entry in index['task_index']:groups.setdefault((entry['k'],enc(entry['weight_spec']).decode()),[]).append(entry)
    coverage=[]
    for (k,spec),rows in sorted(groups.items()):
        present=[e for e in rows if e['status']=='AUDITED_SAVED_PATHS_PROJECTED']
        coverage.append(dict(k=k,weight_spec=json.loads(spec),planned_task_count=len(rows),projected_task_count=len(present),not_supplied_task_count=len(rows)-len(present),candidate_integer_status_counts=dict(Counter(e['candidate_integer_status'] for e in present))))
    exact(index['k_spec_coverage'],coverage,'All k/spec denominators')
    return dict(planned_task_count=1632,projected_task_count=number,not_supplied_task_count=1632-number,shared_path_count=4,verified_jsonl_bytes=offset,verified_jsonl_sha256=digest.hexdigest())

def readback(*,execute=False):
    require(execute is True and type(execute) is bool and all(type(h) is str and re.fullmatch('[a-f0-9]{64}',h) for h in (INDEX_SHA,PUBLICATION_SHA,PRODUCER_SHA)),'Future external pins required')
    require(not OUTPUT.exists(),'Immutable independent namespace')
    require({p.name for p in PARENT.iterdir()}=={'started.json','tasks.jsonl','shared_paths.json','index.json','publication.json'},'Exact successful producer directory')
    fixed_refs,base=fixed_base();item_refs=[]
    sources={str(SOURCE):LOADED,**base}
    def read(r):
        require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and type(r['sha256']) is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Exact source reference')
        require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Source collision')
        blob=Path(r['path']).read_bytes();require(sha(blob)==r['sha256'],'Source bytes changed');sources[r['path']]=r['sha256'];return loads(blob)
    index_ref=ref(PARENT/'index.json',INDEX_SHA);pub_ref=ref(PARENT/'publication.json',PUBLICATION_SHA)
    index=read(index_ref);pub=read(pub_ref)
    require(index['schema']=='SOURCE_BOUND_DATED_PATH_RISK_DISPLAY_V1' and pub['schema']=='DATED_PATH_RISK_DISPLAY_PUBLICATION_V1' and pub['status']=='PUBLISHED_SAVED_PATH_DISPLAY_ONLY','Producer schemas/status')
    flags(index);flags(pub);exact(pub['index_reference'],index_ref,'Publication external index');exact(pub['source_hashes'],index['source_hashes'],'Producer direct closure')
    for obj in (index,pub):
        require(all(obj[k] is False for k in ('comparison_recomputed','audit_reexecuted','full_transitive_source_closure_reverified','cohort_statistics_computed')),'No replay or extra authority')
    require(index['source_hashes'][str(PRODUCER)]==PRODUCER_SHA and index['source_hashes'][str(CORE)]==CORE_SHA,'Frozen producer/core source claims')
    for path,h in base.items():require(sha(Path(path).read_bytes())==h,'Actual independently fixed base bytes')
    refs=index['input_references'];exact(refs,fixed_refs,'Exact six fixed input references')
    started_blob=(PARENT/'started.json').read_bytes();started=loads(started_blob)
    require(started['schema']=='DATED_PATH_RISK_DISPLAY_STARTED_V1','Started schema');flags(started)
    exact(started['input_references'],fixed_refs,'Started six fixed references');exact(started['source_hashes'],base,'Started exact base closure')
    summary=read(refs['task_summary']);batch=read(refs['batch']);audit=read(refs['batch_audit']);initial=read(refs['initial'])
    require(audit['schema']=='DATED_COMPARISON_BATCH_INDEPENDENT_READBACK_V1' and audit['status']=='PASS','Audited comparison batch');exact(audit['result_reference'],refs['batch'],'Batch audit parent')
    check_reader(audit,'batch')
    sa=read(refs['task_summary_audit']);sp=read(refs['task_summary_publication'])
    require(sa['schema']=='DATED_BATCH_SUMMARY_INDEPENDENT_READBACK_V1' and sa['status']=='PASS','Fixed summary audit')
    check_reader(sa,'task_summary');exact(sa['summary_reference'],refs['task_summary'],'Summary audit parent');exact(sa['publication_reference'],refs['task_summary_publication'],'Summary audit publication');exact(sp['summary_reference'],refs['task_summary'],'Summary published reference')
    exact(batch['initial_rows_preserved'],initial['rows'],'Original three comparisons')
    available={r['numerical_task_id']:{'comparison':r['comparison_reference'],'comparison_audit':r['independent_readback_reference']} for r in initial['rows']}
    require(len(available)==3,'Initial three distinct tasks')
    for r in batch['new_completed_rows']:
        tid=r['numerical_task_id'];require(tid not in available,'No repeated completed task');available[tid]={'comparison':r['stage_references']['comparison'],'comparison_audit':r['stage_references']['independent_readback']}
    ids=[r['numerical_task_id'] for r in summary['rows']];require(len(ids)==len(set(ids))==1632,'Original unique task denominator')
    require(set(available).issubset(ids),'No foreign completed ID')
    exact([e['numerical_task_id'] for e in index['task_index'] if e['status']=='AUDITED_SAVED_PATHS_PROJECTED'],[t for t in ids if t in available],'No audited comparison silently omitted')
    exact(index['batch_failure_preserved'],batch['failure'],'Failure preserved');exact(index['unresolved_task_ids'],batch['unresolved_task_ids'],'Unresolved preserved');exact(index['undispatched_task_ids'],batch['undispatched_task_ids'],'Undispatched preserved')
    shared_ref=index['shared_paths_reference'];exact(pub['shared_paths_reference'],shared_ref,'Shared external publication link');require(Path(shared_ref['path'])==PARENT/'shared_paths.json','Fixed shared path');shared=read(shared_ref)
    require(shared['schema']=='DATED_PATH_RISK_SHARED_PATHS_V1','Shared schema');flags(shared)
    jr=index['task_jsonl_reference'];exact(pub['task_jsonl_reference'],jr,'Published JSONL link');require(Path(jr['path'])==PARENT/'tasks.jsonl','Fixed JSONL path')
    def load_sources(tid,r):
        require(set(r)=={'comparison','comparison_audit','inputs','inputs_audit'},'All direct task sources')
        for role in ('comparison','comparison_audit'):exact(r[role],available[tid][role],'Original accepted comparison reference')
        c=read(r['comparison']);a=read(r['comparison_audit']);i=read(r['inputs']);ia=read(r['inputs_audit'])
        item_refs.extend(deepcopy(list(r.values())))
        require(a['status']=='PASS' and ia['status']=='PASS' and ia['schema']=='DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1','Accepted saved audits')
        expected='DATED_COMPARISON_INDEPENDENT_READBACK_V1' if tid==FIRST else 'DATED_PER_TASK_COMPARISON_INDEPENDENT_READBACK_V1'
        require(a['schema']==expected,'First/per-task audit explicit schema');exact(a['comparison_reference'],r['comparison'],'Comparison audit identity');exact(ia['inputs_reference'],r['inputs'],'Inputs audit identity')
        require(i['inputs']['original_task']['numerical_task_id']==tid,'Inputs original task')
        check_reader(a,'first_comparison' if tid==FIRST else 'comparison');check_reader(ia,'inputs')
        require(c['schema']==('SOURCE_BOUND_DATED_FIRST_ECONOMIC_COMPARISON_V1' if tid==FIRST else 'SOURCE_BOUND_DATED_PER_TASK_ECONOMIC_COMPARISON_V1'),'Comparison document schema')
        require(i['schema']=='DATED_ACCOUNT_INPUT_DOCUMENT_V1','Inputs schema')
        if tid!=FIRST:require(c['numerical_task_id']==a['numerical_task_id']==tid,'Comparison task ID')
        for obj in (c,a,c['comparison']):require(all(obj[k] is False for k in ('formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos')),'Saved comparison authority')
        require(all(i[k] is False for k in ('point_in_time_verified','promotion_allowed','future_independent_oos')),'Inputs authority')
        ip=read(ia['publication_reference']);cp=read(a['publication_reference'])
        item_refs.extend((deepcopy(ia['publication_reference']),deepcopy(a['publication_reference'])))
        exact(ip['inputs_reference'],r['inputs'],'Input receipt');exact(cp['comparison_reference'],r['comparison'],'Comparison receipt')
        extra=[]
        if tid!=FIRST:
            ar=c['input_references']['account_audit'];account_audit=read(ar);item_refs.append(deepcopy(ar))
            extra.append(ar)
            exact(account_audit,c['independent_audits_preserved']['account_audit'],'Original account audit bytes')
            exact(c['input_references']['inputs'],r['inputs'],'Comparison used same input')
            exact(c['independent_audits_preserved']['account_audit']['input_readback_reference'],r['inputs_audit'],'Original input audit provenance')
        else:
            require(r['inputs']['sha256']=='ac0201e24925dff189d25e4fb5f0a8c741d567c31060f2aa48e3e2232fd90409' and r['inputs_audit']['sha256']=='396b45c1eec5a3fa0f2441744d409c0642eb21d2f6719da33725360707e114a3','Original first input external anchors')
        # Recheck this item's consumed direct files before releasing large objects.
        for item in (*r.values(),ia['publication_reference'],a['publication_reference'],*extra):require(sha(Path(item['path']).read_bytes())==item['sha256'],'Per-item source drift')
        return c,i
    with (PARENT/'tasks.jsonl').open('rb') as stream:counts=inspect_stream(stream,index,shared['shared_paths'],summary,load_sources)
    check_source_closure(index['source_hashes'],base,item_refs)
    OUTPUT.mkdir(parents=True,exist_ok=False)
    def save(path,value):
        blob=enc(value)
        with path.open('xb') as out:out.write(blob);out.flush();os.fsync(out.fileno())
        require(path.read_bytes()==blob,'Report bytes');return ref(path,sha(blob))
    try:
        report=dict(schema='DATED_PATH_RISK_DISPLAY_INDEPENDENT_READBACK_V1',status='PASS',index_reference=index_ref,publication_reference=pub_ref,reader_sha256=LOADED,source_hashes=sources,**counts,
            producer_called=False,projection_core_called=False,economics_recomputed=False,risk_recomputed=False,formal_comparison_passed=False,point_in_time_verified=False,promotion_allowed=False,
            producer_started_externally_anchored=False,producer_started_sha256=sha(started_blob),
            verification_scope='JSONL_VERIFIED_ONCE_DURING_STREAM;DIRECT_ITEMS_RECHECKED_BEFORE_RELEASE;FIXED_BASE_SHARED_INDEX_PUBLICATION_RECHECKED_AT_END;NO_TRANSITIVE_REPLAY_OR_NUMERIC_RECALCULATION')
        out=save(OUTPUT/'independent_readback.json',report)
        for path,h in ((SOURCE,LOADED),(PRODUCER,PRODUCER_SHA),(CORE,CORE_SHA),(PARENT/'index.json',INDEX_SHA),(PARENT/'publication.json',PUBLICATION_SHA)):
            require(sha(path.read_bytes())==h,'Final base drift')
        for path,h in base.items():require(sha(Path(path).read_bytes())==h,'Final fixed base bytes')
        require(sha(Path(shared_ref['path']).read_bytes())==shared_ref['sha256'],'Final shared path bytes')
        require((PARENT/'started.json').read_bytes()==started_blob,'Final producer started bytes')
        require({p.name for p in OUTPUT.iterdir()}=={'independent_readback.json'},'Exact reader directory');return out
    except Exception as error:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(error),retry_allowed=False));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
