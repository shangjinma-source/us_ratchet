"""Value a pinned, complete prepared batch once; no search or account writes."""
import argparse
import hashlib
import json
from pathlib import Path
import types


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(input_path, expected_sha, output):
    root = Path(__file__).resolve().parents[1]
    kernel = root / 'backtest/return_priority_frozen_nominal_outcome.py'
    kernel_sha = '0494a78bdd36b00a6009c9f02e73098104f75c6db57f1e0e6bd805099e68bf70'
    if digest(input_path) != expected_sha or digest(kernel) != kernel_sha:
        raise ValueError('Reviewed input or kernel changed')
    prepared = json.loads(input_path.read_bytes())
    if prepared['pending_search_cutoffs'] or len(prepared['windows']) != 15:
        raise ValueError('Complete frozen selection batch required')
    for name, expected in prepared['source_hashes'].items():
        path = Path(name)
        if digest(path if path.is_absolute() else root / path) != expected:
            raise ValueError('Prepared source changed: ' + name)
    if any(window['price_gaps'] for window in prepared['windows']):
        raise ValueError('Resolve nominal gaps before valuing batch')
    protected = [root / name for name in ('data/state.json', 'data/broker_positions.json',
                                          'config/config.yaml', 'api/server.py', 'web/index.html')]
    before = {str(path): digest(path) for path in protected}
    module = types.ModuleType('frozen_nominal_outcome_pinned')
    exec(compile(kernel.read_bytes(), str(kernel), 'exec'), module.__dict__)
    # Create before any call: interrupted runs must be inspected, never retried.
    output.mkdir()
    def save(name, value):
        with (output / name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
    save('intent.json', dict(input_sha256=expected_sha, kernel_sha256=kernel_sha,
         runner_sha256=digest(Path(__file__)), maximum_outcome_calls=15,
         search_calls=0, protected_before=before))
    summary = []
    try:
        for window in prepared['windows']:
            cutoff = window['decision_cutoff']
            outcome = module.frozen_nominal_outcome(**window['outcome_arguments'])
            save(cutoff + '.json', outcome)
            summary.append(dict(decision_cutoff=cutoff, status=outcome['status'],
                           return_fraction=outcome['return'], maximum_drawdown=outcome['maximum_drawdown']))
        save('result.json', dict(windows=summary, outcome_calls=len(summary), search_calls=0,
             independent_fresh_cash_windows=True, independent_oos=False,
             swing_limit_strategy_tested=False, promotion_allowed=False))
    finally:
        after = {str(path): digest(path) for path in protected}
        save('protected_after.json', dict(hashes=after, unchanged=after == before))
        if after != before:
            raise ValueError('Protected files changed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--input-sha', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run(args.input, args.input_sha, args.output)
