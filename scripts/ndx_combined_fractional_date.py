"""Source-bound, date-complete base plus delta fractional research cohort.

This adapter never trains, refits, admits a portfolio, or writes an artifact.
Unknown current technology eligibility is intentionally not promoted to True.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from scripts import ndx_equal_weight_base_report as equal_report
from scripts import ndx_non_equal_base_readback as non_equal_readback
from scripts import ndx_dynamic_training_date_v2 as delta_date
from backtest.ndx_fractional_research_gates import fractional_research_gates
from backtest.ndx_dynamic_research_selector import select_research_lane

ROOT = Path(__file__).resolve().parents[1]
_LOADED = {str(ROOT / name): hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
           for name in ('scripts/ndx_combined_fractional_date.py',
                        'scripts/ndx_equal_weight_base_report.py',
                        'scripts/ndx_non_equal_base_readback.py',
                        'scripts/ndx_dynamic_training_date_v2.py',
                        'backtest/ndx_fractional_research_gates.py',
                        'backtest/ndx_dynamic_research_selector.py')}
_KEYS = ('source_batch', 'universe_track', 'selection_date')


def _merge_sources(*maps):
    merged = {}
    for mapping in maps:
        for path, digest in mapping.items():
            if path in merged and merged[path] != digest:
                raise ValueError('Conflicting source binding: ' + path)
            merged[path] = digest
    return merged


def _check_sources(sources):
    for path, digest in sources.items():
        if not Path(path).is_absolute() or hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('Source closure differs: ' + path)


def _combine(*, equal, non_equal, delta, policy_role):
    coordinate = equal['coordinate']
    semantics = equal['training_semantics']
    signature = semantics['training_semantics_sha256']
    cutoff = semantics['payload']['decision_data_end']
    context = non_equal['context']
    if (any(context[key] != coordinate[key] or delta['expected_date'][key] != coordinate[key]
            for key in _KEYS) or context['training_semantics'] != semantics):
        raise ValueError('Base and delta coordinates or training semantics differ')
    counts = equal['input_summary']
    equal_count = counts['equal_weight_base_count']
    base_count = counts['all_base_count']
    delta_count = counts['delta_count']
    if (any(type(value) is not int or value < 0 for value in (equal_count, base_count, delta_count))
            or equal_count > base_count or context['planned'] != base_count - equal_count
            or non_equal['planned'] != context['planned']
            or len(context['tasks']) != context['planned']
            or delta['expected_date']['expected_task_count'] != delta_count
            or len(equal['evaluation']['records']) != equal_count):
        raise ValueError('Base/delta task denominators differ')
    if delta_count and (delta['expected_date']['training_semantics_sha256'] != signature
                        or delta['expected_date']['decision_data_end'] != cutoff):
        raise ValueError('Delta training semantics or cutoff differ')
    expected = dict(coordinate, expected_task_count=base_count + delta_count,
                    decision_data_end=cutoff, training_semantics_sha256=signature)
    records, definitions = [], set()

    def append(task, metrics, status, origin, record_signature=signature):
        if any(task[key] != coordinate[key] for key in _KEYS) or task['decision_data_end'] != cutoff:
            raise ValueError('Task coordinate or cutoff differs')
        definition = (tuple(sorted(task['tickers'].split(';'))), task['weight_spec'])
        if definition in definitions:
            raise ValueError('Duplicate base/delta portfolio definition')
        definitions.add(definition)
        # Old delta results carry the historical $5000 whole-lot diagnostics.
        # They cannot become a mixed aggregate gate in this common cohort.
        clean_metrics = ({key: deepcopy(value) for key, value in metrics.items()
                          if not key.startswith('whole_lot_') and key not in (
                              'declared_constraints_passed', 'constraint_failure_reasons',
                              'projection_reconstruction_audit')}
                         if isinstance(metrics, dict) else None)
        record = dict(task=deepcopy(task), result=clean_metrics, status=status,
                      origin=origin, training_semantics_sha256=record_signature, eligibility={})
        if status == 'EVALUATED':
            try:
                record['eligibility'] = fractional_research_gates(
                    metrics=metrics, contract=semantics['payload']['contract'],
                    holding_count=task['holding_count'])
            except (ValueError, KeyError, TypeError) as error:
                record['status'] = 'INVALID_FRACTIONAL_METRICS'
                record['input_error'] = str(error)
        records.append(record)

    for row in equal['evaluation']['records']:
        identity = dict(schema_version='ndx_equal_base_combined_task_v1', **coordinate,
                        decision_data_end=cutoff, training_semantics_sha256=signature,
                        tickers=row['tickers'], holding_count=row['holding_count'], weight_spec=row['weight_spec'])
        identity['job_id'] = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        metrics = dict(row['fractional_metrics'], **row['risk_liquidity_metrics'])
        metrics.update({key: identity[key] for key in ('tickers', 'holding_count', 'weight_spec')})
        append(identity, metrics, 'EVALUATED', 'EQUAL_WEIGHT_BASE')
    restored = {}
    for record in non_equal['records']:
        job = record['task']['job_id']
        if job in restored:
            raise ValueError('Duplicate restored non-equal task')
        restored[job] = record
    if set(restored) - {task['job_id'] for task in context['tasks']}:
        raise ValueError('Unexpected restored non-equal task')
    for task in context['tasks']:
        record = restored.get(task['job_id'])
        if record is not None and record['task'] != task:
            raise ValueError('Restored non-equal task differs')
        append(task, record['result']['result'] if record else None,
               'EVALUATED' if record else 'MISSING_CHECKPOINT', 'NON_EQUAL_BASE')
    for record in delta['records']:
        append(record['task'], record.get('result'), record['status'], 'DELTA',
               record.get('training_semantics_sha256'))
    selection = select_research_lane(expected_dates=[expected], records=records, policy_role=policy_role)
    return dict(schema='ndx_combined_fractional_date_v1', expected_date=expected,
                records=records, selection=selection,
                counts={origin: dict(planned=count, observed=sum(r['origin'] == origin for r in records),
                    evaluated=sum(r['origin'] == origin and r['status'] == 'EVALUATED' for r in records))
                    for origin, count in (('EQUAL_WEIGHT_BASE', equal_count),
                                          ('NON_EQUAL_BASE', base_count - equal_count), ('DELTA', delta_count))},
                training_semantics=deepcopy(semantics),
                technology_scope_status='UNRESOLVED_CURRENT_PURE_TECH_DEFINITION',
                all_base_candidates_included=True,
                economic_inputs_complete=selection['rows'][0]['status'] != 'INPUT_INVALID',
                whole_lot_status='NOT_EVALUATED', saved_weights_are_execution_targets=False,
                cutoff_refit_required=True, point_in_time_verified=False, promotion_allowed=False)


def prepare_combined_date(*, equal_report_path, equal_report_sha256,
                          non_equal_context_path, non_equal_context_sha256,
                          source_batch, universe_track, selection_date, policy_role='RETURN'):
    _check_sources(_LOADED)
    equal = equal_report.load_report(equal_report_path, expected_sha256=equal_report_sha256)
    if equal['coordinate'] != dict(source_batch=source_batch, universe_track=universe_track, selection_date=selection_date):
        raise ValueError('Requested coordinate differs from equal report')
    non_equal = non_equal_readback.read_context(context_path=non_equal_context_path,
                                               expected_context_sha256=non_equal_context_sha256)
    delta = delta_date.prepare_date_v2(source_batch=source_batch, universe_track=universe_track,
                                     selection_date=selection_date)
    sources = _merge_sources(equal['source_hashes'], non_equal['source_hashes'], delta['source_hashes'],
                             {str(Path(equal_report_path).resolve()): equal_report_sha256}, _LOADED)
    _check_sources(sources)
    result = _combine(equal=equal, non_equal=non_equal, delta=delta, policy_role=policy_role)
    _check_sources(sources)
    result['source_hashes'] = sources
    return result
