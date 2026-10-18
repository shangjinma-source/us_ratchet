"""Display-only chain sums of saved values; no risk gate or account replay."""
from copy import deepcopy
from fractions import Fraction
from datetime import date
import math
import json


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    if type(value) is dict:
        require(set(value) == {'numerator', 'denominator'} and
                all(type(v) is str for v in value.values()), 'Saved rational shape')
        require(int(value['denominator']) > 0, 'Positive denominator')
        result = Fraction(int(value['numerator']), int(value['denominator']))
    else:
        require(type(value) in (str, int, float), 'Saved numeric literal, never bool')
        require(type(value) is not float or math.isfinite(value), 'Finite saved float')
        result = Fraction(str(value))
    require(result >= 0, 'Nonnegative display exposure')
    return result


def ratio(value):
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def grouped(entries, *, defined=True):
    """Keep zero slots and unknown labels; never silently renormalize raw sums."""
    require(type(defined) is bool, 'Explicit denominator bool')
    groups = {}
    identifiers = set()
    total = Fraction(0)
    for entry in entries:
        identifier = entry['security_id']
        require(type(identifier) is str and identifier and identifier not in identifiers,
                'Unique security identifiers')
        identifiers.add(identifier)
        label = entry['risk_chain']
        require(label is None or type(label) is str and bool(label), 'Explicit chain label')
        key = (label is None or label == 'unclassified', label)
        value = number(entry['saved_value'])
        total += value
        if key not in groups:
            groups[key] = dict(risk_chain=label, unknown=key[0], members=[], value=Fraction(0))
        groups[key]['members'].append(deepcopy(entry))
        groups[key]['value'] += value
    if not defined:
        require(total == 0, 'Undefined stock denominator cannot have positive stock weights')
    rows = []
    for group in groups.values():
        value = group.pop('value')
        rows.append(dict(**group, saved_literal_sum=ratio(value),
            normalized_display_share=ratio(value / total) if defined and total > 0 else None))
    unknown = sum((number(row['saved_literal_sum']) for row in rows if row['unknown']), Fraction(0))
    return dict(rows=rows, security_count=len(identifiers), saved_literal_total=ratio(total),
        unknown_saved_literal_total=ratio(unknown),
        normalized_display_denominator=ratio(total) if defined and total > 0 else None,
        stock_denominator_defined=defined and total > 0)


def project_chain_display(projection):
    """Accept the complete saved-path projection before shared-path compaction."""
    require(projection['schema'] == 'DATED_SAVED_PATH_RISK_DISPLAY_PROJECTION_V1', 'Projection schema')
    for key in ('formal_comparison_passed', 'point_in_time_verified', 'promotion_allowed',
                'future_independent_oos', 'economics_recomputed', 'risk_recomputed',
                'weights_normalized', 'source_bytes_authenticated', 'account_executed',
                'fit_performed', 'winner_selected', 'chain_totals_computed'):
        require(projection[key] is False, 'Conditional projection authority')
    require(projection['evaluation_interval_previously_used_for_fitting'] is True, 'Consumed window')
    calendar = projection['calendar']
    require(len(calendar) == 127 and calendar == sorted(set(calendar)), '127 ordered sessions')
    require(calendar[0] == '2026-03-20' and calendar[1] == '2026-03-23' and calendar[-1] == '2026-09-21', 'Fixed evaluation window')
    for session in calendar:
        require(type(session) is str and date.fromisoformat(session).isoformat() == session, 'Canonical session')
    targets, tracks = {}, {}
    for role in ('candidate', 'incumbent'):
        evidence = projection['target_evidence'][role]
        entries = []
        labels = {}
        for row in evidence['rows']:
            position = row['original_position']
            labels[position['security_id']] = row['risk_chain']
            entries.append(dict(security_id=position['security_id'], risk_chain=row['risk_chain'],
                saved_value=deepcopy(position['target_weight']), original_evidence=deepcopy(row)))
        targets[role] = dict(aggregation=grouped(entries), source_evidence=deepcopy(evidence),
            role='ORIGINAL_UNNORMALIZED_TARGET_NOT_ENGINE_EFFECTIVE_OR_ACTUAL_HOLDING')
        for kind in ('integer', 'continuous'):
            name = role + '_' + kind
            track = projection['tracks'][name]
            if track['status'] != 'AVAILABLE':
                require(name == 'candidate_integer' and track['status'] in
                    ('NOT_EXECUTED_NONPOSITIVE_TARGET', 'TECHNICAL_MISSING'), 'Explicit missing integer')
                require(track['path'] is None, 'Missing cannot have a cash path')
                require(track['calendar_slots'] == [dict(session=s, value=None) for s in calendar], 'Full missing calendar slots')
                tracks[name] = dict(status=track['status'], rows=None,
                    calendar_slots=deepcopy(track['calendar_slots']), missing_evidence=deepcopy(track['missing_evidence']))
                continue
            path = track['path']
            require(len(path) == 127 and [r['session'] for r in path] == calendar, 'Full saved path')
            if kind == 'integer':
                require(len(track['risk_rows']) == 127, 'Full saved risk rows')
            rows = []
            for index, day in enumerate(path):
                if kind == 'integer':
                    risk = track['risk_rows'][index]
                    require(risk['session'] == day['session'], 'Risk session identity')
                    require(risk['stock_denominator_status'] in ('POSITIVE_STOCK_ONLY', 'NO_POSITIVE_STOCK'), 'Stock denominator status')
                    require(type(day['shares']) is dict and all(type(v) is int and v >= 0 for v in day['shares'].values()), 'Saved integer shares')
                    positive = {s for s, v in day['shares'].items() if v > 0}
                    require(bool(positive) == (risk['stock_denominator_status'] == 'POSITIVE_STOCK_ONLY'), 'Observed stock denominator')
                    require(json.dumps(risk['saved_risk'], sort_keys=True, allow_nan=False) ==
                        json.dumps(day['risk'], sort_keys=True, allow_nan=False), 'Saved risk copied exactly')
                    weights = day['risk'].get('actual_weights', {})
                    require(type(weights) is dict and positive <= set(weights), 'All held stock weights')
                    require(len(risk['security_exposures']) == len(weights) and
                        {r['security_id'] for r in risk['security_exposures']} == set(weights), 'Exact exposure slots')
                    require(risk['risk_chains'] == day['risk_chains'] and
                        risk['risk_chain_observation_dates'] == day['risk_chain_observation_dates'], 'Daily label evidence')
                    for exposure in risk['security_exposures']:
                        sid = exposure['security_id']
                        require(type(exposure['saved_stock_weight']) is type(weights[sid]) and exposure['saved_stock_weight'] == weights[sid], 'Original weight literal')
                        require(exposure['risk_chain'] == day['risk_chains'].get(sid) and
                            exposure['model_observation_date'] == day['risk_chain_observation_dates'].get(sid), 'Original label and model date')
                    entries = [dict(security_id=r['security_id'], risk_chain=r['risk_chain'],
                        saved_value=deepcopy(r['saved_stock_weight']), original_evidence=deepcopy(r))
                        for r in risk['security_exposures']]
                    aggregate = grouped(entries, defined=risk['stock_denominator_status'] == 'POSITIVE_STOCK_ONLY')
                    require(not positive or aggregate['stock_denominator_defined'], 'Positive stock exposure denominator')
                    total, cash = number(day['total_value_usd']), number(day['cash_usd'])
                    require(total > 0 and cash <= total, 'Saved account cash/total')
                    rows.append(dict(session=day['session'], aggregation=aggregate,
                        saved_risk=deepcopy(risk['saved_risk']),
                        cash_usd_preserved=deepcopy(day['cash_usd']), total_value_usd_preserved=deepcopy(day['total_value_usd']),
                        cash_fraction_display=ratio(cash / total),
                        denominator_scope='SAVED_STOCK_ONLY_WEIGHTS_CASH_SEPARATE_NOT_ACCOUNT_WEIGHT',
                        source_row_index=index))
                else:
                    require({r['security_id'] for r in day['security_rows']} == set(labels), 'All contribution slots')
                    entries = [dict(security_id=r['security_id'], risk_chain=labels[r['security_id']],
                        saved_value=deepcopy(r['contribution_after_cost']), original_evidence=deepcopy(r))
                        for r in day['security_rows']]
                    rows.append(dict(session=day['session'], aggregation=grouped(entries),
                        denominator_scope='SAVED_AFTER_COST_CONTRIBUTION_SUM_NOT_TARGET_WEIGHT_OR_CASH_ACCOUNT',
                        source_row_index=index, saved_path_role=day.get('role')))
            tracks[name] = dict(status='AVAILABLE', rows=rows, source_reference=deepcopy(track['source_reference']))
    return dict(schema='SAVED_RISK_CHAIN_DISPLAY_AGGREGATES_V1', numerical_task_id=projection['numerical_task_id'],
        calendar=deepcopy(calendar), targets=targets, tracks=tracks,
        candidate_engine_normalization_evidence=deepcopy(projection['candidate_normalization_evidence']),
        input_references=deepcopy(projection['input_references']),
        limitations_preserved=deepcopy(projection['input_limitations']),
        original_provenance_and_missing=deepcopy(projection['original_provenance_and_missing']),
        arithmetic='FRACTION_OF_SAVED_JSON_FLOAT_STR_OR_SAVED_RATIONAL_NOT_ORIGINAL_PRICE_PRECISION',
        normalization_scope='ADDITIONAL_DISPLAY_SHARE_ONLY_RAW_SUMS_AND_TARGETS_UNCHANGED',
        source_bytes_authenticated=False, economics_recomputed=False, risk_gate_recomputed=False,
        chain_display_addition_performed=True, original_targets_changed=False,
        point_in_time_verified=False, promotion_allowed=False, future_independent_oos=False,
        evaluation_interval_previously_used_for_fitting=True)
