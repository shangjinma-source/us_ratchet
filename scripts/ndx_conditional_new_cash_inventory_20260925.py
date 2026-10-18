"""Read-only six-coordinate cash-fork input inventory; never executes a fork."""
import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research'
OUTPUT = BASE / 'conditional_new_cash_inventory_20260925_v1'
SOURCE = Path(__file__).resolve()
SCHEMA = 'CONDITIONAL_NEW_CASH_SIX_COORDINATE_INVENTORY_V1'
LANES = ('RETURN', 'BAD_TAIL', 'DRAWDOWN', 'LEGACY_TARGET_DISTANCE')
CLOCK = [('2023-03-31', '2023-04-03'), ('2023-04-28', '2023-05-01'),
         ('2023-05-31', '2023-06-01'), ('2023-06-30', '2023-07-03'),
         ('2023-07-31', '2023-08-01'), ('2023-08-31', '2023-09-01')]
BOUND = {'benchmark': ('return_six_period_benchmarks_20260923_v1/benchmarks.json',
               'ef7ccdbe45a95fdf616d1b681bf9cd5c431db01585d30cf979e5cd4f2d45b423'),
 'control': ('incumbent_price_source_probe_20260912_v1/nominal_control_20260912.json',
             '53d2beb410c37393df266dd6709621dec27822b1b50db5d0623415b2d4ad8ac1'),
 'RETURN_schedule': ('return_lane_targets_20260923_v1/schedule.json',
                     'f5ee54df3651882791e4e6ecac548d0ec7847c44a9c551938d20c17c2cb23c70'),
 'RETURN_account': ('return_six_period_conditional_execution_20260923_v2/account.json',
                    'ed69a9de921d94f9a186d59a6ef16c09f46544ede388e4fff271c10a77f433e2'),
 'RETURN_comparison': ('return_six_period_comparison_20260923_v1/comparison.json',
                       'f138628a3994b9af34c8d07c10e66e5afb56e58fe86202f7c1170ad6399e033f'),
 'RETURN_price': ('return_eight_price_only_20260923_v1/raw_assembly.json',
                  'e1f00af594bfcb9a9c75b02493cf62fc64622e0b280ba2774346832b530b7336'),
 'RETURN_identity': ('return_eight_conditional_identity_20260923_v1/identities.json',
                     '5f5bcbad2f5a3a340e0b3449b4b78ed55a44941d6402a4ee067dd779a4abaa6e'),
 'BAD_TAIL_schedule': ('bad_tail_lane_targets_20260923_v1/schedule.json',
                       '677adb274064b963cfb87290a6d0120a9970e73e65a00d644a9ba8a84d78271e'),
 'BAD_TAIL_account': ('bad_tail_six_period_conditional_execution_20260923_v1/account.json',
                      'b5135462b51f95510aea2f97e5786fde011d843cfee2891be2661b38a497ff6c'),
 'BAD_TAIL_comparison': ('bad_tail_six_period_comparison_20260923_v1/comparison.json',
                         '5d2a760317cef154564743ceb361755539f0cfa9987bc1c286450ad537a60c0e'),
 'BAD_TAIL_projection': ('bad_tail_five_input_projection_20260923_v1/projection.json',
                         '77d03b11751322158158b66a18ecf19fd669cacfa730b99c3dbda1139b25e6be'),
 'DRAWDOWN_schedule': ('drawdown_lane_targets_20260923_v1/schedule.json',
                       '57dda9f62576a597fa27502296d71b3c018709d82a2aa00c09a79f5c5b54c7c9'),
 'DRAWDOWN_account': ('drawdown_six_period_conditional_execution_20260923_v1/account.json',
                      'f711b2377b388c788c7f6ba4e6c80cd0d35a4e4d3fa4ff944bc88e8115b97b14'),
 'DRAWDOWN_comparison': ('drawdown_six_period_comparison_20260923_v1/comparison.json',
                         '4a4c1fdb01835674d8bc28ee77a7a2596825917618a3a15c03319f15bd166b0a'),
 'DRAWDOWN_assembly': ('drawdown_four_input_assembly_20260923_v1/assembly.json',
                       'cb2ab027a2506a43d97e7c65494d524b1c7d7e890e7b9a2f67f863768c61aa67'),
 'LEGACY_TARGET_DISTANCE_schedule': ('legacy_target_distance_targets_20260923_v1/schedule.json',
                                     '7fa92ff703d94fc5ff0dcdb5595ea903ac72c5c36b2c76dfd36da77caaa1e5e2'),
 'LEGACY_TARGET_DISTANCE_account': ('legacy_six_period_conditional_execution_20260923_v1/account.json',
                                    'cbdae21a46a25dd88ff3c060005f210c333884d2e6ae1ac2a10405b2f1e53797'),
 'LEGACY_TARGET_DISTANCE_comparison': ('legacy_six_period_comparison_20260923_v1/comparison.json',
                                       '9a4dd13720580a75338deca76aea581c74ba1bafaeb11034a1556454439e1e78'),
 'LEGACY_TARGET_DISTANCE_price': ('legacy_twelve_price_only_20260923_v1/prices.json',
                                  'a50c4fd387f10262527e82ad0edd2bae7b799b67e2d08cff2e4a47030a64b342'),
 'LEGACY_TARGET_DISTANCE_identity': ('legacy_twelve_conditional_identity_20260923_v1/identities.json',
                                     '82ad1d271f3bd0fb3906647f808c0a9c9f81270ab7e29f7f6c626fbf8e9db8db')}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


LOADED = {str(SOURCE): digest(SOURCE)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def exact(left, right):
    return encode(left) == encode(right)


def strict(sources):
    for path, expected in sources.items():
        require(digest(path) == expected, 'Source bytes changed: ' + path)


def references():
    return {role: {'path': str(BASE / path), 'sha256': sha} for role, (path, sha) in BOUND.items()}


def pointer(refs, role, path):
    return dict(refs[role], json_pointer=path)


def numeric(value, *, positive=False):
    require(type(value) in (int, float, str), 'Saved numeric value must not be bool/object')
    text = str(value)
    require(len(text) <= 100, 'Oversized numeric literal')
    number = Decimal(text)
    require(number.is_finite() and (number > 0 if positive else number >= 0), 'Invalid saved number')
    return {'decimal_literal': text,
            'encoding': 'SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE' if type(value) is float else
                        'SAVED_DECIMAL_STRING' if type(value) is str else 'SAVED_INTEGER'}


def unique_rows(rows, key):
    require(type(rows) is list, 'Expected saved row array')
    result = {}
    for index, row in enumerate(rows):
        value = row[key]
        require(value not in result, 'Duplicate saved row key')
        result[value] = (index, row)
    return result


def price_documents(documents, lane):
    if lane in ('BAD_TAIL', 'DRAWDOWN'):
        role = lane + ('_projection' if lane == 'BAD_TAIL' else '_assembly')
        value = documents[role]
        return role, value['price_projection']['matrices'], '/price_projection/matrices', value['identity_projection']['rows'], '/identity_projection/rows'
    role = lane + '_price'
    return role, documents[role]['matrices'], '/matrices', documents[lane + '_identity']['rows'], '/rows'


def assemble(documents, refs):
    """Metadata/selected saved-cell projection only; no account or cash-fork call."""
    require(set(documents) == set(BOUND) == set(refs), 'Exact hard-bound source roles required')
    benchmark, control = documents['benchmark'], documents['control']
    calendar = benchmark['calendar']
    require(len(calendar) == 107 and calendar == sorted(set(calendar)), 'Exact observed 107-session calendar required')
    require(exact(benchmark['decision_clock'], [list(pair) for pair in CLOCK]), 'Saved six-clock mismatch')
    for decision, execution in CLOCK:
        require(decision in calendar and calendar.index(decision) + 1 < len(calendar)
                and calendar[calendar.index(decision) + 1] == execution, 'Clock not adjacent in saved observed calendar')
    daily = unique_rows(benchmark['incumbent']['daily'], 'session')
    control_daily = unique_rows(control['execution']['daily'], 'session')
    original = unique_rows(control['original_fixed_schedule']['schedule'], 'decision_date')
    price_indexes = {ticker: unique_rows(channel['rows'], 'session')
                     for ticker, channel in control['nominal_quotes']['by_ticker'].items()}
    all_identity = []
    for lane in LANES:
        price_role, _, _, identities, identity_path = price_documents(documents, lane)
        identity_role = price_role if lane in ('BAD_TAIL', 'DRAWDOWN') else lane + '_identity'
        unique_rows(identities, 'security_id')
        for index, row in enumerate(identities):
            all_identity.append((row, pointer(refs, identity_role, identity_path + '/' + str(index))))
    rows = []
    for lane in (*LANES, 'INCUMBENT_ADD_ONLY_CONTROL', 'CASH_RETENTION_CONTROL'):
        is_control = lane not in LANES
        if not is_control:
            schedule = documents[lane + '_schedule']
            account = documents[lane + '_account']
            comparison = documents[lane + '_comparison']
            require(exact(account['schedule'], schedule['schedule']), 'Account schedule differs')
            require(exact(account['calendar'], calendar) and exact(comparison['calendar'], calendar), 'Lane calendar differs')
            require(comparison['candidate_reference']['sha256'] == refs[lane + '_account']['sha256'], 'Comparison account reference mismatch')
            require(account['additional_cash_flows_supported'] is False and comparison['additional_cash_flows_supported'] is False,
                    'Original no-cashflow contract changed')
            price_role, matrices, matrix_path, local_identity_rows, local_identity_path = price_documents(documents, lane)
            local_identity_role = price_role if lane in ('BAD_TAIL', 'DRAWDOWN') else lane + '_identity'
        else:
            schedule = deepcopy(control['original_fixed_schedule'])
            schedule['schedule'] = [deepcopy(original[decision][1]) for decision, _ in CLOCK]
            if lane == 'CASH_RETENTION_CONTROL':
                for item in schedule['schedule']:
                    item['targets'] = {}
            price_role, matrices, matrix_path = 'control', {}, ''
            local_identity_rows, local_identity_path, local_identity_role = [], '', 'control'
        require(len(schedule['schedule']) == len(CLOCK), 'Lane omitted or added decision')
        for position, (decision, execution) in enumerate(CLOCK):
            target_row = schedule['schedule'][position]
            require((target_row['decision_date'], target_row['execution_date']) == (decision, execution), 'Lane decision mismatch')
            daily_index, baseline = daily[decision]
            require(exact(baseline, control_daily[decision][1]), 'Saved incumbent baseline differs from original control')
            baseline_numeric = numeric(baseline['cash_usd'])
            holdings = baseline['shares']
            require(type(holdings) is dict and all(type(q) is int and q >= 0 for q in holdings.values()), 'Invalid incumbent whole shares')
            original_index, original_row = original[decision]
            require(original_row['execution_date'] == execution, 'Incumbent clock mismatch')
            target_map = target_row['targets']
            require(type(target_map) is dict and (target_map or lane == 'CASH_RETENTION_CONTROL'), 'Missing lane targets')
            for target in target_map.values():
                numeric(target['target_weight'], positive=True)
            union = sorted({sid for sid, quantity in holdings.items() if quantity > 0} | set(target_map))
            union_ticker_sids = {}
            for sid in union:
                for coordinate in (target_map.get(sid), original_row['targets'].get(sid)):
                    if coordinate is not None:
                        union_ticker_sids.setdefault(coordinate['ticker'], set()).add(sid)
            target_reference = (pointer(refs, 'control', '/original_fixed_schedule/schedule/' + str(original_index))
                                if is_control else pointer(refs, lane + '_schedule', '/schedule/' + str(position)))
            observations, gaps = [], []
            for sid in union:
                saved = []
                if sid in holdings and holdings[sid] > 0:
                    if sid in original_row['targets']:
                        saved.append({'role': 'SAVED_INCUMBENT_EXECUTION_ATTRIBUTION_NOT_DATED_CERTIFICATION',
                                      'value': deepcopy(original_row['targets'][sid]),
                                      'reference': pointer(refs, 'control', '/original_fixed_schedule/schedule/' + str(original_index) + '/targets/' + sid)})
                if sid in target_map:
                    saved.append({'role': 'SAVED_LANE_TARGET_NOT_ACTUAL_HOLDING', 'value': deepcopy(target_map[sid]),
                                  'reference': dict(target_reference, json_pointer=target_reference['json_pointer'] + '/targets/' + sid)})
                identities = [{'value': deepcopy(row), 'reference': ref} for row, ref in all_identity if row['security_id'] == sid]
                tickers = {item['value']['ticker'] for item in saved} | {item['value']['ticker'] for item in identities}
                issuers = {item['value']['issuer_id'] for item in saved} | {item['value']['issuer_id'] for item in identities}
                reasons = []
                if len(tickers) != 1 or len(issuers) != 1:
                    reasons.append('SAVED_COORDINATE_MISSING_OR_CONFLICT')
                ticker_ambiguous = any(len(union_ticker_sids.get(ticker, set())) > 1 for ticker in tickers)
                if ticker_ambiguous:
                    reasons.append('SAME_TICKER_DIFFERENT_SID_NO_AUTOMATIC_PRICE_JOIN')
                if not identities:
                    reasons.append('DATED_IDENTITY_NOT_IN_BOUND_LANE_EVIDENCE')
                prices = []
                if len(tickers) == 1 and not ticker_ambiguous:
                    ticker = next(iter(tickers))
                    if ticker in matrices.get('open', {}).get(execution, {}):
                        matches = [(index, identity) for index, identity in enumerate(local_identity_rows) if identity['ticker'] == ticker]
                        if len(matches) != 1 or matches[0][1]['security_id'] != sid:
                            reasons.append('AMBIGUOUS_OR_MISSING_LOCAL_MATRIX_SECURITY_BINDING')
                        else:
                            prices.append(dict(numeric(matrices['open'][execution][ticker], positive=True),
                                               currency=None, currency_status='NOT_SAVED_IN_BOUND_MATRIX_UNVERIFIED',
                                               security_binding_references=[pointer(refs, local_identity_role, local_identity_path + '/' + str(matches[0][0]))],
                                               reference=pointer(refs, price_role, matrix_path + '/open/' + execution + '/' + ticker)))
                    if (sid in original_row['targets'] and original_row['targets'][sid]['ticker'] == ticker
                            and ticker in price_indexes and execution in price_indexes[ticker]):
                        quote_index, quote = price_indexes[ticker][execution]
                        require(quote.get('currency') == 'USD', 'Control quote currency differs')
                        prices.append(dict(numeric(quote['nominal_open'], positive=True),
                                           currency='USD', currency_status='SAVED_PROVIDER_FIELD_NOT_INDEPENDENT_CERTIFICATION',
                                           security_binding_references=[pointer(refs, 'control', '/original_fixed_schedule/schedule/' + str(original_index) + '/targets/' + sid)],
                                           reference=pointer(refs, 'control', '/nominal_quotes/by_ticker/' + ticker + '/rows/' + str(quote_index) + '/nominal_open')))
                if not prices:
                    reasons.append('EXECUTION_OPEN_MISSING')
                elif len({Decimal(item['decimal_literal']) for item in prices}) != 1:
                    reasons.append('EXECUTION_OPEN_SOURCE_CONFLICT')
                if prices and any(item['currency'] is None for item in prices):
                    reasons.append('LANE_MATRIX_CURRENCY_NOT_IN_BOUND_SAVED_FIELDS')
                risk_observations = []
                if sid in holdings and holdings[sid] > 0 and sid in baseline['risk_chains']:
                    risk_observations.append({'role': 'INCUMBENT_LAST_SELECTED_OBSERVATION', 'risk_chain': baseline['risk_chains'][sid],
                        'observation_date': baseline['risk_chain_observation_dates'].get(sid),
                        'reference': pointer(refs, 'benchmark', '/incumbent/daily/' + str(daily_index) + '/risk_chains/' + sid)})
                if sid in target_map and sid in schedule['risk_chains_by_decision'][decision]:
                    risk_observations.append({'role': 'LANE_CURRENT_SELECTED_OBSERVATION', 'risk_chain': schedule['risk_chains_by_decision'][decision][sid],
                        'observation_date': decision,
                        'reference': pointer(refs, 'control' if is_control else lane + '_schedule',
                            ('/original_fixed_schedule' if is_control else '') + '/risk_chains_by_decision/' + decision + '/' + sid)})
                if not risk_observations or any(not item['observation_date'] or item['observation_date'] > decision for item in risk_observations):
                    reasons.append('HISTORICAL_RISK_OBSERVATION_MISSING_OR_FUTURE')
                if len({item['risk_chain'] for item in risk_observations}) > 1:
                    reasons.append('HISTORICAL_RISK_LABEL_CONFLICT')
                observations.append({'security_id': sid, 'saved_coordinates': saved, 'dated_identity_evidence': identities,
                    'dated_identity_evidence_semantics': 'PRESERVED_SAVED_FACTS_AND_CONDITIONAL_INTERVAL_ASSUMPTIONS_NOT_NEW_CERTIFICATION',
                    'execution_open_observations': prices, 'risk_observations': risk_observations, 'gaps': reasons,
                    'identity_interval_certified': False, 'provider_binding_verified': False})
                gaps.extend({'security_id': sid, 'reason': reason} for reason in reasons)
            issuer_groups = {}
            for sid, target in target_map.items():
                issuer_groups.setdefault(target['issuer_id'], set()).add(sid)
            for sid, quantity in holdings.items():
                if quantity > 0 and sid in original_row['targets']:
                    issuer_groups.setdefault(original_row['targets'][sid]['issuer_id'], set()).add(sid)
            rows.append({'lane': lane, 'decision_date': decision, 'execution_date': execution,
                'cash_event_amount_usd': None, 'cash_event_status': 'NOT_SPECIFIED_NOT_EXECUTABLE',
                'baseline': deepcopy(baseline), 'baseline_cash_encoding': baseline_numeric,
                'baseline_reference': pointer(refs, 'benchmark', '/incumbent/daily/' + str(daily_index)),
                'lane_target': deepcopy(target_row),
                'lane_target_reference': target_reference,
                'target_semantics': 'EMPTY_BUY_SET_CASH_RETENTION_DERIVED_NOT_SAVED_TARGET' if lane == 'CASH_RETENTION_CONTROL' else 'ORIGINAL_SAVED_STRATEGIC_TARGET_NOT_ACTUAL_WEIGHT',
                'union_security_ids': union, 'securities': observations, 'gaps': gaps,
                'forward_window': {'available_execution_to_end_sessions': len(calendar) - calendar.index(execution),
                                   'available_after_execution_sessions': len(calendar) - calendar.index(execution) - 1,
                                   'equal_horizon_certified': False, 'path_evaluation_ready': False},
                'potential_same_issuer_sid_sets': {key: sorted(value) for key, value in issuer_groups.items() if len(value) > 1},
                'potential_conflict_is_not_zero_buy_candidate_rejection': True,
                'status': 'INVENTORIED_WITH_EVIDENCE_GAPS' if gaps else 'INVENTORIED_CONDITIONAL_INPUTS_ONLY',
                'fork_executable': False})
    return {'schema': SCHEMA, 'calendar': deepcopy(calendar), 'decision_clock': [list(pair) for pair in CLOCK],
            'lane_count': 4, 'control_count': 2, 'coordinate_count': 6, 'lane_coordinate_count': 24,
            'control_coordinate_count': 12, 'branch_coordinate_count': len(rows), 'rows': rows,
            'input_references': deepcopy(refs), 'cash_amount_frozen': False, 'cash_event_chosen': False,
            'cash_fork_called': False, 'fit_called': False, 'account_rerun': False, 'old_audit_rerun': False,
            'nominal_quotes_reconstructed': False, 'promotion_allowed': False, 'point_in_time_verified': False,
            'consumption_contract': 'REQUIRE_EXTERNAL_PUBLICATION_RECEIPT_HASH_EXACT_TWO_FILES_AND_NO_FAILURE_MARKER',
            'full_transitive_source_closure_reverified': False, 'scope': 'SAVED_METADATA_AND_EXECUTION_OPEN_INVENTORY_ONLY'}


def build():
    strict(LOADED)
    refs = references()
    sources = dict(LOADED)
    documents = {}
    for role, ref in refs.items():
        require(ref['path'] not in sources or sources[ref['path']] == ref['sha256'], 'Conflicting direct source')
        sources[ref['path']] = ref['sha256']
        raw = Path(ref['path']).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'Hard input hash mismatch')
        documents[role] = json.loads(raw)
    result = assemble(documents, refs)
    strict(sources)
    result['source_hashes'] = sources
    return result


def publish():
    require(not OUTPUT.exists(), 'Fixed inventory namespace already exists; no overwrite or retry')
    result = build()
    strict(result['source_hashes'])
    OUTPUT.mkdir(parents=True, exist_ok=False)
    path = OUTPUT / 'inventory.json'
    try:
        raw = encode(result)
        durable(path, raw)
        strict(result['source_hashes'])
        require(path.read_bytes() == raw and set(item.name for item in OUTPUT.iterdir()) == {'inventory.json'}, 'Published bytes/directory differ')
        reference = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
        receipt = encode({'schema': 'CONDITIONAL_CASH_INVENTORY_PUBLICATION_RECEIPT_V1',
                          'inventory_reference': reference, 'source_hashes': result['source_hashes'],
                          'status': 'SOURCE_LOCKED_INVENTORY_ONLY_NOT_FORK_READY', 'fork_executed': False})
        durable(OUTPUT / 'publication.json', receipt)
        strict(result['source_hashes'])
        require((OUTPUT / 'publication.json').read_bytes() == receipt and path.read_bytes() == raw
                and set(item.name for item in OUTPUT.iterdir()) == {'inventory.json', 'publication.json'}, 'Final publication readback differs')
        return dict(reference, publication_sha256=hashlib.sha256(receipt).hexdigest())
    except Exception as error:
        durable(OUTPUT / 'failure.json', encode({'status': 'PUBLICATION_FAILED_DO_NOT_CONSUME',
                    'error_type': type(error).__name__, 'error': str(error), 'retry_allowed': False}))
        raise


def durable(path, raw):
    with path.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true', help='Create fixed namespace once; no fork or fit')
    args = parser.parse_args()
    if not args.publish:
        parser.error('Explicit --publish required; no implicit build')
    print(json.dumps(publish(), indent=2))
