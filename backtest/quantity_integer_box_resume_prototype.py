"""Append-only continuation of externally authenticated integer-box frontiers.

Never calls solve or rebuilds a root search queue. Every parent certificate is
verified before work; inherited ledger and frontier ordering remain intact.
Raw SHA approval is external. Ancestor hashes bind saved bytes, not an assertion
that unavailable ancestor files have been independently reopened here.
"""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from backtest import quantity_integer_box_certificate_prototype as core


def resume(*,parent_raw,expected_parent_sha256,expected_input_sha256,additional_node_budget):
    core.require(type(parent_raw)is bytes,'PARENT_RAW_BYTES_REQUIRED')
    core.require(sha256(parent_raw).hexdigest()==expected_parent_sha256,'PARENT_RAW_HASH_CHANGED')
    core.require(type(additional_node_budget)is int and additional_node_budget>=0,'ADDITIONAL_NODE_BUDGET_REQUIRED')
    parent=json.loads(parent_raw)
    core.verify(parent,expected_input_sha256=expected_input_sha256)
    previous=parent.get('resume_binding')
    ancestors=[]
    if previous is not None:
        core.require(type(previous)is dict and previous.get('schema')=='INTEGER_BOX_RESUME_BINDING_V1','PARENT_RESUME_SCHEMA')
        ancestors=previous['ancestor_raw_sha256']
        core.require(type(ancestors)is list and ancestors and all(type(h)is str and len(h)==64 and all(c in '0123456789abcdef' for c in h) for h in ancestors),'PARENT_ANCESTRY_INVALID')
        core.require(ancestors[-1]==previous['parent_raw_sha256'] and previous['input_sha256']==expected_input_sha256,'PARENT_RESUME_BINDING_CHANGED')
        core.require(all(type(previous.get(k))is int and previous[k]>=0 for k in ('parent_processed_nodes','additional_node_budget','added_processed_nodes')) and previous['added_processed_nodes']<=previous['additional_node_budget'] and previous['parent_processed_nodes']+previous['added_processed_nodes']==parent['processed_nodes'],'PARENT_RESUME_COUNTS_CHANGED')
    result=deepcopy(parent);p=core.prepare(**parent['inputs'])
    incumbent=deepcopy(parent['selected']);best,_,notional=core.objective(p,incumbent)
    rank=lambda q,v,n:(v,-n,tuple(sorted(q.items())))
    best_rank=rank(incumbent,best,notional)
    ledger=result['coverage_ledger'];pending=result['unsearched_frontier'];added=0
    while pending and added<additional_node_budget:
        node=pending.pop(0);added+=1;box=node['box'];bound=node['bound']
        if bound['empty']:ledger.append(dict(node,terminal='INFEASIBLE'));continue
        if F(bound['upper'])<best:ledger.append(dict(node,terminal='UPPER_STRICTLY_BELOW_INCUMBENT',incumbent_product=str(best)));continue
        axes=[s for s in p['ids'] if box[s][0]<box[s][1]]
        if not axes:
            q={s:box[s][0] for s in p['ids'] if box[s][0]};v,_,n=core.objective(p,q)
            if rank(q,v,n)>best_rank:incumbent=q;best=v;best_rank=rank(q,v,n)
            ledger.append(dict(node,terminal='EVALUATED',product=str(v)));continue
        axis=min(axes,key=lambda s:(-(box[s][1]-box[s][0]),s));mid=sum(box[axis])//2;children=[]
        for label,limits in [('0',[box[axis][0],mid]),('1',[mid+1,box[axis][1]])]:
            child=deepcopy(box);child[axis]=limits;identifier=node['id']+label
            pending.append(dict(id=identifier,box=child,bound=core.box_bound(p,child,incumbent)));children.append(identifier)
        ledger.append(dict(node,terminal='SPLIT',axis=axis,midpoint=mid,children=children))
    upper=max([best]+[F(node['bound']['upper']) for node in pending if not node['bound']['empty']])
    result.update(selected=incumbent,lower_product=str(best),upper_product=str(upper),product_gap=str(upper-best),
        status='COMPLETE_INTEGER_DOMAIN_COVERAGE' if not pending else 'NODE_BUDGET_STOPPED_UNRESOLVED',objective_value_optimal=not pending,
        node_budget=parent['node_budget']+additional_node_budget,processed_nodes=parent['processed_nodes']+added,
        resume_binding=dict(schema='INTEGER_BOX_RESUME_BINDING_V1',parent_raw_sha256=expected_parent_sha256,input_sha256=expected_input_sha256,
            ancestor_raw_sha256=ancestors+[expected_parent_sha256],parent_processed_nodes=parent['processed_nodes'],additional_node_budget=additional_node_budget,added_processed_nodes=added))
    core.require(result['coverage_ledger'][:len(parent['coverage_ledger'])]==parent['coverage_ledger'],'INHERITED_LEDGER_CHANGED')
    core.verify(result,expected_input_sha256=expected_input_sha256)
    return result
