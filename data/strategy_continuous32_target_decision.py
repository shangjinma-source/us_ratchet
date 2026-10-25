"""Isolated continuous32 target profile. No runtime registration or account writes.

The inherited V2 frontier is validated under its original identity. Additional
proposals are deterministically rechecked, never relabelled as a V2 result.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from pathlib import Path

from core.strategy_account_ledger import canonical
from backtest.continuous_guided_account_decision import (
    VERSION, REQUIRED_PINS, enhanced_search,
)
from backtest.saved_quantity_candidate_comparison import (
    canonical_sha256, compare_saved_candidates,
)
from backtest.quantity_training_upper_bound import training_product_upper_bound, public_bound
from data.strategy_account_target_inputs import build_target_inputs, require
from data.strategy_account_target_decision import validate_result as validate_original

ROOT = Path(__file__).resolve().parents[1]
PROFILE_ID = 'REAL_ACCOUNT_CONTINUOUS32_V1'
PROVENANCE = 'FRESH_ORIGINAL_V2_RESULT_SAME_CALL_NOT_SAVED_HISTORICAL_RESULT'


def validate_result(result, arguments):
    """Recheck the saved frontier and extra proposals; never rerun base search."""
    require(result.get('method_version') == VERSION, 'CONTINUOUS32_METHOD_MISMATCH')
    comparison = result.get('continuous_comparison')
    if result.get('selected') is None:
        # This authoritative branch changes only method and adds its stop reason.
        require(comparison is None and result.get('additional_candidate_status') ==
                'NOT_RUN_ORIGINAL_INCOMPLETE', 'CONTINUOUS32_INCOMPLETE_INVALID')
        original = deepcopy(result)
        original.pop('additional_candidate_status')
        from backtest.continuous_guided_account_decision import BASE_VERSION
        original['method_version'] = BASE_VERSION
        return validate_original(original, arguments)
    require(isinstance(comparison, dict), 'CONTINUOUS32_COMPARISON_REQUIRED')
    original = comparison.get('inherited_saved_result')
    require(isinstance(original, dict), 'CONTINUOUS32_BASE_REQUIRED')
    validate_original(original, arguments)
    expected_comparison = compare_saved_candidates(
        search_arguments=arguments, saved_result=original, iterations=32,
        expected_search_arguments_sha256=canonical_sha256(arguments),
        expected_saved_result_sha256=canonical_sha256(original))
    expected_comparison['binding']['provenance'] = PROVENANCE
    require(comparison == expected_comparison, 'CONTINUOUS32_COMPARISON_CHANGED')
    selected = expected_comparison['selected']
    bound = public_bound(training_product_upper_bound(
        cash=Fraction(str(arguments['entered_cash'])),
        fee=Fraction(str(arguments['fee_bps'])) / 10000,
        buffer=Fraction(str(arguments['minimum_cash_buffer'])),
        prices=arguments['prices'], scenarios=arguments['training_scenarios'],
        quantities=selected['quantities']))
    expected = dict(original, method_version=VERSION, selected=selected,
        best_by_k=expected_comparison['best_by_k'], training_objective_bound=bound,
        continuous_comparison=expected_comparison,
        coverage_scope='INHERITED_FROM_ORIGINAL_V2_CALL_NO_REPLACEMENT_OF_MANDATORY_COVERAGE',
        objective_evaluations_scope='ORIGINAL_V2_ONLY_ADDITIONAL_EVALUATIONS_SEPARATE',
        global_optimum_established=False)
    require(result == expected, 'CONTINUOUS32_RESULT_CHANGED')
    return deepcopy(selected['quantities'])


def decide_target(**input_arguments):
    inputs = build_target_inputs(**input_arguments)
    binding = deepcopy(inputs['binding'])
    for path in REQUIRED_PINS:
        require(path in binding['source_hashes'] and
                sha256((ROOT / path).read_bytes()).hexdigest() == binding['source_hashes'][path],
                'CONTINUOUS32_RUNTIME_SOURCE_CHANGED')
    binding.update(schema='STRATEGY_ACCOUNT_CONTINUOUS32_INPUT_V1',
                   selection_method=VERSION, selector_profile=PROFILE_ID,
                   continuous_iterations=32, original_input_id=inputs['input_id'])
    result = enhanced_search(**deepcopy(binding['search_arguments']))
    quantities = validate_result(result, binding['search_arguments'])
    payload = dict(schema='REAL_STRATEGY_CONTINUOUS32_TARGET_DECISION_V1',
                   input_id=sha256(canonical(binding)).hexdigest(),
                   input_binding=binding, search_result=result,
                   target_quantities=quantities)
    return dict(status='TARGET_READY' if quantities is not None else 'SEARCH_INCOMPLETE',
                decision_id=sha256(canonical(payload)).hexdigest(), payload=payload,
                core_calls=1, orders_created=False, account_mutated=False,
                execution_blocked=True, limitations=[
                    'Isolated profile; not registered or approved for live use.',
                    '32 extra proposal steps are outside the original V2 search budget.',
                    'Validation recomputes proposals, not the original V2 search.',
                    'HALF exposure is a separate policy and is not enabled here.',
                    'Historical next-open results do not establish live limit-order returns.'])
