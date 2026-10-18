"""Independent saved double-replacement point arithmetic and batch partition.

Only domain reconstruction and rank/task projection share frozen 334a/081a.
No production evaluator/cache/risk helper is imported or executed. File/source
and exception/cache runtime authenticity remain outside this IO-free layer.
"""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from backtest import ndx_double_replacement_domain_research as shared_domain

DOMAIN_SHA256='334af655e4d30a928af9d965b1c63bfe664c5c9a633dca3591bfac7f8130d4b6'
MATH_SHA256='081a1d3a72c78c3e4637fa25b3845853a610c33608bfd5b4b2ee8ccdca2dc5e1'
RISK_SHA256='5bb17d621b42707cfe312676279d59b565c3e97900bf3bdd6f9335df65aa0c5f'
NAIVE_SHA256='42640b41f3b54ba827e47d90c4c200c31b03ac13c6d867e928dc9a5956f4d5a2'
SCHEMAS=('EXPLICIT_DOUBLE_REPLACEMENT_EVALUATION_V1','EXPLICIT_DOUBLE_REPLACEMENT_CACHED_EVALUATION_V1')
STATUSES=('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','NOT_EVALUATED_BUDGET','NOT_EVALUATED_TECHNICAL_STOP')
TASK_FALSE = ('source_bytes_authenticated','point_in_time_verified','formal_eligibility_verified',
 'identity_gaps_resolved','risk_evaluated','financial_feasibility_evaluated','economic_winner_selected',
 'global_optimality_claimed','orders_executed','account_executed','fit_executed','old_evaluations_repeated',
 'target_weights_changed','future_returns_used','repair_performed','domain_registered_for_execution')
CHECKS = ('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')
FLAGS = dict.fromkeys(('source_bytes_authenticated','producer_called','evaluator_called','account_executed',
                      'point_in_time_verified','full_ndx_certified','economic_winner_selected','automatic_retry_allowed'),False)


def require(ok,message):
    if not ok:raise ValueError(message)
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def digest(value):return hashlib.sha256(encode(value)).hexdigest()
def exact(a,b,message):require(encode(a)==encode(b),message)
def integer(n):
    require(type(n) is int and n>=0,'Exact nonnegative integer');return n
def error(value):
    require(type(value) is dict and set(value)=={'type','message'} and type(value['type']) is str and bool(value['type']) and type(value['message']) is str,'Exact original error strings')
def number(value):
    require(type(value) is str and 0<len(value)<=80 and value.strip()==value,'Saved decimal literal')
    d=Decimal(value);require(d.is_finite() and len(d.as_tuple().digits)<=40 and abs(d.as_tuple().exponent)<=40,'Bounded finite decimal')
    return Fraction(d)

def arithmetic(row,task):
    """Independent oracle from original saved decimals, not production outputs."""
    marks={s:number(v) for s,v in row['execution_prices'].items()};after=task['proposed_holdings'];trades=task['signed_trade_quantities']
    sale=sum((marks[s]*(-q) for s,q in trades.items() if q<0),Fraction(0));purchase=sum((marks[s]*q for s,q in trades.items() if q>0),Fraction(0))
    rate=number(row['transaction_cost_bps'])/10000;sellfee=sale*rate;buyfee=purchase*rate
    cash=number(row['starting_cash_usd'])+number(row['cash_event']['amount_usd'])+sale-purchase-sellfee-buyfee
    positive={s:marks[s]*q for s,q in sorted(after.items()) if q>0};stock=sum(positive.values(),Fraction(0));require(stock>0,'Positive stock denominator')
    weights={s:value/stock for s,value in positive.items()};ordered=sorted(weights.values(),reverse=True)
    effective=stock*stock/sum((v*v for v in positive.values()),Fraction(0));chains={};issuers={}
    for sid,w in weights.items():
        chain=row['securities'][sid]['risk_chain'];chains[chain]=chains.get(chain,Fraction(0))+w
        issuers.setdefault(row['securities'][sid]['issuer_id'],[]).append(sid)
    conflicts={issuer:ids for issuer,ids in issuers.items() if len(ids)>1};r={k:number(v) for k,v in row['risk_parameters'].items()};slack=Fraction(1,1000000000)
    values=[max(weights.values())<=r['max_single_weight']+slack,min(weights.values())>=r['min_single_weight']-slack,
            sum(ordered[:3])<=r['top_weight_cap']+slack,effective>=r['minimum_effective_n_ratio']*len(weights)-slack,
            max(chains.values())<=r['risk_chain_top1_cap']+slack]
    checks=dict(zip(CHECKS,values));financial=dict(NONNEGATIVE_CASH=cash>=0,CASH_BUFFER=cash>=number(row['minimum_cash_buffer_usd']))
    targets={s:number(v) for s,v in row['target_weights'].items()};l1=sum((abs(weights.get(s,Fraction(0))-targets.get(s,Fraction(0))) for s in set(weights)|set(targets)),Fraction(0))
    initial=sum((marks[s]*q for s,q in row['holdings'].items() if q),Fraction(0))+number(row['starting_cash_usd'])
    pnl=stock+cash-initial-number(row['cash_event']['amount_usd']);require(pnl==-(sellfee+buyfee),'Independent self-financing identity')
    feasible=all(values) and all(financial.values()) and not conflicts
    return dict(status='FEASIBLE' if feasible else 'INFEASIBLE',feasible=feasible,gross_sell_usd=str(sale),gross_buy_usd=str(purchase),sell_fee_usd=str(sellfee),buy_fee_usd=str(buyfee),total_fee_usd=str(sellfee+buyfee),cash_after_usd=str(cash),invested_stock_usd=str(stock),equity_after_usd=str(stock+cash),cash_flow_adjusted_pnl_usd=str(pnl),financial_checks=financial,
                risk=dict(checks=checks,all_passed=all(values),weights={s:str(w) for s,w in weights.items()},effective_n=str(effective),positive_holding_count=len(weights),risk_chain_weights={s:str(w) for s,w in sorted(chains.items())}),issuer_conflicts=conflicts,original_target_stock_l1=str(l1))


def catalogue(prepared):
    require(type(prepared)is dict and set(prepared)=={'document','content_sha256'},'Prepared envelope')
    d=prepared['document'];require(digest(d)==prepared['content_sha256'],'Prepared canonical digest')
    rows=[dict(input_row=deepcopy(c['identity']['original_input_row']),input_reference=deepcopy(c['identity']['input_reference']))for c in d['cases']]
    # Deliberately shared *domain* checker, not an independent domain proof.
    reconstructed=shared_domain.prepare_double_replacement_domain(rows,deepcopy(d['action_contract']))
    exact(reconstructed,prepared,'Entire declared domain reconstruction')
    return reconstructed['document']

def verified_task(document,plan):
    require(type(plan)is dict and set(plan)=={'global_ordinal','task'},'Explicit full plan')
    n=integer(plan['global_ordinal'])
    require(n<document['integer_count'],'Ordinal within complete enumerable domain')
    wanted=shared_domain._task(document,n)
    exact(plan['task'],wanted,'Both outgoing/incoming legs, ordered q, zero slots and full identity')
    return document['cases'][wanted['scenario_index']]['identity']['original_input_row'],wanted

def inspect_saved_evaluation(*,prepared,global_ordinal,task,saved_result):
    d=catalogue(prepared);row,wanted=verified_task(d,dict(global_ordinal=global_ordinal,task=task))
    exact(saved_result,arithmetic(row,wanted),'Independent complete double-replacement arithmetic')
    return dict(schema='DOUBLE_REPLACEMENT_SAVED_EVALUATION_INSPECTION_V1',status='PASS',task_id=wanted['task_id'],global_ordinal=global_ordinal,outcome=saved_result['status'],shared_domain_task_projection=True,domain_source_sha256=DOMAIN_SHA256,budget_math_source_sha256=MATH_SHA256,**FLAGS)

def inspect_explicit_evaluations(*,prepared,registered_plans,max_evaluations,saved_result):
    """Check every saved numeric point and complete supplied/unprovided partition.

    Technical exceptions are evidence declarations, never negative risk results.
    A newly touched cache may have failed before or after insertion; its count is
    constrained to those two possibilities, not certified as an observed call.
    """
    d=catalogue(prepared)
    require(type(registered_plans)is list and len(registered_plans)<=10000,'Complete bounded supplied list')
    require(type(max_evaluations)is int and 0<=max_evaluations<=10000,'Exact invocation budget')
    require(type(saved_result)is dict and saved_result['schema']in SCHEMAS,'Supported saved evaluator schema')
    supplied=deepcopy(registered_plans);seen=set();tasks=[]
    for plan in supplied:
        row,task=verified_task(d,plan);n=plan['global_ordinal'];require(n not in seen,'No duplicate supplied ordinal');seen.add(n);tasks.append((row,task))
    saved_rows=saved_result['results'];require(type(saved_rows)is list and len(saved_rows)==len(supplied),'Every supplied slot retained')
    expected=[];stopped=False;numeric=0;cache_keys=set();cache_hits=0;cache_extra=0
    for i,(plan,(row,task),saved)in enumerate(zip(supplied,tasks,saved_rows)):
        require(type(saved)is dict,'Saved point object')
        prefix=dict(supplied_index=i,plan=plan)
        if stopped or i>=max_evaluations:
            status='NOT_EVALUATED_TECHNICAL_STOP'if stopped else'NOT_EVALUATED_BUDGET'
            wanted=dict(prefix,status=status,evaluation=None)
        elif saved['status']=='EVALUATION_EXCEPTION':
            error(saved['error']);wanted=dict(prefix,status='EVALUATION_EXCEPTION',evaluation=None,error=deepcopy(saved['error']));stopped=True
            key=(task['scenario_index'],task['pair_index'])
            if key in cache_keys:cache_hits+=1
            else:cache_extra=1
        else:
            value=arithmetic(row,task);wanted=dict(prefix,status=value['status'],evaluation=value);numeric+=1
            key=(task['scenario_index'],task['pair_index'])
            if key in cache_keys:cache_hits+=1
            else:cache_keys.add(key)
        exact(saved,wanted,'Exact original slot and independent economic/technical category')
        expected.append(wanted)
    counts={name:sum(row['status']==name for row in expected)for name in STATUSES}
    evaluation_flags=dict.fromkeys((k for k in TASK_FALSE if k not in ('risk_evaluated','financial_feasibility_evaluated')),False)
    schema=saved_result['schema']
    expected_result=dict(schema=schema,prepared_content_sha256=digest(d),prepared_identity_scope='RECONSTRUCTED_INTERNAL_CONSISTENCY_NOT_ORIGINAL_BYTE_AUTHENTICATION',action_contract=deepcopy(d['action_contract']),source_hash_claims=deepcopy(d['source_hash_claims']),full_scenario_count=d['scenario_count'],full_pair_count=d['pair_count'],full_integer_count=d['integer_count'],financial_integer_count_before_issuer=d['financial_integer_count_before_issuer'],structurally_excluded_integer_count=d['structurally_excluded_integer_count'],supplied_plan_count=len(supplied),unsupplied_integer_count=d['integer_count']-len(supplied),max_evaluations=max_evaluations,counts=counts,results=expected,status='TECHNICAL_STOP'if stopped else'ALL_SUPPLIED_EVALUATED'if len(supplied)<=max_evaluations else'BUDGET_LIMITED',risk_tolerance='1e-9',financial_tolerance='0',arithmetic='EXACT_FRACTION_FROM_SAVED_DECIMAL_LITERALS',monetary_value_encoding='EXACT_RATIONAL_STRING_IN_USD_UNITS_NOT_DECIMAL_RENDERING',completed_evaluation_count=numeric,supplied_plan_registration_authenticated=False,prepared_domain_bytes_authenticated=False,domain_source_sha256=DOMAIN_SHA256,budget_math_source_sha256=MATH_SHA256,risk_semantics_source_sha256=RISK_SHA256,enumeration_or_search_called=False,cross_family_winner_selected=False,source_code_bytes_authenticated=False,full_integer_space_infeasibility_claimed=False,**evaluation_flags)
    if schema==SCHEMAS[1]:
        count=integer(saved_result['pair_cache_count']);hits=integer(saved_result['pair_cache_hit_count'])
        require(len(cache_keys)<=count<=len(cache_keys)+cache_extra and hits==cache_hits,'Only provable cache count bounds; no budget hit')
        expected_result.update(pair_cache_count=count,pair_cache_hit_count=hits,cache_scope='WITHIN_VALIDATED_SCENARIO_AND_PAIR_ONLY',risk_result_reused_across_points=False,intervals_skipped=False,naive_oracle_called=False,naive_oracle_source_sha256=NAIVE_SHA256)
    exact(saved_result,expected_result,'Complete saved batch values/types/flags/denominators')
    return dict(schema='DOUBLE_REPLACEMENT_EXPLICIT_EVALUATION_INSPECTION_V1',status='PASS_SAVED_RESULT_EVIDENCE',evaluation_status=expected_result['status'],saved_result_schema=schema,supplied_plan_count=len(supplied),unsupplied_integer_count=d['integer_count']-len(supplied),full_scenario_count=d['scenario_count'],full_pair_count=d['pair_count'],full_integer_count=d['integer_count'],financial_integer_count_before_issuer=d['financial_integer_count_before_issuer'],structurally_excluded_integer_count=d['structurally_excluded_integer_count'],counts=counts,independently_checked_evaluation_count=numeric,all_saved_numeric_rows_checked=True,all_supplied_plans_numerically_checked=numeric==len(supplied),technical_exception_authenticity_verified=False,cache_runtime_counts_independently_verified=False,shared_domain_reconstruction_and_task_projection=True,domain_source_sha256=DOMAIN_SHA256,budget_math_source_sha256=MATH_SHA256,scope='INDEPENDENT_EXACT_POINT_ARITHMETIC_AND_COMPLETE_SAVED_PARTITION_SHARED_DOMAIN_MATH_NOT_SOURCE_OR_RUNTIME_AUTHENTICATION',**FLAGS)
