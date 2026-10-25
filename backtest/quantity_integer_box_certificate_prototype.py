"""Synthetic/research integer coverage prototype for the unchanged V2 objective.

For positive incumbent wealth w_j, AM-GM bounds product(W_j/w_j) by
(sum(W_j/w_j)/m)^m. On an integer box the sum is affine. Starting at
the lower corner, fractional knapsack maximizes that affine expression under
the cash budget and upper bounds, dropping integrality and issuer restrictions.
Thus its result is an upper bound, not a feasible portfolio. Positive lower
coordinates in two classes of one issuer prove the entire box infeasible.

No IO, economic replay, deployment or data-authentication authority. Node budget
counts popped boxes, not CPU time or bound calculations. Pending boxes are
returned explicitly. Budget termination never claims optimality, even at gap 0.
"""
from fractions import Fraction as F
from math import prod
from copy import deepcopy
import json
from hashlib import sha256
from backtest.quantity_training_upper_bound import training_product_upper_bound


def require(condition, reason):
    if not condition:raise ValueError(reason)


def prepare(*,prices,metadata,entered_cash,fee_bps,minimum_cash_buffer,training_scenarios):
    require(type(prices)is dict and prices and set(prices)==set(metadata),'COMMON_DOMAIN_REQUIRED')
    require(all(type(s)is str and s for s in prices),'SID_REQUIRED')
    ids=sorted(prices)
    def number(value):
        require(type(value) in (str,int,float,F),'NONBOOLEAN_NUMBER_REQUIRED')
        return F(str(value))
    p={s:number(prices[s]) for s in ids}
    c,f,b=number(entered_cash),number(fee_bps)/10000,number(minimum_cash_buffer)
    require(c>0 and 0<=f<1 and b>=0 and all(x>0 for x in p.values()),'INVALID_CAPITAL')
    require(type(training_scenarios)is list and training_scenarios,'SCENARIOS_REQUIRED')
    rows=[]
    for row in training_scenarios:
        require(set(row)==set(ids),'SCENARIO_DOMAIN')
        values={s:number(row[s]) for s in ids};require(all(x>0 for x in values.values()),'POSITIVE_SCENARIOS');rows.append(values)
    require(all(type(metadata[s])is dict and all(type(metadata[s].get(k))is str and metadata[s][k] for k in ('ticker','issuer_id')) for s in ids),'IDENTITY_REQUIRED')
    require(len({metadata[s]['ticker'] for s in ids})==len(ids),'UNIQUE_TICKER_REQUIRED')
    return dict(ids=ids,prices=p,cash=c,fee=f,buffer=b,scenarios=rows,metadata=deepcopy(metadata),cost={s:p[s]*(1+f) for s in ids},spendable=max(F(0),c-b))


def objective(problem,quantities):
    require(type(quantities)is dict and all(s in problem['ids'] and type(q)is int and q>0 for s,q in quantities.items()),'INTEGER_QUANTITIES_REQUIRED')
    require(len({problem['metadata'][s]['issuer_id'] for s in quantities})==len(quantities),'ISSUER_CONFLICT')
    notional=sum((problem['prices'][s]*q for s,q in quantities.items()),F(0))
    residual=problem['cash']-notional*(1+problem['fee'])
    require(residual>=0 and (not quantities or residual>=problem['buffer']),'INFEASIBLE_QUANTITIES')
    wealth=[residual+sum((problem['prices'][s]*q*r[s] for s,q in quantities.items()),F(0)) for r in problem['scenarios']]
    return prod(w/problem['cash'] for w in wealth),wealth,notional


def box_bound(problem,box,incumbent):
    ids=problem['ids'];require(set(box)==set(ids),'BOX_DOMAIN')
    require(all(type(v)is list and len(v)==2 and all(type(x)is int for x in v) and 0<=v[0]<=v[1] for v in box.values()),'BOX_INTEGER_BOUNDS')
    lower={s:box[s][0] for s in ids if box[s][0]}
    if len({problem['metadata'][s]['issuer_id'] for s in lower})!=len(lower):return dict(empty=True,reason='FORCED_ISSUER_CONFLICT')
    spent=sum((problem['cost'][s]*box[s][0] for s in ids),F(0))
    if spent>problem['spendable']:return dict(empty=True,reason='LOWER_CORNER_OVER_BUDGET')
    value,wealth,_=objective(problem,incumbent)
    coefficients={s:sum((problem['prices'][s]*(r[s]-1-problem['fee'])/w for r,w in zip(problem['scenarios'],wealth)),F(0)) for s in ids}
    maximum=sum((problem['cash']/w for w in wealth),F(0))+sum((coefficients[s]*box[s][0] for s in ids),F(0))
    remaining=problem['spendable']-spent
    for s in sorted(ids,key=lambda s:(-coefficients[s]/problem['cost'][s],s)):
        if coefficients[s]<=0:continue
        amount=min(F(box[s][1]-box[s][0]),remaining/problem['cost'][s])
        maximum+=amount*coefficients[s];remaining-=amount*problem['cost'][s]
    m=len(wealth)
    local=value*(maximum/m)**m
    global_bound=training_product_upper_bound(cash=problem['cash'],fee=problem['fee'],buffer=problem['buffer'],prices=problem['prices'],scenarios=problem['scenarios'],quantities=incumbent)['product_upper_bound']
    return dict(empty=False,upper=str(min(local,global_bound)),box_relaxation_upper=str(local),global_relaxation_upper=str(global_bound),anchor=deepcopy(incumbent))


def solve(*,node_budget,initial_quantities=None,**arguments):
    require(type(node_budget)is int and node_budget>=0,'NODE_BUDGET_REQUIRED')
    p=prepare(**arguments);incumbent=deepcopy({} if initial_quantities is None else initial_quantities)
    best,_,notional=objective(p,incumbent)
    rank=lambda q,v,n:(v,-n,tuple(sorted(q.items())))
    best_rank=rank(incumbent,best,notional)
    root={s:[0,int(p['spendable']//p['cost'][s])] for s in p['ids']}
    pending=[dict(id='r',box=root,bound=box_bound(p,root,incumbent))];ledger=[];processed=0
    while pending and processed<node_budget:
        node=pending.pop(0);processed+=1;box=node['box'];bound=node['bound']
        if bound['empty']:ledger.append(dict(node,terminal='INFEASIBLE'));continue
        if F(bound['upper'])<best:ledger.append(dict(node,terminal='UPPER_STRICTLY_BELOW_INCUMBENT',incumbent_product=str(best)));continue
        axes=[s for s in p['ids'] if box[s][0]<box[s][1]]
        if not axes:
            q={s:box[s][0] for s in p['ids'] if box[s][0]};v,_,n=objective(p,q)
            if rank(q,v,n)>best_rank:incumbent=q;best=v;best_rank=rank(q,v,n)
            ledger.append(dict(node,terminal='EVALUATED',product=str(v)));continue
        axis=min(axes,key=lambda s:(-(box[s][1]-box[s][0]),s));mid=sum(box[axis])//2
        children=[]
        for label,bounds in [('0',[box[axis][0],mid]),('1',[mid+1,box[axis][1]])]:
            child=deepcopy(box);child[axis]=bounds;identifier=node['id']+label
            pending.append(dict(id=identifier,box=child,bound=box_bound(p,child,incumbent)));children.append(identifier)
        ledger.append(dict(node,terminal='SPLIT',axis=axis,midpoint=mid,children=children))
    upper=max([best]+[F(n['bound']['upper']) for n in pending if not n['bound']['empty']])
    complete=not pending
    normalized=dict(prices={s:str(p['prices'][s]) for s in p['ids']},metadata=p['metadata'],entered_cash=str(p['cash']),fee_bps=str(p['fee']*10000),minimum_cash_buffer=str(p['buffer']),training_scenarios=[{s:str(r[s]) for s in p['ids']} for r in p['scenarios']])
    input_hash=sha256(json.dumps(normalized,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return dict(schema='INTEGER_BOX_TRAINING_CERTIFICATE_PROTOTYPE_V1',input_sha256=input_hash,inputs=normalized,status='COMPLETE_INTEGER_DOMAIN_COVERAGE' if complete else 'NODE_BUDGET_STOPPED_UNRESOLVED',
        objective='TRAINING_PRICE_SCENARIO_MEAN_NET_LOG_WEALTH',selected=incumbent,lower_product=str(best),upper_product=str(upper),product_gap=str(upper-best),
        objective_value_optimal=complete,tie_break_optimality_established=False,node_budget=node_budget,processed_nodes=processed,root_box=root,coverage_ledger=ledger,unsearched_frontier=pending,
        scope='SUPPLIED_INTEGER_TRAINING_DOMAIN_ONLY',data_authenticated=False,future_performance_guaranteed=False)


def verify(certificate,*,expected_input_sha256):
    """Recheck disjoint exhaustive tree and exact inequalities; no search calls."""
    c=certificate
    require(type(c)is dict and c.get('schema')=='INTEGER_BOX_TRAINING_CERTIFICATE_PROTOTYPE_V1' and c.get('objective')=='TRAINING_PRICE_SCENARIO_MEAN_NET_LOG_WEALTH' and c.get('scope')=='SUPPLIED_INTEGER_TRAINING_DOMAIN_ONLY','CERTIFICATE_SCOPE_CHANGED')
    require(c.get('data_authenticated')is False and c.get('future_performance_guaranteed')is False and c.get('tie_break_optimality_established')is False,'UNSUPPORTED_AUTHORITY_CLAIM')
    require(type(c.get('node_budget'))is int and c['node_budget']>=0 and type(c.get('processed_nodes'))is int and c['processed_nodes']>=0 and type(c.get('objective_value_optimal'))is bool,'CERTIFICATE_SUMMARY_TYPES')
    raw=json.dumps(c['inputs'],sort_keys=True,separators=(',',':')).encode()
    require(sha256(raw).hexdigest()==expected_input_sha256==c['input_sha256'],'INPUT_BINDING_CHANGED')
    p=prepare(**c['inputs']);value,_,_=objective(p,c['selected'])
    require(str(value)==c['lower_product'],'LOWER_CHANGED')
    root={s:[0,int(p['spendable']//p['cost'][s])] for s in p['ids']}
    require(root==c['root_box'],'ROOT_CHANGED')
    expected={'r':root};seen=set()
    for node in c['coverage_ledger']:
        identifier=node['id'];require(identifier in expected and identifier not in seen and node['box']==expected[identifier],'PARTITION_CHANGED');seen.add(identifier)
        saved=node['bound'];bound=box_bound(p,node['box'],saved.get('anchor',{}))
        require(bound==saved,'BOUND_CHANGED')
        status=node['terminal']
        if status=='SPLIT':
            axis=node['axis'];lo,hi=node['box'][axis];mid=node['midpoint']
            require(lo<=mid<hi and node['children']==[identifier+'0',identifier+'1'],'SPLIT_CHANGED')
            for label,limits in [('0',[lo,mid]),('1',[mid+1,hi])]:
                child=deepcopy(node['box']);child[axis]=limits;expected[identifier+label]=child
        elif status=='INFEASIBLE':require(bound['empty'],'INFEASIBILITY_CHANGED')
        elif status=='UPPER_STRICTLY_BELOW_INCUMBENT':require(not bound['empty'] and F(bound['upper'])<value,'PRUNING_CHANGED')
        elif status=='EVALUATED':
            require(all(lo==hi for lo,hi in node['box'].values()),'LEAF_CHANGED')
            v,_,_=objective(p,{s:lo for s,(lo,_) in node['box'].items() if lo})
            require(str(v)==node['product'] and v<=value,'LEAF_VALUE_CHANGED')
        else:raise ValueError('TERMINAL_UNKNOWN')
    upper=value
    for node in c['unsearched_frontier']:
        identifier=node['id'];require(identifier in expected and identifier not in seen and node['box']==expected[identifier],'FRONTIER_CHANGED');seen.add(identifier)
        bound=box_bound(p,node['box'],node['bound'].get('anchor',{}));require(bound==node['bound'],'BOUND_CHANGED')
        if not bound['empty']:upper=max(upper,F(bound['upper']))
    require(seen==set(expected),'DOMAIN_OMITTED')
    complete=not c['unsearched_frontier']
    require(c['objective_value_optimal']==complete and c['status']==('COMPLETE_INTEGER_DOMAIN_COVERAGE' if complete else 'NODE_BUDGET_STOPPED_UNRESOLVED'),'FALSE_COMPLETION')
    require(c['processed_nodes']==len(c['coverage_ledger'])<=c['node_budget'] and str(upper)==c['upper_product'] and str(upper-value)==c['product_gap'],'SUMMARY_CHANGED')
    require(c['tie_break_optimality_established']is False,'TIE_BREAK_NOT_CERTIFIED')
    return dict(status='VERIFIED_INTEGER_BOX_COVERAGE',complete=complete,upper_product=str(upper),lower_product=str(value))
