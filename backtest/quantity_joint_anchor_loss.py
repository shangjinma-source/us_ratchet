"""Exact joint loss necessary condition for strict integer improvement.

For any lambda>=0, U-S(q)=lambda*(B-cost(q))+sum coordinate losses.
Each term is nonnegative on the original budget/box. Fixed anchor AM-GM gives
product<=P*(S/m)^m. T=floor_D(root_m(m^m*L/P)) is computed by integer powers;
strict improvement requires S>T, hence loss<U-T. No float root or optimizer.
Dropping issuer restrictions only weakens this necessary condition. All IDs
remain; this kernel neither searches candidates nor updates an incumbent.
"""
from fractions import Fraction as F
from copy import deepcopy
from hashlib import sha256
from math import prod
import json
from backtest import quantity_integer_box_certificate_prototype as core
from backtest import quantity_multi_anchor_bound_prototype as multi
GRID=10**12

def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return sha256(canonical(v)).hexdigest()
def floor_root_ratio(value,degree,denominator=GRID):
    core.require(type(degree)is int and degree>0 and type(denominator)is int and denominator>0,'ROOT_PARAMETERS')
    value=F(value);core.require(value>0,'ROOT_POSITIVE')
    # floor(root(value)*D) = floor_root(floor(value*D**degree)).
    n=(value.numerator*denominator**degree)//value.denominator
    lo=0;hi=1<<((n.bit_length()+degree-1)//degree)
    while hi-lo>1:
        mid=(lo+hi)//2
        if mid**degree<=n:lo=mid
        else:hi=mid
    if hi**degree<=n:lo=hi
    t=F(lo,denominator)
    core.require(t**degree<=value<(t+F(1,denominator))**degree,'ROOT_BRACKET_FAILED')
    return t

def build(*,inputs,box,anchor_quantities,incumbent,dual_lambda):
    p=core.prepare(**inputs);lower=core.objective(p,incumbent)[0]
    core.require(type(dual_lambda)in(str,int,F),'RATIONAL_LAMBDA_REQUIRED');lam=F(dual_lambda);core.require(lam>=0,'NONNEGATIVE_LAMBDA')
    proof=multi.anchor_bound(p,box,anchor_quantities)
    wealth=list(map(F,proof['wealth']));coeff={s:F(v) for s,v in proof['linear_coefficients'].items()};m=len(wealth)
    constant=sum((p['cash']/w for w in wealth),F(0));anchor_product=prod(w/p['cash'] for w in wealth)
    reduced={s:coeff[s]-lam*p['cost'][s] for s in p['ids']}
    endpoints={s:box[s][1] if reduced[s]>=0 else box[s][0] for s in p['ids']}
    upper=constant+lam*p['spendable']+sum((reduced[s]*endpoints[s] for s in p['ids']),F(0))
    target=F(m**m)*lower/anchor_product;t=floor_root_ratio(target,m);gap=upper-t
    binding=dict(inputs=deepcopy(inputs),box=deepcopy(box),anchor_quantities=deepcopy(anchor_quantities),incumbent=deepcopy(incumbent),dual_lambda=str(lam))
    return dict(schema='EXACT_JOINT_ANCHOR_LOSS_V1',scope='SUPPLIED_INTEGER_TRAINING_BOX_STRICT_IMPROVEMENT_NECESSARY_CONDITION',binding=binding,binding_sha256=digest(binding),anchor_proof=proof,
        constant=str(constant),anchor_product=str(anchor_product),scenario_count=m,lower_product=str(lower),spendable=str(p['spendable']),costs={s:str(v) for s,v in p['cost'].items()},
        reduced_coefficients={s:str(v) for s,v in reduced.items()},preferred_endpoints=endpoints,linear_dual_upper=str(upper),root_power_target=str(target),threshold_floor=str(t),threshold_grid_denominator=GRID,strict_loss_budget=str(gap),
        tie_break_optimality_established=False,executable_portfolio=False,lower_bound_updated=False,data_authenticated=False,future_performance_guaranteed=False,solver_calls=0)

def verify(evidence,*,expected_binding_sha256):
    core.require(expected_binding_sha256==evidence['binding_sha256']==digest(evidence['binding']),'BINDING_CHANGED')
    rebuilt=build(**evidence['binding']);core.require(canonical(evidence)==canonical(rebuilt),'LOSS_EVIDENCE_CHANGED')
    return dict(status='VERIFIED_EXACT_JOINT_LOSS_NECESSARY_CONDITION')

def inspect_point(evidence,quantities):
    """Diagnostics only; verifies source proof and a complete feasible integer point."""
    verify(evidence,expected_binding_sha256=evidence['binding_sha256'])
    binding=evidence['binding'];p=core.prepare(**binding['inputs']);value,_,_=core.objective(p,quantities)
    core.require(all(lo<=quantities.get(s,0)<=hi for s,(lo,hi) in binding['box'].items()),'POINT_OUTSIDE_BOX')
    lam=F(binding['dual_lambda']);cost=sum((p['cost'][s]*quantities.get(s,0) for s in p['ids']),F(0))
    budget_loss=lam*(p['spendable']-cost)
    core.require(budget_loss>=0,'POINT_RELAXATION_BUDGET')
    pieces={s:F(evidence['reduced_coefficients'][s])*(evidence['preferred_endpoints'][s]-quantities.get(s,0)) for s in p['ids']}
    core.require(all(v>=0 for v in pieces.values()),'NEGATIVE_LOSS')
    loss=budget_loss+sum(pieces.values(),F(0));coeff=evidence['anchor_proof']['linear_coefficients'];linear=F(evidence['constant'])+sum((F(coeff[s])*quantities.get(s,0) for s in p['ids']),F(0))
    core.require(loss==F(evidence['linear_dual_upper'])-linear,'LOSS_IDENTITY_FAILED')
    return dict(loss=str(loss),linear_sum=str(linear),excluded_for_strict_improvement=loss>=F(evidence['strict_loss_budget']),product=str(value))
