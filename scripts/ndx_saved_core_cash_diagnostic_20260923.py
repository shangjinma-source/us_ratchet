"""Compare saved tactical evidence with unconfirmed core-gap mathematics only."""
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
SNAPSHOT = ROOT / 'data/cache/research/offline_saved_fund_signal_diagnostic_20260923_v1/snapshot.json'
SNAPSHOT_SHA = 'c5b3da4db4a83c84200bdc085343e96e285533b861b1d3b1dd6cca83b564424e'
CORE = ROOT / 'backtest/parallel_deployment.py'
CORE_SHA = 'eafb28d32476234c7ad542b1f1a40239a4b1aaefdf6003a22d60d5a889fd5558'
TACTICAL = ROOT / 'data/cache/research/offline_saved_fund_signal_diagnostic_20260923_v1/diagnostic.json'
TACTICAL_SHA = '3c74d1131cf74ab614952a861786293d787b33a9eb1f4563a327c644562fb67b'
OUTPUT = ROOT / 'data/cache/research/saved_core_cash_diagnostic_20260923_v1/report.json'


def checked(path, expected):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Source hash mismatch: ' + str(path))
    return raw


def number(value):
    if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
        raise ValueError('Explicit finite nonnegative saved number required')
    return value


def symbol(value):
    if type(value) is not str or not value or value != value.upper() or any(c.isspace() for c in value):
        raise ValueError('Canonical saved ticker required')
    return value


def prepare(snapshot):
    """Reject missing fields instead of invoking the old planner's defaults."""
    constraints = snapshot['execution_constraints']
    if constraints['currency'] != 'USD' or constraints['cash_input_net_of_reserve'] is not True:
        raise ValueError('Explicit USD cash net of reserve required')
    if constraints['allow_fractional'] is not False:
        raise ValueError('Whole lots required')
    lot = number(constraints['lot_size'])
    names = number(constraints['buy_plan_compact_target'])
    if lot < 1 or int(lot) != lot or names < 1 or int(names) != names:
        raise ValueError('Positive integer lot/name limit required')
    prices, provenance = {}, {}
    for row in snapshot['symbols']:
        ticker = symbol(row['ticker'])
        if ticker in prices:
            raise ValueError('Duplicate price ticker')
        price = number(row['price'])
        field = 'price'
        if price == 0:
            price = number(row['previous_close'])
            field = 'previous_close'
        if price <= 0:
            raise ValueError('Positive saved quote required')
        if type(row['price_source']) is not str or not row['price_source'].strip():
            raise ValueError('Explicit saved quote source required')
        prices[ticker] = price
        provenance[ticker] = dict(field='symbols.' + field, price=price,
            source=row['price_source'], quote_time=row.get('quote_time'), market_time=row.get('market_time'))
    gaps = snapshot['account']['position_gaps']['rows']
    seen, excluded = set(), []
    for row in gaps:
        ticker = symbol(row['ticker'])
        if ticker in seen or ticker not in prices:
            raise ValueError('Duplicate gap or missing saved quote')
        seen.add(ticker)
        for key in ('gap_amount', 'gap_ratio', 'gap_rank', 'target_amount', 'real_market_value'):
            number(row[key])
        if row['position_kind'] not in ('pending_entry', 'real_position', 'reported_closed'):
            raise ValueError('Unknown position kind')
        for key in ('core_deployment_eligible', 'frozen', 'reported_closed'):
            if type(row[key]) is not bool:
                raise ValueError('Explicit saved eligibility required')
        if row['reported_closed'] or row['position_kind'] == 'reported_closed':
            excluded.append(ticker)
    fee_bps = number(constraints['fee_bps'])
    minimum_fee = number(constraints['min_fee'])
    for price in prices.values():
        notional = number(price * lot)
        number(notional + max(minimum_fee, number(notional * fee_bps) / 10000))
    for row in gaps:
        number(row['gap_amount'] / (prices[row['ticker']] * lot))
        number(row['gap_amount'] * fee_bps)
    return dict(position_gaps=gaps, price_by_ticker=prices, excluded_tickers=excluded,
        max_names=int(names), lot_size=int(lot), fee_bps=number(constraints['fee_bps']),
        min_fee=number(constraints['min_fee'])), provenance


def build(snapshot):
    checked(SOURCE, LOADED_SHA)
    core_bytes = checked(CORE, CORE_SHA)
    namespace = dict(__name__='saved_core_cash_frozen_diagnostic', __file__=str(CORE))
    exec(compile(core_bytes, str(CORE), 'exec'), namespace)
    build_parallel_deployment_plan = namespace['build_parallel_deployment_plan']
    arguments, provenance = prepare(snapshot)
    scenarios = []
    for cash in (1000, 10000):
        draft = build_parallel_deployment_plan(**arguments, cash_usd=cash, broker_confirmed=False)
        scenarios.append(dict(research_cash_usd=cash, executable=False,
            status='SAVED_SNAPSHOT_MATHEMATICAL_DIAGNOSTIC_ONLY',
            account_readiness='NOT_EVALUATED_NO_BROKER_SESSION_AUTHORITY',
            mathematical_core_draft=draft))
    checked(CORE, CORE_SHA)
    checked(SOURCE, LOADED_SHA)
    return dict(schema='SAVED_CORE_CASH_DIAGNOSTIC_V1', scenarios=scenarios,
        saved_state_freshness=snapshot.get('state_freshness'), saved_snapshot_id=snapshot['snapshot_id'],
        saved_timestamp=snapshot['ts'], timestamp_timezone_unspecified=True,
        quote_provenance=provenance, tactical_reference=dict(path=str(TACTICAL), sha256=TACTICAL_SHA),
        prices_equal_tactical_limits=False,
        price_semantics='SAVED_CORE_QUOTE_OR_PREVIOUS_CLOSE_NOT_TACTICAL_LIMIT',
        capital_semantics='ALTERNATIVE_USES_OF_SAME_RESEARCH_CASH_NEVER_SUM_CHANNELS',
        cash_is_user_current_cash=False, account_readiness_verified=False,
        dynamic_new_capital_status='NOT_EVALUATED_REQUIRES_CANONICAL_TARGET_RISK_AND_ADMISSION',
        full_frontend_reproduced=False, orders_created=False, state_changed=False,
        promotion_allowed=False)


def main():
    raw = checked(SNAPSHOT, SNAPSHOT_SHA)
    checked(TACTICAL, TACTICAL_SHA)
    report = build(json.loads(raw))
    report['sources'] = {str(path): digest for path, digest in
        ((SNAPSHOT, SNAPSHOT_SHA), (TACTICAL, TACTICAL_SHA), (CORE, CORE_SHA))}
    report['sources'][str(SOURCE)] = LOADED_SHA
    for path, digest in report['sources'].items():
        checked(Path(path), digest)
    OUTPUT.parent.mkdir(parents=True, exist_ok=False)
    payload = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    with OUTPUT.open('xb') as handle:
        handle.write(payload)
    for path, digest in report['sources'].items():
        checked(Path(path), digest)
    checked(OUTPUT, hashlib.sha256(payload).hexdigest())
    print(json.dumps(dict(path=str(OUTPUT), sha256=hashlib.sha256(OUTPUT.read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
