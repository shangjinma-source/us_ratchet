"""Full-denominator research planning and globally budgeted incremental evaluation.

Default is read-only plan validation. Captured prepared inputs are immutable
JSON, so daily cache appends do not silently create a different resume context.
"""
import argparse
import hashlib
import io
import json
import platform
from pathlib import Path
import sys

import pandas as pd
import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.ndx_joint_weight_delta import build_joint_weight_delta_plan, SUPPORTED_WEIGHT_SPECS
from backtest.ndx_joint_weight_evaluation import CONTRACT_FIELDS
from backtest.ndx_joint_weight_history_inputs import _Sources, prepare_joint_weight_history_inputs
from backtest.ndx_two_stage_joint_coverage import select_joint_coverage_security_sets
from backtest.ndx_joint_weight_runner import (
    _lock, _publish, _sha, _normalize, _panel_context, _source_hashes, _json_bytes,
    run_joint_weight_tasks)

BATCH_ROOT = ROOT / 'data/cache/research/ndx_joint_weight_batches_v1'
PROTECTED = ('config/config.yaml', 'data/state.json', 'data/broker_positions.json')
SCHEMA = 'ndx_joint_weight_revised_experiment_v1'


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _decode(value):
    if isinstance(value, dict):
        if set(value) == {'float_hex'}:
            return float.fromhex(value['float_hex'])
        if set(value) == {'timestamp'}:
            return pd.Timestamp(value['timestamp'])
        if set(value) == {'mapping'}:
            return {k: _decode(v) for k, v in value['mapping'].items()}
        if set(value) == {'sequence_type', 'items'}:
            items = [_decode(v) for v in value['items']]
            return tuple(items) if value['sequence_type'] == 'tuple' else items
        raise ValueError('Unknown captured normalized value')
    return value


def _restore_panel(value):
    raw = _decode(value['payload'])
    if value['kind'] == 'non_panel':
        return raw
    _require(value['kind'] == 'panel', 'Invalid captured panel')
    index = pd.Index(raw['index'], dtype=raw['index_dtype'], name=raw['index_names'][0])
    frame = pd.concat([pd.Series(values, index=index, dtype=dtype, name=column)
        for column, values, dtype in zip(raw['columns'], raw['column_values'], raw['dtypes'])], axis=1)
    if raw['container_type'] == 'Series':
        result = frame.iloc[:, 0]
        result.name = raw['series_name']
        return result
    _require(raw['container_type'] == 'DataFrame', 'Unknown panel container')
    return frame


def build_plan(experiment_path):
    sources = _Sources()
    path = Path(experiment_path).resolve()
    raw = path.read_bytes()
    sources.observe(path, raw)
    experiment = json.loads(raw)
    _require(experiment.get('schema') == SCHEMA, 'Invalid experiment schema')
    _require(set(experiment['evaluation_contract']) == CONTRACT_FIELDS, 'Complete explicit evaluation contract required')
    _require(type(experiment['allow_revised_return_data']) is bool, 'Explicit revised-data flag required')
    _require(experiment['per_frontier_limit'] == 16, 'Coverage requires frontier limit 16')
    _require(sorted(experiment['second_stage_weight_specs']) == sorted(SUPPORTED_WEIGHT_SPECS),
             'Both weight models required')
    for key in ('training_lookback_days', 'minimum_price_rows_before_selection'):
        _require(type(experiment[key]) is int and experiment[key] > 0, 'Invalid explicit history window')
    original = json.loads(sources.read(experiment['original_screen']))
    coverage = json.loads(sources.read(experiment['coverage_report']))
    for relative, digest in coverage.get('sources', {}).items():
        sources.read(dict(path=str(ROOT/relative),sha256=digest))
    _require(coverage['base_original_screen_sha256'] == experiment['original_screen']['sha256'],
             'Coverage/original screen mismatch')
    coverage_rows = {(r['date'], r['k']): r for r in coverage['rows']}
    _require(len(coverage_rows) == len(coverage['rows']) == len(original['rows']), 'Coverage coordinate duplicates/gaps')
    plans = []
    for row in original['rows']:
        child = json.loads(sources.read(dict(path=row['child_manifest_path'], sha256=row['child_manifest_sha256'])))
        coordinate_key = (child['selection_date'], child['holding_count'])
        _require(coordinate_key == (row['date'], row['k']), 'Original coordinate mismatch')
        expected = coverage_rows.pop(coordinate_key)
        candidates_raw = sources.read(dict(path=row['path'], sha256=row['sha256']))
        descriptor=child['artifacts']['candidates']
        _require(descriptor['sha256'] == row['sha256'] and Path(descriptor['path']).resolve() == Path(row['path']).resolve()
                 and descriptor.get('rows',row['candidate_rows']) == row['candidate_rows'], 'Child candidate binding differs')
        candidates = pd.read_csv(io.BytesIO(candidates_raw), dtype=str, keep_default_na=False)
        equal = candidates.loc[candidates.weight_spec.eq('equal_weight')]
        _require(len(candidates) == row['candidate_rows'] and len(equal) == child['search_audit']['first_stage_security_sets'],
                 'Candidate denominator differs')
        selected = select_joint_coverage_security_sets(equal, selection_date=child['selection_date'],
            decision_data_end=child['training_end'], per_frontier_limit=16)
        old = pd.read_csv(io.BytesIO(sources.read(child['artifacts']['second_stage_shortlist'])), dtype=str, keep_default_na=False)
        columns = ['tickers', 'second_stage_selection_tags']
        _require(old[columns].sort_values('tickers').to_dict('records') ==
                 selected['legacy_control'][columns].sort_values('tickers').to_dict('records'), 'Legacy shortlist differs')
        _require(len(old) == child['search_audit']['second_stage_security_sets'], 'Legacy denominator differs')
        added = sorted(set(selected['selected'].tickers)-set(old.tickers))
        _require(_digest(selected['selected'].to_dict('records')) == expected['selected_sha256']
                 and _digest(added) == expected['added_sets_sha256'], 'Coverage selection digest differs')
        _require(all(selected['audit'][k] == v for k,v in expected['audit'].items()), 'Coverage audit differs')
        coordinate = dict(source_batch=Path(row['child_manifest_path']).parents[7].name,
            universe_track=child['universe_track'], selection_date=child['selection_date'],
            holding_count=child['holding_count'], decision_data_end=child['training_end'],
            child_manifest_sha256=row['child_manifest_sha256'])
        delta = build_joint_weight_delta_plan(equal, coordinate=coordinate,
            second_stage_weight_specs=experiment['second_stage_weight_specs'], per_frontier_limit=16)
        _require(len(delta['tasks']) == expected['additional_model_evaluations'], 'Delta denominator differs')
        plans.append(dict(child_path=row['child_manifest_path'], child_sha256=row['child_manifest_sha256'],
                          tasks=delta['tasks'], coordinate=coordinate))
    _require(not coverage_rows and sum(len(p['tasks']) for p in plans) == coverage['additional_model_evaluations'],
             'Incomplete global denominator')
    sources.validate_unchanged()
    return dict(experiment=experiment, experiment_sha256=hashlib.sha256(raw).hexdigest(), plans=plans,
                sources=sources, planned=sum(len(p['tasks']) for p in plans))


def _captured_inputs(destination, plan, experiment, experiment_hash, cli_hash):
    numerical_sources = _source_hashes()
    runtime = dict(python=platform.python_version(), numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__)
    path = destination / (plan['child_sha256'] + '.json')
    if path.exists():
        raw = path.read_bytes()
        captured = json.loads(raw)
        digest = captured.pop('capture_sha256')
        _require(_sha(captured) == digest and _json_bytes({**captured,'capture_sha256':digest}) == raw,
                 'Captured input checksum/encoding differs')
        _require(captured['schema'] == 'ndx_joint_weight_batch_capture_v1'
                 and captured['numerical_sources'] == numerical_sources and captured['runtime'] == runtime,
                 'Captured numerical source/runtime differs')
        _require(captured['experiment_sha256'] == experiment_hash and captured['cli_sha256'] == cli_hash
                 and _json_bytes(captured['tasks']) == _json_bytes(plan['tasks']), 'Captured experiment/code/task differs')
        prepared = {k:_restore_panel(v) for k,v in captured['prepared_inputs'].items()}
        for key,value in prepared.items():
            _require(_json_bytes(_panel_context(value)) == _json_bytes(captured['prepared_inputs'][key]),
                     'Captured input canonical roundtrip differs')
            if isinstance(value,(pd.DataFrame,pd.Series)):
                metadata=captured['panel_metadata'][key]
                if isinstance(value,pd.DataFrame):
                    value.columns.names=metadata['column_names']
                if metadata['index_frequency'] is not None:
                    value.index.freq=metadata['index_frequency']
        evidence = _decode(captured['source_evidence'])
        _require(_json_bytes(_normalize(evidence)) == _json_bytes(captured['source_evidence']),
                 'Captured source evidence canonical roundtrip differs')
        return prepared, evidence
    value = prepare_joint_weight_history_inputs(plan['child_path'], plan['child_sha256'],
        evaluation_contract=experiment['evaluation_contract'], training_lookback_days=experiment['training_lookback_days'],
        minimum_price_rows_before_selection=experiment['minimum_price_rows_before_selection'],
        allow_revised_return_data=experiment['allow_revised_return_data'])
    evidence = dict(experiment_sha256=experiment_hash, cli_sha256=cli_hash, loader_provenance=value['provenance'])
    prepared = {k:value[k] for k in ('universe','returns','target_returns','nominal_prices','incumbent_weights','contract')}
    captured = dict(schema='ndx_joint_weight_batch_capture_v1', experiment_sha256=experiment_hash,
        numerical_sources=numerical_sources,runtime=runtime,
        panel_metadata={k:dict(column_names=list(v.columns.names) if isinstance(v,pd.DataFrame) else None,
            index_frequency=v.index.freqstr if isinstance(v.index,pd.DatetimeIndex) else None)
            for k,v in prepared.items() if isinstance(v,(pd.DataFrame,pd.Series))},
        cli_sha256=cli_hash, tasks=plan['tasks'], prepared_inputs={k:_panel_context(v) for k,v in prepared.items()},
        source_evidence=_normalize(evidence))
    captured['capture_sha256'] = _sha(captured)
    _publish(path,captured)
    return prepared,evidence


def execute_plan(plan, *, max_new_evaluations, destination, cli_hash):
    _require(type(max_new_evaluations) is int and max_new_evaluations > 0, 'Positive global budget required')
    attempted = completed = resumed = 0
    rows = []
    for coordinate in plan['plans']:
        count = len(coordinate['tasks'])
        status = 'NO_DELTA' if count == 0 else 'NOT_VISITED'
        result = dict(coordinate=coordinate['coordinate'], planned=count, status=status)
        if count and attempted < max_new_evaluations:
            prepared,evidence = _captured_inputs(destination, coordinate, plan['experiment'],
                                                 plan['experiment_sha256'], cli_hash)
            outcome = run_joint_weight_tasks(coordinate['tasks'], prepared_inputs=prepared,
                source_evidence=evidence, max_tasks=max_new_evaluations-attempted)
            result.update(outcome)
            attempted += outcome['attempted']; completed += outcome['completed']; resumed += outcome['resumed']
        rows.append(result)
    return dict(planned=plan['planned'], attempted=attempted, completed=completed, resumed=resumed, coordinates=rows,
        status='COMPLETE' if all(r['status'] in ('NO_DELTA','COMPLETE') for r in rows) else 'PARTIAL',
        promotion_allowed=False, unvisited_completion_unknown=True)


def run(experiment_path, *, execute=False, max_new_evaluations=None):
    protected = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in PROTECTED}
    cli_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        plan = build_plan(experiment_path)
        if not execute:
            return dict(status='PLAN_ONLY',planned=plan['planned'],coordinates=len(plan['plans']),promotion_allowed=False)
        _require(type(max_new_evaluations) is int and max_new_evaluations > 0, 'Execute requires positive global budget')
        # Bind both full hashes without exceeding Windows legacy path limits.
        destination = BATCH_ROOT / _sha(dict(experiment_sha256=plan['experiment_sha256'], cli_sha256=cli_hash))
        destination.mkdir(parents=True,exist_ok=True)
        with _lock(destination/'.lock'):
            result = execute_plan(plan,max_new_evaluations=max_new_evaluations,destination=destination,cli_hash=cli_hash)
        plan['sources'].validate_unchanged()
        return result
    finally:
        _require(protected == {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in PROTECTED},
                 'Protected live files changed during batch')
        _require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == cli_hash, 'Batch source changed during run')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--max-new-evaluations',type=int)
    args=parser.parse_args()
    print(json.dumps(run(args.experiment,execute=args.execute,max_new_evaluations=args.max_new_evaluations),ensure_ascii=False,indent=2))
