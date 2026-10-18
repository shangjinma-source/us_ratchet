"""Eight literal local bindings plus preserved baseline control; no transitive source claims used as IO queues."""
from pathlib import Path
import hashlib
import json
import stat

from backtest.ndx_return_priority_first_candidate_research import require, validate_inputs, run_bounded_search

from backtest.ndx_return_priority_first_candidate_research import Budget, evaluate_allocation
import math

ROOT = Path(r'E:\Git\us_ratchet')
BOUND = {
    'control_binding': ('research_contracts/return_priority_control_binding_20261013_v1.json', 'eb4a8943ee139892d9ea1aac571e0fa535b4e8d347ae3b3a022dc4a2e7b5322e', 1479),
    'tsm_sidecar': ('tmp/tsm_original_eight_control_source_candidate_20261013_v1.json', 'd6faafe5f807773a67ec7854f45df7dbe4cb6ce215ee3be1d4cb7639ac8bec37', 78306),
    'tsm_root_readback': ('tmp/tsm_original_eight_control_root_readback_20261013_v1.json', 'b1316c75e8ccc906583ca914269dc6b5dbd91ddd02de076ce0cfbe3a7ac13dce', 1710),
    'mechanics': ('research_contracts/return_priority_candidate_mechanics_addendum_20261013_v1.json', 'b71ef94af6cc887a8cbbfc1d90ed28f2ded71c3207f6f39360951853cda48270', 1634),
    'panel': ('data/cache/research/bulk_conditional_panel_20261003_v1/panel.json', 'f6a0dab67ac375dfdf4283574f6a392e883110a6bc01efdbca72564873430b71', 6321887),
    'plan': ('research_contracts/return_priority_first_candidate_budget_20261013_v1.json', 'c32b6e3bf766198c22c5bfa1f5e8829d7e103b6b035eda984ea0c808d7319880', 3905),
    'policy': ('tmp/joint_full_conditional_source_adapter_design_20261009_v1/CONTRACT.json', '7716af33d029ae3bb245eaeb8446b995e087e0251a856ce75faf77f788ccc3e3', 5371),
    'original8': ('data/cache/research/ndx_original_8_control_v1/manifest.json', '2ca955ce951061a2aa89242c53c645775f36a658e2f51db1dc3732582317a260', 3671),
}


def regular(path):
    for part in (path, *path.parents):
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 1024, 'Reparse/symlink denied')
    require(stat.S_ISREG(path.stat().st_mode), 'Regular pinned file')


def load_fixed_inputs():
    documents, pins = {}, {}
    for role, (relative, digest, size) in BOUND.items():
        path = ROOT / relative
        regular(path)
        raw = path.read_bytes()
        require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest, 'Pinned local artifact changed: ' + role)
        def pairs(items):
            result = {}
            for key, value in items:
                require(key not in result, 'Duplicate JSON key')
                result[key] = value
            return result
        def reject(token):
            raise ValueError('Nonfinite JSON constant: ' + token)
        documents[role] = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
        pins[role] = dict(path=str(path), sha256=digest, bytes=size)
    base_documents = {role: documents[role] for role in ('panel', 'plan', 'policy', 'original8', 'mechanics')}
    prepared = prepare_panel_inputs(documents=base_documents, fixed_pins=pins)
    return extend_original8_control(prepared=prepared, sidecar=documents['tsm_sidecar'], binding=documents['control_binding'], readback=documents['tsm_root_readback'])


def prepare_panel_inputs(*, documents, fixed_pins):
    require(set(documents) == {'panel', 'plan', 'policy', 'original8', 'mechanics'}, 'Exactly five registered documents')
    outer = documents['panel']
    panel = outer['panel']
    require(outer['actual_panel_security_count'] == panel['conditional_security_count'] == 77
            and outer['actual_panel_issuer_count'] == panel['conditional_issuer_count'] == 76, '77/76 original conditional domain')
    require(panel['cutoff'] == documents['plan']['decision_cutoff'] == '2026-09-21', 'Frozen dated cutoff')
    require(panel['point_in_time_verified'] is panel['execution_authorized'] is panel['formal_input_ready'] is False, 'Unqualified source flags retained')
    universe = panel['universe']
    rows = [dict(zip(universe['columns'], values)) for values in universe['data']]
    securities = [{key: row[key] for key in ('security_id', 'issuer_id', 'ticker', 'risk_chain')} for row in rows]
    require(len(securities) == 77 and len({row['issuer_id'] for row in securities}) == 76, 'Full issuer/security domain')
    provenance = panel['observed_provenance_and_missing']
    require(len(provenance) == 101 and len({row['ticker'] for row in provenance}) == 101, 'All101 provenance names')
    ret, close = panel['returns'], panel['nominal_close']
    require(len(ret['index']) == 126 and len(close['index']) == 127 and close['index'][1:] == ret['index'], '126 common returns plus exact initial price coordinate')
    require(ret['columns'] == close['columns'] and set(ret['columns']) == {row['ticker'] for row in securities}, 'Complete column relation')
    require(all(len(row) == 77 for row in ret['data']) and len(ret['data']) == 126
            and all(len(row) == 77 for row in close['data']) and len(close['data']) == 127, 'Full finite panel dimensions')
    dates = [value[:10] for value in ret['index']]
    require(close['index'][0][:10] < dates[0] and dates[-1] == '2026-09-21', 'Matching prior initial close and cutoff')
    columns = {ticker: i for i, ticker in enumerate(ret['columns'])}
    initial = {row['security_id']: close['data'][0][columns[row['ticker']]] for row in securities}
    target = {row['security_id']: close['data'][-1][columns[row['ticker']]] for row in securities}
    returns = {row['security_id']: [values[columns[row['ticker']]] for values in ret['data']] for row in securities}
    validate_inputs(securities, initial, returns, dates, panel['cutoff'])
    fixed = documents['policy']['fixed_policy']
    from fractions import Fraction
    policy = {key: float(Fraction(fixed[key])) for key in ('max_single_weight', 'min_single_weight', 'top_three_cap', 'min_neff_ratio', 'chain_cap')}
    original = documents['original8']['definition']['securities']
    require(len(original) == 8 and sum(row['target_weight'] for row in original) > 0, 'Original eight definition')
    missing_control = sorted({row['ticker'] for row in original} - set(ret['columns']))
    return dict(securities=securities, initial_prices=initial, target_prices=target, returns=returns, return_dates=dates,
                initial_price_date=close['index'][0][:10], cutoff=panel['cutoff'], policy=policy,
                plan=documents['plan'], observed_provenance=provenance, source_checks=documents['policy']['source_checks'],
                source_bindings=fixed_pins, source_authority='LOCAL_FIXED_BYTES_ONLY_NOT_PROVIDER_OR_FULL_PIT',
                original8_definition=original, original8_control_status='BLOCKED_MISSING_MATCHING_PRICE_CHANNEL' if missing_control else 'AVAILABLE_PENDING_SAME_MECHANISM',
                original8_missing_tickers=missing_control,
                raw_transitive_source_reads=0, source_qualification_complete=False)


def extend_original8_control(*, prepared, sidecar, binding, readback):
    from fractions import Fraction
    require(binding['schema'] == 'ROOT_FIXED_ORIGINAL_EIGHT_CONTROL_EXTENSION_V1'
            and binding['separate_control_metric_evaluation_limit'] == 1
            and binding['candidate_objective_limit_unchanged'] == 311296, 'Fixed control scope/budgets')
    require(binding['tsm_sidecar']['sha256'] == BOUND['tsm_sidecar'][1]
            and binding['root_independent_quote_readback']['sha256'] == BOUND['tsm_root_readback'][1], 'Root control pins association')
    require(sidecar['schema'] == 'FIXED_TSM_CONTROL_SAME_BASIS_SOURCE_CANDIDATE_V1'
            and sidecar['status'] == 'COMPLETE_127_QUOTES_126_RETURNS_CONDITIONAL_NOT_FORMAL_PIT'
            and sidecar['cutoff'] == prepared['cutoff'], 'Fixed conditional TSM price scope')
    require(readback['status'] == 'PASS_CAPTURED_TSM_SAME_BASIS_CONTROL_QUOTES_AND_RETURNS'
            and readback['quotes_compared_to_raw'] == 127 and readback['returns_independently_recomputed'] == 126
            and readback['source_unchanged'] is True
            and readback['candidate_reference']['sha256'] == BOUND['tsm_sidecar'][1]
            and readback['point_in_time_verified'] is False, 'Independent Root control readback association')
    quotes, returns = sidecar['quotes'], sidecar['returns']
    days = [prepared['initial_price_date']] + prepared['return_dates']
    require(len(quotes) == 127 and [row['session'] for row in quotes] == days
            and len(returns) == 126 and [row['session'] for row in returns] == days[1:]
            and [row['previous_session'] for row in returns] == days[:-1], 'Complete same127/126 control dates')
    for previous, current, value in zip(quotes, quotes[1:], returns):
        require(previous['split_factor'] == current['split_factor'] == value['declared_share_ratio'] == '1', 'Control no submitted split transition')
        exact = Fraction(current['close_decimal']) / Fraction(previous['close_decimal']) - 1
        require(Fraction(value['exact_decimal_quote_return']) == exact and value['price_return'] == float(exact), 'TSM same split-only return formula')
        require(previous['nominal_close'] == float(previous['close_decimal'])
                and current['nominal_close'] == float(current['close_decimal']), 'Exact nominal close field association')
    by_ticker = {row['ticker']: row for row in prepared['securities']}
    control = {}
    for row in prepared['original8_definition']:
        ticker, sid = row['ticker'], row['security_id']
        if ticker == 'TSM':
            data = dict(target_price=quotes[-1]['nominal_close'], initial_price=quotes[0]['nominal_close'],
                        returns=[value['price_return'] for value in returns], source='ROOT_REGISTERED_TSM_CONTROL_ONLY')
        else:
            require(ticker in by_ticker, 'All other original eight channels present')
            source_sid = by_ticker[ticker]['security_id']
            data = dict(target_price=prepared['target_prices'][source_sid], initial_price=prepared['initial_prices'][source_sid],
                        returns=prepared['returns'][source_sid], source='PINNED_CONDITIONAL_PANEL')
        control[sid] = dict(**data, definition=dict(row))
    require(len(control) == 8 and len({item['definition']['issuer_id'] for item in control.values()}) == 8
            and math.isclose(sum(item['definition']['target_weight'] for item in control.values()), 1, abs_tol=1e-12), 'Unchanged original eight weights/issuers')
    extended = dict(prepared)
    extended.update(original8_channels=control, original8_control_status='AVAILABLE_COMPLETE_CONDITIONAL_CONTROL_ONLY',
                    original8_missing_tickers=[], control_binding=binding)
    require(len(extended['securities']) == 77 and all(row['ticker'] != 'TSM' for row in extended['securities']), 'TSM never joins candidate domain')
    return extended


def evaluate_original8_control(*, prepared, risk_scope):
    plan = prepared['plan']
    channels = prepared['original8_channels']
    invested_capacity = (plan['cash_usd'] - plan['research_buffer_usd']) / (1 + plan['fee_bps'] / 10000)
    all_quantities = {sid: math.floor(invested_capacity * item['definition']['target_weight'] / item['target_price']) for sid, item in channels.items()}
    require(all(type(q) is int and q >= 0 for q in all_quantities.values()), 'Control whole target nonnegative quantities')
    quantities = {sid: q for sid, q in all_quantities.items() if q > 0}
    budget = Budget(1, 0)
    result = evaluate_allocation(quantities=quantities, initial_prices={sid: item['target_price'] for sid,item in channels.items()},
        returns={sid: item['returns'] for sid,item in channels.items()},
        metadata={sid: item['definition'] for sid,item in channels.items()}, policy=prepared['policy'],
        cash=plan['cash_usd'], fee_bps=plan['fee_bps'], buffer=plan['research_buffer_usd'], budget=budget,
        enforce_risk=False, risk_scope=risk_scope)
    require(result is not None, 'Complete original-eight allocation fits same cash convention')
    result.update(original_target_weights={sid: item['definition']['target_weight'] for sid,item in channels.items()},
                  all_eight_target_quantities=all_quantities,
                  zero_allocated_due_to_whole_share_floor=[item['definition']['ticker'] for sid,item in channels.items() if all_quantities[sid] == 0],
                  definition_unchanged=True, candidate_risk_gate_imposed=False, original_definition_count=8,
                  actual_positive_target_count=len(quantities), training_only=True, point_in_time_verified=False,
                  hypothetical_training_initial_economic_units={sid: q * channels[sid]['target_price'] / channels[sid]['initial_price'] for sid,q in quantities.items()})
    return result, budget


def calculate_dated_candidate(*, prepared, risk_scope):
    """Actual computation is only called by a separately approved frozen launcher."""
    plan = prepared['plan']
    budget = plan['finite_budgets']
    result = run_bounded_search(securities=prepared['securities'], initial_prices=prepared['initial_prices'],
        target_prices=prepared['target_prices'], returns=prepared['returns'], return_dates=prepared['return_dates'], cutoff=prepared['cutoff'],
        policy=prepared['policy'], cash=plan['cash_usd'], fee_bps=plan['fee_bps'], buffer=plan['research_buffer_usd'],
        risk_scope=risk_scope, support_limit=budget['support_proposals_per_k'],
        per_support_objectives=budget['objective_evaluations_per_support'],
        per_support_integers=budget['integer_deployment_proposals_per_support'],
        global_objectives=budget['global_objective_evaluations'], global_integers=budget['global_integer_deployment_proposals'], seed=20261013)
    result.update(initial_price_date=prepared['initial_price_date'], return_dates=prepared['return_dates'],
                  full_conditional_inventory=prepared['securities'], all101_observed_provenance=prepared['observed_provenance'],
                  source_checks=prepared['source_checks'], source_bindings=prepared['source_bindings'],
                  source_authority=prepared['source_authority'], original8_definition=prepared['original8_definition'],
                  original8_control_status=prepared['original8_control_status'], original8_missing_tickers=prepared['original8_missing_tickers'],
                  risk_scope=risk_scope, research_cost_convention=dict(cash=plan['cash_usd'], fee_bps=plan['fee_bps'], buffer=plan['research_buffer_usd'], actual_broker_fee_verified=False))
    control, control_budget = evaluate_original8_control(prepared=prepared, risk_scope=risk_scope)
    result.update(original8_control=control, original8_control_status='COMPLETE_CONDITIONAL_SAME_MECHANISM_NOT_PIT',
                  control_objective_calls=control_budget.objective_calls, total_candidate_plus_control_objective_calls=result['budget']['objective_calls'] + control_budget.objective_calls,
                  search_seed=20261013, objective_mechanism='FINAL_WHOLE_TARGET_NOTIONAL_PROPORTIONS_BACKCAST_FIXED_ECONOMIC_UNITS_NET_BUY_AND_HOLD_CAGR',
                  control_metric_budget_limit=1, total_objective_limit=311297)
    return result
