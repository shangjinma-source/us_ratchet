"""Independent winner reduction from saved records, without selector imports."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json

RANKING='NOT_SELECTED_FUTURE_ORIGINAL_TARGET_L1_THEN_TOTAL_BILATERAL_FEE_THEN_STABLE_OUTPAIR_INPAIR_Q1_Q2'
FLAGS=dict.fromkeys(('evaluation_reperformed','account_executed','orders_executed','fit_executed','future_returns_used','cross_family_winner_selected','point_in_time_verified','promotion_allowed','full_ndx_certified','execution_authorized'),False)
def require(v,message):
    if not v:raise ValueError(message)
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encode(a)==encode(b),message)
def number(v):
    require(type(v)is str and 0<len(v)<=1000,'Saved rational');n=Fraction(v);require(n>=0 and str(n)==v,'Canonical rational');return n

def inspect(*,prepared,audit,records,selection):
    d=prepared['document'];require(hashlib.sha256(encode(d)).hexdigest()==prepared['content_sha256'],'Prepared hash')
    require(d['action_contract']['ranking_policy']==RANKING and audit['status']=='PASS_FULL_DOMAIN','Original objective and full audit')
    s=audit['inspection'];total=d['integer_count'];require(type(total)is int and total>=0 and s['full_domain_complete']is True and s['status']=='FULL_NUMERIC_DOMAIN','Full numeric source')
    require(type(s['original_integer_count'])is int and s['original_integer_count']==total==s['next_undispatched_ordinal'],'Original denominator')
    require(set(s['counts'])=={'inspected_feasible','inspected_infeasible','evaluation_exception','supplied_not_evaluated_technical','supplied_not_evaluated_budget','validation_failure_returned','unresolved_dispatch_or_raw','undispatched'}and all(type(v)is int and v>=0 for v in s['counts'].values()),'Exact eight counts')
    require(sum(s['counts'].values())==total and s['counts']['inspected_feasible']+s['counts']['inspected_infeasible']==total,'No technical selection')
    best={};scores={};counts=[[0,0]for c in d['cases']];cursor=0;ci=pi=0;last_quantity=None
    for record in records:
        raw=record['raw'];plan=raw['plan'];task=plan['task'];identity=task['identity']
        require(type(plan['global_ordinal'])is int and plan['global_ordinal']==cursor,'Every original ordinal once')
        while ci<len(d['cases'])and cursor>=d['cases'][ci]['first_global_ordinal']+d['cases'][ci]['integer_count']:ci+=1;pi=0;last_quantity=None
        require(ci<len(d['cases']),'Extra original point');case=d['cases'][ci]
        while pi<len(case['pairs'])and cursor>=case['pairs'][pi]['first_global_ordinal']+case['pairs'][pi]['enumerable_integer_count']:pi+=1;last_quantity=None
        require(pi<len(case['pairs']),'Missing original pair');pair=case['pairs'][pi]
        exact((task['scenario_index'],task['pair_index'],task['global_ordinal']),(ci,pi,cursor),'Independent original coordinate')
        q=identity['buy_quantities'];require(type(q)is list and len(q)==2 and all(type(v)is int and v>=1 for v in q),'Incoming-ordered positive quantities')
        b=pair['financial_bound'];a,c=map(Fraction,b['incoming_unit_costs_with_buy_fee_usd']);budget=Fraction(b['joint_budget_usd']);require(a>0 and c>0 and a*q[0]+c*q[1]<=budget,'Saved nonrectangular budget')
        if last_quantity is None:exact(q,[1,1],'Pair begins at original first quantity')
        else:
            expected=[last_quantity[0],last_quantity[1]+1]
            if a*expected[0]+c*expected[1]>budget:expected=[last_quantity[0]+1,1]
            exact(q,expected,'Independent contiguous quantity order')
        last_quantity=list(q)
        if cursor+1==pair['first_global_ordinal']+pair['enumerable_integer_count']:
            require(a*q[0]+c*(q[1]+1)>budget and a*(q[0]+1)+c>budget,'Pair last point is final feasible quantity')
        expected=dict(schema='DOUBLE_REPLACEMENT_INTEGER_TASK_IDENTITY_V1',scenario_identity_sha256=case['identity_sha256'],rule='SELL_ALL_TWO_POSITIVE_OLD_BUY_TWO_NEW_JOINT_INTEGER_V1',outgoing_security_ids=pair['outgoing_security_ids'],incoming_security_ids=pair['incoming_security_ids'],sell_quantities=pair['sell_quantities'],buy_quantities=q)
        exact(identity,expected,'Original task identity');require(task['task_id']==hashlib.sha256(encode(identity)).hexdigest(),'Task SHA')
        e=raw['evaluation'];require(raw['status']in ('FEASIBLE','INFEASIBLE')and e['status']==raw['status']and e['feasible']is(raw['status']=='FEASIBLE'),'Numeric saved status')
        flags=list(e['risk']['checks'].values())+list(e['financial_checks'].values());require(len(flags)==7 and all(type(v)is bool for v in flags),'Saved exact gate bits')
        require(e['feasible']is(all(flags)and not e['issuer_conflicts']),'Saved gate conjunction')
        target={k:Fraction(v)for k,v in case['identity']['original_input_row']['target_weights'].items()};weights={k:number(v)for k,v in e['risk']['weights'].items()};require(sum(weights.values())==1,'Saved stock denominator')
        distance=sum((abs(weights.get(k,Fraction())-target.get(k,Fraction()))for k in weights.keys()|target.keys()),Fraction())
        fee=number(e['sell_fee_usd'])+number(e['buy_fee_usd']);require(number(e['original_target_stock_l1'])==distance and number(e['total_fee_usd'])==fee,'Independent exact original target and bilateral fee')
        score=(distance,fee,tuple(identity['outgoing_security_ids']),tuple(identity['incoming_security_ids']),q[0],q[1]);feasible=e['feasible'];counts[ci][0 if feasible else 1]+=1
        if feasible and(ci not in scores or score<scores[ci]):scores[ci]=score;best[ci]=deepcopy(record)
        cursor+=1
    require(cursor==total,'Full independent stream required')
    require(sum(x[0]for x in counts)==s['counts']['inspected_feasible']and sum(x[1]for x in counts)==s['counts']['inspected_infeasible'],'Independent full outcome counts')
    rows=[dict(scenario_index=i,scenario_id=c['scenario_id'],integer_count=c['integer_count'],feasible_count=counts[i][0],infeasible_count=counts[i][1],status='SELECTED'if i in best else'NO_FEASIBLE',selected=best.get(i))for i,c in enumerate(d['cases'])]
    expected=dict(schema='DOUBLE_REPLACEMENT_STREAM_SELECTION_V1',ranking_policy=RANKING,prepared_content_sha256=prepared['content_sha256'],full_domain_selected=True,integer_count=total,scenario_count=d['scenario_count'],pair_count=d['pair_count'],rows=rows,**FLAGS)
    exact(selection,expected,'Independent full winner and real RAW locator')
    return dict(schema='DOUBLE_REPLACEMENT_STREAM_SELECTION_INSPECTION_V1',status='PASS',integer_count=total,scenario_count=len(rows),selected_count=len(best),no_feasible_count=len(rows)-len(best),**FLAGS)
