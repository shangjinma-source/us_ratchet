"""Create new eligibility-only inputs; never optimize or overwrite old research.

The official source cache is local evidence, not a historical PIT observation.
This entry point only excludes violations of the explicitly reviewed boundaries.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.known_us_regular_boundary_guard import review_window, guarded_search_arguments

DEFAULT_REGISTRY = 'research_contracts/known_us_regular_boundaries_20261025_v1.json'


def read_pinned(root, name, expected=None):
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path.is_symlink():
        raise ValueError('SOURCE_MUST_REMAIN_WITHIN_WORKSPACE')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected is not None and digest != expected:
        raise ValueError('SOURCE_HASH_MISMATCH:' + name)
    return raw, digest


def load_registry(root, name):
    raw, digest = read_pinned(root, name)
    registry = json.loads(raw)
    pins = {name: digest}
    for boundary in registry['boundaries']:
        for source in boundary['sources']:
            if not source['url'].startswith('https://'):
                raise ValueError('HTTPS_PRIMARY_SOURCE_REQUIRED')
            _, source_digest = read_pinned(root, source['path'], source['sha256'])
            pins[source['path']] = source_digest
    return registry, pins


def prepare_window(monthly, training, registry):
    arguments = monthly['search_arguments']
    decision = monthly['decision_date']
    if arguments['decision_date'] != decision or training['training_dates'][-1] != decision:
        raise ValueError('TRAINING_INPUT_DECISION_MISMATCH')
    if arguments['scenario_dates'] != training['training_dates'][21::21]:
        raise ValueError('SCENARIO_DATES_NOT_BOUND_TO_TRAINING_WINDOW')
    if arguments.get('quote_as_of', decision) != decision:
        raise ValueError('QUOTE_DATE_NOT_BOUND_TO_DECISION')
    identified = [row for row in training['candidates'] if row['security_id'] is not None]
    by_identifier = {row['security_id']: row for row in identified}
    if len(by_identifier) != len(identified):
        raise ValueError('DUPLICATE_TRAINING_CANDIDATE')
    candidates = []
    for security_id, metadata in arguments['metadata'].items():
        row = by_identifier[security_id]
        if row['ticker'] != metadata['ticker']:
            raise ValueError('TRAINING_TICKER_MISMATCH')
        candidates.append(dict(security_id=security_id, ticker=row['ticker'],
            training_closes=row.get('training_close', row.get('raw_close', []))))
    review = review_window(decision_date=decision, training_dates=training['training_dates'],
                           candidates=candidates, registry=registry)
    if len(arguments['training_scenarios']) != 12:
        raise ValueError('TWELVE_TRAINING_SCENARIOS_REQUIRED')
    candidate_inputs = {row['security_id']: row for row in candidates}
    for row in review['rows']:
        if row['status'] != 'PASS_KNOWN_US_BOUNDARY_ONLY':
            continue
        security_id = row['security_id']
        closes = candidate_inputs[security_id]['training_closes']
        for index, scenario in enumerate(arguments['training_scenarios']):
            expected = Fraction(closes[(index + 1) * 21]) / Fraction(closes[index * 21])
            if Fraction(scenario[security_id]) != expected:
                raise ValueError('KNOWN_SECURITY_SCENARIO_NOT_BOUND_TO_REVIEWED_CLOSES')
    return dict(decision_date=decision, eligibility=review,
                guarded_search_arguments=guarded_search_arguments(arguments, review))


def prepare(*, root, assembled_path, training_path, registry_path, through=None):
    registry, pins = load_registry(root, registry_path)
    assembled_raw, pins[assembled_path] = read_pinned(root, assembled_path)
    training_raw, pins[training_path] = read_pinned(root, training_path)
    assembled, training = json.loads(assembled_raw), json.loads(training_raw)
    windows = {row.get('decision_date', row.get('decision_cutoff', '')[:10]): row
               for row in training['windows']}
    if len(windows) != len(training['windows']):
        raise ValueError('DUPLICATE_TRAINING_WINDOW')
    monthly = assembled['monthly_inputs']
    if through is not None:
        monthly = [row for row in monthly if row['active_date'] <= through]
    inputs = [prepare_window(row, windows[row['decision_date']], registry) for row in monthly]
    if not inputs:
        raise ValueError('NO_INPUTS_IN_REQUESTED_SCOPE')
    for name in ('backtest/known_us_regular_boundary_guard.py', 'scripts/prepare_known_us_boundary_inputs.py'):
        _, pins[name] = read_pinned(root, name)
    return dict(schema='KNOWN_US_BOUNDARY_FILTERED_INPUTS_V1', inputs=inputs, source_sha256=pins,
        input_count=len(inputs), affected_windows=sum(bool(row['eligibility']['excluded_security_ids']) for row in inputs),
        excluded_security_windows=sum(len(row['eligibility']['excluded_security_ids']) for row in inputs),
        execution_admitted=False, point_in_time_certified=False, historical_results_replaced=False,
        account_written=False, optimization_calls=0, book_calls=0,
        limitation='Known FER/GEHC US ordinary-start boundaries only; unknown members retain their previous conditional status.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assembled', required=True)
    parser.add_argument('--training', required=True)
    parser.add_argument('--registry', default=DEFAULT_REGISTRY)
    parser.add_argument('--through')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT / 'tmp') or output.exists():
        raise ValueError('NEW_TMP_OUTPUT_REQUIRED')
    result = prepare(root=ROOT, assembled_path=args.assembled, training_path=args.training,
                     registry_path=args.registry, through=args.through)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({key: result[key] for key in ('input_count', 'affected_windows',
        'excluded_security_windows', 'optimization_calls', 'book_calls')}))


if __name__ == '__main__':
    main()
