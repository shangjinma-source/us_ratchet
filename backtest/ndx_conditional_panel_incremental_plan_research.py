"""Pure input-equivalence plan; no result is imported or fitted here."""
import itertools
import math
from collections import Counter
from fractions import Fraction
import numpy as np
import pandas as pd
from backtest import ndx_latest_conditional_panel_research as core
from backtest import ndx_membership_cardinality_plan_research as bounds

PARAMETERS={'fit_days','shrinkage_intensity','turnover_anchor_strength','max_single_weight','min_single_weight','top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap'}


def validate(panel, parameters, fitter_sources):
    if set(parameters)!=PARAMETERS or type(parameters['fit_days']) is not int or parameters['fit_days']!=126:
        raise ValueError('Eight explicit original parameters required')
    if any(type(v) not in (int,float) or not math.isfinite(v) or (k!='fit_days' and not 0<=v<=1) for k,v in parameters.items()):
        raise ValueError('Finite nonboolean original parameters required')
    if parameters['max_single_weight']<=0 or parameters['risk_chain_top1_cap']<=0 or parameters['min_single_weight']>parameters['max_single_weight']:
        raise ValueError('Valid original envelope required')
    if not fitter_sources or any(type(p) is not str or not p or type(h) is not str or len(h)!=64 or any(c not in '0123456789abcdef' for c in h) for p,h in fitter_sources.items()):
        raise ValueError('Explicit fitter source digests required')
    rows=panel['universe'].to_dict('records');ids=[r['security_id'] for r in rows]
    # Validate checksum and all rows individually; multiple share classes may share an issuer.
    for sid in ids:core.selected_mapping(panel,[sid])
    frame=panel['returns']
    if not ids or len(set(ids))!=len(ids) or len({r['ticker'] for r in rows})!=len(rows) or not isinstance(frame.index,pd.DatetimeIndex) or len(frame)!=126 or frame.index.has_duplicates or not frame.index.is_monotonic_increasing or frame.index.tz is not None or frame.index[-1].date().isoformat()!=panel['cutoff'] or any(str(t)!='float64' for t in frame.dtypes) or not np.isfinite(frame.to_numpy()).all() or (frame.to_numpy()<=-1).any():
        raise ValueError('Exact complete finite 126-row typed panel required')
    if not frame.index.equals(frame.index.normalize()) or not frame.index.equals(panel['nominal_close'].index[-126:]):
        raise ValueError('Canonical midnight return sessions and price calendar required')
    return rows


def old_subset(old,new):
    if old['cutoff']!=new['cutoff']:raise ValueError('Different cutoffs cannot reuse old fits')
    old_rows=old['universe'].to_dict('records');new_rows={r['security_id']:r for r in new['universe'].to_dict('records')}
    for row in old_rows:
        if core.canonical_sha(row)!=core.canonical_sha(new_rows.get(row['security_id'])):raise ValueError('Old security metadata changed')
    columns=old['returns'].columns
    for name in ('returns','nominal_close','raw_volume','dollar_volume'):
        if not set(columns)<=set(new[name].columns) or not old[name].equals(new[name][columns]):raise ValueError('Old typed numeric cells changed')
    before=old['observed_provenance_and_missing'];after={r['ticker']:r for r in new['observed_provenance_and_missing']}
    for row in before:
        if row['ticker'] in columns:
            if core.canonical_sha(row)!=core.canonical_sha(after[row['ticker']]):raise ValueError('Old complete provenance changed')


def enumerate_inputs(panel, parameters, fitter_sources, exact_limit=50000):
    if type(exact_limit) is not int or not 1<=exact_limit<=50000:raise ValueError('Explicit bounded exact limit 1..50000 required')
    rows=validate(panel,parameters,fitter_sources)
    by_sid={r['security_id']:r for r in rows};groups={}
    for row in rows:groups.setdefault(row['issuer_id'],[]).append(row['security_id'])
    groups=[sorted(groups[key]) for key in sorted(groups)]
    counts=bounds.combinatorics.issuer_dedup_combination_counts([len(g) for g in groups])
    risk={k:Fraction(str(parameters[k])) for k in bounds._RISK_KEYS}
    # Check every k before materializing even the first task list.
    for k in range(1,len(groups)+1):
        if not bounds._necessary_bounds(k,risk) and int(counts[k])>exact_limit:
            raise ValueError('Exact enumeration budget exceeded')
    cards=[];tasks=[];frame=panel['returns'];dates=[d.date().isoformat() for d in frame.index]
    for k in range(1,len(groups)+1):
        certificates=bounds._necessary_bounds(k,risk)
        cards.append(dict(k=k,combinations=int(counts[k]),necessary_bound_certificates=certificates))
        if certificates:continue
        for chosen in itertools.combinations(groups,k):
            for ids in itertools.product(*chosen):
                ids=sorted(ids);selected={s:{key:by_sid[s][key] for key in ('ticker','issuer_id','risk_chain')} for s in ids}
                tickers=[selected[s]['ticker'] for s in ids]
                matrix=core.canonical_sha(dict(dates=dates,tickers=tickers,returns=frame[tickers].to_numpy().tolist()))
                for spec in ('equal_weight','constrained_fixed_shrinkage'):
                    task=dict(selected=selected,holding_count=k,weight_spec=spec,cutoff=panel['cutoff'],parameters=parameters,previous_target_weights=None)
                    tasks.append(dict(task_id=core.canonical_sha(task),input_equivalence_sha256=core.canonical_sha(dict(task=task,fit_data_sha256=matrix,fitter_source_hashes=fitter_sources)),fit_data_sha256=matrix,task=task))
    return cards,tasks


def build_incremental_plan(*,old_panel,new_panel,old_parameters,new_parameters,old_fitter_sources,new_fitter_sources,exact_limit=50000):
    old_subset(old_panel,new_panel)
    old_cards,old_tasks=enumerate_inputs(old_panel,old_parameters,old_fitter_sources,exact_limit)
    cards,tasks=enumerate_inputs(new_panel,new_parameters,new_fitter_sources,exact_limit)
    previous={t['input_equivalence_sha256']:t for t in old_tasks}
    matching=0
    for row in tasks:
        prior=previous.get(row['input_equivalence_sha256']);matching+=prior is not None
        row.update(status='PENDING_OLD_OR_NEW',old_equivalent_task_id=prior['task_id'] if prior else None,
            input_equivalent_to_old_task=prior is not None,completed_old_result_verified=False,result_reused=False)
    return dict(schema='CONDITIONAL_PANEL_INCREMENTAL_INPUT_PLAN_V1',cardinalities=cards,tasks=tasks,exact_enumeration_limit=exact_limit,
        all_issuer_unique_combinations=sum(c['combinations'] for c in cards),necessary_bound_excluded_combinations=sum(c['combinations'] for c in cards if c['necessary_bound_certificates']),
        old_canonical_count=len(old_tasks),new_canonical_count=len(tasks),input_equivalent_old_count=matching,new_input_count=len(tasks)-matching,
        scope='PURE_INPUT_EQUIVALENCE_ONLY_EXTERNAL_PANEL_AND_RESULT_AUTHENTICATION_REQUIRED',
        result_import_preconditions=['EXTERNAL_RESULT_BYTES_SHA','COMPLETE_SOURCE_AND_MARKER_VERIFICATION','EXACT_TASK_AND_MATRIX_AND_PARAMETERS','SAME_FROZEN_FITTER_SOURCE_CLOSURE','ORIGINAL_RESULT_NUMERICAL_AND_RISK_READBACK'],
        external_source_bytes_verified=False,any_result_reused=False,fit_performed=False,all_ndx_legal_pool_verified=False,point_in_time_verified=False,oos_evaluation_performed=False,promotion_allowed=False)
