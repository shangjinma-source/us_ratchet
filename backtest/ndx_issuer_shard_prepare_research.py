"""Pure counts-only issuer shard plan; no combinations, matrix reads, or fits."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
from backtest import ndx_issuer_combination_index_research as indexing
from backtest import ndx_membership_cardinality_plan_research as bounds

ORDER_VERSION=indexing.ORDER_VERSION
PLAN_VERSION='ISSUER_COUNTS_ONLY_SHARD_PREPARE_V1'
WEIGHT_SPECS=('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')
PARAMETERS={'fit_days','shrinkage_intensity','turnover_anchor_strength','max_single_weight','min_single_weight',
            'top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap'}
MAX_SHARDS=100000
HARD_SOURCES={str(Path(indexing.__file__).resolve()):'bc24b924ba53f093f7f9bfc05fd237234fbed851ff5d32f7b41324a08594d87b',
              str(Path(bounds.__file__).resolve()):'4f433404895070613d217acc8a245e6fb346f2835652fe1a934eb2be909c943c'}
LOADED={path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in HARD_SOURCES}
LOADED[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def canonical_sha(value):
    require(type(value) is str and len(value)==64 and set(value)<=set('0123456789abcdef'),'Canonical SHA256 required')
    return value


def explicit_text(value):
    require(type(value) is str and value and value==value.strip(),'Explicit canonical text required')
    return value


def reference(value):
    require(type(value) is dict and set(value)=={'path','sha256'},'Exact external reference required')
    explicit_text(value['path']);require(Path(value['path']).is_absolute(),'Absolute external reference required')
    canonical_sha(value['sha256']);return deepcopy(value)


def source_map(value):
    require(type(value) is dict and bool(value),'Explicit complete fitter source hash map required')
    for path,sha in value.items():
        explicit_text(path);require(Path(path).is_absolute(),'Absolute fitter source required');canonical_sha(sha)
    return {path:value[path] for path in sorted(value)}


def parameters_contract(parameters):
    require(type(parameters) is dict and set(parameters)==PARAMETERS,'All eight original parameters required')
    require(type(parameters['fit_days']) is int and parameters['fit_days']==126,'Exact 126 fit days required')
    for key,value in parameters.items():
        require(type(value) in (int,float) and math.isfinite(value),'Finite nonboolean parameter required')
        if key!='fit_days':require(0<=value<=1,'Unit interval parameter required')
    require(parameters['max_single_weight']>0 and parameters['risk_chain_top1_cap']>0 and
        parameters['min_single_weight']<=parameters['max_single_weight'],'Valid original risk envelope required')
    return deepcopy(parameters)


def previous_contract(previous):
    if previous is None:return None
    require(type(previous) is dict and bool(previous),'Full nonempty prior target or None required')
    total=Fraction(0)
    for sid,weight in previous.items():
        explicit_text(sid)
        require(type(weight) in (int,float) and math.isfinite(weight) and 0<=weight<=1,'Finite nonboolean prior weight required')
        total+=Fraction(str(weight))
    require(abs(total-1)<=Fraction(1,10**9),'Full prior target must preserve unit mass')
    # Never intersect with current groups: exiting securities stay in the plan.
    return {sid:previous[sid] for sid in sorted(previous)}


def prepare_issuer_shards(*,groups,panel_reference,panel_audit_reference,decision_cutoff,parameters,
                          fitter_source_hashes,previous_target_weights,shard_size,max_shards):
    """Build only interval descriptors, using the frozen conservative bounds.

    References and fitter source maps are assertions to be verified by a future
    runner. No input files are read here and no completed state is accepted.
    """
    require(all(LOADED[path]==sha for path,sha in HARD_SOURCES.items()),'Imported mathematical source differs')
    require(type(shard_size) is int and 1<=shard_size<=indexing.MAX_SLICE_SIZE,'Explicit shard size must be 1..10000')
    require(type(max_shards) is int and 1<=max_shards<=MAX_SHARDS,'Explicit plan descriptor budget must be 1..100000')
    panel=reference(panel_reference);audit=reference(panel_audit_reference)
    require(type(decision_cutoff) is str and date.fromisoformat(decision_cutoff).isoformat()==decision_cutoff,'Canonical decision cutoff required')
    require(panel['path']!=audit['path'],'Independent audit must not be the panel itself')
    params=parameters_contract(parameters);sources=source_map(fitter_source_hashes);prior=previous_contract(previous_target_weights)
    index=indexing.IssuerCombinationIndex(groups)
    risk={key:Fraction(str(params[key])) for key in bounds._RISK_KEYS}
    cards=[];descriptor_count=0;excluded=0;planned=0
    for k,total in index.counts_by_k().items():
        certificates=deepcopy(bounds._necessary_bounds(k,risk))
        count=0 if certificates else (total+shard_size-1)//shard_size
        descriptor_count+=count
        if certificates:excluded+=total
        else:planned+=total
        cards.append(dict(k=k,combination_count=total,necessary_bound_certificates=certificates,
            status='NECESSARY_BOUND_EXCLUDED' if certificates else 'PLANNED_NOT_ENUMERATED',
            planned_shard_count=count,planned_combination_count=0 if certificates else total,
            planned_canonical_task_count=0 if certificates else total*len(WEIGHT_SPECS)))
    require(descriptor_count<=max_shards,'Descriptor budget exceeded; no partial plan is produced')
    context=dict(plan_version=PLAN_VERSION,order_version=ORDER_VERSION,group_fingerprint=index.group_fingerprint,
        panel_reference=panel,panel_audit_reference=audit,decision_cutoff=decision_cutoff,parameters=params,
        fitter_source_fingerprint=digest(sources),previous_target_weights=prior,weight_specs=list(WEIGHT_SPECS),
        shard_size=shard_size,mathematical_source_fingerprint=digest(LOADED))
    plan_id=digest(context);shards=[]
    for card in cards:
        if card['necessary_bound_certificates']:continue
        total=card['combination_count']
        for start in range(0,total,shard_size):
            stop=min(start+shard_size,total)
            identity=dict(context,k=card['k'],start=start,stop=stop)
            shards.append(dict(identity,shard_id=digest(identity),plan_id=plan_id,ordinal=len(shards),
                combination_count=stop-start,planned_canonical_task_count=(stop-start)*len(WEIGHT_SPECS),
                status='PLANNED_NOT_ENUMERATED',completed_canonical_task_count=0,
                remaining_canonical_task_count=(stop-start)*len(WEIGHT_SPECS)))
    require(len(shards)==descriptor_count,'Descriptor count differs')
    return dict(schema=PLAN_VERSION,plan_id=plan_id,context=context,
        canonical_groups=[dict(issuer_id=issuer,security_ids=list(group)) for issuer,group in zip(index.issuer_ids,index.security_groups)],
        cardinalities=cards,shards=shards,issuer_count=len(index.issuer_ids),security_count=sum(map(len,index.security_groups)),
        all_k_combination_count=excluded+planned,necessary_bound_excluded_combination_count=excluded,
        planned_combination_count=planned,planned_canonical_task_count=planned*len(WEIGHT_SPECS),
        completed_canonical_task_count=0,remaining_canonical_task_count=planned*len(WEIGHT_SPECS),
        planned_shard_count=descriptor_count,max_shards=max_shards,status='PLANNED_NOT_ENUMERATED',
        conservative_bound_contract=dict(risk_tolerance=str(bounds._RISK_TOLERANCE),simplex_tolerance=str(bounds._SIMPLEX_TOLERANCE),
            rounding_margin_per_term=str(bounds._ROUNDING_MARGIN_PER_TERM),source_reference=dict(path=str(Path(bounds.__file__).resolve()),sha256=HARD_SOURCES[str(Path(bounds.__file__).resolve())])),
        fitter_source_hashes=sources,loaded_mathematical_source_hashes=deepcopy(LOADED),
        combination_enumeration_performed=False,risk_feasibility_proven=False,score_filtering_performed=False,
        task_identity_generated=False,runner_attached=False,external_source_bytes_verified=False,source_bytes_reverified_at_call=False,
        anchor_alias_equivalence_verified=False,all_three_specs_planned_without_alias_deduplication=True,
        identity_authenticated=False,fit_performed=False,promotion_allowed=False)
