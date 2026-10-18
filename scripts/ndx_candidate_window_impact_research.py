"""Read-only sensitivity masks for one evidenced GOOG correction, fifteen dates."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backtest import ndx_candidate_input_equivalence_v2_research as equivalence
from scripts.ndx_joint_weight_verify import _restore_input

SOURCE = Path(__file__).resolve()
SOURCE_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
REVIEW = ROOT / 'data/cache/research/root_return_semantics_probe_20260912_v1/root_return_semantics_review_20260912.json'
REVIEW_SHA = 'a0cfca247b790779de4abdfa8ce4d284214cf4405e35e1fb38233f018db6c02b'


def run():
    eq = equivalence.previous
    eq._verify({str(REVIEW): REVIEW_SHA, str(SOURCE): SOURCE_SHA})
    review = json.loads(REVIEW.read_bytes())
    eq._verify(review['source_hashes'])
    correction = [row for row in review['known_split_day_return_errors']
                  if row['ticker'] == 'GOOG' and row['session'] == '2022-07-18']
    if len(correction) != 1 or len(review['actual_window_error_locations']) != 15:
        raise ValueError('Explicit known correction and fifteen original contexts required')
    error = correction[0]
    sources = dict(review['source_hashes']) | {str(REVIEW): REVIEW_SHA, str(SOURCE): SOURCE_SHA}
    rows = []
    seen = set()
    for location in review['actual_window_error_locations']:
        context_sha = location['context_sha256']
        paths = [path for path in review['source_hashes'] if context_sha in path and Path(path).name == 'context.json']
        if len(paths) != 1 or location['coordinate']['selection_date'] in seen:
            raise ValueError('Unique context/date required')
        seen.add(location['coordinate']['selection_date'])
        path = paths[0]
        context = json.loads(Path(path).read_bytes())
        inputs = {key: _restore_input(value) for key, value in context['prepared_inputs'].items()}
        if inputs['returns'].loc[error['session'], 'GOOG'] != error['legacy_root_return']:
            raise ValueError('Original GOOG cell differs from bound finding')
        if 'GOOG' not in inputs['incumbent_weights']:
            raise ValueError('Original GOOG incumbent dependency absent')
        changed = deepcopy(inputs)
        changed['returns'].loc[error['session'], 'GOOG'] = error['provider_split_adjusted_price_return']
        cases = []
        for engine in sorted(eq.ENGINES):
            numerical = eq.numerical_source_hashes(engine)
            sources.update(numerical)
            for includes_goog in (False, True):
                combo = sorted(['AMAT', 'AVGO', 'CDNS', 'GOOG' if includes_goog else 'QCOM'])
                task = dict(location['coordinate'], tickers=';'.join(combo), holding_count=4,
                    decision_data_end=str(inputs['returns'].index[-1].date()),
                    weight_spec='equal_weight' if engine == 'equal_weight_fractional_v1'
                    else 'constrained_fixed_shrinkage_turnover_anchor')
                common = dict(task=task, engine=engine, runtime=context['runtime'],
                    source_hashes=numerical | {path: review['source_hashes'][path], str(REVIEW): REVIEW_SHA})
                result = equivalence.compare_candidate_numerical_inputs(
                    left=dict(common, inputs=inputs), right=dict(common, inputs=changed))
                offsets = result['left']['dependency_row_offsets']
                position = inputs['returns'].index.get_loc(error['session'])
                expected_equal = position not in offsets['incumbent_and_target_forward'] and (
                    not includes_goog or position not in offsets['selected_return_union'])
                if result['numerical_input_equivalent'] != expected_equal:
                    raise ValueError('Fingerprint and independent mask classification differ')
                cases.append(dict(engine=engine, selected_includes_goog=includes_goog,
                    selected_tickers=combo, numerical_input_equivalent=result['numerical_input_equivalent'],
                    changed_dependency_fields=result['changed_dependency_fields'],
                    old_fingerprint=result['left']['numerical_input_sha256'],
                    corrected_fingerprint=result['right']['numerical_input_sha256']))
        rows.append(dict(coordinate=location['coordinate'], context_sha256=context_sha,
            known_error_fit_window_count=location['windows_with_error_in_fit'],
            known_error_forward_window_count=location['windows_with_error_in_forward'], cases=cases))
    sources.update(equivalence.previous.LOADED)
    sources[str(equivalence.SOURCE)] = equivalence.LOADED_SHA
    eq._verify(sources)
    return dict(schema='ndx_candidate_window_impact_research_v1', source_hashes=sources,
        scope='ONE_KNOWN_GOOG_RETURN_CELL_CORRECTION_NOT_FULL_PROVIDER_PANEL_REPLACEMENT',
        correction=error, date_count=len(rows), explicit_representative_cases=sum(len(row['cases']) for row in rows),
        rows=rows, selected_fit_effect_can_propagate_through_anchor_and_turnover=True,
        only_directly_overlapping_windows_affected_claimed=False, all_candidate_results_recomputed=False,
        training_performed=False, checkpoints_reused=False, old_records_invalidated=False,
        point_in_time_verified=False, promotion_allowed=False)


if __name__ == '__main__':
    report = run()
    path = REVIEW.with_name('candidate_window_impact_v2_20260912.json')
    raw = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    with path.open('xb') as handle: handle.write(raw)
    equivalence.previous._verify(report['source_hashes'])
    print(json.dumps(dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), dates=report['date_count'],
                         representative_cases=report['explicit_representative_cases'])))
