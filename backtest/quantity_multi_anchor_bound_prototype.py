"""Fixed four-anchor rational AM-GM bounds, never executable portfolios.

For arbitrary strictly positive reference wealth v, AM-GM bounds product(W/C)
by product(v/C)*(max_box sum(W/v)/m)^m. Fractional knapsack computes this
linear maximum after dropping integer/issuer constraints. Take the minimum with
the old exact bound. Anchors follow three fixed half-steps toward the previous
LP maximizer; no market-tuned parameters, incumbent update, or domain pruning.
"""
from copy import deepcopy
from fractions import Fraction as F
from math import prod
from hashlib import sha256
import json
from backtest import quantity_integer_box_certificate_prototype as core

RULE='INCUMBENT_THEN_THREE_HALF_STEPS_TOWARD_PREVIOUS_BOX_LP_V1'


def canonical_hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def anchor_bound(problem,box,quantities):
    """Reference may be fractional and need not obey issuer exclusivity."""
    ids=problem['ids'];core.require(set(box)==set(ids) and all(type(v)is list and len(v)==2 and all(type(x)is int for x in v) and 0<=v[0]<=v[1] for v in box.values()),'BOX_INTEGER_BOUNDS')
    core.require(set(quantities)==set(ids),'ANCHOR_DOMAIN')
    core.require(all(type(v)in(str,int,F) for v in quantities.values()),'ANCHOR_RATIONAL_REQUIRED')
    q={s:F(v) for s,v in quantities.items()}
    core.require(all(v>=0 for v in q.values()),'ANCHOR_NONNEGATIVE_REQUIRED')
    residual=problem['cash']-sum((problem['cost'][s]*q[s] for s in ids),F(0))
    core.require(residual>=0,'ANCHOR_CASH_INFEASIBLE')
    wealth=[residual+sum((problem['prices'][s]*q[s]*r[s] for s in ids),F(0)) for r in problem['scenarios']]
    core.require(all(w>0 for w in wealth),'ANCHOR_WEALTH_NOT_POSITIVE')
    coefficients={s:sum((problem['prices'][s]*(r[s]-1-problem['fee'])/w for r,w in zip(problem['scenarios'],wealth)),F(0)) for s in ids}
    lp={s:F(box[s][0]) for s in ids}
    remaining=problem['spendable']-sum((problem['cost'][s]*lp[s] for s in ids),F(0))
    core.require(remaining>=0,'BOX_LOWER_INFEASIBLE')
    for s in sorted(ids,key=lambda s:(-coefficients[s]/problem['cost'][s],s)):
        if coefficients[s]<=0:continue
        amount=min(F(box[s][1]-box[s][0]),remaining/problem['cost'][s]);lp[s]+=amount;remaining-=amount*problem['cost'][s]
    maximum=sum((problem['cash']/w for w in wealth),F(0))+sum((coefficients[s]*lp[s] for s in ids),F(0))
    core.require(maximum>0,'RELAXATION_WEALTH_SUM_NOT_POSITIVE')
    upper=prod(w/problem['cash'] for w in wealth)*(maximum/len(wealth))**len(wealth)
    return dict(quantities={s:str(q[s]) for s in ids},wealth=list(map(str,wealth)),linear_coefficients={s:str(coefficients[s]) for s in ids},linear_extreme={s:str(lp[s]) for s in ids},maximum_wealth_ratio_sum=str(maximum),upper_product=str(upper),executable_portfolio=False)


def bound(*,inputs,box,incumbent):
    p=core.prepare(**inputs);old=core.box_bound(p,box,incumbent)
    binding=dict(inputs=deepcopy(inputs),box=deepcopy(box),incumbent=deepcopy(incumbent))
    result=dict(schema='MULTI_POSITIVE_ANCHOR_BOUND_PROTOTYPE_V1',rule=RULE,binding=binding,binding_sha256=canonical_hash(binding),old_bound=old,anchors=[],scope='SUPPLIED_INTEGER_TRAINING_BOX_OBJECTIVE_UPPER_BOUND',executable_portfolio=False,source_authenticated=False,future_performance_guaranteed=False)
    if old['empty']:return dict(result,empty=True,upper_product=None)
    quantities={s:F(incumbent.get(s,0)) for s in p['ids']}
    for index in range(4):
        item=anchor_bound(p,box,quantities);result['anchors'].append(item)
        quantities={s:(quantities[s]+F(item['linear_extreme'][s]))/2 for s in p['ids']}
    upper=min([F(old['upper'])]+[F(a['upper_product']) for a in result['anchors']])
    return dict(result,empty=False,upper_product=str(upper))


def verify(evidence,*,expected_binding_sha256):
    core.require(evidence['binding_sha256']==expected_binding_sha256==canonical_hash(evidence['binding']),'MULTI_ANCHOR_BINDING_CHANGED')
    rebuilt=bound(**evidence['binding'])
    core.require(evidence==rebuilt,'MULTI_ANCHOR_EVIDENCE_CHANGED')
    return dict(status='VERIFIED_MATHEMATICAL_UPPER_BOUND_ONLY',empty=evidence['empty'],upper_product=evidence['upper_product'])
