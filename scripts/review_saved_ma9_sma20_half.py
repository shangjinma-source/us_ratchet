"""Read-only verification of one completed new arm; never starts a simulation."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from scripts.run_continuous_guided_ma9_sma20_half import (
    ROOT, OUTPUT, ARM, SCENARIOS, prepare_run, canonical_hash, verify_pins,
)
from scripts.compare_monthly_latched_exit import integer_text_limit
from scripts.review_ma9_sma20_half import review
from scripts.review_ma9_sma20_signals import review as review_signals

REVIEWER_PATHS = ['scripts/review_saved_ma9_sma20_half.py',
    'scripts/review_ma9_sma20_half.py', 'scripts/review_ma9_sma20_signals.py',
    'scripts/review_cost_stress_saved_ledger.py', 'scripts/review_cost_stress_nav_metrics.py']

@integer_text_limit()
def run(scenario):
    if scenario not in SCENARIOS:
        raise ValueError('UNKNOWN_SCENARIO')
    reviewer_hashes = {name:sha256((ROOT / name).read_bytes()).hexdigest() for name in REVIEWER_PATHS}
    directory = ROOT / OUTPUT / (scenario + '__' + ARM)
    terminal_path = directory / 'terminal.json'
    terminal_raw = terminal_path.read_bytes()
    terminal = json.loads(terminal_raw)
    if terminal['status'] != 'COMPLETE':
        raise ValueError('COMPLETED_ARM_REQUIRED')
    prepared, assembled, resolver, receipt = prepare_run()
    receipt_hash = canonical_hash(receipt)
    preflight_path = ROOT / OUTPUT / 'preflight.json'
    preflight_raw = preflight_path.read_bytes()
    stored = json.loads(preflight_raw)
    if stored != receipt or canonical_hash(stored) != receipt_hash:
        raise ValueError('SAVED_PREFLIGHT_CHANGED')
    outcome_path = directory / 'outcome.json'
    outcome_raw = outcome_path.read_bytes()
    if sha256(outcome_raw).hexdigest() != terminal['outcome_sha256']:
        raise ValueError('OUTCOME_TERMINAL_MISMATCH')
    metrics_path = directory / 'metrics.json'
    metrics_raw = metrics_path.read_bytes()
    outcome = json.loads(outcome_raw)
    metrics = json.loads(metrics_raw)
    result = review(assembled=assembled, ohlc=prepared['ohlc'], outcome=outcome,
        scenario=scenario, expected_pins=receipt['source_hashes'],
        expected_receipt_sha256=receipt_hash, metrics=metrics)
    signals = review_signals(assembled=assembled, outcome=outcome, history_resolver=resolver)
    verify_pins(receipt['source_hashes'])
    # Reject a changing result while it is being reviewed.
    for path, raw in ((terminal_path, terminal_raw), (outcome_path, outcome_raw),
                      (metrics_path, metrics_raw), (preflight_path, preflight_raw)):
        if sha256(path.read_bytes()).digest() != sha256(raw).digest():
            raise ValueError('RESULT_CHANGED_DURING_REVIEW')
    if any(sha256((ROOT / name).read_bytes()).hexdigest() != digest
           for name, digest in reviewer_hashes.items()):
        raise ValueError('REVIEWER_CHANGED_DURING_REVIEW')
    return dict(status='SAVED_MA9_SMA20_HALF_REVIEWED', scenario=scenario, arm=ARM,
        receipt_sha256=receipt_hash, outcome_sha256=sha256(outcome_raw).hexdigest(),
        metrics_sha256=sha256(metrics_raw).hexdigest(), terminal_sha256=sha256(terminal_raw).hexdigest(),
        evidence_review=result, signal_review=signals,
        reviewer_hashes=reviewer_hashes,
        source_authenticity_certified=False, independent_out_of_sample=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', required=True, choices=list(SCENARIOS))
    args = parser.parse_args()
    destination = ROOT / 'tmp/ma9_sma20_half_reviews_20261019_v1' / (args.scenario + '.json')
    if destination.exists():
        raise FileExistsError('REVIEW_EXISTS')
    result = run(args.scenario)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(status=result['status'], scenario=args.scenario, output=str(destination))))


if __name__ == '__main__':
    main()
