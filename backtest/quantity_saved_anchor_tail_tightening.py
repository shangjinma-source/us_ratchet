"""Exact nested-tail binary tightening with one immutable positive anchor.

For fixed wealth v, AM-GM upper = product(v/C)*(max_B sum(W/v)/m)^m.
Raising a lower endpoint shrinks B. Exact fractional-knapsack maximum cannot
increase; its positive mth power and min with an unchanged inherited cap cannot
increase either. Forced-issuer/budget emptiness persists for nested tails.
Thus the closure predicate upper<=incumbent is monotone, without float tests.
The lo sentinel is only a search boundary, never a false nonclosure claim.
All discarded budget slabs and certified tails are retained; value-only.
"""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from backtest import quantity_saved_anchor_coordinate_fixing as prior
from backtest import quantity_integer_box_certificate_prototype as core
from backtest import quantity_multi_anchor_bound_prototype as multi

def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def build(*,fixing_raw,expected_fixing_sha256,fixing_sources):
    core.require(type(fixing_raw)is bytes and sha256(fixing_raw).hexdigest()==expected_fixing_sha256,'FIXING_RAW_CHANGED')
    parent=json.loads(fixing_raw);prior.verify(parent,**fixing_sources)
    source=json.loads(fixing_sources['anchor_raw']);p=core.prepare(**source['binding']['inputs'])
    lower=F(parent['lower_product']);original=deepcopy(parent['remaining_box']);box=deepcopy(original)
    cap=F(parent['upper_product']);anchor=source['repaired_quantities'];rows=[];closed=[];calls=0
    minimum=sum((p['cost'][s]*box[s][0] for s in p['ids']),F(0));remaining=p['spendable']-minimum
    # In an already closed parent there is nothing left to tighten.
    active=not parent['remaining_closed']
    core.require(not active or remaining>=0,'ACTIVE_LOWER_INFEASIBLE')
    maxima={s:min(box[s][1],box[s][0]+int(remaining//p['cost'][s])) for s in p['ids']} if active else {s:box[s][1] for s in p['ids']}
    budget=sum((maxima[s]-box[s][0]).bit_length() for s in p['ids']) if active else 0
    def bound(child):
        forced=[s for s in p['ids'] if child[s][0]>0]
        if len({p['metadata'][s]['issuer_id'] for s in forced})!=len(forced):return dict(empty=True,reason='FORCED_ISSUER_CONFLICT',anchor=None,upper_product=None)
        cost=sum((p['cost'][s]*child[s][0] for s in p['ids']),F(0))
        if cost>p['spendable']:return dict(empty=True,reason='LOWER_CORNER_OVER_BUDGET',minimum_cost=str(cost),anchor=None,upper_product=None)
        proof=multi.anchor_bound(p,child,anchor)
        return dict(empty=False,reason=None,anchor=proof,upper_product=str(min(cap,F(proof['upper_product']))))
    if active:
        for sid in p['ids']:
            lo,hi=box[sid]
            if lo==hi:continue
            row=dict(sid=sid,before_box=deepcopy(box),budget_slab=None,tests=[])
            limit=maxima[sid]
            if limit<hi:
                slab=deepcopy(box);slab[sid]=[limit+1,hi]
                cost=sum((p['cost'][s]*slab[s][0] for s in p['ids']),F(0))
                core.require(cost>p['spendable'],'INVALID_BUDGET_EXCLUSION')
                proof=dict(empty=True,reason='LOWER_CORNER_OVER_BUDGET',minimum_cost=str(cost),spendable=str(p['spendable']))
                row['budget_slab']=dict(box=slab,proof=proof);closed.append(dict(box=slab,reason='BUDGET',row=len(rows)))
                box[sid]=[lo,limit];hi=limit
            row['binary_input_box']=deepcopy(box)
            left,right=lo,hi+1;last_closed=None
            while right-left>1:
                middle=(left+right)//2;tail=deepcopy(box);tail[sid]=[middle,hi];proof=bound(tail);calls+=1
                is_closed=proof['empty'] or F(proof['upper_product'])<=lower
                row['tests'].append(dict(threshold=middle,box=tail,bound=proof,closed=is_closed))
                if is_closed:right=middle;last_closed=len(row['tests'])-1
                else:left=middle
            row['first_closed_threshold']=right;row['closure_test']=None
            if right<=hi:
                core.require(last_closed is not None and row['tests'][last_closed]['threshold']==right,'MISSING_THRESHOLD_PROOF')
                row['closure_test']=last_closed
                closed.append(dict(box=deepcopy(row['tests'][last_closed]['box']),reason='EXACT_UPPER',row=len(rows),test=last_closed))
                box[sid]=[lo,right-1]
            row['retained_box']=deepcopy(box);rows.append(row)
    core.require(calls<=budget,'CONDITIONAL_BUDGET_EXCEEDED')
    proof=bound(box) if active else deepcopy(parent['remaining_bound'])
    done=parent['remaining_closed'] or proof['empty'] or F(proof['upper_product'])<=lower
    upper=lower if done else max(lower,F(proof['upper_product']))
    return dict(schema='EXACT_SAVED_ANCHOR_TAIL_TIGHTENING_V1',rule='ONE_ASCENDING_SID_PASS_EXACT_BUDGET_THEN_NESTED_TAIL_BINARY',scope='SUPPLIED_INTEGER_TRAINING_BOX_OBJECTIVE_VALUE_ONLY',
        binding=dict(fixing_sha256=expected_fixing_sha256,parent_binding=deepcopy(parent['binding'])),original_box=original,rows=rows,closed_regions=closed,remaining_box=box,remaining_bound=proof,remaining_closed=done,
        conditional_bound_calls=calls,conditional_bound_calls_max=budget,remaining_bound_calls=int(active),remaining_nonfixed_count=sum(lo<hi for lo,hi in box.values()),lower_product=str(lower),upper_product=str(upper),
        objective_value_covered=done,tie_break_optimality_established=False,data_authenticated=False,future_performance_guaranteed=False,solver_calls=0)

def verify(certificate,**sources):
    expected=build(**sources)
    core.require(canonical(certificate)==canonical(expected),'TAIL_CERTIFICATE_CHANGED')
    return dict(status='VERIFIED_EXACT_TAIL_TIGHTENING',objective_value_covered=expected['objective_value_covered'],conditional_bound_calls=expected['conditional_bound_calls'])
