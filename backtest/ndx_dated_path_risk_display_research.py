"""Pure projection of saved curves and per-security risk evidence, without replay.

Callers authenticate all supplied bytes. References and audit flags alone are not
source authentication. Shared paths are deduplicated by exact evidence identity.
"""
from copy import deepcopy
from datetime import date
import hashlib
import json
import re

FIRST = '89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
TRACKS = ('candidate_integer', 'incumbent_integer', 'candidate_continuous', 'incumbent_continuous')
MODES = ('STRICT_SAME_SESSION_FX', 'BACKWARD_LATEST_VALID_FX')
AUTHORITY = ('formal_comparison_passed', 'point_in_time_verified', 'promotion_allowed', 'future_independent_oos')
FLAGS = dict.fromkeys(AUTHORITY + ('source_bytes_authenticated', 'economics_recomputed', 'risk_recomputed',
    'chain_totals_computed', 'weights_normalized', 'account_executed', 'fit_performed', 'winner_selected'), False)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def exact(left, right, message):
    require(encode(left) == encode(right), message)


def reference(value, *, pointer=False):
    allowed = {'path', 'sha256', 'json_pointer'} if pointer else {'path', 'sha256'}
    require(type(value) is dict and set(value) == allowed, 'Exact evidence reference fields')
    require(type(value['path']) is str and value['path'].strip() == value['path'] and value['path'], 'Explicit source path')
    require(type(value['sha256']) is str and re.fullmatch('[a-f0-9]{64}', value['sha256']), 'SHA256 evidence')
    if pointer:
        require(type(value['json_pointer']) is str and value['json_pointer'].startswith('/'), 'Explicit JSON pointer')


def false_flags(value, names=AUTHORITY):
    for name in names:
        require(value[name] is False, 'Conditional authority: ' + name)


def calendar_check(calendar):
    require(type(calendar) is list and len(calendar) == 127 and calendar == sorted(set(calendar)), 'Full ordered 127 sessions')
    for session in calendar:
        require(type(session) is str and date.fromisoformat(session).isoformat() == session, 'Canonical session')
    require(calendar[0] == '2026-03-20' and calendar[1] == '2026-03-23' and calendar[-1] == '2026-09-21', 'Fixed saved evaluation window')


def _path_reference(track, *, first, integer, role):
    value = deepcopy(track['source_reference'])
    if first:
        reference(value)
        pointer = track['path_pointer']
        require(pointer == ('/account/daily' if integer else '/tracks/' + role + '/path'), 'First path contract')
        value['json_pointer'] = pointer
    else:
        reference(value, pointer=True)
        value['json_pointer'] += '/daily' if integer else '/path'
    reference(value, pointer=True)
    return value


def project_saved_comparison(*, task_id, document, document_reference, audit, audit_reference,
        inputs_document, inputs_reference, input_audit, input_audit_reference):
    """Copy one independently audited first/per-task comparison and its inputs."""
    require(type(task_id) is str and re.fullmatch('[a-f0-9]{64}', task_id), 'Task ID')
    references = dict(comparison=document_reference, comparison_audit=audit_reference,
        inputs=inputs_reference, inputs_audit=input_audit_reference)
    claims = {}
    for ref in references.values():
        reference(ref)
        require(ref['path'] not in claims or claims[ref['path']] == ref['sha256'], 'Evidence source conflict')
        claims[ref['path']] = ref['sha256']
    require(audit['status'] == 'PASS' and input_audit['status'] == 'PASS', 'Saved audits required')
    exact(audit['comparison_reference'], document_reference, 'Comparison audit reference')
    exact(input_audit['inputs_reference'], inputs_reference, 'Input audit reference')
    require(input_audit['schema'] == 'DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1', 'Input audit schema')
    require(inputs_document['schema'] == 'DATED_ACCOUNT_INPUT_DOCUMENT_V1', 'Explicit account input schema')
    false_flags(document)
    false_flags(audit)
    false_flags(inputs_document, ('point_in_time_verified', 'promotion_allowed', 'future_independent_oos'))
    first = task_id == FIRST
    require(document['schema'] == ('SOURCE_BOUND_DATED_FIRST_ECONOMIC_COMPARISON_V1' if first else 'SOURCE_BOUND_DATED_PER_TASK_ECONOMIC_COMPARISON_V1'), 'Explicit comparison schema')
    require(audit['schema'] == ('DATED_COMPARISON_INDEPENDENT_READBACK_V1' if first else 'DATED_PER_TASK_COMPARISON_INDEPENDENT_READBACK_V1'), 'Explicit comparison audit schema')
    if not first:
        require(document['numerical_task_id'] == audit['numerical_task_id'] == task_id, 'Audited task identity')
    inputs = inputs_document['inputs']
    require(inputs['original_task']['numerical_task_id'] == task_id, 'Inputs task identity')
    comparison = document['comparison']
    require(comparison['schema'] == ('DATED_SAME_WINDOW_ECONOMIC_DIAGNOSTIC_V1' if first else 'DATED_PER_TASK_PARTIAL_ECONOMIC_DIAGNOSTIC_V1'), 'Comparison inner schema')
    false_flags(comparison)
    require(comparison['evaluation_interval_previously_used_for_fitting'] is True, 'Consumed evaluation scope preserved')
    calendar = comparison['calendar']
    calendar_check(calendar)
    exact(inputs['calendar'], calendar, 'Same input calendar')
    require(set(comparison['tracks']) == set(TRACKS), 'Four track slots')
    exact(comparison['mode_order'], list(MODES), 'Both FX modes')
    require(set(comparison['nav_modes']) == set(MODES) and comparison['modes_retained_separately'] is True, 'Separate NAV modes')
    output_tracks, target_evidence = {}, {}
    for role in ('candidate', 'incumbent'):
        continuous = comparison['saved_paths_preserved'][role]['continuous_track'] if first else comparison['tracks'][role + '_continuous']['original_track_preserved']
        positions = continuous['positions_preserved']
        require(type(positions) is list and positions and len({p['security_id'] for p in positions}) == len(positions), 'Full unique target slots')
        if role == 'candidate':
            expected_positions = {s: {k: v[k] for k in ('ticker', 'issuer_id', 'target_weight')} for s, v in inputs['original_fit_result']['targets'].items()}
        else:
            expected_positions = {p['security_id']: {k: p[k] for k in ('ticker', 'issuer_id', 'target_weight')} for p in inputs['original_incumbent_definition']}
        exact({p['security_id']: {k: p[k] for k in ('ticker', 'issuer_id', 'target_weight')} for p in positions}, expected_positions, 'Original target coordinates and unnormalized weights')
        role_inputs = inputs[role]
        labels = role_inputs['risk_chains_by_decision']
        require(type(labels) is dict and set(labels) == {calendar[0]}, 'Explicit frozen label observation date')
        labels = labels[calendar[0]]
        require(set(labels) == {p['security_id'] for p in positions}, 'Full target label slots including unknown')
        targets = []
        for position in positions:
            sid = position['security_id']
            require(role_inputs['original_ticker_by_security'][sid] == position['ticker'], 'Real ticker, never engine alias')
            label = labels[sid]
            require(label is None or type(label) is str and bool(label), 'Explicit label or unknown')
            targets.append(dict(original_position=deepcopy(position), risk_chain=label,
                risk_chain_status='UNKNOWN' if label in (None, 'unclassified') else 'SAVED_CONDITIONAL_LABEL',
                model_observation_date=calendar[0], observation_date_is_source_publication_date=False))
        target_evidence[role] = dict(rows=targets, original_schedule=deepcopy(role_inputs['schedule']),
            label_mapping_preserved=deepcopy(labels), weights_changed=False,
            input_pointer='/inputs/' + role, source_reference=deepcopy(inputs_reference))
    for name in TRACKS:
        role = name.split('_')[0]
        integer = name.endswith('_integer')
        track = comparison['tracks'][name]
        status = 'AVAILABLE' if first else track['status']
        if status != 'AVAILABLE':
            require(name == 'candidate_integer' and status in ('NOT_EXECUTED_NONPOSITIVE_TARGET', 'TECHNICAL_MISSING'), 'Only explicit integer absence')
            require(all(track[k] is None for k in ('metrics', 'stored_values_exact', 'source_reference', 'original_account_preserved')), 'No synthetic missing-account cash path')
            output_tracks[name] = dict(status=status, source_reference=None, path=None,
                missing_evidence=deepcopy(track['missing_evidence']), calendar_slots=[dict(session=d, value=None) for d in calendar])
            continue
        pathref = _path_reference(track, first=first, integer=integer, role=role)
        require(pathref['path'] not in claims or claims[pathref['path']] == pathref['sha256'], 'Track source conflict')
        claims[pathref['path']] = pathref['sha256']
        original = comparison['saved_paths_preserved'][role]['integer_account' if integer else 'continuous_track'] if first else track['original_account_preserved' if integer else 'original_track_preserved']
        path = original['daily' if integer else 'path']
        require(type(path) is list and len(path) == 127 and [r['session'] for r in path] == calendar, 'Full saved daily path')
        require(type(track['stored_values_exact']) is list and len(track['stored_values_exact']) == 127, 'Full stored values')
        normalized = track['metrics']['normalized_values_exact']
        require(type(normalized) is list and len(normalized) == 127 and normalized[0] == '1', 'Saved normalization, not recomputed')
        risk_rows = []
        if integer:
            for row in path:
                require(type(row['shares']) is dict and all(type(q) is int and q >= 0 for q in row['shares'].values()), 'Saved whole shares')
                positive = {sid for sid, q in row['shares'].items() if q > 0}
                weights = row['risk'].get('actual_weights', {})
                require(type(weights) is dict and positive <= set(weights), 'Saved positive-stock weights')
                require(positive <= set(row['risk_chains']) and positive <= set(row['risk_chain_observation_dates']), 'Actual held label evidence')
                security_rows = []
                for sid, weight in weights.items():
                    require(sid in inputs[role]['original_ticker_by_security'], 'Actual SID must retain original ticker')
                    security_rows.append(dict(security_id=sid, ticker=inputs[role]['original_ticker_by_security'][sid],
                        saved_stock_weight=deepcopy(weight), risk_chain=row['risk_chains'].get(sid),
                        model_observation_date=row['risk_chain_observation_dates'].get(sid)))
                risk_rows.append(dict(session=row['session'], stock_denominator_status='NO_POSITIVE_STOCK' if not positive else 'POSITIVE_STOCK_ONLY',
                    saved_risk=deepcopy(row['risk']), security_exposures=security_rows,
                    risk_chains=deepcopy(row['risk_chains']), risk_chain_observation_dates=deepcopy(row['risk_chain_observation_dates'])))
        output_tracks[name] = dict(status='AVAILABLE', source_reference=pathref, path=deepcopy(path),
            stored_values_exact=deepcopy(track['stored_values_exact']), saved_normalized_values_exact=deepcopy(normalized),
            metrics=deepcopy(track['metrics']), value_encoding=track['value_encoding'], risk_rows=risk_rows if integer else None,
            decisions=deepcopy(original['decisions']) if integer else None,
            executions=deepcopy(original['executions']) if integer else None,
            continuous_security_contributions_preserved=not integer, missing_evidence=None)
    nav = {}
    for mode in MODES:
        value = comparison['nav_modes'][mode]
        original = value['original_mode' if first else 'original_mode_preserved']
        observations = original['observations']
        require(type(observations) is list and len(observations) == 127 and [r['session'] for r in observations] == calendar, 'Full NAV observations')
        r = deepcopy(value['source_reference'])
        if first:
            reference(r)
            r['json_pointer'] = value['path_pointer'] + '/observations'
        else:
            reference(r, pointer=True)
            r['json_pointer'] += '/modes/' + mode + '/observations'
        reference(r, pointer=True)
        require(r['path'] not in claims or claims[r['path']] == r['sha256'], 'NAV source conflict')
        claims[r['path']] = r['sha256']
        nav[mode] = dict(source_reference=r, observations=deepcopy(observations), metrics=deepcopy(value['metrics']), mode=mode)
    return dict(schema='DATED_SAVED_PATH_RISK_DISPLAY_PROJECTION_V1', numerical_task_id=task_id,
        calendar=deepcopy(calendar), tracks=output_tracks, nav_modes=nav, target_evidence=target_evidence,
        candidate_normalization_evidence=deepcopy(inputs['candidate_engine_normalization_evidence']),
        original_provenance_and_missing=deepcopy(inputs_document['original_provenance_and_missing']),
        preserved_evidence_sidecars=deepcopy(inputs_document['preserved_evidence_sidecars']),
        input_limitations=deepcopy(inputs['limitations']), input_references=deepcopy(references), source_hash_claims=claims,
        evaluation_interval_previously_used_for_fitting=True,
        scope='SAVED_PATH_AND_SECURITY_EXPOSURE_COPY_ONLY;LABELS_CONDITIONAL_NOT_OFFICIAL_PIT;NO_CHAIN_TOTAL_RECALCULATION', **FLAGS)


def collect_projections(projections):
    """Collect already projected tasks; deduplicate immutable shared paths only."""
    require(type(projections) is list and projections, 'Explicit bounded task list')
    tasks, shared, identities, seen, claims = [], {}, {}, set(), {}
    for value in projections:
        require(value['schema'] == 'DATED_SAVED_PATH_RISK_DISPLAY_PROJECTION_V1', 'Projection schema')
        false_flags(value, tuple(FLAGS))
        tid = value['numerical_task_id']
        require(tid not in seen, 'No duplicate task')
        seen.add(tid)
        for path, h in value['source_hash_claims'].items():
            require(path not in claims or claims[path] == h, 'Cross-task source conflict')
            claims[path] = h
        row = deepcopy(value)
        for role, container in [('incumbent_integer', row['tracks']), ('incumbent_continuous', row['tracks'])] + [(mode, row['nav_modes']) for mode in MODES]:
            payload = deepcopy(container[role])
            # First/new schemas use different literal encoding descriptions.
            # Keep each literal on its task link rather than merging that text.
            encoding = payload.pop('value_encoding', None)
            source = payload['source_reference']
            reference(source, pointer=True)
            identity = dict(role=role, source_reference=source)
            key = hashlib.sha256(encode(identity)).hexdigest()
            if key in shared:
                exact(shared[key]['payload'], payload, 'Shared evidence cannot differ under same identity')
            else:
                shared[key] = dict(identity=deepcopy(identity), payload=deepcopy(payload))
            if role in identities:
                exact(identities[role], identity, 'One immutable shared identity per role')
            identities[role] = deepcopy(identity)
            container[role] = dict(shared_path_id=key, value_encoding_preserved=encoding)
        tasks.append(row)
    return dict(schema='DATED_SAVED_PATH_RISK_DISPLAY_COLLECTION_V1', tasks=tasks, task_count=len(tasks),
        shared_paths=shared, source_hash_claims=claims, full_queue_completeness_verified=False, **FLAGS)
