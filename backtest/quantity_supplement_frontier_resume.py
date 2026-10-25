"""Isolated continuation of a fully bound supplemental partition.

Fixed rule: FIFO boxes; split the axis maximizing price * integer width, then
ascending SID; integer midpoint, lower child first. Four-anchor rule is frozen
by the imported bound module. No new root and no reopening supplemental closures.
Only supplied training objective value may be certified; tie-break is not.
"""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from backtest import quantity_box_supplemental_certificate as supplemental
from backtest import quantity_multi_anchor_bound_prototype as multi
from backtest import quantity_integer_box_certificate_prototype as core

RULE='FIFO_MAX_PRICE_TIMES_INTEGER_WIDTH_MIDPOINT_LOWER_FIRST_V1'


def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def load(raw,h):
    core.require(type(raw)is bytes and sha256(raw).hexdigest()==h,'RAW_HASH_CHANGED');return json.loads(raw)


def context(*,supplement_raw,expected_supplement_sha256,bound_sources):
    s=load(supplement_raw,expected_supplement_sha256);supplemental.verify(s,**bound_sources)
    parent=load(bound_sources['parent_raw'],bound_sources['expected_parent_sha256'])
    binding=dict(supplement_sha256=expected_supplement_sha256,parent_sha256=bound_sources['expected_parent_sha256'],manifest_sha256=bound_sources['expected_manifest_sha256'],input_sha256=bound_sources['expected_input_sha256'])
    return s,parent,binding


def verify(certificate,*,supplement_raw,expected_supplement_sha256,bound_sources):
    s,parent,binding=context(supplement_raw=supplement_raw,expected_supplement_sha256=expected_supplement_sha256,bound_sources=bound_sources)
    c=certificate;p=core.prepare(**parent['inputs'])
    link=c.get('parent_continuation_raw_sha256')
    core.require(link is None or (type(link)is str and len(link)==64 and all(ch in '0123456789abcdef' for ch in link)),'CONTINUATION_LINK_INVALID')
    core.require(c.get('schema')=='SUPPLEMENT_FRONTIER_RESUME_V1' and c.get('rule')==RULE and c.get('scope')=='SUPPLIED_INTEGER_TRAINING_DOMAIN_ONLY' and canonical(c['binding'])==canonical(binding),'RESUME_BINDING_CHANGED')
    core.require(c.get('tie_break_optimality_established')is False and c.get('data_authenticated')is False and c.get('future_performance_guaranteed')is False,'AUTHORITY_CHANGED')
    core.require(type(c.get('node_budget'))is int and c['node_budget']>=0 and type(c.get('processed_nodes'))is int and c['processed_nodes']>=0 and type(c.get('objective_value_optimal'))is bool,'SUMMARY_TYPES')
    core.require(c['original_closed_nodes_sha256']==sha256(canonical(s['closed_nodes'])).hexdigest() and c['original_closed_count']==len(s['closed_nodes']) and type(c['original_closed_count'])is int,'CLOSED_DOMAIN_CHANGED')
    value,_,_=core.objective(p,c['selected']);core.require(value>=F(s['lower_product']) and str(value)==c['lower_product'],'LOWER_CHANGED')
    expected={r['parent_node']['id']:r['parent_node']['box'] for r in s['remaining_frontier']};seen=set();queue=list(expected)
    def check_node(node):
        identifier=node['id'];core.require(identifier in expected and identifier not in seen and canonical(node['box'])==canonical(expected[identifier]),'PARTITION_CHANGED');seen.add(identifier)
        ev=node['bound'];core.require(canonical(ev['binding']['inputs'])==canonical(parent['inputs']) and canonical(ev['binding']['box'])==canonical(node['box']),'NODE_INPUT_CHANGED')
        core.require(canonical(ev)==canonical(multi.bound(**ev['binding'])),'BOUND_CHANGED')
        return ev
    for node in c['coverage_ledger']:
        core.require(queue and node['id']==queue.pop(0),'FIFO_LEDGER_ORDER_CHANGED')
        ev=check_node(node);status=node['terminal']
        if status=='SPLIT':
            axes=[sid for sid in p['ids'] if node['box'][sid][0]<node['box'][sid][1]];core.require(axes,'SPLIT_LEAF')
            axis=min(axes,key=lambda sid:(-p['prices'][sid]*(node['box'][sid][1]-node['box'][sid][0]),sid));lo,hi=node['box'][axis];mid=(lo+hi)//2
            core.require(node['axis']==axis and type(node['midpoint'])is int and node['midpoint']==mid and node['children']==[node['id']+'0',node['id']+'1'],'SPLIT_RULE_CHANGED')
            for suffix,limits in [('0',[lo,mid]),('1',[mid+1,hi])]:
                box=deepcopy(node['box']);box[axis]=limits;expected[node['id']+suffix]=box
                queue.append(node['id']+suffix)
        elif status=='CLOSED_BY_UPPER':core.require(ev['empty'] or F(ev['upper_product'])<=value,'INVALID_PRUNE')
        elif status=='EVALUATED':
            core.require(all(lo==hi for lo,hi in node['box'].values()),'LEAF_CHANGED')
            v,_,_=core.objective(p,{sid:lo for sid,(lo,_) in node['box'].items() if lo});core.require(str(v)==node['product'] and v<=value,'LEAF_PRODUCT_CHANGED')
        else:raise ValueError('UNKNOWN_NODE_TERMINAL')
    upper=value
    core.require([n['id'] for n in c['unsearched_frontier']]==queue,'FIFO_FRONTIER_ORDER_CHANGED')
    for node in c['unsearched_frontier']:
        ev=check_node(node)
        if not ev['empty']:upper=max(upper,F(ev['upper_product']))
    core.require(seen==set(expected),'DOMAIN_OMITTED')
    complete=not c['unsearched_frontier'];core.require(c['objective_value_optimal']==complete and c['status']==('COMPLETE_INTEGER_OBJECTIVE_COVERAGE' if complete else 'NODE_BUDGET_STOPPED_UNRESOLVED'),'FALSE_COMPLETION')
    core.require(c['processed_nodes']==len(c['coverage_ledger'])<=c['node_budget'] and c['upper_product']==str(upper) and c['product_gap']==str(upper-value),'SUMMARY_CHANGED')
    return dict(status='VERIFIED_SUPPLEMENT_CONTINUATION',objective_value_optimal=complete)


def verify_transition(certificate,*,previous_raw,expected_previous_sha256,**context_args):
    """Additionally bind immediate lineage; verify alone certifies mathematics."""
    previous=load(previous_raw,expected_previous_sha256)
    verify(previous,**context_args);result=verify(certificate,**context_args)
    core.require(certificate['parent_continuation_raw_sha256']==expected_previous_sha256,'CONTINUATION_LINK_CHANGED')
    core.require(canonical(certificate['coverage_ledger'][:len(previous['coverage_ledger'])])==canonical(previous['coverage_ledger']),'INHERITED_LEDGER_CHANGED')
    core.require(certificate['processed_nodes']>=previous['processed_nodes'] and certificate['node_budget']>=previous['node_budget'] and certificate['processed_nodes']-previous['processed_nodes']<=certificate['node_budget']-previous['node_budget'],'CONTINUATION_BUDGET_CHANGED')
    return dict(result,immediate_parent_raw_hash_verified=True)


def resume(*,supplement_raw,expected_supplement_sha256,bound_sources,additional_node_budget,previous_raw=None,expected_previous_sha256=None):
    core.require(type(additional_node_budget)is int and additional_node_budget>=0,'NODE_BUDGET_REQUIRED')
    args=dict(supplement_raw=supplement_raw,expected_supplement_sha256=expected_supplement_sha256,bound_sources=bound_sources)
    s,parent,binding=context(**args);p=core.prepare(**parent['inputs'])
    if previous_raw is not None:
        prior=load(previous_raw,expected_previous_sha256);verify(prior,**args);out=deepcopy(prior)
    else:
        core.require(expected_previous_sha256 is None,'PREVIOUS_BYTES_REQUIRED');prior=None
        frontier=[]
        for row in s['remaining_frontier']:
            node=row['parent_node'];ev=json.loads(bound_sources['evidence_raw_by_id'][node['id']])
            frontier.append(dict(id=node['id'],box=deepcopy(node['box']),bound=ev))
        out=dict(schema='SUPPLEMENT_FRONTIER_RESUME_V1',rule=RULE,scope='SUPPLIED_INTEGER_TRAINING_DOMAIN_ONLY',binding=binding,original_closed_nodes_sha256=sha256(canonical(s['closed_nodes'])).hexdigest(),original_closed_count=len(s['closed_nodes']),selected=deepcopy(s['selected']),coverage_ledger=[],unsearched_frontier=frontier,node_budget=0,processed_nodes=0,tie_break_optimality_established=False,data_authenticated=False,future_performance_guaranteed=False)
    incumbent=out['selected'];best,_,notional=core.objective(p,incumbent);rank=lambda q,v,n:(v,-n,tuple(sorted(q.items())));best_rank=rank(incumbent,best,notional)
    pending=out['unsearched_frontier'];ledger=out['coverage_ledger'];added=0
    while pending and added<additional_node_budget:
        node=pending.pop(0);added+=1;ev=node['bound'];box=node['box']
        if ev['empty'] or F(ev['upper_product'])<=best:ledger.append(dict(node,terminal='CLOSED_BY_UPPER'));continue
        axes=[sid for sid in p['ids'] if box[sid][0]<box[sid][1]]
        if not axes:
            q={sid:box[sid][0] for sid in p['ids'] if box[sid][0]};v,_,n=core.objective(p,q)
            if rank(q,v,n)>best_rank:incumbent=q;best=v;best_rank=rank(q,v,n)
            ledger.append(dict(node,terminal='EVALUATED',product=str(v)));continue
        axis=min(axes,key=lambda sid:(-p['prices'][sid]*(box[sid][1]-box[sid][0]),sid));mid=sum(box[axis])//2;children=[]
        for suffix,limits in [('0',[box[axis][0],mid]),('1',[mid+1,box[axis][1]])]:
            child=deepcopy(box);child[axis]=limits;identifier=node['id']+suffix
            pending.append(dict(id=identifier,box=child,bound=multi.bound(inputs=parent['inputs'],box=child,incumbent=incumbent)));children.append(identifier)
        ledger.append(dict(node,terminal='SPLIT',axis=axis,midpoint=mid,children=children))
    upper=max([best]+[F(n['bound']['upper_product']) for n in pending if not n['bound']['empty']])
    out.update(selected=incumbent,lower_product=str(best),upper_product=str(upper),product_gap=str(upper-best),objective_value_optimal=not pending,status='COMPLETE_INTEGER_OBJECTIVE_COVERAGE' if not pending else 'NODE_BUDGET_STOPPED_UNRESOLVED',node_budget=out['node_budget']+additional_node_budget,processed_nodes=out['processed_nodes']+added)
    out['parent_continuation_raw_sha256']=expected_previous_sha256
    if prior is not None:core.require(canonical(ledger[:len(prior['coverage_ledger'])])==canonical(prior['coverage_ledger']),'INHERITED_LEDGER_CHANGED')
    if prior is not None:verify_transition(out,previous_raw=previous_raw,expected_previous_sha256=expected_previous_sha256,**args)
    else:verify(out,**args)
    return out
