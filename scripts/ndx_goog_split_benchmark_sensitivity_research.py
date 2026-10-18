"""Recompute incumbent windows for one explicit GOOG error; never fit candidates."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_joint_weight_verify import _restore_input
from backtest import ndx_candidate_input_equivalence_v2_research as equivalence
from backtest.ndx_cardinality_discovery import _window_metrics

DIRECTORY = ROOT / 'data/cache/research/root_return_semantics_probe_20260912_v1'


def window_statistics(values):
    gross = [1.0 + float(value) for value in values]
    nav, peak, drawdown = 1.0, 1.0, 0.0
    for factor in gross:
        if not np.isfinite(factor) or factor <= 0:
            raise ValueError('Invalid benchmark return')
        nav *= factor
        peak = max(peak, nav)
        drawdown = max(drawdown, 1.0 - nav / peak)
    return dict(annualized_return=nav ** (252.0 / len(gross)) - 1.0,
                maximum_drawdown=drawdown, terminal_nav=nav)


def main():
    review_path = DIRECTORY / 'root_return_semantics_review_20260912.json'
    expected = 'a0cfca247b790779de4abdfa8ce4d284214cf4405e35e1fb38233f018db6c02b'
    if hashlib.sha256(review_path.read_bytes()).hexdigest() != expected:
        raise ValueError('Original sensitivity evidence changed')
    review = json.loads(review_path.read_bytes())
    sources = dict(review['source_hashes'])
    sources[str(review_path)] = expected
    sources[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for engine in equivalence.previous.ENGINES:
        sources.update(equivalence.previous.numerical_source_hashes(engine))
    equivalence.previous._verify(sources)
    correction, = [row for row in review['known_split_day_return_errors']
                  if row['ticker'] == 'GOOG' and row['session'] == '2022-07-18']
    rows = []
    for location in review['actual_window_error_locations']:
        path, = [Path(path) for path, digest in sources.items()
                 if digest == location['context_sha256'] and Path(path).name == 'context.json']
        context = json.loads(path.read_bytes())
        inputs = {key: _restore_input(value) for key, value in context['prepared_inputs'].items()}
        original = inputs['returns']
        revised = original.copy(deep=True)
        if original.loc[correction['session'], 'GOOG'] != correction['legacy_root_return']:
            raise ValueError('Known old GOOG cell absent')
        revised.loc[correction['session'], 'GOOG'] = correction['provider_split_adjusted_price_return']
        weights = inputs['incumbent_weights']
        tickers = sorted(weights)
        contract = inputs['contract']
        starts = range(contract['fit_days'], len(original) - contract['window_days'] + 1, contract['step_days'])
        variants = []
        # Preserve the two original normalization summation orders explicitly.
        for mode, order in [('EQUAL_BASE_NORMALIZATION', list(weights)), ('NON_EQUAL_AND_V3_NORMALIZATION', tickers)]:
            total = sum(weights[ticker] for ticker in order)
            normalized = pd.Series({ticker: weights[ticker] / total for ticker in order})
            old_series = original[tickers].mul(normalized, axis=1).sum(axis=1)
            new_series = revised[tickers].mul(normalized, axis=1).sum(axis=1)
            windows = []
            for ordinal, start in enumerate(starts):
                end = start + contract['window_days']
                previous = old_series.iloc[start:end]
                after = new_series.iloc[start:end]
                old_metrics, new_metrics = window_statistics(previous), window_statistics(after)
                for series, observed in ((previous, old_metrics), (after, new_metrics)):
                    expected_return, expected_drawdown = _window_metrics(series, len(series), len(series))
                    if (abs(expected_return[0] - observed['annualized_return']) > 1e-13
                            or abs(expected_drawdown[0] - observed['maximum_drawdown']) > 1e-13):
                        raise ValueError('Independent benchmark arithmetic differs from original metric kernel')
                changed = not previous.equals(after)
                if changed != (correction['session'] in previous.index.strftime('%Y-%m-%d')):
                    raise ValueError('Unexpected benchmark delta support')
                windows.append(dict(window_ordinal=ordinal, start=previous.index[0].date().isoformat(),
                    end=previous.index[-1].date().isoformat(), return_row_count=len(previous),
                    old=old_metrics, corrected=new_metrics, daily_returns_changed=changed,
                    annualized_return_delta=new_metrics['annualized_return']-old_metrics['annualized_return'],
                    maximum_drawdown_delta=new_metrics['maximum_drawdown']-old_metrics['maximum_drawdown']))
            variants.append(dict(normalization_mode=mode, normalized_weights=normalized.to_dict(),
                windows=windows, changed_window_count=sum(row['daily_returns_changed'] for row in windows)))
        rows.append(dict(coordinate=location['coordinate'], context_sha256=location['context_sha256'], variants=variants))
    equivalence.previous._verify(sources)
    result = dict(schema='ndx_goog_split_benchmark_sensitivity_v1', source_hashes=sources,
        correction=correction, dates=rows, date_count=len(rows),
        scope='ONE_PROVIDER_EVIDENCED_GOOG_CELL_REPLACEMENT_INCUMBENT_WINDOWS_ONLY',
        candidate_fit_performed=False, candidate_metrics_recomputed=False, candidate_paired_quantiles_inferred=False,
        full_provider_panel_replaced=False, old_contexts_modified=False,
        old_training_rerun=False, original_012922_returns_preserved=True,
        benchmark_is_fractional_constant_daily_weights=True, whole_lot_execution_performed=False,
        current_incumbent_recommendation=False, point_in_time_verified=False, promotion_allowed=False)
    output = DIRECTORY / 'goog_split_benchmark_sensitivity_20260912.json'
    with output.open('x', encoding='utf8') as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')
    print(json.dumps(dict(path=str(output), sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        changed=[dict(date=row['coordinate']['selection_date'],
            windows=[item for item in row['variants'][0]['windows'] if item['daily_returns_changed']]) for row in rows])))


if __name__ == '__main__':
    main()
