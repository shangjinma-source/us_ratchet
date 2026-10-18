"""Independent display addition readback; no producer/core imports or economics replay."""
import argparse,hashlib,json,math,os
from collections import Counter
from copy import deepcopy
from fractions import Fraction
from datetime import date
from pathlib import Path
STORAGE=Path('D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714')
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=STORAGE/'dated_risk_chain_display_20261003_v1'
PROJECTION=STORAGE/'dated_path_risk_display_20261003_v1'
OUTPUT=STORAGE/'dated_risk_chain_display_independent_readback_20261003_v1'
BOUND={
 'index':(str(PARENT/'index.json'), '8e98d0350404ef814a9b90ae7bbbd4ec245afb6352310c8f57e10a8fe4cb416e'),
 'publication':(str(PARENT/'publication.json'), 'a7577afc9c3e6724fbac568804dc4fbe628cc42b346a208ebc0a45ca25bfc72a'),
 'producer':(str(ROOT/'scripts/ndx_dated_risk_chain_display_20261003.py'), '356f802e36a77938a5702e29b33a8697ce588bdd04746b85d663bf2eb8af4217'),
 'projection_index':(str(PROJECTION/'index.json'), '4fca462ffc0c45c2bc0fc248a37bfd6ea926b5b3c00d1f24b09984d652cda3f8'),
 'projection_publication':(str(PROJECTION/'publication.json'), 'fcebd238aa5d8351ac24c7cb26adf4320f714ca7217c6cb960477853b855b5be'),
 'projection_audit':(str(STORAGE/'dated_path_risk_display_independent_readback_20261003_v1/independent_readback.json'), '36a392c9a459140f7f5657aba5f373d33affb9956d947cf9c9eda6e7e58070fe'),
 'projection_reader':(str(ROOT/'scripts/ndx_dated_path_risk_display_independent_readback_20261003.py'), 'ebb843119024fb6a29808625be5e07f980e84a811e0f9c4f2f91b5bafa242913'),
 'projection_producer':(str(ROOT/'scripts/ndx_dated_path_risk_display_20261003.py'), '7f4395264f9e5d8715b7014d57c47f0ec3fbb928bf656677a5cabaf2280fd854'),
 'projection_core':(str(ROOT/'backtest/ndx_dated_path_risk_display_research.py'),'afb909618ba50ce22d9491587957e350b7f37675dd14be046f97a502f18a26b3'),
 'core':(str(ROOT/'backtest/ndx_saved_risk_chain_display_research.py'),'428a1b1f2d391dcc24694b02df9213ae08dc9e61459a47c229bf9d1ba90df9bc')}
FALSE=('economics_recomputed','risk_gate_recomputed','account_executed','fit_performed','audit_reexecuted','point_in_time_verified','promotion_allowed','future_independent_oos','formal_comparison_passed','winner_selected','cohort_statistics_computed','original_targets_changed','full_transitive_source_closure_reverified')
ROLES=('incumbent_integer','incumbent_continuous','STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')

def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def integer(v,n):require(type(v) is int and v==n,'Exact count')
def ratio(v):return dict(numerator=str(v.numerator),denominator=str(v.denominator))
def number(v):
    if type(v) is dict:
        require(set(v)=={'numerator','denominator'} and all(type(x) is str for x in v.values()) and int(v['denominator'])>0,'Rational literal')
        n=Fraction(int(v['numerator']),int(v['denominator']))
    else:
        require(type(v) in (str,int,float) and (type(v) is not float or math.isfinite(v)),'Saved literal not bool/nonfinite');n=Fraction(str(v))
    require(n>=0,'Nonnegative exposure');return n
def flags(d):
    for k in FALSE:require(d[k] is False,'Display-only authority '+k)
def loads(b):
    def pairs(xs):
        d={}
        for k,v in xs:require(k not in d,'Duplicate key');d[k]=v
        return d
    def bad(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=bad)

def inspect_group(saved,entries,defined=True):
    require(type(defined) is bool,'Denominator boolean')
    ids=[e['security_id'] for e in entries];require(len(ids)==len(set(ids)) and all(type(s) is str and s for s in ids),'Full unique original coordinates')
    labels=[];sums={};members={}
    for e in entries:
        label=e['risk_chain'];require(label is None or type(label) is str and bool(label),'Explicit label')
        if label not in sums:labels.append(label);sums[label]=Fraction();members[label]=[]
        sums[label]+=number(e['saved_value']);members[label].append(e)
    total=sum(sums.values(),Fraction());require(defined or total==0,'Undefined denominator must be zero')
    expected=[]
    for label in labels:
        expected.append(dict(risk_chain=label,unknown=label is None or label=='unclassified',members=members[label],saved_literal_sum=ratio(sums[label]),normalized_display_share=ratio(sums[label]/total) if defined and total else None))
    exact(saved,dict(rows=expected,security_count=len(ids),saved_literal_total=ratio(total),unknown_saved_literal_total=ratio(sum((v for k,v in sums.items() if k is None or k=='unclassified'),Fraction())),normalized_display_denominator=ratio(total) if defined and total else None,stock_denominator_defined=bool(defined and total)),'Independent complete chain sums, unknown and normalization')

def inspect_target(saved,evidence):
    exact(saved['source_evidence'],evidence,'Original target evidence not actual holdings')
    require(saved['role']=='ORIGINAL_UNNORMALIZED_TARGET_NOT_ENGINE_EFFECTIVE_OR_ACTUAL_HOLDING','Target role')
    entries=[dict(security_id=r['original_position']['security_id'],risk_chain=r['risk_chain'],saved_value=r['original_position']['target_weight'],original_evidence=r) for r in evidence['rows']]
    inspect_group(saved['aggregation'],entries)
    return {r['original_position']['security_id']:r['risk_chain'] for r in evidence['rows']}

def inspect_track(saved,source,labels,kind,calendar):
    if source['status']!='AVAILABLE':
        require(source['status'] in ('NOT_EXECUTED_NONPOSITIVE_TARGET','TECHNICAL_MISSING') and source['path'] is None,'Explicit unavailable integer')
        exact(source['calendar_slots'],[dict(session=s,value=None) for s in calendar],'Full missing slots')
        exact(saved,dict(status=source['status'],rows=None,calendar_slots=source['calendar_slots'],missing_evidence=source['missing_evidence']),'Unavailable not fabricated cash')
        return
    require(saved['status']=='AVAILABLE','Track availability');exact(saved['source_reference'],source['source_reference'],'Saved track source')
    require(len(saved['rows'])==len(source['path'])==len(calendar)==127,'127 full track rows')
    if kind=='integer':require(len(source['risk_rows'])==127,'127 saved risk rows')
    for i,(got,day) in enumerate(zip(saved['rows'],source['path'])):
        require(day['session']==calendar[i] and got['session']==calendar[i],'Track calendar');integer(got['source_row_index'],i)
        if kind=='integer':
            risk=source['risk_rows'][i];require(risk['session']==calendar[i],'Risk date');exact(risk['saved_risk'],day['risk'],'Saved original risk')
            require(risk['stock_denominator_status'] in ('POSITIVE_STOCK_ONLY','NO_POSITIVE_STOCK'),'Known saved denominator')
            defined=risk['stock_denominator_status']=='POSITIVE_STOCK_ONLY';require(type(day['shares']) is dict and all(type(q) is int and q>=0 for q in day['shares'].values()),'Saved integer shares')
            require(any(q>0 for q in day['shares'].values())==defined,'Positive stock status')
            weights=day['risk'].get('actual_weights',{});require({e['security_id'] for e in risk['security_exposures']}==set(weights),'All saved exposure coordinates')
            exact(risk['risk_chains'],day['risk_chains'],'Saved risk labels');exact(risk['risk_chain_observation_dates'],day['risk_chain_observation_dates'],'Saved label dates')
            entries=[]
            for e in risk['security_exposures']:
                sid=e['security_id'];exact(e['saved_stock_weight'],weights[sid],'Original stock weight literal');exact(e['risk_chain'],day['risk_chains'].get(sid),'Original label');exact(e['model_observation_date'],day['risk_chain_observation_dates'].get(sid),'Original observed date')
                entries.append(dict(security_id=sid,risk_chain=e['risk_chain'],saved_value=e['saved_stock_weight'],original_evidence=e))
            inspect_group(got['aggregation'],entries,defined)
            require(not defined or got['aggregation']['stock_denominator_defined'] is True,'Positive holdings require positive saved stock denominator')
            for key,value in dict(saved_risk=risk['saved_risk'],cash_usd_preserved=day['cash_usd'],total_value_usd_preserved=day['total_value_usd'],denominator_scope='SAVED_STOCK_ONLY_WEIGHTS_CASH_SEPARATE_NOT_ACCOUNT_WEIGHT').items():exact(got[key],value,'Saved integer evidence')
            cash=number(day['cash_usd']);total=number(day['total_value_usd']);require(total>0 and cash<=total,'Positive account denominator');exact(got['cash_fraction_display'],ratio(cash/total),'Cash displayed separately')
        else:
            require({e['security_id'] for e in day['security_rows']}==set(labels),'All contribution coordinates')
            entries=[dict(security_id=e['security_id'],risk_chain=labels[e['security_id']],saved_value=e['contribution_after_cost'],original_evidence=e) for e in day['security_rows']]
            inspect_group(got['aggregation'],entries)
            require(got['denominator_scope']=='SAVED_AFTER_COST_CONTRIBUTION_SUM_NOT_TARGET_WEIGHT_OR_CASH_ACCOUNT','Contribution denominator');exact(got['saved_path_role'],day.get('role'),'Path role')

def restore(row,shared):
    out=deepcopy(row);used=[]
    require(type(shared) is dict and len(shared)==4,'Four shared raw roles')
    for role in ROLES:
        container=out['tracks'] if role.startswith('incumbent') else out['nav_modes'];link=container[role]
        require(set(link)=={'shared_path_id','value_encoding_preserved'},'Exact shared link');key=link['shared_path_id'];item=shared[key]
        require(item['identity']['role']==role and key==sha(enc(item['identity'])),'Shared role identity')
        exact(item['identity']['source_reference'],item['payload']['source_reference'],'Shared actual pointer');container[role]=deepcopy(item['payload'])
        if link['value_encoding_preserved'] is not None:container[role]['value_encoding']=deepcopy(link['value_encoding_preserved'])
        used.append(key)
    require(set(used)==set(shared),'Exactly all shared payloads');return out

def inspect_row(got,row,shared,controls,verified_controls):
    original=restore(row,shared);calendar=original['calendar'];require(len(calendar)==127 and calendar==sorted(set(calendar)) and calendar[:2]==['2026-03-20','2026-03-23'] and calendar[-1]=='2026-09-21','127 fixed source dates')
    for day in calendar:require(type(day) is str and date.fromisoformat(day).isoformat()==day,'Canonical source date')
    require(original['schema']=='DATED_SAVED_PATH_RISK_DISPLAY_PROJECTION_V1' and original['evaluation_interval_previously_used_for_fitting'] is True,'Original projection role')
    for k in ('formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','economics_recomputed','risk_recomputed','weights_normalized','source_bytes_authenticated','account_executed','fit_performed','winner_selected','chain_totals_computed'):require(original[k] is False,'Original projection limitations')
    require(got['schema']=='SAVED_RISK_CHAIN_DISPLAY_AGGREGATES_V1' and got['numerical_task_id']==row['numerical_task_id'],'Saved aggregate task')
    exact(got['calendar'],calendar,'Same full calendar')
    for k in ('source_bytes_authenticated','economics_recomputed','risk_gate_recomputed','original_targets_changed','point_in_time_verified','promotion_allowed','future_independent_oos'):require(got[k] is False,'Pure authority')
    require(got['chain_display_addition_performed'] is True and got['evaluation_interval_previously_used_for_fitting'] is True,'Display-only consumed period')
    require(got['arithmetic']=='FRACTION_OF_SAVED_JSON_FLOAT_STR_OR_SAVED_RATIONAL_NOT_ORIGINAL_PRICE_PRECISION' and got['normalization_scope']=='ADDITIONAL_DISPLAY_SHARE_ONLY_RAW_SUMS_AND_TARGETS_UNCHANGED','Precision and role')
    for a,b in [('candidate_engine_normalization_evidence','candidate_normalization_evidence'),('input_references','input_references'),('limitations_preserved','input_limitations'),('original_provenance_and_missing','original_provenance_and_missing'),('original_task_summary_row','original_task_summary_row'),('preserved_evidence_sidecars','preserved_evidence_sidecars'),('projection_input_references','input_references')]:exact(got[a],original[b],'Full preserved evidence '+a)
    for role in ('candidate','incumbent'):
        labels=inspect_target(got['targets'][role],original['target_evidence'][role])
        for kind in ('integer','continuous'):
            name=role+'_'+kind;track=got['tracks'][name]
            if role=='incumbent':
                key=row['tracks'][name]['shared_path_id'];exact(track,dict(shared_aggregate_id=key),'One shared control link');item=controls[key]
                exact(item['identity'],shared[key]['identity'],'Shared aggregated identity')
                identity=sha(enc(dict(track={k:v for k,v in original['tracks'][name].items() if k!='value_encoding'},labels=labels)))
                if key in verified_controls:require(verified_controls[key]==identity,'Shared control evidence/labels invariant');continue
                inspect_track(item['aggregation'],original['tracks'][name],labels,kind,calendar);verified_controls[key]=identity
            else:inspect_track(track,original['tracks'][name],labels,kind,calendar)

def streamed_record(stream,location,digest,offset,count):
    line=stream.readline();require(line.endswith(b'\n'),'Complete JSONL line')
    exact(location,dict(record_index=count,byte_start=offset,byte_stop=offset+len(line),row_sha256=sha(line)),'Exact byte location')
    row=loads(line);require(enc(row)+b'\n'==line,'Canonical record');digest.update(line)
    return row,offset+len(line),count+1

def inspect_streams(original_stream,output_stream,parent,index,shared,controls):
    require(len(parent['task_index'])==len(index['task_index'])==1632,'Complete1632')
    strata=Counter();coverage=Counter();seen=set();verified={};dh=hashlib.sha256();oh=hashlib.sha256();do=oo=dc=oc=0
    for ordinal,(old,new) in enumerate(zip(parent['task_index'],index['task_index'])):
        integer(old['task_ordinal'],ordinal);integer(new['task_ordinal'],ordinal);tid=old['numerical_task_id'];require(tid not in seen,'Unique task');seen.add(tid)
        require(type(old['k']) is int and 4<=old['k']<=20,'Original cardinality');key=(old['k'],enc(old['weight_spec']).decode());strata[key]+=1
        exact({k:v for k,v in new.items() if k not in ('status','jsonl_record')},{k:v for k,v in old.items() if k not in ('status','jsonl_record')},'Original task index projection')
        if old['status']=='COMPARISON_NOT_SUPPLIED':require(new['status']=='COMPARISON_NOT_SUPPLIED' and old['jsonl_record'] is None and new['jsonl_record'] is None,'Missing preserved');continue
        require(old['status']=='AUDITED_SAVED_PATHS_PROJECTED' and new['status']=='SAVED_CHAIN_DISPLAY_ADDED','Only display addition')
        row,do,dc=streamed_record(original_stream,old['jsonl_record'],dh,do,dc);got,oo,oc=streamed_record(output_stream,new['jsonl_record'],oh,oo,oc)
        require(row['numerical_task_id']==got['numerical_task_id']==tid,'Original ordered task identity')
        for k in ('numerical_task_id','k','weight_spec'):exact(row['original_task_summary_row'][k],old[k],'Summary coordinate')
        exact(row['calendar'],parent['calendar'],'Original full index dates');inspect_row(got,row,shared,controls,verified);coverage[key]+=1
    require(original_stream.read(1)==output_stream.read(1)==b'','No extra records')
    require(len(strata)==51 and set(strata.values())=={32} and {k for k,s in strata}==set(range(4,21)),'51 strata32')
    specifications={s for k,s in strata};require(len(specifications)==3,'Three original specs')
    for document,h,offset,count in ((parent,dh,do,dc),(index,oh,oo,oc)):
        descriptor=document['task_jsonl_reference'];exact(descriptor['sha256'],h.hexdigest(),'Whole stream hash');integer(descriptor['byte_count'],offset);integer(descriptor['record_count'],count);integer(document['planned_task_count'],1632);integer(document['projected_task_count'],count);integer(document['not_supplied_task_count'],1632-count)
    exact(index['k_spec_coverage'],[dict(k=k,weight_spec=loads(s),planned_task_count=n,projected_task_count=coverage[(k,s)],not_supplied_task_count=n-coverage[(k,s)]) for (k,s),n in sorted(strata.items())],'All missing/present stratum counts')
    require(set(verified)==set(controls) and len(controls)==(2 if dc else 0),'Exactly two shared controls once')
    exact(index['calendar'],parent['calendar'],'Output same calendar');exact(index['full_new_cutoff_task_denominator'],parent['full_new_cutoff_task_denominator'],'Unchanged global denominator')
    return dict(planned_tasks=1632,projected_tasks=dc,not_supplied_tasks=1632-dc,k_spec_strata=51,shared_control_paths_verified_once=len(verified),original_jsonl_sha256=dh.hexdigest(),output_jsonl_sha256=oh.hexdigest(),economics_recomputed=False)
def ref(p,h):return dict(path=str(p),sha256=h)
def validref(r):require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'].strip()==r['path'] and bool(r['path']) and type(r['sha256']) is str and len(r['sha256'])==64 and set(r['sha256'])<=set('0123456789abcdef'),'Exact reference/pending pins')
def merge(s,p,h):require(p not in s or s[p]==h,'Source conflict');s[p]=h
def read(r,s):
    validref(r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed source hash');merge(s,r['path'],r['sha256']);return b
def guard(s):
    require(sha(SOURCE.read_bytes())==LOADED,'Loaded reader drift')
    for p,h in s.items():require(sha(Path(p).read_bytes())==h,'Source drift '+p)
def expected_producer_sources(refs,shared_ref,jsonl):
    mapping={'index':'projection_index','publication':'projection_publication','audit':'projection_audit','reader':'projection_reader','producer':'projection_producer','projection_core':'projection_core','core':'core'}
    bound={k:refs[v] for k,v in mapping.items()};sources={refs['producer']['path']:refs['producer']['sha256']}
    for r in bound.values():merge(sources,r['path'],r['sha256'])
    merge(sources,shared_ref['path'],shared_ref['sha256']);merge(sources,jsonl['path'],jsonl['sha256'])
    return bound,sources

def readback(*,execute=False):
    require(execute is True and not OUTPUT.exists(),'Explicit action/create-only')
    refs={k:ref(p,h) for k,(p,h) in BOUND.items()}
    for r in refs.values():validref(r)
    sources={str(SOURCE):LOADED};blobs={k:read(r,sources) for k,r in refs.items()};guard(sources)
    index,pub,parent,pp,pa=(loads(blobs[k]) for k in ('index','publication','projection_index','projection_publication','projection_audit'))
    require(index['schema']=='SOURCE_BOUND_DATED_CHAIN_DISPLAY_V1' and pub['schema']=='DATED_CHAIN_DISPLAY_PUBLICATION_V1' and pub['status']=='PUBLISHED_DISPLAY_ADDITION_NOT_RISK_REEVALUATION','Published chain display')
    require(parent['schema']=='SOURCE_BOUND_DATED_PATH_RISK_DISPLAY_V1' and pp['schema']=='DATED_PATH_RISK_DISPLAY_PUBLICATION_V1' and pp['status']=='PUBLISHED_SAVED_PATH_DISPLAY_ONLY','Published original display')
    require(pa['schema']=='DATED_PATH_RISK_DISPLAY_INDEPENDENT_READBACK_V1' and pa['status']=='PASS','External original audit')
    exact(pa['index_reference'],refs['projection_index'],'Original audited index');exact(pa['publication_reference'],refs['projection_publication'],'Original audited receipt');require(pa['reader_sha256']==refs['projection_reader']['sha256'],'Original independent reader')
    for role in ('projection_reader','projection_producer','projection_core','projection_index','projection_publication'):require(pa['source_hashes'].get(refs[role]['path'])==refs[role]['sha256'],'External audited source')
    for k in ('producer_called','projection_core_called','economics_recomputed','risk_recomputed','formal_comparison_passed','point_in_time_verified','promotion_allowed'):require(pa[k] is False,'Original audit scope')
    exact(pp['index_reference'],refs['projection_index'],'Parent receipt');exact(pp['source_hashes'],parent['source_hashes'],'Parent source claims')
    exact(pub['index_reference'],refs['index'],'Output receipt');flags(index);flags(pub)
    for k in ('formal_comparison_passed','point_in_time_verified','promotion_allowed','risk_recomputed','chain_totals_computed','weights_normalized','account_executed','fit_performed','winner_selected'):require(parent[k] is False and pp[k] is False,'Original projection scope')
    require({p.name for p in PARENT.iterdir()}=={'started.json','tasks.jsonl','shared_control_aggregates.json','index.json','publication.json'},'Complete chain namespace')
    require({p.name for p in PROJECTION.iterdir()}=={'started.json','tasks.jsonl','shared_paths.json','index.json','publication.json'},'Complete projection namespace')
    sr=parent['shared_paths_reference'];validref(sr);require(Path(sr['path'])==PROJECTION/'shared_paths.json','Original shared path');shared=loads(read(sr,sources));require(shared['schema']=='DATED_PATH_RISK_SHARED_PATHS_V1','Original shared schema')
    cr=index['shared_control_aggregates_reference'];validref(cr);require(Path(cr['path'])==PARENT/'shared_control_aggregates.json','Output shared path');controls=loads(read(cr,sources));require(controls['schema']=='DATED_CHAIN_SHARED_CONTROL_AGGREGATES_V1','Shared aggregates schema');flags(controls)
    ij=parent['task_jsonl_reference'];oj=index['task_jsonl_reference'];require(Path(ij['path'])==PROJECTION/'tasks.jsonl' and Path(oj['path'])==PARENT/'tasks.jsonl','Fixed streams')
    exact(pp['task_jsonl_reference'],ij,'Original stream receipt');exact(pp['shared_paths_reference'],sr,'Original shared receipt');exact(pub['task_jsonl_reference'],oj,'Output stream receipt');exact(pub['shared_control_aggregates_reference'],cr,'Output shared receipt')
    exact(pa['verified_jsonl_sha256'],ij['sha256'],'Previously audited stream hash');exact(pa['verified_jsonl_bytes'],ij['byte_count'],'Previously audited bytes')
    for k in ('planned_task_count','projected_task_count','not_supplied_task_count'):exact(pa[k],parent[k],'Original audit scope count')
    bound,expected=expected_producer_sources(refs,sr,ij);exact(index['input_references'],bound,'Producer fixed input roles');exact(index['source_hashes'],expected,'Independent exact producer closure');exact(pub['source_hashes'],expected,'Receipt exact closure')
    startbytes=(PARENT/'started.json').read_bytes();merge(sources,str(PARENT/'started.json'),sha(startbytes));started=loads(startbytes)
    require(started['schema']=='DATED_CHAIN_DISPLAY_STARTED_V1' and started['retry_allowed'] is False,'Source started contract');flags(started);exact(started['input_references'],bound,'Started fixed roles');exact(started['source_hashes'],{p:h for p,h in expected.items() if p!=ij['path']},'Started source closure before single stream consumption')
    exact(index['original_projection_index_reference'],refs['projection_index'],'Original parent pointer');exact(index['original_projection_source_hashes_preserved'],parent['source_hashes'],'Parent map retained not reaudited')
    for a,b in [('original_batch_failure_preserved','batch_failure_preserved'),('original_unresolved_task_ids','unresolved_task_ids'),('original_undispatched_task_ids','undispatched_task_ids')]:exact(index[a],parent[b],'Full original missing/failure evidence')
    require(index['chain_display_addition_performed'] is True and index['source_verification_scope']=='INPUT_JSONL_HASH_VERIFIED_ONCE_DURING_STREAM_OTHER_DIRECT_BYTES_RECHECKED_AT_PUBLICATION_NO_PARENT_AUDIT_REPLAY','Single pass source scope')
    OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        with Path(ij['path']).open('rb') as original,Path(oj['path']).open('rb') as output:
            detail=inspect_streams(original,output,parent,index,shared['shared_paths'],controls['aggregates'])
        # Each large stream authenticated exactly once. Direct metadata/code rechecked after processing.
        guard(sources);merge(sources,ij['path'],ij['sha256']);merge(sources,oj['path'],oj['sha256'])
        report=dict(schema='DATED_RISK_CHAIN_DISPLAY_INDEPENDENT_READBACK_V1',status='PASS',index_reference=refs['index'],publication_reference=refs['publication'],reader_sha256=LOADED,source_hashes=sources,detail=detail,started_reference_externally_anchored=False,source_verification_scope='BOTH_JSONL_STREAMS_FULL_HASH_ONCE_DURING_CONSUMPTION_OTHER_DIRECT_SOURCES_RECHECKED',producer_called=False,core_called=False,**dict.fromkeys(FALSE,False))
        b=enc(report);path=OUTPUT/'independent_readback.json'
        with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
        guard({p:h for p,h in sources.items() if p not in (ij['path'],oj['path'])});require(path.read_bytes()==b and {p.name for p in OUTPUT.iterdir()}=={'independent_readback.json'},'Final report/namespace')
        return ref(path,sha(b))
    except Exception as error:
        with (OUTPUT/'failure.json').open('xb') as f:f.write(enc(dict(status='FAILED_DO_NOT_CONSUME',error=str(error),retry_allowed=False)));f.flush();os.fsync(f.fileno())
        raise
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args();print(json.dumps(readback(execute=a.execute)))
