"""Full-domain continuous anchors, certified exclusively by exact AM-GM.

Fixed SLSQP settings are numerical tolerances, not return-fit parameters.
Float success is diagnostic only. verify never imports or runs the optimizer.
Inherited bound is re-proven from frozen multi-anchor evidence on a containing
box; a naked claimed upper bound is never accepted. No executable portfolio or
lower bound is produced.
"""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
import math
from backtest import quantity_integer_box_certificate_prototype as core
from backtest import quantity_multi_anchor_bound_prototype as multi

SETTINGS=dict(method='SLSQP',maxiter=2000,ftol=1e-12,quantity_grid_denominator=100000000)
SCHEMA='CONTINUOUS_ANCHOR_EXACT_BOUND_V1'
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return sha256(canonical(v)).hexdigest()
def require(v,m):core.require(v,m)

def _context(inputs,box,inherited_evidence):
    p=core.prepare(**inputs);binding=inherited_evidence['binding']
    require(canonical(binding['inputs'])==canonical(inputs),'INHERITED_INPUT_CHANGED')
    require(canonical(inherited_evidence)==canonical(multi.bound(**binding)),'INHERITED_PROOF_CHANGED')
    require(set(box)==set(p['ids']) and all(type(b)is list and len(b)==2 and all(type(x)is int for x in b) and 0<=b[0]<=b[1] for b in box.values()),'BOX_DOMAIN')
    outer=binding['box']
    require(all(outer[s][0]<=box[s][0]<=box[s][1]<=outer[s][1] for s in p['ids']),'BOX_NOT_CONTAINED')
    empty=core.box_bound(p,box,binding['incumbent'])
    return p,empty

def _repair(p,box,candidate):
    require(type(candidate)is dict and set(candidate)==set(p['ids']),'CANDIDATE_DOMAIN')
    require(all(type(v)is float and math.isfinite(v) for v in candidate.values()),'FINITE_FLOAT_CANDIDATE_REQUIRED')
    require(all(v>=0 for v in candidate.values()),'NEGATIVE_CANDIDATE')
    grid=SETTINGS['quantity_grid_denominator'];q={}
    for s in p['ids']:
        lo,hi=box[s];v=min(F(hi),max(F(lo),F(repr(candidate[s]))))
        q[s]=F(lo)+F(((v-lo)*grid).__floor__(),grid)
    lower={s:F(box[s][0]) for s in p['ids']}
    spent=sum((p['cost'][s]*q[s] for s in p['ids']),F(0));floorcost=sum((p['cost'][s]*lower[s] for s in p['ids']),F(0))
    require(floorcost<=p['spendable'],'LOWER_INFEASIBLE')
    if spent>p['spendable']:
        t=(p['spendable']-floorcost)/(spent-floorcost)
        q={s:lower[s]+t*(q[s]-lower[s]) for s in p['ids']}
    require(all(box[s][0]<=q[s]<=box[s][1] for s in p['ids']),'REPAIR_BOX')
    require(sum((p['cost'][s]*q[s] for s in p['ids']),F(0))<=p['spendable'],'REPAIR_BUDGET')
    return {s:str(q[s]) for s in p['ids']}

def _evidence(inputs,box,inherited_evidence,candidate,diagnostics):
    p,empty=_context(inputs,box,inherited_evidence)
    require(type(diagnostics)is dict and set(diagnostics)=={'success','status','iterations','message'},'DIAGNOSTIC_FIELDS')
    require(type(diagnostics['success'])is bool and type(diagnostics['status'])is int and type(diagnostics['iterations'])is int and diagnostics['iterations']>=0 and type(diagnostics['message'])is str,'DIAGNOSTIC_TYPES')
    binding=dict(inputs=deepcopy(inputs),box=deepcopy(box),inherited_evidence=deepcopy(inherited_evidence))
    base=dict(schema=SCHEMA,scope='SUPPLIED_INTEGER_TRAINING_BOX_OBJECTIVE_UPPER_BOUND',binding=binding,binding_sha256=digest(binding),settings=deepcopy(SETTINGS),candidate=deepcopy(candidate),solver_diagnostics=deepcopy(diagnostics),solver_optimality_trusted=False,executable_portfolio=False,lower_bound_updated=False,data_authenticated=False,future_performance_guaranteed=False)
    if empty['empty']:
        require(candidate is None,'EMPTY_BOX_CANDIDATE')
        return dict(base,empty=True,empty_proof=empty,repaired_quantities=None,anchor=None,upper_product=None)
    repaired=_repair(p,box,candidate);anchor=multi.anchor_bound(p,box,repaired)
    require(not inherited_evidence['empty'],'INCONSISTENT_INHERITED_EMPTY')
    upper=min(F(inherited_evidence['upper_product']),F(anchor['upper_product']))
    return dict(base,empty=False,empty_proof=None,repaired_quantities=repaired,anchor=anchor,upper_product=str(upper))

def from_candidate(*,inputs,box,inherited_evidence,candidate,diagnostics):
    """Certify an untrusted full float candidate; diagnostics confer no authority."""
    return _evidence(inputs,box,inherited_evidence,candidate,diagnostics)

def verify(evidence,*,expected_binding_sha256):
    require(type(expected_binding_sha256)is str and evidence['binding_sha256']==expected_binding_sha256==digest(evidence['binding']),'BINDING_CHANGED')
    rebuilt=_evidence(**evidence['binding'],candidate=evidence['candidate'],diagnostics=evidence['solver_diagnostics'])
    require(canonical(evidence)==canonical(rebuilt),'EVIDENCE_CHANGED')
    return dict(status='VERIFIED_EXACT_ANCHOR_BOUND',empty=rebuilt['empty'],upper_product=rebuilt['upper_product'],solver_optimality_trusted=False)

def optimize(*,inputs,box,inherited_evidence):
    """One fixed full-variable synthetic/research solve, never a portfolio order."""
    p,empty=_context(inputs,box,inherited_evidence)
    if empty['empty']:
        return _evidence(inputs,box,inherited_evidence,None,dict(success=False,status=-1,iterations=0,message='EXACT_EMPTY_BOX_NO_SOLVER'))
    if all(lo==hi for lo,hi in box.values()):
        return _evidence(inputs,box,inherited_evidence,{s:float(box[s][0]) for s in p['ids']},dict(success=False,status=-2,iterations=0,message='FIXED_BOX_NO_SOLVER'))
    import numpy as np
    from scipy.optimize import minimize
    ids=p['ids'];cash=p['cash']
    costs=np.array([float(p['cost'][s]/cash) for s in ids]);lo=np.array([float(p['cost'][s]*box[s][0]/cash) for s in ids]);hi=np.array([float(p['cost'][s]*box[s][1]/cash) for s in ids])
    matrix=np.array([[float((p['prices'][s]*r[s]-p['cost'][s])/p['cost'][s]) for s in ids] for r in p['scenarios']])
    budget=float(p['spendable']/cash)
    require(np.isfinite(costs).all() and (costs>0).all() and np.isfinite(lo).all() and np.isfinite(hi).all() and np.isfinite(matrix).all() and math.isfinite(budget),'FLOAT_RANGE')
    # Exact lower corner must be a positive reference before the numerical call.
    multi.anchor_bound(p,box,{s:str(box[s][0]) for s in ids})
    def fun(z):
        wealth=1+matrix@z
        return float(-np.mean(np.log(wealth))) if (wealth>0).all() else float('inf')
    def jac(z):
        wealth=1+matrix@z
        require((wealth>0).all(),'FLOAT_WEALTH_NONPOSITIVE')
        return -np.mean(matrix/wealth[:,None],axis=0)
    result=minimize(fun,lo,method=SETTINGS['method'],jac=jac,bounds=list(zip(lo,hi)),constraints=[dict(type='ineq',fun=lambda z:budget-float(np.sum(z)),jac=lambda z:-np.ones(len(ids)))],options=dict(maxiter=SETTINGS['maxiter'],ftol=SETTINGS['ftol']))
    require(len(result.x)==len(ids) and np.isfinite(result.x).all(),'SOLVER_VECTOR')
    candidate={s:float(result.x[i]/costs[i]) for i,s in enumerate(ids)}
    diagnostics=dict(success=bool(result.success),status=int(getattr(result,'status',-3)),iterations=int(getattr(result,'nit',0)),message=str(result.message))
    return _evidence(inputs,box,inherited_evidence,candidate,diagnostics)
