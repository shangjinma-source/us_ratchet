"""New supplemental certificate over an unchanged verified parent partition.

Consumes externally hashed saved bounds, never searches or rewrites the parent.
Every original frontier node gets exactly one bound bound to parent inputs, box,
and incumbent. A valid upper <= incumbent closes objective VALUE only; equality
cannot prove the incumbent wins tie-breaking. Unclosed boxes remain explicit.
"""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from backtest import quantity_integer_box_certificate_prototype as core
from backtest import quantity_multi_anchor_bound_prototype as multi


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def _load(raw,expected):
    core.require(type(raw)is bytes and sha256(raw).hexdigest()==expected,'EXTERNAL_RAW_HASH_CHANGED')
    return json.loads(raw)


def supplement(*,parent_raw,expected_parent_sha256,expected_input_sha256,evidence_manifest_raw,expected_manifest_sha256,evidence_raw_by_id):
    parent=_load(parent_raw,expected_parent_sha256)
    core.verify(parent,expected_input_sha256=expected_input_sha256)
    manifest=_load(evidence_manifest_raw,expected_manifest_sha256)
    rows=manifest['rows'];core.require(type(rows)is list,'MANIFEST_ROWS_REQUIRED')
    ids=[r['id'] for r in rows];frontier={n['id']:n for n in parent['unsearched_frontier']}
    core.require(len(ids)==len(set(ids)) and set(ids)==set(frontier)==set(evidence_raw_by_id),'FRONTIER_EVIDENCE_COVERAGE_MISMATCH')
    by_id={r['id']:r for r in rows};lower=F(parent['lower_product']);closed=[];remaining=[];verified=[]
    for node in parent['unsearched_frontier']:
        identifier=node['id'];ref=by_id[identifier]
        evidence=_load(evidence_raw_by_id[identifier],ref['sha256'])
        required=dict(inputs=parent['inputs'],box=node['box'],incumbent=parent['selected'])
        core.require(_canonical(evidence['binding'])==_canonical(required),'PARENT_BOX_INPUT_OR_INCUMBENT_MISMATCH')
        required_hash=multi.canonical_hash(required)
        core.require(ref['binding_sha256']==required_hash,'MANIFEST_BINDING_CHANGED')
        multi.verify(evidence,expected_binding_sha256=required_hash)
        core.require(_canonical(evidence)==_canonical(multi.bound(**required)),'MULTI_ANCHOR_STRICT_EVIDENCE_CHANGED')
        proof=dict(id=identifier,evidence_sha256=ref['sha256'],binding_sha256=required_hash,upper_product=evidence['upper_product'],empty=evidence['empty'])
        verified.append(proof)
        if evidence['empty'] or F(evidence['upper_product'])<=lower:
            closed.append(dict(proof,reason='EMPTY_RELAXATION' if evidence['empty'] else 'VALID_UPPER_NOT_ABOVE_INCUMBENT'))
        else:
            remaining.append(dict(parent_node=deepcopy(node),supplemental_bound=proof))
    upper=max([lower]+[F(r['supplemental_bound']['upper_product']) for r in remaining])
    return dict(schema='INTEGER_BOX_SUPPLEMENTAL_CERTIFICATE_V1',parent_raw_sha256=expected_parent_sha256,input_sha256=expected_input_sha256,
        evidence_manifest_raw_sha256=expected_manifest_sha256,parent_processed_nodes=parent['processed_nodes'],parent_ledger_sha256=multi.canonical_hash(parent['coverage_ledger']),
        parent_frontier_count=len(frontier),verified_bounds=verified,closed_nodes=closed,remaining_frontier=remaining,selected=deepcopy(parent['selected']),
        lower_product=str(lower),upper_product=str(upper),product_gap=str(upper-lower),objective_value_optimal=not remaining,tie_break_optimality_established=False,
        status='COMPLETE_SUPPLEMENTAL_OBJECTIVE_COVERAGE' if not remaining else 'SUPPLEMENTAL_GAP_UNRESOLVED',scope='SUPPLIED_INTEGER_TRAINING_DOMAIN_ONLY',
        parent_ledger_modified=False,new_search_nodes=0,data_authenticated=False,future_performance_guaranteed=False)


def verify(certificate,**bound_sources):
    rebuilt=supplement(**bound_sources)
    core.require(_canonical(certificate)==_canonical(rebuilt),'SUPPLEMENTAL_CERTIFICATE_CHANGED')
    return dict(status='VERIFIED_SUPPLEMENTAL_OBJECTIVE_COVERAGE',objective_value_optimal=rebuilt['objective_value_optimal'],remaining_boxes=len(rebuilt['remaining_frontier']),upper_product=rebuilt['upper_product'])
