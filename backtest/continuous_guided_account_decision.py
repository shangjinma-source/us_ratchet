"""Experimental V2 plus continuous proposals through unchanged capital validation; no IO."""
from copy import deepcopy
import hashlib
import json

from backtest.return_priority_fresh_cash_quantity_search_v2 import search_fresh_cash_quantities as original_search
from backtest.saved_quantity_candidate_comparison import compare_saved_candidates, canonical_sha256
from backtest.quantity_training_upper_bound import training_product_upper_bound, public_bound
from fractions import Fraction
from data.current_research_capital_decision import decide_quantity_for_account

VERSION = 'FAIR_K_V2_PLUS_CONTINUOUS32_EXPERIMENT_V1'
BASE_VERSION = 'EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2'
REQUIRED_PINS = (
    'data/current_research_capital_decision_v2.py',
    'backtest/continuous_guided_account_decision.py',
    'backtest/continuous_quantity_candidates.py',
    'backtest/saved_quantity_candidate_comparison.py',
    'data/current_research_capital_decision.py',
    'backtest/return_priority_fresh_cash_quantity_search_v2.py',
    'backtest/affordable_support_seeds.py',
    'backtest/log_concave_integer_search.py',
    'backtest/quantity_training_upper_bound.py',
)


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


def decide_continuous_guided_for_account(**arguments):
    """Preserve V2 terminal semantics while reusing exact capital validation.

    Pins are caller-authenticated; this pure function does not read source files.
    The legacy core is pinned for the imported validator, never executed here.
    """
    if 'search' in arguments:
        raise ValueError('V2 search cannot be replaced')
    if any(path not in arguments['source_hashes'] for path in REQUIRED_PINS):
        raise ValueError('V2_METHOD_SOURCE_PINS_REQUIRED')
    observed = []

    def compatibility(**kwargs):
        result = enhanced_search(**kwargs)
        if result.get('method_version') != VERSION:
            raise ValueError('V2_METHOD_VERSION_MISMATCH')
        statuses = {
            'INSUFFICIENT_BUDGET_FOR_MANDATORY_COVERAGE': 'INSUFFICIENT_BUDGET_FOR_ALL_K_INITIALIZATION',
            'PER_K_SEARCH_STOPPED_WITH_UNUSED_BUDGET': 'LOCAL_NEIGHBORHOODS_EXHAUSTED',
            'BUDGET_STOPPED': 'BUDGET_STOPPED',
        }
        if result.get('status') not in statuses:
            raise ValueError('UNKNOWN_V2_TERMINAL_STATUS')
        observed.append(deepcopy(result))
        return dict(result, status=statuses[result['status']])

    result = decide_quantity_for_account(**arguments, search=compatibility)
    result['search_result'] = observed[0]  # Never publish the internal status translation.
    result['method'] = VERSION
    result['binding']['schema'] = 'CAPITAL_DECISION_CONTINUOUS_GUIDED_EXPERIMENT_V1'
    result['binding']['continuous_iterations'] = 32
    result['binding']['selection_method'] = VERSION
    identifier = hashlib.sha256(json.dumps(result['binding'], sort_keys=True,
        separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    result.update(decision_id=identifier, research_id=identifier[:24])
    result['limitations'].append('Original fair-k V2 plus 32 extra continuous proposal steps; not equal-budget, not production, not a drawdown guarantee.')
    return result
