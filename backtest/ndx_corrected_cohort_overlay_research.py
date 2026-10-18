"""A partial numerical overlay retains the complete original candidate denominator."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math

ECONOMIC_KEYS={'return_p50','return_p10','max_drawdown_p50','max_drawdown_p90',
    'paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent',
    'paired_drawdown_cost_p50_vs_incumbent','paired_drawdown_cost_p90_vs_incumbent',
    'return_p50_vs_012922','return_p10_vs_012922','max_drawdown_p50_vs_012922','max_drawdown_p90_vs_012922',
    'target_012922_distance','turnover','initial_turnover','initial_transaction_cost',
    'ongoing_rebalance_turnover_p50','turnover_p90','turnover_max','transaction_cost'}
PAIRED_KEYS={key for key in ECONOMIC_KEYS if key.startswith('paired_')}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def overlay_date(*,coordinate,original_records,actions,expected_counts,correction_signature):
    if not isinstance(correction_signature,str) or len(correction_signature)!=64:
        raise ValueError('Explicit correction signature required')
    records=[];jobs=set();definitions=set();counts=Counter();usable=Counter();pending=Counter()
    for old in original_records:
        task=old['task'];origin=old['origin'];identifier=task['job_id']
        if old['status']!='EVALUATED' or not isinstance(old['result'],dict):raise ValueError('Complete original evaluated records required')
        if origin not in expected_counts or any(task[key]!=value for key,value in coordinate.items()):raise ValueError('Original coordinate/model differs')
        names=task['tickers'].split(';')
        if type(task['holding_count']) is not int or len(names)!=task['holding_count'] or names!=sorted(set(names)):
            raise ValueError('Original exact security definition required')
        definition=(tuple(names),task['weight_spec'])
        if identifier in jobs or definition in definitions:raise ValueError('Duplicate task or portfolio/model definition')
        jobs.add(identifier);definitions.add(definition);counts[origin]+=1
        if identifier not in actions:raise ValueError('Missing explicit action')
        action=actions[identifier]
        if action['task']!=task or action['origin']!=origin:raise ValueError('Replacement lineage differs')
        mode=action['mode'];metrics=None
        if mode=='PENDING':
            if action.get('metrics') is not None or action.get('patch') is not None:raise ValueError('Pending must not expose stale metrics')
            pending[origin]+=1
        elif mode=='ORIGINAL_UNCHANGED':
            if action.get('evidence')!='NO_DEPENDENCY_ON_THREE_CELLS':raise ValueError('Explicit no-dependency evidence required')
            metrics=deepcopy(old['result']);usable[origin]+=1
        elif mode=='REPLACED_FULL':
            metrics=deepcopy(action['metrics'])
            for key in ('tickers','holding_count','weight_spec'):
                if metrics.get(key)!=task[key]:raise ValueError('Corrected result identity differs')
            usable[origin]+=1
        elif mode=='SAVED_WINDOW_ECONOMIC_PATCH':
            if origin!='NON_EQUAL_BASE' or set(action['patch'])!=ECONOMIC_KEYS:raise ValueError('Exact twenty-metric BASE patch required')
            patch=action['patch']
            for key,value in patch.items():
                if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Finite patch values required')
                if key not in PAIRED_KEYS and abs(value-old['result'][key])>1e-12:
                    raise ValueError('Unchanged candidate/target/fee metric differs')
            metrics=dict(deepcopy(old['result']),**deepcopy(patch));usable[origin]+=1
        else:raise ValueError('Unsupported overlay action')
        if metrics is not None:
            for key in {'return_p50','return_p10','max_drawdown_p50','max_drawdown_p90'}|PAIRED_KEYS:
                if type(metrics.get(key)) not in (int,float) or not math.isfinite(metrics[key]):raise ValueError('Available economic metric invalid')
        records.append(dict(task=deepcopy(task),origin=origin,status='PENDING_NUMERICAL_DELTA' if mode=='PENDING' else 'AVAILABLE',
            result=metrics,overlay_mode=mode,lineage=deepcopy(action['lineage']),
            original_training_semantics_sha256=task.get('training_semantics_sha256'),
            correction_signature=correction_signature,
            overlay_record_id=digest(dict(parent_task=task,origin=origin,correction_signature=correction_signature)),
            eligibility=None,promotion_allowed=False))
    if set(actions)!=jobs or dict(counts)!=expected_counts:raise ValueError('Full original denominator differs')
    return dict(schema='ndx_corrected_cohort_overlay_v1',coordinate=coordinate,records=records,
        original_count=sum(counts.values()),available_count=sum(usable.values()),pending_count=sum(pending.values()),
        counts={origin:dict(planned=counts[origin],available=usable[origin],pending=pending[origin]) for origin in expected_counts},
        economic_inputs_complete=not pending,pending_is_economic_failure=False,economic_failure_count=0,
        scope='ORIGINAL_RESEARCHED_SUBPOOL_NOT_FULL_NDX',original_scope_label_is_not_new_membership_approval=True,
        selection_performed=False,winner=None,whole_lot_executed=False,point_in_time_verified=False,promotion_allowed=False)
