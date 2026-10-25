"""Audit completed cost arms without executing or changing the historical run."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from scripts.run_continuous_guided_cost_stress import prepare_run, canonical_hash, OUTPUT, ROOT
from scripts.compare_monthly_latched_exit import integer_text_limit
from scripts.review_continuous_guided_cost_stress import review as review_cash
from scripts.review_cost_stress_nav_metrics import review as review_nav


@integer_text_limit()
def run(scenario, arm):
    if scenario not in ('slippage5', 'fee1_slippage10') or arm not in ('continuous32', 'continuous32_half'):
        raise ValueError('UNKNOWN_ARM')
    prepared, assembled, _, current = prepare_run()
    base = ROOT / OUTPUT
    saved = json.loads((base / 'preflight.json').read_bytes())
    if current != saved:
        raise ValueError('REVIEW_INPUT_DRIFT')
    directory = base / (scenario + '__' + arm)
    terminal = json.loads((directory / 'terminal.json').read_bytes())
    raw = (directory / 'outcome.json').read_bytes()
    if terminal['status'] != 'COMPLETE' or sha256(raw).hexdigest() != terminal['outcome_sha256']:
        raise ValueError('COMPLETED_OUTCOME_REQUIRED')
    outcome = json.loads(raw)
    metrics_raw = (directory / 'metrics.json').read_bytes()
    metrics = json.loads(metrics_raw)
    cash = review_cash(assembled=assembled, ohlc=prepared['ohlc'], outcome=outcome,
        scenario=scenario, expected_pins=saved['source_hashes'], arm=arm, initial_cash='20000')
    nav = review_nav(outcome=outcome, metrics=metrics, assembled=assembled,
                     ohlc=prepared['ohlc'], initial_cash='20000')
    result = dict(status='SAVED_ARM_ARITHMETIC_REVIEWED', scenario=scenario, arm=arm,
        receipt_sha256=canonical_hash(saved), outcome_sha256=terminal['outcome_sha256'],
        metrics_sha256=sha256(metrics_raw).hexdigest(), cash_cost_review=cash, nav_review=nav,
        full_holdings_replay=False, historical_prices_certified=False,
        independent_oos=False, automatic_promotion=False)
    result['reviewer_hashes'] = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in (
        'scripts/review_saved_cost_stress.py', 'scripts/review_continuous_guided_cost_stress.py',
        'scripts/review_cost_stress_nav_metrics.py')}
    destination = ROOT / 'tmp/continuous_guided_cost_stress_reviews_20261019_v1'
    destination.mkdir(exist_ok=True)
    with (destination / (scenario + '__' + arm + '.json')).open('x', encoding='utf8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return dict(status=result['status'], scenario=scenario, arm=arm,
                cash_status=cash['status'], nav_status=nav['status'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', required=True)
    parser.add_argument('--arm', required=True)
    print(json.dumps(run(**vars(parser.parse_args()))))
