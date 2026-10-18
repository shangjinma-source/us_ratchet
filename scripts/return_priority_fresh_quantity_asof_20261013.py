"""Create-only current conditional quantity search; no account or API writes."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / 'tmp/fresh_quantity_input_asof_20261013_v1'
OUTPUT = ROOT / 'tmp/fresh_quantity_actual_asof_20261013_v1'
CORE = ROOT / 'backtest/return_priority_fresh_cash_quantity_search.py'
PROTECTED = ('data/state.json', 'data/broker_positions.json', 'config/config.yaml', 'api/server.py', 'web/index.html')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reviewed-core-sha256', required=True)
    args = parser.parse_args()
    if OUTPUT.exists():
        raise ValueError('Create-only search exists; inspect saved outcome, do not rerun')
    if digest(CORE) != args.reviewed_core_sha256:
        raise ValueError('Reviewed core changed')
    inputs = json.loads((INPUTS / 'inputs.json').read_bytes())
    registration = json.loads((INPUTS / 'registration.json').read_bytes())
    for path, expected in registration['source_pins'].items():
        if digest(ROOT / path) != expected:
            raise ValueError('Changed input source: ' + path)
    if inputs['max_objective_evaluations'] != 8192 or inputs['decision_date'] != '2026-10-13':
        raise ValueError('Registered finite budget/date changed')
    protected = {path: digest(ROOT / path) for path in PROTECTED}
    OUTPUT.mkdir(exist_ok=False)

    def save(name, value):
        with (OUTPUT / name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)

    save('start.json', dict(core_sha256=args.reviewed_core_sha256,
                            inputs_sha256=digest(INPUTS / 'inputs.json'),
                            registration_sha256=digest(INPUTS / 'registration.json'),
                            runner_sha256=digest(Path(__file__)), protected_before=protected,
                            scope='CURRENT_CONDITIONAL_PRICE_SCENARIO_FIT_NOT_FORECAST',
                            maximum_objective_evaluations=8192, broker_orders_authorized=False))
    core = importlib.import_module('backtest.return_priority_fresh_cash_quantity_search')
    result = core.search_fresh_cash_quantities(**inputs)
    save('result.json', result)
    after = {path: digest(ROOT / path) for path in PROTECTED}
    if after != protected or digest(CORE) != args.reviewed_core_sha256:
        raise ValueError('Protected files or core changed during search; result not verified')
    for path, expected in registration['source_pins'].items():
        if digest(ROOT / path) != expected:
            raise ValueError('Source changed during search: ' + path)
    save('receipt.json', dict(status='SEARCH_RETURNED_REQUIRES_INDEPENDENT_READBACK',
                              result_sha256=digest(OUTPUT / 'result.json'), protected_after=after,
                              original_book_replays=0, source_registration=registration,
                              current_service_changed=False, forecast_return=None,
                              point_in_time_verified=False, total_return_certified=False))
    print(json.dumps(dict(output=str(OUTPUT), result_keys=list(result))))


if __name__ == '__main__':
    main()
