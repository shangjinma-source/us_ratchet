"""One exact SID-ordered coordinate fixing pass using a saved rational anchor.

Each successful split closes q_i>=lo_i+1 by an exact upper bound <= incumbent,
then retains q_i=lo_i. All identities remain. Value-only, not tie-break proof.
No optimizer, support heuristic, changed objective or real data access.
"""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from backtest import quantity_continuous_anchor_bound as saved_anchor
from backtest import quantity_integer_box_certificate_prototype as core
from backtest import quantity_multi_anchor_bound_prototype as multi

def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def build(*,anchor_raw,expected_anchor_sha256,expected_anchor_binding_sha256,incumbent):
    core.require(type(anchor_raw)is bytes and sha256(anchor_raw).hexdigest()==expected_anchor_sha256,'ANCHOR_RAW_CHANGED')
    source=json.loads(anchor_raw);saved_anchor.verify(source,expected_binding_sha256=expected_anchor_binding_sha256)
    core.require(not source['empty'],'NONEMPTY_ANCHOR_REQUIRED')
    inputs=source['binding']['inputs'];original=source['binding']['box'];p=core.prepare(**inputs)
    lower=core.objective(p,incumbent)[0];box=deepcopy(original);rows=[];closed=[]
    def bound(child):
        guard=core.box_bound(p,child,incumbent)
        if guard['empty']:return dict(empty=True,reason=guard['reason'],anchor=None,upper_product=None)
        proof=multi.anchor_bound(p,child,source['repaired_quantities'])
        upper=min(F(proof['upper_product']),F(source['upper_product']))
        return dict(empty=False,reason=None,anchor=proof,upper_product=str(upper))
    for sid in p['ids']:
        lo,hi=box[sid]
        if lo==hi:continue
        before=deepcopy(box);tail=deepcopy(box);tail[sid]=[lo+1,hi];proof=bound(tail)
        fix=proof['empty'] or F(proof['upper_product'])<=lower
        row=dict(sid=sid,before_box=before,tested_tail=tail,bound=proof,fix_lower=fix)
        if fix:
            box[sid]=[lo,lo];row['retained_box']=deepcopy(box);closed.append(dict(sid=sid,box=tail,proof_row=len(rows)))
        else:row['retained_box']=deepcopy(box)
        rows.append(row)
    remaining=bound(box)
    remaining_closed=remaining['empty'] or F(remaining['upper_product'])<=lower
    upper=lower if remaining_closed else max(lower,F(remaining['upper_product']))
    return dict(schema='EXACT_SAVED_ANCHOR_COORDINATE_FIXING_V1',rule='ONE_PASS_ASCENDING_SID_LOWER_VS_POSITIVE_INCREMENT',scope='SUPPLIED_INTEGER_TRAINING_BOX_OBJECTIVE_VALUE_ONLY',
        binding=dict(anchor_raw_sha256=expected_anchor_sha256,anchor_binding_sha256=expected_anchor_binding_sha256,incumbent=deepcopy(incumbent)),
        original_box=deepcopy(original),rows=rows,closed_regions=closed,remaining_box=box,remaining_bound=remaining,remaining_closed=remaining_closed,
        fixed_coordinate_count=len(closed),remaining_nonfixed_count=sum(lo<hi for lo,hi in box.values()),lower_product=str(lower),upper_product=str(upper),
        objective_value_covered=remaining_closed,tie_break_optimality_established=False,data_authenticated=False,future_performance_guaranteed=False,solver_calls=0)

def verify(certificate,**sources):
    expected=build(**sources)
    core.require(canonical(certificate)==canonical(expected),'FIXING_CERTIFICATE_CHANGED')
    return dict(status='VERIFIED_EXACT_COORDINATE_FIXING',fixed_coordinate_count=expected['fixed_coordinate_count'],objective_value_covered=expected['objective_value_covered'])
