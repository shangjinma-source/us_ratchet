"""Five literal local bindings; no transitive source claims used as IO queues."""
from pathlib import Path
import hashlib
import json
import stat

from backtest.ndx_return_priority_first_candidate_research import require, validate_inputs, run_bounded_search

ROOT = Path(r'E:\Git\us_ratchet')
BOUND = {
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
    return prepare_panel_inputs(documents=documents, fixed_pins=pins)


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
        global_objectives=budget['global_objective_evaluations'], global_integers=budget['global_integer_deployment_proposals'])
    result.update(initial_price_date=prepared['initial_price_date'], return_dates=prepared['return_dates'],
                  full_conditional_inventory=prepared['securities'], all101_observed_provenance=prepared['observed_provenance'],
                  source_checks=prepared['source_checks'], source_bindings=prepared['source_bindings'],
                  source_authority=prepared['source_authority'], original8_definition=prepared['original8_definition'],
                  original8_control_status=prepared['original8_control_status'], original8_missing_tickers=prepared['original8_missing_tickers'],
                  risk_scope=risk_scope, research_cost_convention=dict(cash=plan['cash_usd'], fee_bps=plan['fee_bps'], buffer=plan['research_buffer_usd'], actual_broker_fee_verified=False))
    return result
