"""Read-only fixed four-arm preflight. No execute option or economic run."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from backtest.continuous_guided_cost_stress import ARMS, SCENARIOS, prepare_arm
from scripts.run_continuous_guided_half_exposure import prepare

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = 'research_contracts/continuous_guided_cost_stress_20261019_v1.json'
CONTRACT_SHA256 = 'bba2e3246f62454d44f5650d5b037eb5c4d071a3becb81836baf830d93bb4bb7'


def preflight():
    raw = (ROOT / CONTRACT).read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONTRACT_SHA256:
        raise ValueError('DECLARED_CONTRACT_CHANGED')
    contract = json.loads(raw)
    if contract['scenarios'] != SCENARIOS or contract['arms'] != list(ARMS):
        raise ValueError('CONTRACT_IMPLEMENTATION_MISMATCH')
    if (contract['initial_cash'], contract['continuous_iterations'], contract['max_objective_evaluations'],
        contract['signal_window'], contract['off_exposure']) != ('20000', 32, 8192, 20, '1/2'):
        raise ValueError('FIXED_ECONOMIC_PARAMETERS_REQUIRED')
    saved = (ROOT / contract['zero_cost_comparison']).read_bytes()
    if hashlib.sha256(saved).hexdigest() != contract['zero_cost_comparison_sha256']:
        raise ValueError('SEALED_COMPARISON_CHANGED')
    with patch('urllib.request.urlopen', side_effect=AssertionError('OFFLINE_PREFLIGHT')):
        _, assembled, original_receipt, _ = prepare()
    configurations = []
    for scenario in SCENARIOS:
        arm_inputs = prepare_arm(assembled, scenario)
        for arm in ARMS:
            configurations.append(dict(arm=arm, scenario=scenario,
                monthly_windows=len(arm_inputs['monthly_inputs']), **SCENARIOS[scenario]))
    pins = dict(original_receipt['source_hashes'])
    for name in (CONTRACT, 'backtest/continuous_guided_cost_stress.py',
                 'backtest/continuous_guided_cost_half_next_open.py',
                 'backtest/continuous_guided_cost_full_next_open.py',
                 'backtest/continuous_guided_cost_monthly_provider.py',
                 'scripts/preflight_continuous_guided_cost_stress.py'):
        pins[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    return dict(status='PREFLIGHT_ONLY_NO_SEARCH', scenarios=configurations,
                source_hashes=pins, search_calls=0, account_writes=False,
                historical_execution_enabled=False, automatic_promotion=False)


if __name__ == '__main__':
    print(json.dumps(preflight(), indent=2))
