"""Exact FIFO continuation with inherited ancestor caps; frozen sources unchanged.

Capital-span axis, midpoint and lower-first rule are fixed. One source-chain
validation per public operation. Private verification reconstructs local proofs
and the partition topologically; it never invokes resume or searches new nodes.
"""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from backtest import quantity_ancestor_bound_supplement as ancestor
from backtest import quantity_multi_anchor_bound_prototype as multi
from backtest import quantity_integer_box_certificate_prototype as core

RULE='FIFO_MAX_PRICE_TIMES_INTEGER_WIDTH_MIDPOINT_LOWER_FIRST_V1'
SCHEMA='ANCESTOR_CAPPED_RESUME_V1'
SCOPE='SUPPLIED_INTEGER_TRAINING_DOMAIN_OBJECTIVE_VALUE_ONLY'

def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def require(v,msg):core.require(v,msg)
def load(raw,h):
    require(type(raw)is bytes and sha256(raw).hexdigest()==h,'RAW_HASH_CHANGED')
    return json.loads(raw)

def context(ancestor_raw,expected_ancestor_sha256,ancestor_sources):
    a=load(ancestor_raw,expected_ancestor_sha256)
    ancestor.verify(a,**ancestor_sources)
    c=json.loads(ancestor_sources['continuation_raw'])
    inputs=json.loads(ancestor_sources['continuation_sources']['bound_sources']['parent_raw'])['inputs']
    nodes={n['id']:n for n in c['unsearched_frontier']}
    roots=[]
    for row in a['rows']:
        if row['id'] in a['remaining_node_ids']:
            n=nodes[row['id']]
            roots.append(dict(id=n['id'],box=deepcopy(n['box']),bound=deepcopy(n['bound']),parent_id=None,
                inherited_proof_ref=dict(ancestor_sha256=expected_ancestor_sha256,row_id=row['id'],row_sha256=sha256(canonical(row)).hexdigest()),
                effective_upper_product=row['effective_upper_product'],effective_empty=row['empty']))
    binding=dict(ancestor_sha256=expected_ancestor_sha256,continuation_sha256=ancestor_sources['expected_continuation_sha256'],source_binding=a['binding'],closed_ids_sha256=sha256(canonical(a['closed_node_ids'])).hexdigest())
    return dict(a=a,c=c,inputs=inputs,p=core.prepare(**inputs),roots=roots,binding=binding)

def proof(n):
    return dict(node_id=n['id'],sha256=sha256(canonical({k:n[k] for k in ('id','box','effective_empty','effective_upper_product','inherited_proof_ref')})).hexdigest())

def axis_split(p,n):
    axes=[s for s in p['ids'] if n['box'][s][0]<n['box'][s][1]]
    if not axes:return None,None
    axis=min(axes,key=lambda s:(-p['prices'][s]*(n['box'][s][1]-n['box'][s][0]),s))
    return axis,sum(n['box'][axis])//2

def child_node(ctx,parent,identifier,box,incumbent):
    ev=multi.bound(inputs=ctx['inputs'],box=box,incumbent=incumbent)
    empty=parent['effective_empty'] or ev['empty']
    upper=None if empty else str(min(F(parent['effective_upper_product']),F(ev['upper_product'])))
    return dict(id=identifier,box=box,bound=ev,parent_id=parent['id'],inherited_proof_ref=proof(parent),effective_empty=empty,effective_upper_product=upper)

def initial(ctx):
    return dict(schema=SCHEMA,scope=SCOPE,rule=RULE,binding=deepcopy(ctx['binding']),selected=deepcopy(ctx['c']['selected']),coverage_ledger=[],unsearched_frontier=deepcopy(ctx['roots']),node_budget=0,processed_nodes=0,parent_continuation_raw_sha256=None,tie_break_optimality_established=False,data_authenticated=False,future_performance_guaranteed=False)

def finish(out,ctx):
    lower=core.objective(ctx['p'],out['selected'])[0]
    upper=max([lower]+[F(n['effective_upper_product']) for n in out['unsearched_frontier'] if not n['effective_empty']])
    complete=not out['unsearched_frontier']
    out.update(lower_product=str(lower),upper_product=str(upper),product_gap=str(upper-lower),objective_value_optimal=complete,status='COMPLETE_INTEGER_OBJECTIVE_COVERAGE' if complete else 'NODE_BUDGET_STOPPED_UNRESOLVED')
    return out

def _verify(c,ctx):
    require(type(c.get('node_budget'))is int and c['node_budget']>=0 and type(c.get('processed_nodes'))is int,'BUDGET_TYPE')
    link=c.get('parent_continuation_raw_sha256')
    require(link is None or type(link)is str and len(link)==64 and all(x in '0123456789abcdef' for x in link),'LINK_INVALID')
    inventory=c['coverage_ledger']+c['unsearched_frontier']
    all_nodes={n['id']:n for n in inventory}
    require(len(all_nodes)==len(inventory),'DUPLICATE_NODE')
    expected={n['id']:n for n in ctx['roots']};queue=list(expected);seen=set();cache={}
    lower=core.objective(ctx['p'],c['selected'])[0]
    require(lower>=F(ctx['a']['lower_product']),'LOWER_REGRESSED')
    def node_check(n):
        key=n['id'];require(key in expected and key not in seen,'PARTITION_CHANGED');seen.add(key)
        target=expected[key]
        for field in ('box','parent_id','inherited_proof_ref','effective_upper_product','effective_empty'):
            require(canonical(n[field])==canonical(target[field]),'INHERITANCE_CHANGED')
        ev=n['bound'];binding=ev['binding']
        require(canonical(binding['inputs'])==canonical(ctx['inputs']) and canonical(binding['box'])==canonical(n['box']),'BOUND_INPUT_CHANGED')
        h=sha256(canonical(ev)).hexdigest()
        if h not in cache:
            require(canonical(ev)==canonical(multi.bound(**binding)),'BOUND_CHANGED');cache[h]=True
        if n['parent_id'] is None:require(canonical(ev)==canonical(target['bound']),'ROOT_BOUND_CHANGED')
    for n in c['coverage_ledger']:
        require(queue and queue.pop(0)==n['id'],'FIFO_CHANGED');node_check(n)
        if n['terminal']=='SPLIT':
            axis,mid=axis_split(ctx['p'],n);require(axis is not None,'SPLIT_LEAF')
            require(n['axis']==axis and type(n['midpoint'])is int and n['midpoint']==mid and n['children']==[n['id']+'0',n['id']+'1'],'SPLIT_CHANGED')
            for suffix,limits in [('0',[n['box'][axis][0],mid]),('1',[mid+1,n['box'][axis][1]])]:
                key=n['id']+suffix;box=deepcopy(n['box']);box[axis]=limits
                # Child's local bound is checked when visited, without rebuilding twice.
                actual=all_nodes.get(key);require(actual is not None,'MISSING_CHILD')
                ev=actual['bound'];empty=n['effective_empty'] or ev['empty']
                expected[key]=dict(box=box,parent_id=n['id'],inherited_proof_ref=proof(n),effective_empty=empty,effective_upper_product=None if empty else str(min(F(n['effective_upper_product']),F(ev['upper_product']))))
                queue.append(key)
        elif n['terminal']=='CLOSED_BY_UPPER':require(n['effective_empty'] or F(n['effective_upper_product'])<=lower,'INVALID_PRUNE')
        elif n['terminal']=='EVALUATED':
            require(all(lo==hi for lo,hi in n['box'].values()),'NOT_LEAF')
            v=core.objective(ctx['p'],{s:lo for s,(lo,_) in n['box'].items() if lo})[0]
            require(n['product']==str(v) and v<=lower,'LEAF_CHANGED')
        else:raise ValueError('TERMINAL_CHANGED')
    require([n['id'] for n in c['unsearched_frontier']]==queue,'FRONTIER_CHANGED')
    for n in c['unsearched_frontier']:node_check(n)
    require(seen==set(expected),'DOMAIN_OMITTED')
    want=initial(ctx)
    for k in ('selected','coverage_ledger','unsearched_frontier','node_budget','processed_nodes','parent_continuation_raw_sha256'):want[k]=deepcopy(c[k])
    require(c['processed_nodes']==len(c['coverage_ledger'])<=c['node_budget'],'COUNT_CHANGED')
    finish(want,ctx);require(canonical(c)==canonical(want),'CERTIFICATE_CHANGED')
    require(F(c['upper_product'])<=F(ctx['a']['upper_product']),'UPPER_REGRESSED')
    return dict(status='VERIFIED_ANCESTOR_CAPPED_CONTINUATION',objective_value_optimal=c['objective_value_optimal'])

def checked(c,ctx):return _verify(c,ctx)

def verify(certificate,**sources):return checked(certificate,context(**sources))

def _transition(c,previous,ctx):
    require(canonical(c['coverage_ledger'][:len(previous['coverage_ledger'])])==canonical(previous['coverage_ledger']),'PREFIX_CHANGED')
    inventory=c['coverage_ledger']+c['unsearched_frontier']
    nodes={n['id']:n for n in inventory}
    require(len(nodes)==len(inventory),'DUPLICATE_NODE')
    fields=('id','box','bound','parent_id','inherited_proof_ref','effective_empty','effective_upper_product')
    for old in previous['unsearched_frontier']:
        require(old['id'] in nodes,'INHERITED_PENDING_MISSING')
        new=nodes[old['id']]
        require(canonical({k:old[k] for k in fields})==canonical({k:new[k] for k in fields}),'INHERITED_PENDING_CHANGED')
    require(c['processed_nodes']>=previous['processed_nodes'] and c['node_budget']>=previous['node_budget'],'BUDGET_REGRESSED')
    require(c['processed_nodes']-previous['processed_nodes']<=c['node_budget']-previous['node_budget'],'BUDGET_EXCEEDED')
    require(F(c['upper_product'])<=F(previous['upper_product']) and F(c['lower_product'])>=F(previous['lower_product']),'BOUND_REGRESSED')
    require(F(c['upper_product'])/F(c['lower_product'])<=F(previous['upper_product'])/F(previous['lower_product']),'RELATIVE_GAP_REGRESSED')

def verify_transition(certificate,*,previous_raw,expected_previous_sha256,**sources):
    ctx=context(**sources);previous=load(previous_raw,expected_previous_sha256)
    require(certificate['parent_continuation_raw_sha256']==expected_previous_sha256,'LINK_CHANGED')
    checked(previous,ctx);result=checked(certificate,ctx)
    _transition(certificate,previous,ctx)
    return result

def resume(*,additional_node_budget,previous_raw=None,expected_previous_sha256=None,**sources):
    require(type(additional_node_budget)is int and additional_node_budget>=0,'BUDGET_REQUIRED');ctx=context(**sources)
    if previous_raw is not None:
        previous=load(previous_raw,expected_previous_sha256);checked(previous,ctx);out=deepcopy(previous)
    else:
        require(expected_previous_sha256 is None,'PREVIOUS_REQUIRED');previous=None;out=finish(initial(ctx),ctx)
    pending=out['unsearched_frontier'];ledger=out['coverage_ledger'];best=F(out['lower_product']);added=0
    while pending and added<additional_node_budget:
        n=pending.pop(0);added+=1
        if n['effective_empty'] or F(n['effective_upper_product'])<=best:ledger.append(dict(n,terminal='CLOSED_BY_UPPER'));continue
        axis,mid=axis_split(ctx['p'],n)
        if axis is None:
            q={s:lo for s,(lo,_) in n['box'].items() if lo};v,_,notional=core.objective(ctx['p'],q)
            oldnotional=core.objective(ctx['p'],out['selected'])[2]
            if (v,-notional,tuple(sorted(q.items())))>(best,-oldnotional,tuple(sorted(out['selected'].items()))):out['selected']=q;best=v
            ledger.append(dict(n,terminal='EVALUATED',product=str(v)));continue
        children=[]
        for suffix,limits in [('0',[n['box'][axis][0],mid]),('1',[mid+1,n['box'][axis][1]])]:
            box=deepcopy(n['box']);box[axis]=limits;key=n['id']+suffix
            pending.append(child_node(ctx,n,key,box,out['selected']));children.append(key)
        ledger.append(dict(n,terminal='SPLIT',axis=axis,midpoint=mid,children=children))
    out.update(node_budget=out['node_budget']+additional_node_budget,processed_nodes=out['processed_nodes']+added,parent_continuation_raw_sha256=expected_previous_sha256)
    finish(out,ctx);checked(out,ctx)
    if previous is not None:_transition(out,previous,ctx)
    return out
