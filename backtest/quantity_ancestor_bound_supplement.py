"""Exact inherited upper-bound evidence over an unchanged continuation.

No search. An upper bound for a box also bounds each explicitly contained child.
Proof identities remain attached to their original nodes. Equality closes only
objective value, never the tie-break winner. All original frontier nodes remain
accounted for in closed/remaining rows.
"""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from backtest import quantity_supplement_frontier_resume as continuation
from backtest import quantity_integer_box_certificate_prototype as core


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def build(*,continuation_raw,expected_continuation_sha256,continuation_sources):
    core.require(type(continuation_raw)is bytes and sha256(continuation_raw).hexdigest()==expected_continuation_sha256,'CONTINUATION_RAW_HASH_CHANGED')
    c=json.loads(continuation_raw);continuation.verify(c,**continuation_sources)
    s,parent,binding=continuation.context(**continuation_sources)
    roots={r['parent_node']['id']:r for r in s['remaining_frontier']}
    nodes={n['id']:n for n in c['coverage_ledger']+c['unsearched_frontier']};parents={}
    for node in c['coverage_ledger']:
        if node['terminal']=='SPLIT':
            for child in node['children']:
                core.require(child not in parents,'DUPLICATE_PARENT')
                core.require(child in nodes,'MISSING_CHILD')
                pbox=node['box'];box=nodes[child]['box']
                core.require(set(box)==set(pbox) and all(pbox[sid][0]<=box[sid][0]<=box[sid][1]<=pbox[sid][1] for sid in box),'ANCESTOR_CONTAINMENT_FAILED')
                parents[child]=node['id']
    lower=F(c['lower_product']);rows=[];closed=[];remaining=[]
    for node in c['unsearched_frontier']:
        identifier=node['id'];path=[];seen=set();candidate_bounds=[]
        while True:
            core.require(identifier not in seen and identifier in nodes,'ANCESTOR_PATH_INVALID');seen.add(identifier)
            ancestor=nodes[identifier];evidence=ancestor['bound']
            proof=dict(node_id=identifier,proof_kind='CONTINUATION_LOCAL_BOUND',proof_sha256=sha256(canonical(evidence)).hexdigest(),empty=evidence['empty'],upper_product=evidence['upper_product'])
            candidate_bounds.append(proof)
            if identifier not in parents:break
            parent_id=parents[identifier]
            path.append(dict(parent_id=parent_id,child_id=identifier))
            identifier=parent_id
        core.require(identifier in roots,'UNBOUND_ANCESTOR_ROOT')
        original=roots[identifier];root_box=original['parent_node']['box']
        core.require(canonical(root_box)==canonical(nodes[identifier]['box']),'SUPPLEMENT_ROOT_BOX_CHANGED')
        proof=original['supplemental_bound']
        candidate_bounds.append(dict(node_id=identifier,proof_kind='ORIGINAL_SUPPLEMENT_BOUND',proof_sha256=proof['evidence_sha256'],empty=proof['empty'],upper_product=proof['upper_product']))
        empty=any(p['empty'] for p in candidate_bounds)
        chosen=None if empty else min(candidate_bounds,key=lambda p:F(p['upper_product']))
        effective=None if empty else chosen['upper_product']
        row=dict(id=node['id'],box=deepcopy(node['box']),parent_child_path=path,original_bounds=candidate_bounds,empty=empty,
            effective_upper_product=effective,binding_proof=deepcopy(chosen),closed_by_value=empty or F(effective)<=lower)
        rows.append(row)
        (closed if row['closed_by_value'] else remaining).append(node['id'])
    upper=max([lower]+[F(r['effective_upper_product']) for r in rows if not r['closed_by_value']])
    return dict(schema='INTEGER_ANCESTOR_BOUND_SUPPLEMENT_V1',scope='SUPPLIED_INTEGER_TRAINING_DOMAIN_OBJECTIVE_VALUE_ONLY',continuation_raw_sha256=expected_continuation_sha256,
        binding=deepcopy(binding),original_frontier_count=len(c['unsearched_frontier']),rows=rows,closed_node_ids=closed,remaining_node_ids=remaining,
        lower_product=str(lower),upper_product=str(upper),product_gap=str(upper-lower),objective_value_optimal=not remaining,tie_break_optimality_established=False,
        search_nodes=0,parent_modified=False,data_authenticated=False,future_performance_guaranteed=False,
        status='COMPLETE_ANCESTOR_OBJECTIVE_COVERAGE' if not remaining else 'ANCESTOR_GAP_UNRESOLVED')


def verify(certificate,**bound_sources):
    expected=build(**bound_sources)
    core.require(canonical(certificate)==canonical(expected),'ANCESTOR_CERTIFICATE_CHANGED')
    return dict(status='VERIFIED_ANCESTOR_BOUND_COVERAGE',remaining_boxes=len(expected['remaining_node_ids']),objective_value_optimal=expected['objective_value_optimal'])
