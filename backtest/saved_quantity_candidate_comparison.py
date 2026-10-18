"""Compare additional proposals with a caller-authenticated saved V2 frontier.

Never invokes V2 search or a trading book. Expected canonical hashes must come
from the caller's verified saved-input binding; accepting arbitrary self-signed
hashes does not authenticate original inputs, search coverage or source units.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction
from hashlib import sha256
import json
import math
from backtest.continuous_quantity_candidates import generate_candidates, number, require


def canonical_sha256(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str,allow_nan=False).encode()).hexdigest()


def compare_saved_candidates(*, search_arguments, saved_result, iterations,
                             expected_search_arguments_sha256, expected_saved_result_sha256):
    require(canonical_sha256(search_arguments)==expected_search_arguments_sha256
            and canonical_sha256(saved_result)==expected_saved_result_sha256, 'CALLER_SAVED_BINDING_MISMATCH')
    arguments=deepcopy(search_arguments);old=deepcopy(saved_result)
    require(set(arguments)=={'prices','metadata','entered_cash','fee_bps','minimum_cash_buffer',
        'training_scenarios','scenario_dates','decision_date','max_objective_evaluations','fixed_seed'}, 'SEARCH_ARGUMENT_FIELDS')
    decision=arguments['decision_date'];dates=arguments['scenario_dates']
    require(type(decision)is str and date.fromisoformat(decision).isoformat()==decision, 'DECISION_DATE')
    require(type(dates)is list and len(dates)==len(arguments['training_scenarios']) and dates==sorted(set(dates))
            and all(type(d)is str and date.fromisoformat(d).isoformat()==d and d<=decision for d in dates), 'SCENARIO_DATES')
    require(type(arguments['fixed_seed'])is str and arguments['fixed_seed']
            and type(arguments['max_objective_evaluations'])is int and arguments['max_objective_evaluations']>0,'SEARCH_BUDGET_OR_SEED')
    require(old.get('method_version')=='EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2'
            and old.get('objective')=='TRAINING_PRICE_SCENARIO_MEAN_NET_LOG_WEALTH'
            and old.get('status') in ('BUDGET_STOPPED','PER_K_SEARCH_STOPPED_WITH_UNUSED_BUDGET'), 'SAVED_V2_RESULT_REQUIRED')
    for field in ('decision_date','scenario_dates','max_objective_evaluations'):
        require(old.get(field)==arguments[field], 'SAVED_CONTEXT_MISMATCH')
    for field in ('entered_cash','fee_bps','minimum_cash_buffer'):
        require(number(old[field])==number(arguments[field]), 'SAVED_CONTEXT_MISMATCH')
    generated=generate_candidates(**{k:arguments[k] for k in ('prices','metadata','entered_cash','fee_bps','minimum_cash_buffer','training_scenarios')},iterations=iterations)
    cash=number(arguments['entered_cash']);fee=number(arguments['fee_bps'])/10000;buffer=number(arguments['minimum_cash_buffer'])
    marks={k:number(v) for k,v in arguments['prices'].items()}
    scenarios=[{k:number(v) for k,v in row.items()} for row in arguments['training_scenarios']]
    cache={}
    def evaluate(quantities):
        require(type(quantities)is dict and all(sid in marks and type(q)is int and q>0 for sid,q in quantities.items()), 'INVALID_QUANTITIES')
        signature=tuple(sorted(quantities.items()))
        if signature in cache:return cache[signature]
        q=dict(signature)
        require(len({arguments['metadata'][sid]['issuer_id'] for sid in q})==len(q),'ISSUER_CONFLICT')
        notional=sum((marks[sid]*n for sid,n in q.items()),Fraction(0));residual=cash-notional*(1+fee)
        require(residual>=0 and (not q or residual>=buffer),'INFEASIBLE_QUANTITIES')
        growth=[(residual+sum((marks[sid]*n*row[sid] for sid,n in q.items()),Fraction(0)))/cash for row in scenarios]
        product=math.prod(growth);large=max(product.numerator.bit_length(),product.denominator.bit_length())>4096
        record=dict(quantities=q,actual_k=len(q),notional=str(notional),fees=str(notional*fee),residual_cash=str(residual),
            training_mean_net_log_wealth=sum(math.log(v.numerator)-math.log(v.denominator) for v in growth)/len(growth),
            training_gross_growth_product=None if large else str(product),exact_product_comparison=True,
            large_exact_product_serialization_omitted=large,actual_weights={sid:str(marks[sid]*n/cash) for sid,n in q.items()},
            cash_fraction=str(residual/cash),issuer_unique=True,budget_conservation_exact=True)
        cache[signature]=((product,-notional,signature),record);return cache[signature]
    require(type(old.get('best_by_k'))is dict and old['best_by_k'] and type(old.get('selected'))is dict,'SAVED_FRONTIER_REQUIRED')
    frontier={}
    for k,record in old['best_by_k'].items():
        rank,recomputed=evaluate(record['quantities'])
        require(k==str(recomputed['actual_k']) and record==recomputed,'SAVED_RECORD_MISMATCH')
        frontier[k]=(rank,recomputed)
    rank,selected=evaluate(old['selected']['quantities'])
    require(old['selected']==selected and max(frontier.values(),key=lambda v:v[0])[1]==selected,'SAVED_SELECTION_MISMATCH')
    old_rank=rank;old_evaluations=len(cache)
    for candidate in generated['candidates']:
        rank,record=evaluate(candidate['quantities']);k=str(record['actual_k'])
        if k not in frontier or rank>frontier[k][0]:frontier[k]=(rank,record)
    winner=max(frontier.values(),key=lambda v:v[0]);require(winner[0]>=old_rank,'INTERNAL_NONDEGRADATION_FAILURE')
    return dict(status='SAVED_FRONTIER_PLUS_CONTINUOUS_CANDIDATES',selected=winner[1],
        best_by_k={k:v[1] for k,v in sorted(frontier.items(),key=lambda item:int(item[0]))},
        inherited_saved_result=old,inherited_coverage_reverified=False,
        binding=dict(search_arguments_sha256=expected_search_arguments_sha256,saved_result_sha256=expected_saved_result_sha256,
                     provenance='CALLER_VERIFIED_CANONICAL_SAVED_BINDING_NOT_INDEPENDENTLY_AUTHENTICATED'),
        additional_generation=generated,exact_evaluations=dict(saved_unique=old_evaluations,new_unique=len(cache)-old_evaluations),
        original_search_budget=arguments['max_objective_evaluations'],equal_computation_budget_comparison=False,
        selected_training_objective_not_lower=True,research_only=True,global_optimum_established=False,
        historical_backtest_run=False,future_return_or_drawdown_guaranteed=False)
