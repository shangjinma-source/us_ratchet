"""Independent saved-input audit; no evaluator, training, or network call."""
import csv
import hashlib
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research/root_return_semantics_probe_20260912_v1'
SHA = 'a0cfca247b790779de4abdfa8ce4d284214cf4405e35e1fb38233f018db6c02b'


def main():
    path = BASE / 'root_return_semantics_review_20260912.json'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SHA
    report = json.loads(path.read_bytes())
    sources = dict(report['source_hashes'])
    sources[str(path)] = SHA
    sources[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def verify():
        for filename, digest in sources.items():
            assert hashlib.sha256(Path(filename).read_bytes()).hexdigest() == digest
    verify()
    manifest = json.loads((BASE / 'manifest.json').read_bytes())
    probe = next(row for row in manifest['probes'] if 'goog' in row['name'])
    raw = json.loads(Path(probe['response_path']).read_bytes())['chart']['result'][0]
    dates = [datetime.fromtimestamp(stamp, ZoneInfo('America/New_York')).date().isoformat() for stamp in raw['timestamp']]
    position = dates.index('2022-07-18')
    quote = raw['indicators']['quote'][0]['close']
    goog_return = quote[position] / quote[position - 1] - 1
    assert dates[position - 1] == '2022-07-15'
    assert abs(goog_return - (-.025335378898117544)) < 1e-15
    windows, comparison_count = [], 0
    for entry in report['actual_window_error_locations']:
        matches = [Path(name) for name, digest in sources.items() if Path(name).name == 'context.json' and digest == entry['context_sha256']]
        assert len(matches) == 1
        prepared = json.loads(matches[0].read_bytes())['prepared_inputs']
        panel = prepared['returns']['payload']['mapping']
        sessions = [row['timestamp'][:10] for row in panel['index']['items']]
        columns = panel['columns']['items']
        contract = prepared['contract']['payload']['mapping']
        fit, width, step = (contract[key] for key in ('fit_days', 'window_days', 'step_days'))
        expected = []
        for ordinal, start in enumerate(range(fit, len(sessions) - width + 1, step)):
            history = sessions[start - fit:start]
            forward = sessions[start:start + width]
            expected.append((history[0], history[-1], forward[0], forward[-1],
                             '2022-07-18' in history, '2022-07-18' in forward))
        assert len(expected) == len(entry['windows'])
        for row, actual in zip(expected, entry['windows']):
            assert row[:4] == (actual['fit_start'], actual['fit_end'], actual['forward_start'], actual['forward_end'])
            assert row[4] == any(e['session'] == '2022-07-18' for e in actual['known_errors_in_fit'])
            assert row[5] == any(e['session'] == '2022-07-18' for e in actual['known_errors_in_forward'])
        for ticker in ('AMAT', 'AVGO', 'CDNS', 'GOOG', 'NVDA'):
            col = columns.index(ticker)
            declared = [float.fromhex(x['float_hex']) for x in panel['column_values']['items'][col]['items']]
            table = list(csv.DictReader((ROOT / 'data/cache' / (ticker + '.csv')).open(encoding='utf8')))
            close = {row['Date']: float(row['Close']) for row in table}
            calendar = list(close)
            derived = {calendar[i]: close[calendar[i]] / close[calendar[i - 1]] - 1 for i in range(1, len(calendar))}
            assert all(actual == derived[day] for actual, day in zip(declared, sessions))
            comparison_count += 1
        windows.append({'selection_date': entry['coordinate']['selection_date'], 'return_rows': len(sessions),
                        'goog_error_fit_windows': sum(row[4] for row in expected),
                        'goog_error_forward_windows': sum(row[5] for row in expected)})
    verify()
    out = dict(schema='ndx_root_return_semantics_independent_audit_v1', status='PASS',
        source_hashes=sources, goog_20220718_price_return=goog_return,
        exact_context_root_return_comparisons=comparison_count, window_locations=windows,
        coverage_scope='FIFTEEN_BOUND_CONTEXTS_FIVE_TICKERS_NOT_ALL_BATCH_TASKS',
        dependency_findings={
            'equal_weight': 'No fit covariance consumption. Forward candidate series changes when GOOG has positive candidate weight; fixed incumbent GOOG return changes paired comparison even if candidate excludes it.',
            'non_equal': 'Fit history changes GOOG-containing candidate covariance/projection/weights. Changed weights also alter turnover fees, risk summaries, lots and later continuous execution state.',
            'turnover_anchor': 'An affected fit can propagate via last_weights anchor to subsequent windows even after the split date exits the current fit window. Changed previous weights can affect following entry cost even without anchor.',
            'v3': 'Projection reconstruction changes numerical failure recovery, not the shared history/forward split-neutrality dependency. Successful v3 reconstruction does not repair the underlying return source.',
            'reuse': 'Window masks are dependency evidence, not automatic exact reuse authorization; all scorer/input dependencies require separate equality proof.'},
        future_meta_counterexample='Provider request META does not justify historical ticker META on 2022-06-08; dated identity evidence requires FB until 2022-06-09.',
        full_training_coverage_limit='First cohort 98/101 and last 97/101 have listed full close dates plus some earlier close; this is not finite-value, adjustment, exact immediately-prior-close, or identity authentication.',
        training_rerun=False, old_training_reuse_authorized=False, point_in_time_verified=False, promotion_allowed=False)
    target = BASE / 'independent_audit_20260912.json'
    with target.open('x', encoding='utf8') as handle:
        json.dump(out, handle, indent=2, sort_keys=True)
        handle.write('\n')
    verify()
    print(json.dumps({'path': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'comparisons': comparison_count}))


if __name__ == '__main__': main()
