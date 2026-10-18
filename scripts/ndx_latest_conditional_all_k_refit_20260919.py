"""Exact conditional subset enumeration and one explicit first-decision refit."""
import argparse,copy,hashlib,itertools,json,math,sys
from collections import Counter
from fractions import Fraction
from pathlib import Path
from types import FunctionType
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_latest_conditional_panel_20260919 as panel_io
from backtest import ndx_latest_conditional_panel_research as panel_core
from backtest import ndx_membership_cardinality_plan_research as bounds
from backtest import ndx_dynamic_cutoff_refit_v2_research as fitter
from backtest import ndx_root_price_archive_contract_research as archive
from scripts.ndx_latest_conditional_channels_20260919 import exclusive_publish
SEARCH=ROOT/'data/cache/research/latest_conditional_input_readiness_20260919_v1/observed_inputs/search.yaml'
SEARCH_SHA='41c26814561224ea6e96113092595f116bdec5845359188dbbd94b9f9b7b0b4c'
PANEL_AUDIT=ROOT/'data/cache/research/latest_conditional_panel_20260919_v1/independent_readback.json'
PANEL_AUDIT_SHA='fe2742de54d20602045a55a80b196c0961b40af846993c7a471c66b318373a2e'
PARAMETERS=('fit_days','shrinkage_intensity','turnover_anchor_strength','max_single_weight','min_single_weight','top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap')
FALSE=('point_in_time_verified','promotion_allowed','execution_authorized','legal_training_input_admitted','dual_benchmark_evaluation_performed','whole_lot_execution_performed','oos_evaluation_performed','winner_selected','global_optimum_proven','strict_loader_validation_passed')
LOADED={str(Path(m.__file__).resolve()):hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (panel_io,panel_core,bounds,fitter,archive)}
for path in (Path(__file__).resolve(),Path(exclusive_publish.__code__.co_filename).resolve()):LOADED[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
archive.merge(LOADED,bounds._LOADED)
def digest(v):return panel_core.canonical_sha(v)
def read(path,sha,sources):
    path=Path(path).resolve();raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External source SHA differs')
    archive.merge(sources,{str(path):sha});return json.loads(raw)
def verify_sources(sources):
    for p,h in LOADED.items():
        if sources.get(p)!=h:raise ValueError('Loaded source omitted')
    return archive.verify_expected_sources(sources,archive.load_contract())

def declared_partition(expected,contract):
    """Derive metadata only; caller must separately verify the entire source set."""
    live=dict(contract['authority_source_hashes']);resolved=[];gaps=[]
    for p,h in expected.items():
        row=contract['rows'].get(p)
        if row is None:archive.merge(live,{p:h});continue
        if h!=row['expected_historical_sha256']:raise ValueError('Archive historical expectation differs')
        evidence=dict(original_path=p,expected_historical_sha256=h,archived_path=row['archived_path'],archived_sha256=row['archived_sha256'],original_live_path_verified=False)
        if row['historical_expected_bytes_preserved']:resolved.append(dict(evidence,historical_bytes_exact=True))
        else:gaps.append(dict(evidence,historical_bytes_recovered=False,role='SEALED_CURRENT_OBSERVATION_NOT_HISTORICAL_BYTES'))
    return dict(live_verified_source_hashes=live,archive_resolutions=resolved,historical_gap_observations=gaps,historical_full_source_closure_recovered=False,point_in_time_verified=False,promotion_allowed=False)

def enumerate_plan(panel,parameters,exact_limit):
    """Pure mathematics over an explicit conditional panel, not a member certificate."""
    if set(parameters)!=set(PARAMETERS) or type(parameters['fit_days']) is not int or parameters['fit_days']!=126:raise ValueError('Original eight explicit parameters required')
    if any(type(v) not in (float,int) or not math.isfinite(v) for v in parameters.values()):raise ValueError('Finite nonboolean parameters required')
    if any(not 0<=v<=1 for k,v in parameters.items() if k!='fit_days') or parameters['max_single_weight']<=0 or parameters['risk_chain_top1_cap']<=0 or parameters['min_single_weight']>parameters['max_single_weight']:raise ValueError('Original valid risk/shrinkage envelope required')
    if type(exact_limit) is not int or exact_limit<1:raise ValueError('Explicit positive exact limit required')
    rows=panel['universe'].to_dict('records');ids=sorted(r['security_id'] for r in rows)
    if not ids:raise ValueError('Nonempty conditional subset required')
    for sid in ids:panel_core.selected_mapping(panel,[sid])
    issuer={r['security_id']:r['issuer_id'] for r in rows};n=len(set(issuer.values()))
    risk={k:Fraction(str(parameters[k])) for k in bounds._RISK_KEYS}
    counts=bounds.combinatorics.issuer_dedup_combination_counts(list(Counter(issuer.values()).values()))
    cards=[];tasks=[];aliases=[];preference=None
    for k in range(1,n+1):
        certificates=bounds._necessary_bounds(k,risk)
        count=int(counts[k])
        cards.append(dict(k=k,issuer_unique_combinations=count,necessary_infeasibility_certificates=certificates,
            status='NO_SEARCH_NECESSARY_BOUND_PROOF' if certificates else 'NOT_PROVEN_FEASIBLE',evaluated=False))
        if certificates:continue
        if count>exact_limit:raise ValueError('Exact budget exceeded; this version never substitutes bounded search')
        groups=[[s for s in ids if issuer[s]==iid] for iid in sorted(set(issuer.values()))]
        for group_subset in itertools.combinations(groups,k):
          for combination in itertools.product(*group_subset):
            selected_ids=sorted(combination)
            selected=panel_core.selected_mapping(panel,selected_ids)
            canonical=None
            for spec in ('equal_weight','constrained_fixed_shrinkage'):
                task=dict(selected=selected,holding_count=k,weight_spec=spec,cutoff=panel['cutoff'],parameters=parameters,previous_target_weights=None)
                task=dict(task,task_id=digest(task));tasks.append(task)
                if spec=='constrained_fixed_shrinkage':canonical=task['task_id']
                if spec=='equal_weight' and {r['ticker'] for r in selected.values()}=={'AMAT','AVGO','CDNS','GOOG'}:preference=task['task_id']
            alias=dict(selected=selected,weight_spec='constrained_fixed_shrinkage_turnover_anchor',canonical_task_id=canonical,
                status='PENDING_REAL_PROBE_EQUIVALENCE_NOT_EVALUATED',numerical_equivalence_verified=False,effective_anchor_strength_expected=0,actual_fitter_called=False)
            aliases.append(dict(alias,alias_id=digest(alias)))
    return dict(cardinalities=cards,canonical_tasks=sorted(tasks,key=lambda x:x['task_id']),anchor_aliases=aliases,
        complete_issuer_unique_combinations=sum(r['issuer_unique_combinations'] for r in cards),
        canonical_task_count=len(tasks),alias_count=len(aliases),input_security_count=len(ids),input_issuer_count=n,
        user_preference_reference_task_id=preference,user_preference_status='REFERENCE_NOT_FIXED_ANSWER' if preference else 'UNAVAILABLE_EXPLICITLY_REPORTED',
        exact_enumeration_limit=exact_limit,all_input_k_reported=True,continuous_weight_space_exhausted=False)

def validate_panel_audit(audit,panel_reference,panel):
    if audit['schema']!='LATEST_CONDITIONAL_PANEL_INDEPENDENT_READBACK_V1' or digest(audit['panel_reference'])!=digest(panel_reference):raise ValueError('Independent panel audit reference differs')
    if any(audit.get(k) is not False for k in ('raw_oracle_repeated','producer_assemble_called','fitter_called','point_in_time_verified','legal_training_input_admitted','promotion_allowed')):raise ValueError('Independent panel audit boundaries differ')
    d=audit['details'];n=len(panel['universe'])
    expected=dict(observed_rows=101,numeric_channels=96,conditional_securities=n,returns_cells=126*n,nominal_close_cells=127*n,volume_cells=63*n,dollar_volume_cells=63*n)
    if any(type(d.get(k)) is not int or d[k]!=v for k,v in expected.items()):raise ValueError('Independent panel audit denominator differs')
    for key in ('all_four_numeric_frames_reconstructed','universe_and_all_101_gap_rows_reconstructed','rangeindex_and_panel_checksum_verified','distinct_dates_and_original_facts_verified'):
        if d.get(key) is not True:raise ValueError('Complete independent panel audit required')

def prepare(panel_path,panel_sha256,audit_path,audit_sha256):
    if Path(audit_path).resolve()!=PANEL_AUDIT or audit_sha256!=PANEL_AUDIT_SHA:raise ValueError('This version requires the sealed independently published panel audit')
    sources=dict(LOADED);document=read(panel_path,panel_sha256,sources);panel_io.verify(document)
    archive.merge(sources,document['historical_expected_source_hashes']);panel=panel_io.typed_decode(document['panel'])
    audit=read(audit_path,audit_sha256,sources);validate_panel_audit(audit,dict(path=str(Path(panel_path).resolve()),sha256=panel_sha256),panel)
    archive.merge(sources,audit['historical_expected_source_hashes'])
    if archive.verify_expected_sources(audit['historical_expected_source_hashes'],archive.load_contract())!=audit['archive_resolution']:raise ValueError('Independent audit source partition differs')
    raw=SEARCH.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SEARCH_SHA:raise ValueError('Immutable observed search contract differs')
    archive.merge(sources,{str(SEARCH):SEARCH_SHA});archive.merge(sources,fitter._sources())
    search=yaml.safe_load(raw)['search_contract'];parameters={k:search[k] for k in PARAMETERS}
    scope=enumerate_plan(panel,parameters,search['exact_enumeration_max_feasible_combinations'])
    partition=verify_sources(sources)
    return dict(schema='LATEST_CONDITIONAL_ALL_K_REFIT_PLAN_V1',panel_reference=dict(path=str(Path(panel_path).resolve()),sha256=panel_sha256),
        independent_panel_audit_reference=dict(path=str(Path(audit_path).resolve()),sha256=audit_sha256),
        cutoff=panel['cutoff'],policy='FIRST_DECISION_NO_PRIOR_TARGET_DIAGNOSTIC',scope=panel_core.SCOPE,
        observed_security_count=101,observed_issuer_count=100,complete_observed_provenance_and_missing=panel['observed_provenance_and_missing'],
        **scope,historical_expected_source_hashes=sources,archive_resolution=partition,**dict.fromkeys(FALSE,False))

def check_result(result,task,panel):
    selected=task['selected'];parameters=task['parameters'];sids=sorted(selected);tickers=[selected[s]['ticker'] for s in sids]
    if (result['schema']!='ndx_dynamic_cutoff_refit_research_v2' or result['cutoff']!=task['cutoff'] or result['weight_spec']!=task['weight_spec']
        or type(result['fit_row_count']) is not int or result['fit_row_count']!=126
        or type(result['effective_anchor_strength']) not in (int,float) or result['effective_anchor_strength']!=0):raise ValueError('Original first-decision fitter contract differs')
    if any(result.get(k) is not False for k in ('checkpoint_weights_used','point_in_time_verified','source_authenticity_verified','promotion_allowed','historical_task_evaluation_performed','order_generation_allowed')):raise ValueError('Original result scope upgraded')
    frame=panel['returns'][tickers].iloc[-126:]
    payload=dict(dates=[d.date().isoformat() for d in frame.index],tickers=tickers,returns=frame.to_numpy().tolist())
    if result['fit_data_sha256']!=digest(payload) or result['fit_start']!=payload['dates'][0] or result['fit_end']!=task['cutoff']:raise ValueError('Actual fit matrix differs')
    if digest(result['declared_parameters'])!=digest({k:float(v) for k,v in parameters.items() if k!='fit_days'}) or type(result['previous_target_weights']) is not dict or result['previous_target_weights']!={} or type(result['surviving_anchor_mass']) not in (int,float) or result['surviving_anchor_mass']!=0:raise ValueError('Original parameters/first anchor differs')
    anchors=result['anchor_by_security']
    if type(anchors) is not dict or set(anchors)!=set(sids) or any(type(v) not in (int,float) or v!=0 for v in anchors.values()) or result['risk_chains_by_security']!={s:selected[s]['risk_chain'] for s in sids}:raise ValueError('Anchor/risk identities differ')
    if set(result['targets'])!=set(sids):raise ValueError('Target denominator differs')
    weights=[];chains={}
    for sid in sids:
        row=result['targets'][sid];v=row['target_weight']
        if row['ticker']!=selected[sid]['ticker'] or row['issuer_id']!=selected[sid]['issuer_id'] or type(v) not in (float,int) or not math.isfinite(v) or v<0:raise ValueError('Finite exact target identity required')
        weights.append(v);chain=selected[sid]['risk_chain'];chains[chain]=chains.get(chain,0.)+v
    if not math.isclose(sum(weights),1.,abs_tol=1e-9,rel_tol=0):raise ValueError('Target simplex differs')
    ordered=sorted(weights,reverse=True)
    checks=dict(MAX_SINGLE_WEIGHT=ordered[0]<=parameters['max_single_weight']+1e-9,
        MIN_SINGLE_WEIGHT=ordered[-1]>=parameters['min_single_weight']-1e-9,
        SECURITY_TOP3_WEIGHT=sum(ordered[:3])<=parameters['top_weight_cap']+1e-9,
        MINIMUM_EFFECTIVE_N=1/sum(v*v for v in weights)>=len(weights)*parameters['minimum_effective_n_ratio']-1e-9,
        RISK_CHAIN_TOP1_WEIGHT=max(chains.values())<=parameters['risk_chain_top1_cap']+1e-9)
    if digest(checks)!=digest(result['declared_constraint_checks']):raise ValueError('Original five risks differ from targets')
    if result['declared_constraints_passed'] is not all(checks.values()):raise ValueError('Combined original risk verdict differs')

def run_one(plan_path,plan_sha256,task_id,output):
    output=Path(output).resolve();started=Path(str(output)+'.started.json');failure=Path(str(output)+'.failure.json')
    if any(p.exists() for p in (output,started,failure)):raise ValueError('Existing attempt/result refuses automatic refit')
    sources=dict(LOADED);plan=read(plan_path,plan_sha256,sources);ref=plan['panel_reference']
    audit=plan['independent_panel_audit_reference']
    if digest(plan)!=digest(prepare(ref['path'],ref['sha256'],audit['path'],audit['sha256'])):raise ValueError('Complete plan must reproduce from hard panel')
    task,=[t for t in plan['canonical_tasks'] if t['task_id']==task_id]
    archive.merge(sources,plan['historical_expected_source_hashes'])
    document=read(ref['path'],ref['sha256'],sources);panel=panel_io.typed_decode(document['panel'])
    selected=panel_core.selected_mapping(panel,list(task['selected']))
    if digest(selected)!=digest(task['selected']):raise ValueError('Explicit selected coordinate differs')
    verify_sources(sources)
    marker=exclusive_publish(started,dict(schema='LATEST_ALL_K_SINGLE_ATTEMPT_V1',plan_sha256=plan_sha256,task_id=task_id,attempt_count=1))
    archive.merge(sources,{marker['path']:marker['sha256']})
    try:
        result=fitter.refit_dynamic_cutoff_weights(returns=panel['returns'],cutoff=task['cutoff'],selected=selected,
            weight_spec=task['weight_spec'],previous_target_weights=None,**task['parameters'])
        # Original result is retained, including projection relaxation and failed risks.
        if result['schema']!='ndx_dynamic_cutoff_refit_research_v2' or result['cutoff']!=task['cutoff'] or result['weight_spec']!=task['weight_spec'] or result['fit_row_count']!=126 or result['effective_anchor_strength']!=0:raise ValueError('Original first-decision fitter contract differs')
        checks=result['declared_constraint_checks']
        if len(checks)!=5 or any(type(v) is not bool for v in checks.values()) or result['declared_constraints_passed'] is not all(checks.values()):raise ValueError('Original risk diagnostics malformed')
        check_result(result,task,panel)
        if digest(result['source_hashes'])!=digest(fitter._sources()):raise ValueError('Complete original numerical source closure differs')
        archive.merge(sources,result['source_hashes'])
        value=dict(schema='LATEST_CONDITIONAL_ALL_K_SINGLE_REFIT_V1',plan_reference=dict(path=str(Path(plan_path).resolve()),sha256=plan_sha256),task=task,
            status='FITTED_ORIGINAL_FIVE_RISKS_PASSED' if all(checks.values()) else 'FITTED_ORIGINAL_FIVE_RISKS_FAILED',result=result,attempt_count=1,
            historical_expected_source_hashes=sources,archive_resolution=verify_sources(sources),**dict.fromkeys(FALSE,False))
        saved=exclusive_publish(output,value);verify_sources(sources);return saved
    except BaseException as exc:
        # Never turn source drift or a solver exception into an economic infeasibility certificate.
        if not output.exists() and not failure.exists():exclusive_publish(failure,dict(schema='LATEST_ALL_K_FAILED_ATTEMPT_V1',plan_sha256=plan_sha256,task_id=task_id,error_type=type(exc).__name__,attempt_count=1,partial_result=None,automatic_retry_allowed=False))
        raise
    finally:verify_sources(sources)

def bounded_index(plan_reference,folder,entries,total):
    return dict(schema='LATEST_ALL_K_BOUNDED_INDEX_V1',plan_reference=plan_reference,output_directory=str(folder),planned=total,
        completed=len(entries),status='COMPLETE' if len(entries)==total else 'PARTIAL',entries=entries,**dict.fromkeys(FALSE,False))

def run_bounded(plan_path,plan_sha256,folder,*,max_new,index_path=None,index_sha256=None):
    """One verified private snapshot, no global rebinding, at most 100 new fits."""
    if type(max_new) is not int or not 0<=max_new<=100:raise ValueError('Explicit integer budget 0..100 required')
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    sources=dict(LOADED);plan=read(plan_path,plan_sha256,sources);ref=plan['panel_reference'];audit=plan['independent_panel_audit_reference']
    rebuilt=prepare(ref['path'],ref['sha256'],audit['path'],audit['sha256'])
    if digest(rebuilt)!=digest(plan):raise ValueError('Exact complete plan required')
    archive.merge(sources,plan['historical_expected_source_hashes']);document=read(ref['path'],ref['sha256'],sources)
    panel=panel_io.typed_decode(document['panel']);tasks=plan['canonical_tasks'];total=len(tasks)
    plan_reference=dict(path=str(Path(plan_path).resolve()),sha256=plan_sha256);entries=[]
    if (index_path is None)!=(index_sha256 is None):raise ValueError('External index path/SHA pair required')
    if index_path is not None:
        index=read(index_path,index_sha256,sources);entries=index['entries']
        if digest(index)!=digest(bounded_index(plan_reference,folder,entries,total)):raise ValueError('Recovery index schema/status/count differs')
    if len(entries)>total or [e['task_id'] for e in entries]!=[t['task_id'] for t in tasks[:len(entries)]]:raise ValueError('Completed canonical prefix required')
    allowed={e['task_id']+suffix for e in entries for suffix in ('.json','.json.started.json')}
    for path in folder.glob('*.json'):
        if path.name not in allowed and not path.name.startswith('index_'):raise ValueError('Unindexed started/result/failure refuses any new fitting')
    contract=archive.load_contract();fitter_sources=fitter._sources()
    for e,t in zip(entries,tasks):
        path=folder/(t['task_id']+'.json')
        if e['path']!=str(path):raise ValueError('Indexed result address differs')
        value=read(path,e['sha256'],sources);marker=read(str(path)+'.started.json',e['started_sha256'],sources)
        if digest(marker)!=digest(dict(schema='LATEST_ALL_K_SINGLE_ATTEMPT_V1',plan_sha256=plan_sha256,task_id=t['task_id'],attempt_count=1)):raise ValueError('Original attempt differs')
        if (value['schema']!='LATEST_CONDITIONAL_ALL_K_SINGLE_REFIT_V1' or digest(value['task'])!=digest(t) or digest(value['plan_reference'])!=digest(plan_reference)
            or type(value['attempt_count']) is not int or value['attempt_count']!=1 or any(value.get(k) is not False for k in FALSE)):raise ValueError('Saved result identity/scope differs')
        check_result(value['result'],t,panel)
        if digest(value['result']['source_hashes'])!=digest(fitter_sources):raise ValueError('Saved numerical closure differs')
        passed=value['result']['declared_constraints_passed']
        if type(passed) is not bool or value['status']!=('FITTED_ORIGINAL_FIVE_RISKS_PASSED' if passed else 'FITTED_ORIGINAL_FIVE_RISKS_FAILED'):raise ValueError('Saved result status differs')
        required=dict(plan['historical_expected_source_hashes']);archive.merge(required,{plan_reference['path']:plan_sha256,str(Path(str(path)+'.started.json')):e['started_sha256']})
        if any(value['historical_expected_source_hashes'].get(p)!=h for p,h in required.items()):raise ValueError('Saved complete source closure omitted')
        if digest(value['archive_resolution'])!=digest(declared_partition(value['historical_expected_source_hashes'],contract)):raise ValueError('Saved archive partition metadata differs')
        archive.merge(sources,value['historical_expected_source_hashes'])
    partition=verify_sources(sources);memory=digest(panel_io.typed_encode(panel));plan_digest=digest(plan)
    numerical={p:h for p,h in sources.items() if Path(p).suffix=='.py'}
    def small_verify(actual):
        if memory!=digest(panel_io.typed_encode(panel)) or plan_digest!=digest(plan):raise ValueError('Private snapshot changed')
        for p,h in actual.items():
            if p not in sources and p not in numerical:
                # Only the current exclusive attempt may be newly introduced by run_one.
                if Path(p).parent!=folder or not p.endswith('.started.json'):raise ValueError('Unexpected task dependency')
            if p in numerical or p not in sources or p in (str(SEARCH),plan_reference['path'],ref['path'],audit['path']):
                if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise ValueError('Task source changed')
        return declared_partition(actual,contract)
    def cached_prepare(*args):
        if args!=(ref['path'],ref['sha256'],audit['path'],audit['sha256']):raise ValueError('Private snapshot coordinate differs')
        return plan
    private=FunctionType(run_one.__code__,dict(run_one.__globals__,prepare=cached_prepare,verify_sources=small_verify),run_one.__name__,run_one.__defaults__,run_one.__closure__)
    pending=tasks[len(entries):len(entries)+max_new]
    try:
        for position,task in enumerate(pending):
            path=folder/(task['task_id']+'.json');saved=private(plan_reference['path'],plan_sha256,task['task_id'],path)
            marker=Path(str(path)+'.started.json');marker_sha=hashlib.sha256(marker.read_bytes()).hexdigest()
            entries.append(dict(task_id=task['task_id'],**saved,started_sha256=marker_sha));archive.merge(sources,{saved['path']:saved['sha256'],str(marker):marker_sha})
            # PARTIAL checkpoints enable recovery; the bounded final index requires full closure.
            index=bounded_index(plan_reference,folder,entries,total)
            if position==len(pending)-1:verify_sources(sources)
            published=exclusive_publish(folder/('index_'+digest(index)+'.json'),index);print(json.dumps(published),flush=True)
    finally:verify_sources(sources)
    return bounded_index(plan_reference,folder,entries,total)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--panel');p.add_argument('--panel-sha');p.add_argument('--audit');p.add_argument('--audit-sha');p.add_argument('--plan',required=True);p.add_argument('--execute',action='store_true');p.add_argument('--plan-sha');p.add_argument('--task-id');p.add_argument('--output');p.add_argument('--folder');p.add_argument('--max-new',type=int,default=0);p.add_argument('--index');p.add_argument('--index-sha');a=p.parse_args()
    if a.execute:
        if a.folder:
            if not a.plan_sha:p.error('Bounded execution requires external plan SHA')
            print(json.dumps(run_bounded(a.plan,a.plan_sha,a.folder,max_new=a.max_new,index_path=a.index,index_sha256=a.index_sha)))
        else:
            if not all((a.plan_sha,a.task_id,a.output)):p.error('Explicit plan SHA, task ID and output required')
            print(json.dumps(run_one(a.plan,a.plan_sha,a.task_id,a.output)))
    else:
        if not all((a.panel,a.panel_sha,a.audit,a.audit_sha)):p.error('Prepare requires external panel and independent audit paths/SHA')
        value=prepare(a.panel,a.panel_sha,a.audit,a.audit_sha);saved=exclusive_publish(a.plan,value);verify_sources(value['historical_expected_source_hashes']);print(json.dumps(saved))
