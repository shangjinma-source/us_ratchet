"""Bounded, deterministic issuer-cover and rank-stratified research positions.

No panel IO, fitting, scoring, or completed-result selection. SHA references are
caller assertions; a source-bound consumer must authenticate their bytes.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
from pathlib import Path
from backtest import ndx_issuer_shard_prepare_research as contracts

indexing=contracts.indexing
bounds=contracts.bounds
require=contracts.require
digest=contracts.digest
SCHEMA='BULK_BUDGETED_SEARCH_POSITIONS_V1'
ORDER='BULK_ISSUER_COVER_STRATIFIED_RANK_V1'
PARAMETERS=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,
    max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,
    minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
MAX_PROPOSALS=100000
MAX_POSITIONS=10000
HARD_SOURCES={str(Path(contracts.__file__).resolve()):'722f48952a6d0c8c878df76eedeb0b8ca3b1e3feeb77560598414890ae00a4ec',**contracts.HARD_SOURCES}
LOADED={str(Path(__file__).resolve()):hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),**contracts.LOADED,**bounds._LOADED}
PLAN_FALSE=('combination_enumeration_performed','task_inputs_materialized','fit_performed','old_fit_results_reused',
 'old_plan_build_called','panel_audit_repeated','execution_authorized','point_in_time_verified','promotion_allowed',
 'legal_training_input_admitted','full_transitive_source_closure_reverified','complete_ndx_eligible_pool_verified',
 'continuous_weight_space_exhausted','winner_selected','dual_benchmark_evaluation_performed','oos_evaluation_performed')


def exact(actual,expected,message):
    require(digest(actual)==digest(expected),message)


def validate_lazy_plan(lazy_plan):
    """Recheck semantic counts/intervals/certificates, never eager-build shards."""
    require(all(LOADED.get(path)==sha for path,sha in HARD_SOURCES.items()),'Loaded mathematical implementation differs')
    require(type(lazy_plan) is dict,'Lazy plan mapping required')
    plan=lazy_plan;unsigned=deepcopy(plan);saved=unsigned.pop('content_sha256',None)
    contracts.canonical_sha(saved);require(digest(unsigned)==saved,'Plan content hash differs')
    require(plan['schema']=='ISSUER_ALL_K_LAZY_INTERVAL_PLAN_V1','Lazy plan schema required')
    context=plan['context'];require(type(context) is dict,'Context mapping required')
    require(set(context)=={'plan_version','order_version','group_fingerprint','panel_reference','panel_audit_reference',
        'decision_cutoff','parameters','fitter_source_fingerprint','previous_target_weights','weight_specs','shard_size',
        'mathematical_source_fingerprint'},'Exact context contract required')
    require(context['plan_version']==plan['schema'] and context['order_version']==indexing.ORDER_VERSION,'Order/schema differs')
    require(plan['plan_id']==digest(context),'Plan identity differs')
    params=contracts.parameters_contract(context['parameters']);exact(params,PARAMETERS,'Original eight parameters differ')
    exact(contracts.previous_contract(context['previous_target_weights']),context['previous_target_weights'],'Prior differs')
    exact(context['weight_specs'],list(contracts.WEIGHT_SPECS),'Three unaliased specs required')
    sources=contracts.source_map(plan['fitter_source_hashes'])
    require(digest(sources)==context['fitter_source_fingerprint'],'Fitter source fingerprint differs')
    contracts.canonical_sha(context['mathematical_source_fingerprint'])
    panel=contracts.reference(context['panel_reference']);audit=contracts.reference(context['panel_audit_reference'])
    require(panel['path']!=audit['path'],'Independent panel audit required')
    cutoff=context['decision_cutoff'];require(type(cutoff) is str and date.fromisoformat(cutoff).isoformat()==cutoff,'Canonical cutoff')
    size=context['shard_size'];require(type(size) is int and 1<=size<=10000,'Exact shard size')
    groups=plan['canonical_groups'];require(type(groups) is list and 0<len(groups)<=256,'Bounded groups')
    require(all(type(row) is dict and set(row)=={'issuer_id','security_ids'} for row in groups),'Exact group fields')
    index=indexing.IssuerCombinationIndex([(row['issuer_id'],row['security_ids']) for row in groups])
    require(sum(map(len,index.security_groups))<=512,'Engineering security bound')
    exact(groups,[dict(issuer_id=issuer,security_ids=list(sids)) for issuer,sids in zip(index.issuer_ids,index.security_groups)],'Groups not canonical')
    require(context['group_fingerprint']==index.group_fingerprint,'Group fingerprint differs')
    cards=[];planned=excluded=shards=0
    risk={key:Fraction(str(params[key])) for key in bounds._RISK_KEYS}
    for k,total in index.counts_by_k().items():
        cert=bounds._necessary_bounds(k,risk);count=0 if cert else total;pages=(count+size-1)//size
        cards.append(dict(k=k,combination_count=total,necessary_bound_certificates=cert,
            status='NECESSARY_BOUND_EXCLUDED' if cert else 'PLANNED_NOT_ENUMERATED',
            planned_combination_count=count,planned_canonical_task_count=3*count,planned_shard_count=pages,
            first_global_shard_ordinal=shards,first_global_planned_combination_ordinal=planned,
            interval_rule=dict(start=0,stop=count,shard_size=size)))
        planned+=count;excluded+=total if cert else 0;shards+=pages
    exact(plan['cardinalities'],cards,'Cardinality count, certificate or offset differs')
    expected=dict(issuer_count=len(groups),security_count=sum(map(len,index.security_groups)),
        all_k_combination_count=planned+excluded,necessary_bound_excluded_combination_count=excluded,
        planned_combination_count=planned,planned_canonical_task_count=3*planned,
        completed_canonical_task_count=0,remaining_canonical_task_count=3*planned,planned_shard_count=shards,
        status='PLANNED_NOT_ENUMERATED',shard_descriptors_materialized=False,shard_page_limit=1000,
        integer_encoding='JSON_INTEGER_REQUIRE_ARBITRARY_PRECISION_PYTHON_INT_NOT_FLOAT_OR_JS_NUMBER',
        page_limit_is_not_search_budget_or_denominator_limit=True,all_three_specs_planned_without_alias_deduplication=True,
        anchor_alias_equivalence_verified=False,risk_feasibility_proven=False,**dict.fromkeys(PLAN_FALSE,False))
    for key,value in expected.items():exact(plan[key],value,'Plan field differs: '+key)
    conservative=dict(risk_tolerance=str(bounds._RISK_TOLERANCE),simplex_tolerance=str(bounds._SIMPLEX_TOLERANCE),
        rounding_margin_per_term=str(bounds._ROUNDING_MARGIN_PER_TERM),source_hashes=HARD_SOURCES)
    exact(plan['conservative_bound_contract'],conservative,'Conservative frozen bound sources differ')
    require(set(plan)==set(expected)|{'schema','plan_id','context','canonical_groups','cardinalities','fitter_source_hashes','conservative_bound_contract','content_sha256'},'Unexpected lazy plan fields')
    return index


def _coverage(index,k,seed,plan_id):
    permutation=sorted(range(len(index.issuer_ids)),key=lambda i:(digest([ORDER,seed,plan_id,k,index.issuer_ids[i]]),index.issuer_ids[i]))
    n=len(permutation);base=[]
    for start in range(0,n,k):
        members=sorted(permutation[(start+j)%n] for j in range(k))
        base.append(tuple(index.security_groups[i][0] for i in members))
    # Every alternative SID gets a variant of its issuer's first base block.
    for i,group in enumerate(index.security_groups):
        original=next(row for row in base if group[0] in row)
        for sid in group[1:]:base.append(tuple(sid if value==group[0] else value for value in original))
    unique=[];seen=set()
    for row in base:
        rank=index.rank(k,row)
        if rank not in seen:seen.add(rank);unique.append((rank,row))
    return unique


def plan_budgeted_positions(*,lazy_plan,seed_hex,combinations_per_k,max_proposals,existing_completed_reference):
    """Global proposal budget includes coverage attempts and rejected hash draws.

    Output positions are diagnostics only unless status is PLANNED_NOT_ATTEMPTED.
    Existing completion metadata is retained but never influences point choice.
    """
    index=validate_lazy_plan(lazy_plan);contracts.canonical_sha(seed_hex)
    reference=contracts.reference(existing_completed_reference)
    require(type(max_proposals) is int and 0<=max_proposals<=MAX_PROPOSALS,'Global bounded exact proposal budget')
    retained=[row['k'] for row in lazy_plan['cardinalities'] if row['planned_combination_count']]
    require(type(combinations_per_k) is dict and all(type(k) is int for k in combinations_per_k) and set(combinations_per_k)==set(retained),'Budgets must exactly cover retained k')
    covers={k:_coverage(index,k,seed_hex,lazy_plan['plan_id']) for k in retained}
    for k in retained:
        value=combinations_per_k[k]
        require(type(value) is int and len(covers[k])<=value<=index.count(k),'Budget must cover all SID and not exceed complete domain')
    require(sum(combinations_per_k.values())<=MAX_POSITIONS,'Position resource cap, not universe cap')
    positions=[];log=[];selected={k:set() for k in retained};strata=[]
    def accept(k,rank,kind,extra):
        if len(log)>=max_proposals:return False
        number=len(log);duplicate=rank in selected[k]
        log.append(dict(proposal_index=number,k=k,rank=rank,selection_kind=kind,outcome='DUPLICATE' if duplicate else 'ACCEPTED',**extra))
        if not duplicate:
            selected[k].add(rank);positions.append(dict(k=k,rank=rank,prefix_security_ids=list(index.unrank(k,rank)),selection_kind=kind,proposal_index=number))
        return True
    def draw(k,lo,hi,kind,ordinal,attempt):
        if len(log)>=max_proposals:return None
        width=hi-lo;bits=(width-1).bit_length();byte_count=max(1,(bits+7)//8)
        raw=b'';block=0
        while len(raw)<byte_count:
            raw+=hashlib.sha256(bytes.fromhex(digest([ORDER,seed_hex,lazy_plan['plan_id'],k,kind,ordinal,attempt,block]))).digest();block+=1
        value=int.from_bytes(raw[:byte_count],'big') & ((1<<bits)-1)
        if value>=width:
            log.append(dict(proposal_index=len(log),k=k,rank=None,selection_kind=kind,outcome='HASH_RANGE_REJECTED',interval_start=lo,interval_stop=hi,stratum_index=ordinal,draw_index=attempt))
        else:accept(k,lo+value,kind,dict(interval_start=lo,interval_stop=hi,stratum_index=ordinal,draw_index=attempt))
        return value if value<width else None
    for k in retained:
        for rank,_ in covers[k]:
            if not accept(k,rank,'SID_COVERAGE',{}):break
        if len(log)>=max_proposals:continue
        remainder=combinations_per_k[k]-len(covers[k]);total=index.count(k)
        for j in range(remainder):
            lo=j*total//remainder;hi=(j+1)*total//remainder
            strata.append(dict(k=k,stratum_index=j,start=lo,stop=hi))
            attempt=0
            while len(log)<max_proposals:
                if sum(lo<=rank<hi for rank in selected[k])==hi-lo:break
                before=len(selected[k]);draw(k,lo,hi,'STRATIFIED_RANK',j,attempt);attempt+=1
                if len(selected[k])>before:break
        attempt=0
        while len(selected[k])<combinations_per_k[k] and len(log)<max_proposals:
            draw(k,0,total,'STRATIFIED_REFILL',-1,attempt);attempt+=1
    complete=all(len(selected[k])==combinations_per_k[k] for k in retained)
    coverage=[]
    for card in lazy_plan['cardinalities']:
        k=card['k'];rows=[row for row in positions if row['k']==k]
        exposures={sid:0 for group in index.security_groups for sid in group}
        for row in rows:
            for sid in row['prefix_security_ids']:exposures[sid]+=1
        coverage.append(dict(k=k,combination_count=card['combination_count'],necessary_bound_certificates=deepcopy(card['necessary_bound_certificates']),
            requested_position_count=combinations_per_k.get(k,0),selected_position_count=len(rows),
            unselected_planned_combination_count=card['planned_combination_count']-len(rows),
            security_exposures=exposures,all_security_ids_covered=all(exposures.values()),
            issuer_exposures={issuer:sum(exposures[sid] for sid in group) for issuer,group in zip(index.issuer_ids,index.security_groups)}))
    result=dict(schema=SCHEMA,order_version=ORDER,status='PLANNED_NOT_ATTEMPTED' if complete else 'INCOMPLETE_POINT_SELECTION',
        materialization_allowed=complete,plan_content_sha256=lazy_plan['content_sha256'],plan_id=lazy_plan['plan_id'],seed_hex=seed_hex,
        combinations_per_k={str(k):combinations_per_k[k] for k in retained},max_proposals=max_proposals,proposal_budget_scope='GLOBAL_INCLUDING_HASH_REJECTION_AND_DUPLICATES',
        positions=positions,cardinality_coverage=coverage,strata=strata,proposal_log=log,proposal_count=len(log),
        requested_position_count=sum(combinations_per_k.values()),selected_position_count=len(positions),
        all_k_combination_count=lazy_plan['all_k_combination_count'],planned_combination_count=lazy_plan['planned_combination_count'],
        planned_canonical_task_count=lazy_plan['planned_canonical_task_count'],unselected_planned_combination_count=lazy_plan['planned_combination_count']-len(positions),
        existing_completed_reference=reference,existing_completion_used_to_change_selection=False,completed_task_count=0,
        source_bytes_authenticated=False,risk_feasibility_proven=False,uniform_combination_sampling_claimed=False,
        global_optimum_proven=False,**dict.fromkeys(PLAN_FALSE,False))
    result.update(combination_enumeration_performed=bool(positions),full_domain_enumeration_performed=False,
        enumerated_position_count=len(positions))
    result['content_sha256']=digest(result)
    return result
