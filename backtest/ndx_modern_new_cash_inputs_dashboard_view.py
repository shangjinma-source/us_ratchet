"""Fresh fixed-source dashboard view. Bulk evidence is referenced, not embedded.

This module performs no reference IO, fitting, account simulation or cash read.
The source loader owns its four fixed artifact reads and source validation.
"""
from copy import deepcopy
import json

from backtest import ndx_modern_new_cash_inputs_research as source_loader

FLAGS = deepcopy(source_loader.FLAGS)
SCHEMA = 'MODERN_DYNAMIC_NEW_CASH_DASHBOARD_VIEW_V1'
ROOT_KEYS = {
    'schema', 'status', 'input_references', 'coordinates_preserved', 'lanes',
    'tracks', 'counts', 'parameters', 'execution_contract_preserved',
    'original_provenance_and_missing', 'full_candidate_inventory_preserved',
    'preserved_evidence_sidecars', 'saved_source_claims', 'blockers',
    'current_new_money', 'current_account', 'plan_rows', *FLAGS,
}
LANE_KEYS = {
    'lane_index', 'fx_mode', 'lane', 'decisions', 'source_pointer', 'source_slots',
    'price_evidence_references', 'exact_quote_conversion_evidence', 'price_path_role',
    'price_unit_role', 'stateful_prices_pointer', 'original_targets_schedule',
}
ROOT_REFERENCED = {
    'original_provenance_and_missing': '/inputs/original_provenance_and_missing',
    'full_candidate_inventory_preserved': '/inputs/full_candidate_inventory_preserved',
    'preserved_evidence_sidecars': '/inputs/preserved_evidence_sidecars',
    'saved_source_claims': '/inputs/source_hashes',
}


def require(condition, message):
    if not condition:
        raise ValueError('Modern dashboard view: ' + message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def exact(left, right, message):
    require(encoded(left) == encoded(right), message)


def project_modern_new_cash_inputs(source):
    """Pure detached projection of the complete accepted loader output."""
    require(type(source) is dict and set(source) == ROOT_KEYS, 'closed source shape')
    exact(source['schema'], 'MODERN_DYNAMIC_NEW_CASH_SOURCE_INPUTS_V1', 'source schema')
    exact(source['status'], 'CONDITIONAL_SOURCE_INPUTS_AVAILABLE_NOT_P5', 'source status')
    expected_refs = {role: dict(path=str(source_loader.ROOT / path), sha256=digest)
                     for role, (path, digest) in source_loader.BOUND.items()}
    exact(source['input_references'], expected_refs, 'fixed four source identities')
    for key in FLAGS:
        require(source[key] is False, 'no authority: ' + key)
    require(source['current_new_money'] is None and source['current_account'] is None,
            'no current cash or account')
    exact(source['plan_rows'], [], 'no execution plan')
    exact(source['parameters'], source_loader.PARAMETERS, 'original parameters')
    exact(source['blockers'], list(source_loader.BLOCKERS), 'complete blockers')
    exact(source['counts'], dict(coordinates=48, lanes=8, tracks=16,
                                blocked_tracks=8, prepared_tracks=8), 'complete counts')
    coordinates, lanes, tracks = (source[key] for key in ('coordinates_preserved', 'lanes', 'tracks'))
    require(type(coordinates) is list and len(coordinates) == 48, '48 coordinates')
    require(type(lanes) is list and len(lanes) == 8, '8 lanes')
    require(type(tracks) is list and len(tracks) == 16, '16 tracks')

    def reference(pointer):
        return dict(reference=deepcopy(expected_refs['inputs']), json_pointer=pointer,
                    embedded=False, representation='REFERENCE_ONLY_NOT_EMBEDDED')

    compact_coordinates = []
    blocked_count = security_count = price_count = 0
    identities = [(cutoff, mode, lane) for cutoff in source_loader.CUTOFFS
                  for mode in source_loader.MODES for lane in source_loader.LANES]
    for index, (row, identity) in enumerate(zip(coordinates, identities)):
        require(type(row) is dict and set(row) == {
            'coordinate', 'coordinate_index', 'coordinator_row_preserved', 'evidence', 'status'},
            'coordinate closed shape')
        exact(row['coordinate'], list(identity), 'coordinate order')
        require(type(row['coordinate_index']) is int and row['coordinate_index'] == index,
                'coordinate index')
        blocked = identity[1] == source_loader.MODES[0]
        require((row['evidence'] is None) == blocked, 'blocked coordinate evidence')
        require((row['status'] == 'SOURCE_BLOCKED') == blocked, 'blocked status')
        blocked_count += int(blocked)
        pointer = '/inputs/outer_coordinate_rows_preserved/' + str(index)
        compact_coordinates.append(dict(
            coordinate=deepcopy(row['coordinate']), coordinate_index=index, status=row['status'],
            evidence_state='ORIGINAL_NULL_BLOCKED' if blocked else 'REFERENCE_ONLY_NOT_EMBEDDED',
            original_coordinate_reference=reference(pointer),
            original_evidence_reference=reference(pointer + '/evidence'),
            original_coordinator_reference=reference(pointer + '/coordinator_row_preserved')))

    compact_lanes = []
    for index, lane in enumerate(lanes):
        require(type(lane) is dict and set(lane) == LANE_KEYS, 'lane closed shape')
        require(type(lane['lane_index']) is int and lane['lane_index'] == index, 'lane order')
        exact([lane['fx_mode'], lane['lane']],
              [source_loader.MODES[index // 4], source_loader.LANES[index % 4]], 'lane identity')
        blocked = index < 4
        require(type(lane['decisions']) is list and len(lane['decisions']) == (0 if blocked else 6),
                'complete decisions; no invented blocked k')
        require(type(lane['original_targets_schedule']) is list
                and len(lane['original_targets_schedule']) == len(lane['decisions']), 'full schedule')
        for decision_index, (decision, schedule) in enumerate(zip(lane['decisions'], lane['original_targets_schedule'])):
            require(type(decision) is dict and set(decision) == {
                'decision_date', 'execution_date', 'target_count', 'securities', 'prices',
                'targets_pointer', 'coordinate_pointer', 'price_available_at'}, 'decision closed shape')
            exact(decision['decision_date'], source_loader.CUTOFFS[decision_index], 'decision date')
            exact([decision['decision_date'], decision['execution_date']],
                  [schedule['decision_date'], schedule['execution_date']], 'original schedule dates')
            require(decision['price_available_at'] is None, 'unknown price availability')
            securities, prices = decision['securities'], decision['prices']
            require(type(securities) is list and type(prices) is list, 'security and price arrays')
            require(type(decision['target_count']) is int and decision['target_count'] == len(securities),
                    'dynamic k')
            require(len(prices) == 2 * len(securities), 'complete two prices per security')
            require(len({security['security_id'] for security in securities}) == len(securities),
                    'unique securities')
            exact({security['security_id']: {key: value for key, value in security.items()
                   if key not in ('security_id', 'risk_chain', 'identity_pointer')} for security in securities},
                  schedule['targets'], 'original target fields and precision')
            expected_prices = {(security['security_id'], session, field) for security in securities
                for session, field in ((decision['decision_date'], 'nominal_close_exact'),
                                       (decision['execution_date'], 'nominal_open_exact'))}
            require({(price['security_id'], price['session'], price['saved_quote_field'])
                     for price in prices} == expected_prices, 'price identities')
            for price in prices:
                require(price['price_available_at'] is None, 'unknown original price availability')
                for key in ('source_json_pointer', 'quote_projection_pointer', 'account_matrix_pointer'):
                    require(type(price[key]) is str and price[key].startswith('/'), 'original price pointer')
            security_count += len(securities)
            price_count += len(prices)
        for track_index, track_name in enumerate(('CONTINUOUS', 'WHOLE_LOT')):
            track = tracks[2 * index + track_index]
            exact([track['lane_index'], track['track']], [index, track_name], 'track order')
            exact(track['input_status'], 'BLOCKED_ENGINE_OR_SOURCE_INPUT' if blocked
                  else 'ENGINE_INPUTS_PREPARED_NOT_EXECUTED', 'track source status')
            expected_blockers = [dict(coordinate_index=cutoff * 8 + index,
                reason='MISSING_OUTER_EVIDENCE:SOURCE_BLOCKED') for cutoff in range(6)] if blocked else []
            exact(track['blocking_reasons'], expected_blockers, 'full per-track blockers')
        omitted = {
            'source_slots': '/inputs/rows/' + str(index) + '/source_slots',
            'exact_quote_conversion_evidence': '/inputs/rows/' + str(index) + '/exact_quote_conversion_evidence',
            'price_evidence_references': '/inputs/price_evidence_references',
        }
        compact_lane = deepcopy({key: value for key, value in lane.items() if key not in omitted})
        compact_lane['reference_sidecars'] = {key: reference(pointer) for key, pointer in omitted.items()}
        compact_lanes.append(compact_lane)
    require((blocked_count, security_count, price_count) == (24, 150, 300), 'full selection and price domain')
    copied_keys = ROOT_KEYS - set(ROOT_REFERENCED) - {'schema', 'coordinates_preserved', 'lanes'}
    result = deepcopy({key: source[key] for key in copied_keys})
    result.update(schema=SCHEMA, source_schema=source['schema'],
                  coordinates_preserved=compact_coordinates, lanes=compact_lanes,
                  reference_sidecars={key: reference(pointer) for key, pointer in ROOT_REFERENCED.items()},
                  projection_contract=dict(embedded_security_rows=security_count,
                      embedded_price_rows=price_count, original_blocked_coordinates=blocked_count,
                      reference_values_embedded=False, source_claim_references_followed=False))
    return result


def load_modern_new_cash_inputs_view():
    """Fresh fixed artifact validation on every call, including API cache hits."""
    return project_modern_new_cash_inputs(source_loader.load_modern_new_cash_inputs())
