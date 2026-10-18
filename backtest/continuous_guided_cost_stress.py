"""Fixed research stress arms; no IO and no implicit historical execution."""
from copy import deepcopy
import hashlib
import json
import re
from backtest.continuous_guided_cost_full_next_open import run_cost_full_next_open
from backtest.continuous_guided_cost_half_next_open import run_cost_half_next_open


SCENARIOS = {'slippage5': {'fee_bps': '0', 'slippage_bps': '5'},
             'fee1_slippage10': {'fee_bps': '1', 'slippage_bps': '10'}}
ARMS = ('continuous32', 'continuous32_half')


def prepare_arm(assembled, scenario, reviewed_pins=None):
    if scenario not in SCENARIOS:
        raise ValueError('UNDECLARED_COST_SCENARIO')
    result = deepcopy(assembled)
    pins = dict(reviewed_pins or {})
    if any(not isinstance(name, str) or not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value)
           for name, value in pins.items()):
        raise ValueError('INVALID_REVIEWED_PINS')
    if not result['monthly_inputs']:
        raise ValueError('MONTHLY_INPUTS_REQUIRED')
    for plan in result['monthly_inputs']:
        for name, digest in pins.items():
            if name in plan['source_hashes'] and plan['source_hashes'][name] != digest:
                raise ValueError('MONTHLY_SOURCE_PIN_CONFLICT')
            plan['source_hashes'][name] = digest
        arguments = plan['search_arguments']
        if type(arguments['max_objective_evaluations']) is not int or arguments['max_objective_evaluations'] != 8192:
            raise ValueError('FIXED_8192_BUDGET_REQUIRED')
        arguments['fee_bps'] = SCENARIOS[scenario]['fee_bps']
    return result


def run_cost_stress_arm(*, arm, scenario, assembled, ohlc, initial_cash,
                        history_resolver=None, progress=None, reviewed_pins=None):
    if arm not in ARMS:
        raise ValueError('UNDECLARED_ARM')
    prepared = prepare_arm(assembled, scenario, reviewed_pins)
    binding = dict(schema='COST_STRESS_ARM_BINDING_V1', arm=arm, scenario=scenario,
                   initial_cash=str(initial_cash), continuous_iterations=32,
                   max_objective_evaluations=8192, source_hashes=dict(reviewed_pins or {}),
                   **SCENARIOS[scenario])
    binding_hash = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    parameters = dict(assembled=prepared, ohlc=ohlc, initial_cash=initial_cash,
                      progress=progress, **SCENARIOS[scenario])
    if arm == 'continuous32_half':
        if history_resolver is None:
            raise ValueError('HISTORY_RESOLVER_REQUIRED')
        result = run_cost_half_next_open(history_resolver=history_resolver, **parameters)
    else:
        result = run_cost_full_next_open(**parameters)
    result.update(cost_stress_scenario=scenario, cost_stress_arm=arm,
                  cost_stress_binding=binding, cost_stress_binding_sha256=binding_hash,
                  automatic_promotion=False, costs_are_research_assumptions=True)
    result['cost_stress_monthly_bindings'] = [dict(arm_binding_sha256=binding_hash,
        decision_date=row['decision_date'], account_state=deepcopy(row['account_state']))
        for row in result['selection_account_states']]
    return result
