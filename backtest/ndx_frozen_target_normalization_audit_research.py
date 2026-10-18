"""Independent reconstruction of the frozen engine's single float normalization.

Preserve the declared strategic schedule. This records the executor's existing
ordered binary-float sum/division without invoking or changing the executor.
"""
from copy import deepcopy
import hashlib
import json
import math


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def normalized_schedule(schedule):
    if type(schedule) is not list or not schedule: raise ValueError('Nonempty explicit schedule required')
    result=deepcopy(schedule);periods=[]
    for original,normalized in zip(schedule,result):
        targets=original['targets']
        if type(targets) is not dict or not targets: raise ValueError('Ordered target mapping required')
        order=list(targets);weights=[]
        for sid in order:
            target=targets[sid];weight=target['target_weight']
            if type(weight) not in (int,float) or not math.isfinite(weight) or weight<=0: raise ValueError('Positive nonboolean finite weight required')
            if type(sid) is not str or not sid or set(target)!={'ticker','issuer_id','target_weight'}: raise ValueError('Exact target identity fields required')
            weights.append(float(weight))
        total=sum(weights)
        if not math.isfinite(total) or abs(total-1.)>1e-12: raise ValueError('Only unit strategic targets within original fit tolerance supported')
        differences=[]
        for sid,weight in zip(order,weights):
            effective=weight/total
            normalized['targets'][sid]['target_weight']=effective
            differences.append(dict(security_id=sid,original_weight=weight,effective_weight=effective,absolute_binary_float_difference=abs(effective-weight)))
        periods.append(dict(decision_date=original['decision_date'],target_iteration_order=order,binary_float_weight_sum=total,
            normalization_count=1,weights=differences,maximum_absolute_binary_float_difference=max(r['absolute_binary_float_difference'] for r in differences)))
    evidence=dict(schema='FROZEN_ORDERED_FLOAT_TARGET_NORMALIZATION_AUDIT_V1',policy='ONE_DIVISION_BY_PYTHON_FLOAT_SUM_IN_SUBMITTED_TARGET_ORDER',
        original_schedule_sha256=digest(schedule),effective_schedule_sha256=digest(result),periods=periods,
        original_strategic_schedule_modified=False,engine_or_owner_normalizer_called=False,normalization_tolerance_used_for_saved_target_comparison=False,
        numerical_execution_performed=False,point_in_time_verified=False,promotion_allowed=False)
    return result,evidence
