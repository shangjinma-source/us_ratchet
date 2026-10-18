"""Window-aware input equality, with complete v1 legality checks retained."""
from copy import deepcopy
import hashlib
from pathlib import Path

from backtest import ndx_candidate_input_equivalence_research as previous

SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def candidate_numerical_input_fingerprint(**arguments):
    arguments = deepcopy(arguments)
    checked = previous.candidate_numerical_input_fingerprint(**arguments)
    inputs, task, engine = arguments['inputs'], arguments['task'], arguments['engine']
    payload = deepcopy(checked['payload'])
    fit_days, window_days = inputs['contract']['fit_days'], inputs['contract']['window_days']
    starts = payload['window_offsets']
    forward = sorted({position for start in starts for position in range(start, start + window_days)})
    fit = ([] if engine == 'equal_weight_fractional_v1' else
           sorted({position for start in starts for position in range(start-fit_days, start)}))
    selected_rows = sorted(set(fit) | set(forward))
    nominal_rows = list(range(starts[0], starts[-1]+window_days)) if engine == 'joint_weight_v3' else []
    for key in ('returns', 'target_returns', 'nominal_prices'):
        payload.pop(key)
    payload.update(schema='ndx_candidate_numerical_input_projection_v2',
        full_calendar=[str(day.date()) for day in inputs['returns'].index],
        selected_returns=previous._panel(inputs['returns'].iloc[selected_rows], task['tickers'].split(';')),
        incumbent_forward_returns=previous._panel(inputs['returns'].iloc[forward], sorted(inputs['incumbent_weights'])),
        target_forward_returns=previous._panel(inputs['target_returns'].iloc[forward]),
        continuous_execution_nominal_prices=(previous._panel(inputs['nominal_prices'].iloc[nominal_rows],
            task['tickers'].split(';')) if nominal_rows else None))
    sources = dict(checked['source_hashes'])
    if str(SOURCE) in sources and sources[str(SOURCE)] != LOADED_SHA:
        raise ValueError('Conflicting v2 equivalence source')
    sources[str(SOURCE)] = LOADED_SHA
    previous._verify(sources)
    return dict(schema='ndx_candidate_numerical_input_fingerprint_research_v2',
        numerical_input_sha256=previous._digest(payload), payload=payload,
        source_hashes=sources, full_training_semantics=checked['full_training_semantics'],
        v1_conservative_input_sha256=checked['numerical_input_sha256'],
        dependency_row_offsets=dict(selected_fit=fit, selected_forward=forward,
            selected_return_union=selected_rows, incumbent_and_target_forward=forward,
            continuous_execution_nominal=nominal_rows),
        dependency_projection='WINDOW_AWARE_SUFFICIENT_INPUT_EQUALITY_NOT_RESULT_REUSE_PERMISSION',
        entire_supplied_input_validation_passed=True,
        fractional_nominal_channel='VALIDATION_ONLY_NOT_NUMERICAL_OUTPUT_DEPENDENCY',
        synthetic_selection_price='CONSERVATIVELY_RETAINED_DISCARDED_FLOOR_DIAGNOSTICS',
        runtime_record_authenticated=False, source_to_typed_input_linkage_verified=False,
        historical_result_verified=False, candidate_membership_verified=False,
        price_identity_authenticated=False, point_in_time_verified=False,
        result_reuse_authorized=False, execution_performed=False, promotion_allowed=False)


def compare_candidate_numerical_inputs(*, left, right):
    before = candidate_numerical_input_fingerprint(**left)
    after = candidate_numerical_input_fingerprint(**right)
    previous._verify(before['source_hashes'])
    previous._verify(after['source_hashes'])
    changed = sorted(key for key in before['payload'] if before['payload'][key] != after['payload'][key])
    return dict(schema='ndx_candidate_numerical_input_equivalence_research_v2',
        numerical_input_equivalent=not changed, changed_dependency_fields=changed,
        left=before, right=after,
        full_training_semantics_equal=before['full_training_semantics'] == after['full_training_semantics'],
        v1_conservative_projection_equal=before['v1_conservative_input_sha256'] == after['v1_conservative_input_sha256'],
        prior_results_reused=False, result_reuse_authorized=False, point_in_time_verified=False,
        global_search_completeness_verified=False, whole_lot_result_reuse_allowed=False,
        new_scope_membership_verified=False, execution_performed=False, promotion_allowed=False)
