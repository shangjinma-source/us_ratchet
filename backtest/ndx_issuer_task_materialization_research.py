"""Bounded pure task-input materialization; no file reads at call time or fitting."""
from copy import deepcopy
from datetime import date
import hashlib
import json
import math
from pathlib import Path
from backtest import ndx_issuer_combination_index_research as indexing
from backtest import ndx_issuer_shard_prepare_research as planning

SCHEMA='ISSUER_BOUNDED_TASK_MATERIALIZATION_V1'
NUMERICAL_ID_SCHEMA='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1'
LOCATION_ID_SCHEMA='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1'
HARD_SOURCES={str(Path(indexing.__file__).resolve()):'bc24b924ba53f093f7f9bfc05fd237234fbed851ff5d32f7b41324a08594d87b',
 str(Path(planning.__file__).resolve()):'722f48952a6d0c8c878df76eedeb0b8ca3b1e3feeb77560598414890ae00a4ec'}
LOADED={path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in HARD_SOURCES}
LOADED[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def validate_panel(panel,context,index):
    require(type(panel) is dict and set(panel)=={'panel_reference','panel_content_sha256','dates','columns','returns','universe'},'Exact pure panel projection required')
    require(panel['panel_reference']==context['panel_reference'],'Panel reference differs from plan')
    planning.canonical_sha(panel['panel_content_sha256'])
    days=panel['dates'];columns=panel['columns'];matrix=panel['returns'];universe=panel['universe']
    require(type(days) is list and len(days)==126 and days==sorted(set(days)) and
        all(type(day) is str and date.fromisoformat(day).isoformat()==day for day in days) and days[-1]==context['decision_cutoff'],'Exact 126 canonical cutoff dates required')
    require(type(columns) is list and columns and all(type(name) is str and name and name==name.strip()==name.upper() for name in columns)
        and len(columns)==len(set(columns)),'Unique canonical uppercase ticker columns required')
    require(type(matrix) is list and len(matrix)==126 and all(type(row) is list and len(row)==len(columns) for row in matrix),'Complete full-panel matrix dimensions required')
    values=[]
    for row in matrix:
        converted=[]
        for value in row:
            require(type(value) in (int,float) and math.isfinite(value) and value>-1,'All panel returns must be finite nonboolean and exceed -1')
            converted.append(float(value))
        values.append(converted)
    require(type(universe) is list and universe,'Complete explicit universe required')
    by_sid={};tickers=set();groups={}
    for row in universe:
        require(type(row) is dict and set(row)=={'security_id','ticker','issuer_id','risk_chain'},'Exact selected-coordinate projection required')
        for value in row.values():planning.explicit_text(value)
        sid=row['security_id'];ticker=row['ticker']
        require(sid not in by_sid and ticker not in tickers and ticker in columns,'Unique full-universe SID/ticker required')
        by_sid[sid]=deepcopy(row);tickers.add(ticker);groups.setdefault(row['issuer_id'],[]).append(sid)
    require(tickers==set(columns),'All panel columns must match full universe')
    canonical=[(issuer,tuple(sorted(group))) for issuer,group in sorted(groups.items())]
    require(canonical==list(zip(index.issuer_ids,index.security_groups)),'Full panel issuer groups differ from plan')
    return values,by_sid


def materialize_slice(*,plan,plan_reference,shard_id,panel,start,stop,max_materialized_combinations):
    """Materialize only an explicit slice, with all validation preceding unrank.

    A future source-bound wrapper must authenticate the supplied plan and panel
    bytes. This pure function authenticates neither identifiers nor references.
    """
    require(all(LOADED[path]==sha for path,sha in HARD_SOURCES.items()),'Imported helper implementation differs')
    plan_ref=planning.reference(plan_reference);planning.canonical_sha(shard_id)
    require(type(plan) is dict and plan.get('schema')==planning.PLAN_VERSION,'Counts-only plan schema required')
    context=plan['context'];groups=[(row['issuer_id'],row['security_ids']) for row in plan['canonical_groups']]
    rebuilt=planning.prepare_issuer_shards(groups=groups,panel_reference=context['panel_reference'],panel_audit_reference=context['panel_audit_reference'],
        decision_cutoff=context['decision_cutoff'],parameters=context['parameters'],fitter_source_hashes=plan['fitter_source_hashes'],
        previous_target_weights=context['previous_target_weights'],shard_size=context['shard_size'],max_shards=plan['max_shards'])
    require(digest(rebuilt)==digest(plan),'Complete plan identity, intervals, certificates or pending state differ')
    matches=[row for row in plan['shards'] if row['shard_id']==shard_id]
    require(len(matches)==1,'Exactly one declared shard required');shard=matches[0]
    require(type(start) is int and type(stop) is int and type(max_materialized_combinations) is int,'Exact integer slice coordinates required')
    require(1<=max_materialized_combinations<=indexing.MAX_SLICE_SIZE,'Explicit materialization budget must be 1..10000')
    require(shard['start']<=start<=stop<=shard['stop'] and stop-start<=max_materialized_combinations,'Requested interval exceeds shard or budget')
    index=indexing.IssuerCombinationIndex(groups)
    matrix,by_sid=validate_panel(panel,context,index)
    prior=context['previous_target_weights']
    if prior is not None:
        # Match the actual frozen fitter float summation gate, not the wider plan gate.
        require(math.isclose(sum(float(value) for value in prior.values()),1.,abs_tol=1e-12,rel_tol=0),
                'Full prior fails the actual fitter 1e-12 mass gate; no renormalization')
    locations={ticker:position for position,ticker in enumerate(panel['columns'])}
    sliced=index.slice(shard['k'],start,stop,max_slice_size=max_materialized_combinations)
    combinations=[]
    for offset,prefix_sids in enumerate(sliced['combinations']):
        position=start+offset;ordered=sorted(prefix_sids)
        selected={sid:{key:by_sid[sid][key] for key in ('ticker','issuer_id','risk_chain')} for sid in ordered}
        # Index guarantees issuer uniqueness; retain an independent explicit gate.
        require(len({value['issuer_id'] for value in selected.values()})==len(selected),'Selected issuer duplicate')
        tickers=[selected[sid]['ticker'] for sid in ordered]
        payload=dict(dates=deepcopy(panel['dates']),tickers=tickers,returns=[[row[locations[ticker]] for ticker in tickers] for row in matrix])
        matrix_sha=digest(payload);tasks=[]
        for spec_index,spec in enumerate(context['weight_specs']):
            numerical=dict(schema=NUMERICAL_ID_SCHEMA,cutoff=context['decision_cutoff'],holding_count=shard['k'],selected=deepcopy(selected),
                weight_spec=spec,parameters=deepcopy(context['parameters']),requested_previous_target_weights=deepcopy(prior),
                fit_data_sha256=matrix_sha,fitter_source_fingerprint=context['fitter_source_fingerprint'])
            location=dict(schema=LOCATION_ID_SCHEMA,plan_reference=deepcopy(plan_ref),plan_id=plan['plan_id'],shard_id=shard_id,
                order_version=context['order_version'],group_fingerprint=context['group_fingerprint'],k=shard['k'],rank=position,spec_index=spec_index,weight_spec=spec)
            tasks.append(dict(numerical_task_id=digest(numerical),numerical_identity=numerical,location_id=digest(location),location_identity=location,
                status='MATERIALIZED_NOT_ATTEMPTED',wrapper_call_attempt_count=0,fit_performed=False,
                expected_fitter_previous_target_weights={} if prior is None else deepcopy(prior),anchor_alias_equivalence_verified=False))
        combinations.append(dict(k=shard['k'],rank=position,prefix_security_ids=list(prefix_sids),fitter_sorted_security_ids=ordered,
            fit_matrix=payload,fit_data_sha256=matrix_sha,tasks=tasks))
    return dict(schema=SCHEMA,status='MATERIALIZED_NOT_ATTEMPTED',plan_reference=plan_ref,plan_id=plan['plan_id'],shard_id=shard_id,
        order_version=context['order_version'],group_fingerprint=context['group_fingerprint'],k=shard['k'],start=start,stop=stop,
        panel_reference=deepcopy(context['panel_reference']),panel_audit_reference=deepcopy(context['panel_audit_reference']),
        panel_content_sha256=panel['panel_content_sha256'],fitter_source_hashes=deepcopy(plan['fitter_source_hashes']),
        materializer_loaded_source_hashes=deepcopy(LOADED),combination_count=len(combinations),materialized_task_count=len(combinations)*3,
        completed_task_count=0,remaining_unattempted_materialized_task_count=len(combinations)*3,max_materialized_combinations=max_materialized_combinations,
        combinations=combinations,source_bytes_authenticated=False,source_bytes_reverified_at_call=False,identity_authenticated=False,
        old_task_identity_reused=False,full_shard_completed=False,all_plan_tasks_completed=False,fit_performed=False,promotion_allowed=False)
