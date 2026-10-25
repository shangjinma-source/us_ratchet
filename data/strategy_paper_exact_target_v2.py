"""Paper-only arithmetic acceleration; same policy, budget, result and validator.

The live account selector and frozen legacy search remain unchanged. Exact
rational scenario wealth uses precomputed integer coefficients in the new core.
"""
from copy import deepcopy
from hashlib import sha256
from fractions import Fraction
from core.strategy_account_ledger import canonical
from backtest.paper_exact_integer_quantity_search_v2 import search_fresh_cash_quantities as original_search
from backtest.continuous_guided_account_decision import VERSION, BASE_VERSION
from backtest.saved_quantity_candidate_comparison import compare_saved_candidates, canonical_sha256
from backtest.quantity_training_upper_bound import training_product_upper_bound, public_bound
from data.strategy_continuous32_target_decision import validate_result

def enhanced_search(**arguments):
    original = original_search(**arguments)
    if original.get('method_version') != BASE_VERSION:
        raise ValueError('ORIGINAL_V2_VERSION_REQUIRED')
    if original['selected'] is None:
        return dict(original, method_version=VERSION, additional_candidate_status='NOT_RUN_ORIGINAL_INCOMPLETE')
    comparison = compare_saved_candidates(search_arguments=arguments,saved_result=original,iterations=32,
        expected_search_arguments_sha256=canonical_sha256(arguments),expected_saved_result_sha256=canonical_sha256(original))
    selected = comparison['selected']
    bound = public_bound(training_product_upper_bound(cash=Fraction(str(arguments['entered_cash'])),
        fee=Fraction(str(arguments['fee_bps']))/10000,buffer=Fraction(str(arguments['minimum_cash_buffer'])),
        prices=arguments['prices'],scenarios=arguments['training_scenarios'],quantities=selected['quantities']))
    comparison['binding']['provenance']='FRESH_ORIGINAL_V2_RESULT_SAME_CALL_NOT_SAVED_HISTORICAL_RESULT'
    return dict(original,method_version=VERSION,selected=selected,best_by_k=comparison['best_by_k'],
        training_objective_bound=bound,continuous_comparison=comparison,
        coverage_scope='INHERITED_FROM_ORIGINAL_V2_CALL_NO_REPLACEMENT_OF_MANDATORY_COVERAGE',
        objective_evaluations_scope='ORIGINAL_V2_ONLY_ADDITIONAL_EVALUATIONS_SEPARATE',
        global_optimum_established=False)


def select_target_core(inputs, *, scope):
    binding=inputs['binding']
    result=enhanced_search(**deepcopy(binding['search_arguments']))
    quantities=validate_result(result,binding['search_arguments'])
    payload=dict(schema='PAPER_CONTINUOUS32_TARGET_DECISION_V1',input_id=inputs['input_id'],
                 target_month=binding['valuation_date'][:7], input_binding=binding,
                 search_result=result,target_quantities=quantities)
    return dict(status='TARGET_READY' if quantities is not None else 'SEARCH_INCOMPLETE',
        payload=payload,decision_id=sha256(canonical(payload)).hexdigest(),core_calls=1,
        source_bytes_verified=True,source_authenticated=False,full_pit_verified=False,
        orders_created=False,account_mutated=False,target_published=False,
        application_scope=scope,automatic_acceptance_allowed=False)

