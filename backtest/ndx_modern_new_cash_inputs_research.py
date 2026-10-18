"""Fixed saved modern dynamic inputs; conditional research, never P5 admission.

No fitter, account engine, producer, broker, current cash, or source-claim IO.
The four pinned artifacts establish saved projection provenance only. Original
prices retain session and source pointers; historical availability is unknown.
"""
from copy import deepcopy
from pathlib import Path
from fractions import Fraction
import ast
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[1]
BOUND = {
    'inputs': ('data/cache/research/multidecision_account_inputs_20261003_v1/inputs.json', 'c3311e2e9aea24c96c695e5a860f6ecd784356bbc8995657f1e13061de0ff4b9'),
    'publication': ('data/cache/research/multidecision_account_inputs_20261003_v1/publication.json', '64c301cd36c9274f345997a2adb6ba67eb46ce824d8190865b4578441afca940'),
    'readback': ('data/cache/research/multidecision_account_inputs_independent_readback_20261003_v1/independent_readback.json', '8568bbe2ea6fa33d2aa9956a72a8b11d902f353b6078044a9a832384ec0886fb'),
    'reader': ('scripts/ndx_multidecision_account_inputs_independent_readback_20261003.py', '85f3fd668a948bf9b3e68f1d4c013ee6def02d806f57373c41ef65698443576d'),
}
RISK_PATH = 'backtest/ndx_dynamic_whole_lot_repair_path.py'
RISK_SHA = 'e614be1a2fe461e483e17413af03153f9a2fe99c31e0412b5daa8954c53d3f34'
EXECUTION_BOUND = {
    'result': ('data/cache/research/multidecision_account_execution_20261003_v1/result.json', 'c79aafa533d78be14f888cd109d9942702c829c39d5ce0d09904501b5c812870'),
    'publication': ('data/cache/research/multidecision_account_execution_20261003_v1/publication.json', 'e1b00c1c1f8e4b4d31893e77ba46bc12009ba3e5fd452fdca1b1b01266ab68c7'),
    'readback': ('data/cache/research/multidecision_account_execution_independent_readback_20261003_v1/independent_readback.json', '33ebcb571c81793f92070c8db789b409b98eca139778c0c192c80fa6abcc74bb'),
    'reader': ('scripts/ndx_multidecision_account_execution_independent_readback_20261003.py', '69c54a144ca582a8537a4c52b0fbb6fdf61a0f2ece0d4233206cc87f6f729ca2'),
}
HISTORICAL_RAW_HASHES = (
    '577dee1468d30ac5f3631e3ee1b4ceb709be5ac887a48510b443fa0be968f65f',
    '2883f15e524b46cd35d71d16a0b31752919240d2140b73c4d35e58fce73833dc',
    '1d65d36cdeb91e997a17f37e5314dce2949d085a9bd33aa2a1078bbad0fa2767',
    '78bbfbb5a3cac0b3c266f09ab76cf1afc02f88e3e101d59b3c799d5a62b95e9f',
    'a5c4d3ed8e834b21003a6174b3a159ba6f34ce5e096141469c8e7a7bf70fbd7c',
    '1165d8b604a7348bf3034139a1c36d7b47849c1d22e1ad64e351fe0f187d5fd1',
    '86473ddde7992ca3ca39721ec3d20e94c84b0a07539963e99cabfe0ec4024b15',
    '7bb44403b225fb5546072067fd9bc87a23986e1493f75cee4af14757b77a78ef')
CUTOFFS = ('2026-03-31', '2026-04-30', '2026-05-29', '2026-06-30', '2026-07-31', '2026-08-31')
MODES = ('STRICT_SAME_SESSION_FX', 'BACKWARD_LATEST_VALID_FX')
LANES = ('RETURN', 'BAD_TAIL', 'DRAWDOWN', 'TARGET_ENVELOPE')
PARAMETERS = dict(initial_cash_usd=25000, minimum_cash_buffer_usd=100,
                  transaction_cost_bps=10, max_single_weight=.45,
                  min_single_weight=.05, top_weight_cap=.8,
                  minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55)
FLAGS = dict.fromkeys(('source_bytes_authenticated', 'full_transitive_source_closure_reverified',
    'point_in_time_verified', 'full_ndx_membership_verified', 'price_available_at_verified',
    'modern_dynamic_policy_binding_verified', 'formal_admission_allowed', 'p5_unlock_allowed',
    'execution_authorized', 'promotion_allowed', 'current_account_verified',
    'current_new_money_supplied', 'fit_called', 'account_engine_called'), False)
BLOCKERS = ('MODERN_DYNAMIC_POLICY_NOT_BOUND_TO_FORMAL_REGISTRY_AND_COHORT_AUTHORITY',
    'FORMAL_12_MATURE_COHORT_TWO_REGIME_DUAL_BENCHMARK_EVIDENCE_NOT_ESTABLISHED_BY_THIS_SOURCE',
    'HISTORICAL_PRICE_AVAILABLE_AT_NOT_ESTABLISHED', 'FULL_POINT_IN_TIME_UNIVERSE_NOT_ESTABLISHED',
    'CURRENT_ACCOUNT_AND_EXPLICIT_NEW_MONEY_NOT_SUPPLIED',
    'ADD_ONLY_NEW_MONEY_ACTION_FAMILY_NOT_BOUND_TO_THIS_FULL_REBALANCE_RESEARCH')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def exact(left, right, message):
    require(encoded(left) == encoded(right), message)


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def false_fields(value):
    for key in FLAGS:
        if key in value:
            require(value[key] is False, 'No authority: ' + key)
    for key in ('weights_refitted', 'inner_window_weights_used', 'formal_benchmark_passed',
                'selection_performed', 'fit_performed', 'account_simulation_performed'):
        if key in value:
            require(value[key] is False, 'Original research restriction: ' + key)


def pointer(document, path):
    require(path.startswith('/'), 'JSON pointer required')
    value = document
    for token in path.split('/')[1:]:
        token = token.replace('~1', '/').replace('~0', '~')
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def _namespace(folder, expected):
    require(folder.is_dir() and not folder.is_symlink(), 'Saved namespace')
    require({p.name for p in folder.iterdir()} == set(expected), 'Exact saved namespace inventory')
    for path in folder.iterdir():
        require(path.is_file() and not path.is_symlink(), 'Regular saved artifact only')


def _read(path, expected):
    for parent in (path, *path.parents):
        require(not parent.is_symlink(), 'No linked source path')
    require(not (path.parent / 'failure.json').exists(), 'Failed saved namespace')
    require(path.is_file() and path.stat().st_size <= 64_000_000, 'Bounded saved source')
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'Pinned source bytes changed: ' + str(path))
    return raw


def _project(document, publication, audit, references):
    """Structural extraction after fixed-byte validation; not a new source audit."""
    require(document['schema'] == 'MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1', 'Saved input document schema')
    require(publication['schema'] == 'MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_PUBLICATION_V1'
            and publication['status'] == 'PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS', 'Input publication role')
    require(audit['schema'] == 'MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_INDEPENDENT_READBACK_V1'
            and audit['status'] == 'PASS', 'Original independent projection readback')
    for item in (publication, audit):
        exact(item['inputs_reference'], references['inputs'], 'Input anchor association')
    exact(audit['publication_reference'], references['publication'], 'Publication anchor association')
    exact(audit['reader_sha256'], references['reader']['sha256'], 'Reader code anchor association')
    inspection = audit['inspection']
    for key, count in (('coordinate_count', 48), ('lane_count', 8), ('track_count', 16)):
        require(type(inspection[key]) is int and inspection[key] == count, 'Original complete counts')
    for item in (document, publication, audit, inspection):
        false_fields(item)
    saved = document['inputs']
    require(saved['schema'] == 'MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_V1', 'Saved projection schema')
    false_fields(saved)
    coordinates = saved['outer_coordinate_rows_preserved']
    require(len(coordinates) == 48 and len(saved['rows']) == 8, 'No truncated or champion projection')
    expected_coordinates = [[cutoff, mode, lane] for cutoff in CUTOFFS for mode in MODES for lane in LANES]
    for index, row in enumerate(coordinates):
        require(type(row['coordinate_index']) is int and row['coordinate_index'] == index, 'Original coordinate position')
        exact(row['coordinate'], expected_coordinates[index], 'Full coordinate identity')
    lanes = []
    tracks = []
    for lane_index, lane in enumerate(saved['rows']):
        base = '/inputs/rows/' + str(lane_index)
        exact([lane['fx_mode'], lane['lane']], [MODES[lane_index // 4], LANES[lane_index % 4]], 'Original lane order')
        indexes = [lane_index + 8 * i for i in range(6)]
        exact(lane['coordinate_indexes'], indexes, 'All six original decisions')
        false_fields(lane)
        schedule = lane['original_targets_schedule']
        require(len(schedule) in (0, 6), 'Entire six-decision lane or original blocked lane')
        slots = {slot['security_id']: (i, slot) for i, slot in enumerate(lane['source_slots'])}
        require(len(slots) == len(lane['source_slots']), 'Unique original SID source slots')
        quotes = {(q['security_id'], q['session'], q['field']): (i, q)
                  for i, q in enumerate(lane['exact_quote_conversion_evidence'])}
        require(len(quotes) == len(lane['exact_quote_conversion_evidence']), 'Unique original quote coordinates')
        decisions = []
        for decision_index, item in enumerate(schedule):
            coordinate = coordinates[indexes[decision_index]]
            require(coordinate['evidence'] is not None, 'No target replacing a blocked original coordinate')
            evidence = coordinate['evidence']
            require(evidence['readback']['status'] == 'PASS' and evidence['readback']['prior_eligible'] is True, 'Original target must have accepted readback')
            exact(item['targets'], evidence['raw_result']['result']['targets'], 'Outer refit targets, never rolling fit weights')
            exact(item['decision_date'], coordinate['coordinate'][0], 'Original decision date')
            require(len({t['issuer_id'] for t in item['targets'].values()}) == len(item['targets']), 'Unique issuer per complete target')
            identities = []
            prices = []
            for sid, target in item['targets'].items():
                source_index, slot = slots[sid]
                identity = slot['coordinate_preserved']
                exact([sid, target['ticker'], target['issuer_id']], [identity['security_id'], identity['ticker'], identity['issuer_id']], 'SID ticker issuer source binding')
                require(type(target['target_weight']) in (float, int) and math.isfinite(target['target_weight']) and target['target_weight'] > 0, 'Positive original weight')
                identities.append(dict(security_id=sid, **deepcopy(target), risk_chain=identity['risk_chain'],
                    identity_pointer=base + '/source_slots/' + str(source_index) + '/coordinate_preserved'))
                stateful = lane['tracks'][1]['stateful_input']
                column = stateful['internal_columns_by_security'][sid]
                for matrix_name, session, field in (('closes', item['decision_date'], 'nominal_close_exact'),
                                                     ('opens', item['execution_date'], 'nominal_open_exact')):
                    quote_index, quote = quotes[(sid, session, field)]
                    matrix = stateful[matrix_name]
                    row_position = matrix['index'].index(session)
                    column_position = matrix['columns'].index(column)
                    value = matrix['data'][row_position][column_position]
                    require(float(Fraction(quote['exact'])).hex() == quote['binary64_hex'] == float(value).hex(), 'Original exact quote and account matrix binding')
                    prices.append(dict(security_id=sid, session=session, saved_quote_field=field,
                        exact=quote['exact'], binary64_hex=quote['binary64_hex'], value=value,
                        source_json_pointer=quote['json_pointer'],
                        quote_projection_pointer=base + '/exact_quote_conversion_evidence/' + str(quote_index),
                        account_matrix_pointer=base + '/tracks/1/stateful_input/' + matrix_name + '/data/' + str(row_position) + '/' + str(column_position),
                        price_available_at=None))
            decisions.append(dict(decision_date=item['decision_date'], execution_date=item['execution_date'],
                target_count=len(item['targets']), securities=identities, prices=prices,
                targets_pointer=base + '/original_targets_schedule/' + str(decision_index) + '/targets',
                coordinate_pointer='/inputs/outer_coordinate_rows_preserved/' + str(indexes[decision_index]),
                price_available_at=None))
        require(len(lane['tracks']) == 2, 'Both distinct original tracks')
        for track_index, track in enumerate(lane['tracks']):
            false_fields(track)
            exact(track['track'], ('CONTINUOUS', 'WHOLE_LOT')[track_index], 'Original track identity')
            exact(track['stateful_input']['parameters'], PARAMETERS, 'Original risk costs and buffer')
            exact(track['own_initial_state'], track['stateful_input']['initial_state'], 'Own historical initial state')
            blocked = bool(track['blocking_reasons'])
            require(track['status'] == ('BLOCKED_ENGINE_OR_SOURCE_INPUT' if blocked else 'ENGINE_INPUTS_PREPARED_NOT_EXECUTED'), 'Original input eligibility')
            require((not schedule) == blocked, 'No replacement of original missing decision evidence')
            tracks.append(dict(lane_index=lane_index, track=track['track'], input_status=track['status'],
                blocking_reasons=deepcopy(track['blocking_reasons']),
                source_pointer=base + '/tracks/' + str(track_index),
                historical_initial_state=deepcopy(track['own_initial_state']),
                historical_state_role='SAVED_ZERO_FLOW_RESEARCH_INITIAL_STATE_NOT_CURRENT_ACCOUNT'))
        lanes.append(dict(lane_index=lane_index, fx_mode=lane['fx_mode'], lane=lane['lane'],
            decisions=decisions, source_pointer=base,
            source_slots=deepcopy(lane['source_slots']),
            price_evidence_references=deepcopy(saved['price_evidence_references']),
            exact_quote_conversion_evidence=deepcopy(lane['exact_quote_conversion_evidence']),
            price_path_role=saved['price_path_role'],
            price_unit_role='SAVED_NOMINAL_CHANNEL_VALUES_USED_BY_USD_ACCOUNT_NOT_NEW_FX_OR_AVAILABILITY_VERIFICATION',
            stateful_prices_pointer=base + '/tracks/1/stateful_input',
            original_targets_schedule=deepcopy(schedule)))
    return dict(schema='MODERN_DYNAMIC_NEW_CASH_SOURCE_INPUTS_V1',
        status='CONDITIONAL_SOURCE_INPUTS_AVAILABLE_NOT_P5', input_references=deepcopy(references),
        coordinates_preserved=deepcopy(coordinates), lanes=lanes, tracks=tracks,
        counts=dict(coordinates=48, lanes=8, tracks=16,
                    blocked_tracks=sum(bool(t['blocking_reasons']) for t in tracks),
                    prepared_tracks=sum(not t['blocking_reasons'] for t in tracks)),
        parameters=deepcopy(PARAMETERS), execution_contract_preserved=deepcopy(saved['execution_contract_preserved']),
        original_provenance_and_missing=deepcopy(saved['original_provenance_and_missing']),
        full_candidate_inventory_preserved=deepcopy(saved['full_candidate_inventory_preserved']),
        preserved_evidence_sidecars=deepcopy(saved['preserved_evidence_sidecars']),
        saved_source_claims=deepcopy(saved['source_hashes']), blockers=list(BLOCKERS),
        current_new_money=None, current_account=None, plan_rows=[], **FLAGS)


def load_modern_new_cash_inputs():
    """Read fixed artifacts afresh; no caller-selectable paths or success cache."""
    references = {role: dict(path=str(ROOT / path), sha256=sha) for role, (path, sha) in BOUND.items()}
    namespaces = [(ROOT / BOUND['inputs'][0]).parent, (ROOT / BOUND['readback'][0]).parent]
    inventories = [('started.json', 'inputs.json', 'publication.json'), ('started.json', 'independent_readback.json')]
    for folder, inventory in zip(namespaces, inventories):
        _namespace(folder, inventory)
    raw = {role: _read(Path(ref['path']), ref['sha256']) for role, ref in references.items()}
    result = _project(*(decode(raw[role]) for role in ('inputs', 'publication', 'readback')), references)
    for role, ref in references.items():
        _read(Path(ref['path']), ref['sha256'])
    for folder, inventory in zip(namespaces, inventories):
        _namespace(folder, inventory)
    return result


def load_historical_frozen_states():
    """All 16 saved track outcomes and exact decision-day states, never broker state.

    The eight returned raw files are separately pinned. No source_hashes path
    is followed, and a missing/failed original track cannot select a substitute.
    """
    projected = load_modern_new_cash_inputs()
    references = {role: dict(path=str(ROOT / path), sha256=sha)
                  for role, (path, sha) in EXECUTION_BOUND.items()}
    root = Path(references['result']['path']).parent
    audit_root = Path(references['readback']['path']).parent
    require({p.name for p in root.iterdir()} == {'started.json', 'result.json', 'publication.json', 'tracks'}, 'Execution namespace inventory')
    _namespace(audit_root, ('started.json', 'independent_readback.json'))
    require(not (root / 'tracks').is_symlink() and {p.name for p in (root / 'tracks').iterdir()} == {f'{i:02d}' for i in range(16)}, 'All16 original track folders')
    raw_sources = {role: _read(Path(ref['path']), ref['sha256']) for role, ref in references.items()}
    document, publication, audit = (decode(raw_sources[role]) for role in ('result', 'publication', 'readback'))
    require(document['schema'] == 'MULTIDECISION_ACCOUNT_EXECUTION_RESULT_V1', 'Historical account result schema')
    require(publication['schema'] == 'MULTIDECISION_ACCOUNT_EXECUTION_PUBLICATION_V1' and audit['schema'] == 'MULTIDECISION_ACCOUNT_EXECUTION_INDEPENDENT_READBACK_V1' and audit['status'] == 'PASS', 'Historical account audit roles')
    for item in (publication, audit):
        exact(item['result_reference'], references['result'], 'Historical result anchor')
    exact(audit['publication_reference'], references['publication'], 'Historical publication anchor')
    exact(audit['reader_sha256'], references['reader']['sha256'], 'Historical reader anchor')
    exact(document['input_references'], projected['input_references'], 'Historical account uses original modern inputs4')
    for item in (document, publication, audit):
        false_fields(item)
    require(len(document['rows']) == len(audit['rows']) == 16, 'All16 historical outcomes')
    result = []
    guards = []
    inventories = []
    risk_math_used = False
    for index, row in enumerate(document['rows']):
        require(type(row['track_index']) is int and row['track_index'] == index, 'Historical original track position')
        track = projected['tracks'][index]
        lane = projected['lanes'][index // 2]
        exact([row['fx_mode'], row['lane'], row['track']], [lane['fx_mode'], lane['lane'], track['track']], 'Same historical track identity')
        exact(audit['rows'][index]['outcome'], row['outcome'], 'Audit preserves blocked/returned outcome')
        folder = root / 'tracks' / f'{index:02d}'
        names = ('started.json', 'postcheck.json') if index < 8 else ('started.json', 'postcheck.json', 'raw_result.json')
        _namespace(folder, names)
        inventories.append((folder, names))
        entry = dict(track_index=index, fx_mode=row['fx_mode'], lane=row['lane'], track=row['track'],
            outcome=row['outcome'], blocking_reasons=deepcopy(row['blocking_reasons']),
            result_pointer='/rows/' + str(index), historical_decision_states=[])
        if track['blocking_reasons']:
            require(row['outcome'] == 'BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT' and row['raw_reference'] is None, 'No replacing source-blocked account')
        else:
            require(row['outcome'] == 'ACCOUNT_RETURNED_PENDING_INDEPENDENT_READBACK', 'Original returned historical account only')
            raw_ref = dict(path=str(folder / 'raw_result.json'), sha256=HISTORICAL_RAW_HASHES[index - 8])
            exact(row['raw_reference'], raw_ref, 'Fixed historical raw path and SHA, no claim-selected IO')
            exact(audit['rows'][index]['saved_references']['raw_reference'], raw_ref, 'Audited raw anchor')
            raw = decode(_read(Path(raw_ref['path']), raw_ref['sha256']))
            guards.append(raw_ref)
            false_fields(raw)
            exact(raw['input_references'], projected['input_references'], 'Raw modern input association')
            require(raw['returned'] is True and raw['error'] is None, 'Original account actually returned')
            daily = raw['result']['daily']
            require(len({day['session'] for day in daily}) == len(daily), 'Unique saved historical sessions')
            for decision in lane['decisions']:
                positions = [i for i, day in enumerate(daily) if day['session'] == decision['decision_date']]
                require(len(positions) == 1, 'Exact decision-day state, no previous/next fallback')
                position = positions[0]
                state = daily[position]
                whole = track['track'] == 'WHOLE_LOT'
                shares = state['shares'] if whole else {sid: holding['shares'] for sid, holding in state['holdings'].items()}
                risk = None
                if whole and shares:
                    risk = recheck_conditional_whole_lot_risk(shares=state['shares'], marks=state['prices'], chains=state['risk_chains'])
                    risk_math_used = True
                    exact(risk['result'], state['risk'], 'Original saved whole-state risk equals original-math recheck')
                entry['historical_decision_states'].append(dict(
                    session=state['session'], shares=deepcopy(shares), cash_usd=state['cash_usd'],
                    original_state_preserved=deepcopy(state),
                    saved_account_marks=deepcopy(state['prices']) if whole else None,
                    mark_role='ORIGINAL_SAVED_ACCOUNT_MARKS_FROM_NOMINAL_CHANNEL_NOT_ORIGINAL_CURRENCY_OR_FX_AUTHENTICATION',
                    risk_chains=deepcopy(state['risk_chains']) if whole else None,
                    raw_reference=deepcopy(raw_ref), state_pointer='/result/daily/' + str(position),
                    state_role='HISTORICAL_OWN_ACCOUNT_FROZEN_STATE_NOT_CURRENT_BROKER',
                    conditional_original_risk_recheck=risk,
                    risk_not_applied_reason=('FRACTIONAL_TRACK_OR_EMPTY_HOLDINGS' if risk is None else None)))
        result.append(entry)
    for ref in [*references.values(), *guards]:
        _read(Path(ref['path']), ref['sha256'])
    for path, sha in BOUND.values():
        _read(ROOT / path, sha)
    for folder, names in inventories:
        _namespace(folder, names)
    require({p.name for p in root.iterdir()} == {'started.json', 'result.json', 'publication.json', 'tracks'}, 'Final execution namespace inventory')
    require(not (root / 'tracks').is_symlink() and {p.name for p in (root / 'tracks').iterdir()} == {f'{i:02d}' for i in range(16)}, 'Final all16 track folders')
    _namespace(audit_root, ('started.json', 'independent_readback.json'))
    _namespace((ROOT / BOUND['inputs'][0]).parent, ('started.json', 'inputs.json', 'publication.json'))
    _namespace((ROOT / BOUND['readback'][0]).parent, ('started.json', 'independent_readback.json'))
    if risk_math_used:
        _read(ROOT / RISK_PATH, RISK_SHA)
    projected['historical_execution_references'] = references
    projected['historical_execution_tracks'] = result
    projected['historical_execution_counts'] = deepcopy(document['counts'])
    return projected


def recheck_conditional_whole_lot_risk(*, shares, marks, chains):
    """Original risk arithmetic only; inputs confer no account/source authority."""
    require(type(shares) is dict and shares and set(shares) == set(marks) == set(chains), 'Exact nonempty SID risk sets')
    require(all(type(q) is int and q > 0 for q in shares.values()), 'Whole positive shares; never truncate fractional state')
    require(all(type(p) in (int, float) and math.isfinite(p) and p > 0 for p in marks.values()), 'Finite positive nominal marks')
    require(all(type(c) is str and c and c.strip() == c for c in chains.values()), 'Original canonical risk chains')
    raw = _read(ROOT / RISK_PATH, RISK_SHA)
    tree = ast.parse(raw)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_risk_snapshot']
    require(len(functions) == 1, 'Fixed original risk function')
    module = ast.Module(body=functions, type_ignores=[])
    namespace = dict(math=math, NdxDynamicWholeLotRepairPathError=ValueError)
    exec(compile(ast.fix_missing_locations(module), str(ROOT / RISK_PATH), 'exec', flags=__import__('__future__').annotations.compiler_flag), namespace)
    result = namespace['_risk_snapshot'](deepcopy(shares), deepcopy(marks), deepcopy(chains),
        **{k: PARAMETERS[k] for k in ('max_single_weight', 'min_single_weight', 'top_weight_cap', 'minimum_effective_n_ratio', 'risk_chain_top1_cap')})
    return dict(schema='CONDITIONAL_ORIGINAL_WHOLE_LOT_RISK_RECHECK_V1', result=result,
                risk_math_reference=dict(path=str(ROOT / RISK_PATH), sha256=RISK_SHA), **FLAGS)
