"""Once-only four-arm historical research runner; default is read-only preflight."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

from backtest.continuous_guided_cost_stress import ARMS, SCENARIOS, prepare_arm, run_cost_stress_arm
from scripts.preflight_continuous_guided_cost_stress import preflight
from scripts.run_continuous_guided_half_exposure import prepare
from scripts.compare_monthly_latched_exit import statistics, integer_text_limit

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = 'tmp/continuous_guided_cost_stress_20261019_v1'
RUNNER = 'scripts/run_continuous_guided_cost_stress.py'


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def verify_pins(pins):
    for name, expected in pins.items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('SOURCE_DRIFT:' + name)


def prepare_run():
    receipt = preflight()
    with patch('urllib.request.urlopen', side_effect=AssertionError('OFFLINE_PREFLIGHT')):
        prepared, assembled, _, resolver = prepare()
    pins = dict(receipt['source_hashes'])
    for name in (RUNNER, 'scripts/compare_monthly_latched_exit.py', 'backtest/continuous_calendar_year_metrics.py'):
        digest = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if name in pins and pins[name] != digest:
            raise ValueError('RUN_SOURCE_CONFLICT')
        pins[name] = digest
    verify_pins(pins)
    bindings = []
    for scenario in SCENARIOS:
        arm_inputs = prepare_arm(assembled, scenario, pins)
        for arm in ARMS:
            bindings.append(dict(arm=arm, scenario=scenario,
                assembled_sha256=canonical_hash(arm_inputs), **SCENARIOS[scenario]))
    receipt = dict(receipt, schema='COST_STRESS_RUN_RECEIPT_V1', source_hashes=pins,
                   initial_cash='20000', output_directory=OUTPUT, arm_bindings=bindings,
                   prepared_sha256=canonical_hash(prepared),
                   execution_gate='EXACT_REVIEWED_RECEIPT_SHA256_AND_CREATE_ONLY_FIXED_DIRECTORY')
    return prepared, assembled, resolver, receipt


def summarize(outcome, assembled, ohlc):
    report = statistics(outcome, assembled['session_dates'])
    fills = [row for row in outcome['order_log'] if row['event'] == 'ASSUMED_NEXT_OPEN_FILLED']
    report['modeled_slippage_dollars'] = str(sum((row['quantity'] * abs(
        Fraction(row['price']) - Fraction(ohlc[row['security_id']][row['date']]['open']))
        for row in fills), Fraction(0)))
    previous = {}
    changes = []
    for row in outcome['daily_ledger']:
        shares = {sid: quantity for sid, quantity in row['shares'].items() if quantity}
        if shares != previous:
            changes.append(dict(date=row['date'], previous=previous, shares=shares))
            previous = shares
    report['dated_position_changes'] = changes
    report['cost_stress_binding_sha256'] = outcome['cost_stress_binding_sha256']
    return report


@integer_text_limit()
def run_once(output_directory=OUTPUT, expected_receipt_sha256=None, execute=False):
    output = (ROOT / output_directory).resolve()
    if output != (ROOT / OUTPUT).resolve():
        raise ValueError('FIXED_ONCE_ONLY_OUTPUT_REQUIRED')
    if execute and output.exists():
        raise FileExistsError('EXISTING_RUN_NO_RETRY')
    prepared, assembled, resolver, receipt = prepare_run()
    digest = canonical_hash(receipt)
    if not execute:
        return dict(receipt=receipt, receipt_sha256=digest, status='PREFLIGHT_ONLY_NO_SEARCH')
    if expected_receipt_sha256 != digest:
        raise ValueError('REVIEWED_RECEIPT_SHA256_REQUIRED')
    verify_pins(receipt['source_hashes'])
    output.mkdir(exist_ok=False, parents=True)

    def save(path, value):
        with path.open('x', encoding='utf8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())

    stamp = lambda: datetime.now(timezone.utc).isoformat()
    save(output / 'started.json', dict(at=stamp(), pid=os.getpid(), receipt_sha256=digest))
    try:
        save(output / 'preflight.json', receipt)
        reports = {}
        with patch('urllib.request.urlopen', side_effect=AssertionError('OFFLINE_COST_STRESS')):
            for scenario in SCENARIOS:
                reports[scenario] = {}
                for arm in ARMS:
                    verify_pins(receipt['source_hashes'])
                    directory = output / (scenario + '__' + arm)
                    directory.mkdir(exist_ok=False)
                    save(directory / 'started.json', dict(at=stamp(), scenario=scenario, arm=arm))
                    def progress(row):
                        with (directory / 'progress.jsonl').open('a', encoding='utf8') as handle:
                            handle.write(json.dumps(row) + '\n')
                            handle.flush()
                            os.fsync(handle.fileno())
                    result = run_cost_stress_arm(arm=arm, scenario=scenario,
                        assembled=deepcopy(assembled), ohlc=deepcopy(prepared['ohlc']),
                        initial_cash='20000', history_resolver=resolver, progress=progress,
                        reviewed_pins=receipt['source_hashes'])
                    save(directory / 'outcome.json', result)
                    verify_pins(receipt['source_hashes'])
                    save(directory / 'terminal.json', dict(at=stamp(), status=result['status'],
                        outcome_sha256=hashlib.sha256((directory / 'outcome.json').read_bytes()).hexdigest()))
                    if result['status'] != 'COMPLETE':
                        raise ValueError('ARM_NOT_COMPLETE:' + scenario + ':' + arm)
                    reports[scenario][arm] = summarize(result, assembled, prepared['ohlc'])
                    save(directory / 'metrics.json', reports[scenario][arm])
        comparisons = {}
        for scenario, arms in reports.items():
            full, half = arms['continuous32'], arms['continuous32_half']
            comparisons[scenario] = dict(joint_improvement=
                Fraction(half['final_equity']) >= Fraction(full['final_equity']) and
                Fraction(half['maximum_close_drawdown']) < Fraction(full['maximum_close_drawdown']))
        verify_pins(receipt['source_hashes'])
        save(output / 'comparison.json', dict(status='PENDING_INDEPENDENT_REVIEW', arms=reports,
            comparisons=comparisons, both_scenarios_joint_improvement=all(
                row['joint_improvement'] for row in comparisons.values()),
            automatic_promotion=False, independent_oos=False, point_in_time_certified=False))
        terminal = dict(status='COMPLETE_PENDING_INDEPENDENT_REVIEW', at=stamp(),
                        source_pins_unchanged=True, automatic_promotion=False)
        save(output / 'terminal.json', terminal)
        return terminal
    except BaseException as error:
        save(output / 'terminal.json', dict(status='FAILED', at=stamp(),
            error_type=type(error).__name__, reason=str(error), automatic_retry_allowed=False))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--expected-receipt-sha256')
    arguments = parser.parse_args()
    print(json.dumps(run_once(execute=arguments.execute,
        expected_receipt_sha256=arguments.expected_receipt_sha256), ensure_ascii=False, indent=2))
