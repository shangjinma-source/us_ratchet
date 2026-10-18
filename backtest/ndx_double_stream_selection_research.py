"""Bounded selection of saved, fully audited double replacements; no evaluator IO.

Authentication belongs to the source adapter. The cursor consumes every original
ordinal once, retaining only one winner per scenario. No quantity-domain array.
"""
from copy import deepcopy
from fractions import Fraction
from itertools import combinations
import hashlib
import json

RANKING='NOT_SELECTED_FUTURE_ORIGINAL_TARGET_L1_THEN_TOTAL_BILATERAL_FEE_THEN_STABLE_OUTPAIR_INPAIR_Q1_Q2'
RULE='SELL_ALL_TWO_POSITIVE_OLD_BUY_TWO_NEW_JOINT_INTEGER_V1'
KINDS=('inspected_feasible','inspected_infeasible','evaluation_exception','supplied_not_evaluated_technical','supplied_not_evaluated_budget','validation_failure_returned','unresolved_dispatch_or_raw','undispatched')
FLAGS=dict.fromkeys(('evaluation_reperformed','account_executed','orders_executed','fit_executed','future_returns_used','cross_family_winner_selected','point_in_time_verified','promotion_allowed','full_ndx_certified','execution_authorized'),False)

def require(value,message):
    if not value:raise ValueError(message)
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value):return hashlib.sha256(encode(value)).hexdigest()
def exact(a,b,message):require(encode(a)==encode(b),message)
def integer(value):
    require(type(value)is int and value>=0,'Exact nonnegative integer');return value
def rational(value):
    require(type(value)is str and 0<len(value)<=1000,'Saved rational string')
    result=Fraction(value);require(result>=0 and str(result)==value,'Canonical nonnegative rational');return result

def catalogue(prepared):
    require(set(prepared)=={'document','content_sha256'} and digest(prepared['document'])==prepared['content_sha256'],'Prepared envelope')
    d=prepared['document'];require(d['schema']=='DOUBLE_REPLACEMENT_DOMAIN_PREPARATION_V1','Double domain')
    contract=d['action_contract'];require(contract['rule']==RULE and contract['ranking_policy']==RANKING and contract['cross_family_ranking_registered']is False,'Frozen objective only')
    exact([c['scenario_id']for c in d['cases']],contract['expected_scenario_ids'],'Original case order')
    require(len(d['cases'])==integer(d['scenario_count']) and len(set(contract['expected_scenario_ids']))==len(d['cases']),'Unique all cases')
    cursor=financial=excluded=pairs=0
    for ci,c in enumerate(d['cases']):
        exact(c['scenario_index'],ci,'Case index');require(integer(c['first_global_ordinal'])==cursor and digest(c['identity'])==c['identity_sha256'],'Case start/identity')
        exact(c['identity']['action_contract'],contract,'Case original contract')
        original=c['identity']['original_input_row'];old=sorted(s for s,q in original['holdings'].items()if q>0);new=sorted(set(original['target_weights'])-set(old))
        expected=[(list(a),list(b))for a in combinations(old,2)for b in combinations(new,2)]
        require(len(c['pairs'])==integer(c['pair_count'])==len(expected),'All original outgoing/incoming pairs')
        start=cursor;cf=ce=0
        for pi,(p,ids) in enumerate(zip(c['pairs'],expected)):
            exact(p['pair_index'],pi,'Pair index');exact((p['outgoing_security_ids'],p['incoming_security_ids']),ids,'Original pair order')
            require(integer(p['first_global_ordinal'])==cursor,'Pair starts at next ordinal')
            n=integer(p['enumerable_integer_count']);f=integer(p['financial_integer_count'])
            require(n==(0 if p['issuer_exclusion_certificate']['conflicts']else f),'Financial/excluded partition')
            cursor+=n;cf+=f;ce+=f-n;pairs+=1
        require(integer(c['integer_count'])==cursor-start and integer(c['financial_integer_count_before_issuer'])==cf and integer(c['structurally_excluded_integer_count'])==ce,'Case complete partition')
        financial+=cf;excluded+=ce
    require(integer(d['integer_count'])==cursor and integer(d['pair_count'])==pairs and integer(d['financial_integer_count_before_issuer'])==financial and integer(d['structurally_excluded_integer_count'])==excluded and cursor+excluded==financial,'Whole domain partition')
    return d

def full_audit(audit,total):
    require(audit['schema']=='DOUBLE_REPLACEMENT_C_STREAM_INDEPENDENT_READBACK_V1' and audit['status']=='PASS_FULL_DOMAIN','Complete independently inspected request only')
    s=audit['inspection'];require(s['full_domain_complete']is True and s['status']=='FULL_NUMERIC_DOMAIN' and integer(s['original_integer_count'])==total and integer(s['next_undispatched_ordinal'])==total,'No prefix or unknown domain')
    require(set(s['counts'])==set(KINDS),'All eight original categories')
    counts={k:integer(s['counts'][k])for k in KINDS}
    require(sum(counts.values())==total and not any(counts[k]for k in KINDS[2:]),'No technical or undispatched points')
    return counts

def checked_records(prepared,records):
    """Validate ordered task identity and stored objective; yield no full-domain list."""
    d=catalogue(prepared);iterator=iter(records);ordinal=0
    for case in d['cases']:
        original=case['identity']['original_input_row']
        targets={s:Fraction(v)for s,v in original['target_weights'].items()}
        for pair in case['pairs']:
            q1=q2=1;b=pair['financial_bound'];a,c=map(Fraction,b['incoming_unit_costs_with_buy_fee_usd']);budget=Fraction(b['joint_budget_usd'])
            require(a>0 and c>0,'Positive saved unit costs')
            for unused in range(pair['enumerable_integer_count']):
                require(a*q1+c*q2<=budget,'Original joint quantity budget')
                try:record=next(iterator)
                except StopIteration:raise ValueError('Missing original ordinal')from None
                raw=record['raw'];plan=raw['plan'];task=plan['task'];identity=task['identity']
                exact(plan['global_ordinal'],ordinal,'Original plan ordinal');exact(task['global_ordinal'],ordinal,'Original task ordinal')
                exact(task['scenario_index'],case['scenario_index'],'Original case');exact(task['pair_index'],pair['pair_index'],'Original pair')
                wanted=dict(schema='DOUBLE_REPLACEMENT_INTEGER_TASK_IDENTITY_V1',scenario_identity_sha256=case['identity_sha256'],rule=RULE,outgoing_security_ids=pair['outgoing_security_ids'],incoming_security_ids=pair['incoming_security_ids'],sell_quantities=pair['sell_quantities'],buy_quantities=[q1,q2])
                exact(identity,wanted,'Original identity and q1/q2 rank');require(task['task_id']==digest(identity),'Original task hash')
                evaluation=raw['evaluation'];status=raw['status'];require(status in ('FEASIBLE','INFEASIBLE') and evaluation['status']==status and evaluation['feasible']is(status=='FEASIBLE'),'Numeric outcome only')
                risk=evaluation['risk'];checks=risk['checks'];financial=evaluation['financial_checks']
                require(len(checks)==5 and set(financial)=={'NONNEGATIVE_CASH','CASH_BUFFER'} and all(type(v)is bool for v in (*checks.values(),*financial.values())),'Exact saved gates')
                feasible=all(checks.values())and all(financial.values())and not evaluation['issuer_conflicts']
                require(feasible is evaluation['feasible'] and risk['all_passed']is all(checks.values()),'Saved eligibility conjunction')
                weights={s:rational(v)for s,v in risk['weights'].items()};require(sum(weights.values())==1,'Stock-only saved weights')
                l1=sum((abs(weights.get(s,0)-targets.get(s,0))for s in set(weights)|set(targets)),Fraction())
                require(rational(evaluation['original_target_stock_l1'])==l1,'Original target L1 from saved exact weights')
                fee=rational(evaluation['total_fee_usd']);require(fee==rational(evaluation['sell_fee_usd'])+rational(evaluation['buy_fee_usd']),'Exact bilateral fee sum')
                key=(l1,fee,tuple(identity['outgoing_security_ids']),tuple(identity['incoming_security_ids']),q1,q2)
                yield case['scenario_index'],key,record
                ordinal+=1;q2+=1
                if a*q1+c*q2>budget:q1+=1;q2=1
            if pair['enumerable_integer_count']:require(a*q1+c*q2>budget,'Pair cannot silently omit its final quantity')
    try:next(iterator)
    except StopIteration:return
    raise ValueError('Extra point beyond complete original domain')

def select(*,prepared,audit,records):
    d=catalogue(prepared);counts=full_audit(audit,d['integer_count']);keys={}
    rows=[dict(scenario_index=c['scenario_index'],scenario_id=c['scenario_id'],integer_count=c['integer_count'],feasible_count=0,infeasible_count=0,status='NO_FEASIBLE',selected=None)for c in d['cases']]
    for ci,key,record in checked_records(prepared,records):
        row=rows[ci];feasible=record['raw']['status']=='FEASIBLE';row['feasible_count'if feasible else'infeasible_count']+=1
        if feasible and(ci not in keys or key<keys[ci]):keys[ci]=key;row['status']='SELECTED';row['selected']=deepcopy(record)
    for field,kind in (('feasible_count','inspected_feasible'),('infeasible_count','inspected_infeasible')):require(sum(r[field]for r in rows)==counts[kind],'Full audited outcome counts')
    return dict(schema='DOUBLE_REPLACEMENT_STREAM_SELECTION_V1',ranking_policy=RANKING,prepared_content_sha256=prepared['content_sha256'],full_domain_selected=True,integer_count=d['integer_count'],scenario_count=d['scenario_count'],pair_count=d['pair_count'],rows=rows,**FLAGS)
