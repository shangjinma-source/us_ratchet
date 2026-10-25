"""Read-only proposal over one saved native monthly decision's candidate frontier.

No optimizer, IO, current cash, runtime registration or account mutation. Content
hashes and arithmetic are checked here; source-byte admission remains the caller's
responsibility. This proposal is deliberately not an executable monthly target.
"""
from copy import deepcopy
from datetime import date, datetime
from fractions import Fraction
from hashlib import sha256
import json
import math
import re
from zoneinfo import ZoneInfo


SCHEMA = 'NATIVE_MONTHLY_SAVED_FRONTIER_CAP50_PROPOSAL_V1'
ORIGINAL_METHOD = 'FAIR_K_V2_PLUS_CONTINUOUS32_EXPERIMENT_V1'


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode()


def _digest(value):
    return sha256(_canonical(value)).hexdigest()


def _number(value):
    _require(type(value) in (str, int, float, Fraction), 'FINITE_NONBOOLEAN_NUMBER_REQUIRED')
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError, OverflowError) as error:
        raise ValueError('FINITE_NUMBER_REQUIRED') from error


def _signature(quantities):
    return tuple(sorted((sid, quantity) for sid, quantity in quantities.items() if quantity))


def _product_hash(value):
    return sha256(f'{value.numerator:x}/{value.denominator:x}'.encode()).hexdigest()


def build_frontier_proposal(*, target):
    """Preserve a native target verbatim and return separately identified ranking.

    The only economic inputs are those already bound to ``target``. A caller
    must separately admit the source bytes, new monthly publication and complete
    execution/risk domain; this function grants none of those authorizations.
    """
    original = deepcopy(target)
    monthly = original['payload']
    decision = monthly['decision']
    selected = decision['payload']
    binding = selected['input_binding']
    for document, identifier in ((monthly, original['target_id']),
                                 (selected, decision['decision_id']),
                                 (binding, selected['input_id'])):
        _require(_digest(document) == identifier, 'ORIGINAL_NATIVE_ID_CHANGED')
    _require(monthly['schema'] == 'REAL_STRATEGY_MONTHLY_TARGET_V1'
             and selected['schema'] == 'REAL_STRATEGY_CONTINUOUS32_TARGET_DECISION_V1'
             and binding['schema'] == 'STRATEGY_ACCOUNT_CONTINUOUS32_INPUT_V1', 'ORIGINAL_NATIVE_SCHEMA_REQUIRED')
    _require(decision['status'] == 'TARGET_READY'
             and binding['selector_profile'] == 'REAL_ACCOUNT_CONTINUOUS32_V1'
             and binding['selection_method'] == ORIGINAL_METHOD
             and binding['continuous_iterations'] == 32, 'ORIGINAL_PROFILE_REQUIRED')
    _require(re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', monthly['target_month']) is not None,
             'TARGET_MONTH_REQUIRED')
    _require(monthly['account_id'] == binding['account_id'], 'ACCOUNT_ID_BINDING')
    arguments = binding['search_arguments']
    result = selected['search_result']
    _require(result['method_version'] == ORIGINAL_METHOD
             and result['objective'] == 'TRAINING_PRICE_SCENARIO_MEAN_NET_LOG_WEALTH'
             and result['fee_scope'] == 'INITIAL_BUY_ONLY_NO_TERMINAL_LIQUIDATION', 'ORIGINAL_OBJECTIVE_REQUIRED')
    _require(monthly['target_quantities'] == selected['target_quantities']
             == result['selected']['quantities'], 'ORIGINAL_SELECTED_TARGET_CHANGED')
    _require(arguments['decision_date'] == result['decision_date'] == binding['valuation_date'],
             'VALUATION_DATE_BINDING')
    _require(monthly['target_month'] == binding['valuation_date'][:7], 'ORIGINAL_TARGET_MONTH_BINDING')
    valuation_at = datetime.fromisoformat(binding['valuation_at'])
    _require(valuation_at.utcoffset() is not None, 'AWARE_ORIGINAL_VALUATION_REQUIRED')
    _require(valuation_at.astimezone(ZoneInfo('America/New_York')).date().isoformat()
             == binding['valuation_date'], 'NEW_YORK_VALUATION_DATE_BINDING')
    cutoff = date.fromisoformat(binding['training_cutoff_date'])
    _require(cutoff <= date.fromisoformat(binding['valuation_date']), 'TRAINING_AFTER_VALUATION')
    dates = arguments['scenario_dates']
    scenarios = arguments['training_scenarios']
    _require(dates == sorted(set(dates)) == result['scenario_dates']
             and len(dates) == len(scenarios) == 12
             and all(date.fromisoformat(day) <= cutoff for day in dates), 'MATURE_TWELVE_SCENARIOS_REQUIRED')
    _require(arguments['max_objective_evaluations'] == result['max_objective_evaluations'] == 8192,
             'ORIGINAL_GENERATION_BUDGET_REQUIRED')
    for key in ('entered_cash', 'fee_bps', 'minimum_cash_buffer'):
        _require(_number(arguments[key]) == _number(result[key]), 'RESULT_FINANCIAL_BINDING')
    equity = _number(binding['strategy_equity'])
    fee = _number(arguments['fee_bps']) / 10000
    buffer = _number(arguments['minimum_cash_buffer'])
    _require(equity == _number(arguments['entered_cash']) > 0
             and 0 <= fee < 1 and buffer >= 0, 'VALID_FINANCIAL_INPUTS_REQUIRED')
    prices = {sid: _number(value) for sid, value in arguments['prices'].items()}
    metadata, marks = arguments['metadata'], binding['marks']
    _require(bool(prices) and set(prices) == set(metadata), 'COMPLETE_SELECTION_IDENTITY_DOMAIN')
    sources = binding['source_hashes']
    _require(all(type(value) is str and re.fullmatch('[a-f0-9]{64}', value)
                 for value in sources.values()), 'SOURCE_HASH_SHAPE')
    _require(all(path in sources for path in binding['documents'].values()), 'DOCUMENT_SOURCE_BINDING')

    def identity(sid, *, held_only=False):
        _require(sid in marks and (sid in metadata or held_only), 'REQUIRED_SECURITY_DOMAIN_MISSING')
        mark = marks[sid]
        if sid in metadata:
            item = metadata[sid]
            _require(type(item['issuer_id']) is str and bool(item['issuer_id'])
                     and type(item['ticker']) is str and bool(item['ticker']), 'SECURITY_IDENTITY_REQUIRED')
        else:
            # A native monthly selection can retain an old holding outside the
            # new candidate pool. Its bound mark supports valuation, while the
            # missing issuer remains explicitly unresolved for later admission.
            _require(type(mark['ticker']) is str and bool(mark['ticker']), 'HELD_MARK_TICKER_REQUIRED')
            item = dict(ticker=mark['ticker'], issuer_id=None)
        _require(mark['security_id'] == sid and mark['ticker'] == item['ticker']
                 and mark['currency'] == 'USD' and _number(mark['price']) > 0
                 and mark['price_basis'] == binding['current_price_basis'], 'MARK_IDENTITY_BINDING')
        for field in ('observed_at', 'captured_at', 'checked_at'):
            observed = datetime.fromisoformat(mark[field])
            _require(observed.utcoffset() is not None and observed <= valuation_at, 'MARK_AFTER_ORIGINAL_VALUATION')
        references = mark['source_references']
        _require(bool(references) and len(references) == len(set(references))
                 and set(references) == set(mark['source_hashes'])
                 and all(mark['source_hashes'][path] == sources.get(path) for path in references),
                 'MARK_SOURCE_BINDING')
        return item, mark

    for sid, price in prices.items():
        _, mark = identity(sid)
        _require(price == _number(mark['price']) > 0, 'SEARCH_MARK_PRICE_BINDING')
    held = binding['strategy_shares']
    _require(all(type(quantity) is int and quantity >= 0 for quantity in held.values()), 'WHOLE_HELD_SHARES_REQUIRED')
    available = _number(binding['total_uninvested_cash'])
    _require(available >= 0, 'NONNEGATIVE_ORIGINAL_CASH_REQUIRED')
    held_value = Fraction(0)
    for sid, quantity in held.items():
        if quantity:
            _, mark = identity(sid, held_only=True)
            value = quantity * _number(mark['price'])
            _require(value == _number(binding['holding_market_values'][sid]), 'HELD_MARK_VALUE_BINDING')
            held_value += value
    _require(available + held_value == equity, 'ORIGINAL_ACCOUNT_EQUITY_BINDING')

    # Independent affine wealth calculation. Exact integer numerators allow all
    # saved baskets to be checked without importing any selection implementation.
    coefficients = []
    for scenario in scenarios:
        _require(set(scenario) == set(prices), 'COMPLETE_SCENARIO_DOMAIN')
        relatives = {sid: _number(value) for sid, value in scenario.items()}
        _require(all(value > 0 for value in relatives.values()), 'POSITIVE_SCENARIOS_REQUIRED')
        values = {sid: prices[sid] * (relatives[sid] - 1 - fee) / equity for sid in prices}
        denominator = math.lcm(*(value.denominator for value in values.values()))
        coefficients.append((denominator, {sid: value.numerator * (denominator // value.denominator)
                                           for sid, value in values.items()}))
    scores = {}

    def score(quantities):
        _require(all(sid in prices and type(quantity) is int and quantity > 0
                     for sid, quantity in quantities.items()), 'VALID_WHOLE_BASKET_REQUIRED')
        signature = _signature(quantities)
        if signature in scores:
            return scores[signature]
        _require(len({metadata[sid]['issuer_id'] for sid in quantities}) == len(quantities), 'UNIQUE_ISSUERS_REQUIRED')
        notional = sum((quantity * prices[sid] for sid, quantity in quantities.items()), Fraction(0))
        residual = equity - notional * (1 + fee)
        _require(residual >= 0 and (not quantities or residual >= buffer), 'AFFORDABLE_SAVED_BASKET_REQUIRED')
        growth = [Fraction(denominator + sum(values[sid] * quantity for sid, quantity in quantities.items()), denominator)
                  for denominator, values in coefficients]
        _require(all(value > 0 for value in growth), 'POSITIVE_SCENARIO_WEALTH_REQUIRED')
        assessed = dict(product=math.prod(growth), notional=notional, residual=residual,
                        mean_log=sum(math.log(value.numerator) - math.log(value.denominator)
                                     for value in growth) / len(growth))
        scores[signature] = assessed
        return assessed

    raw_records, cap_scores, origins = {}, {}, {}
    frontier = result['best_by_k']
    _require(type(frontier) is dict and bool(frontier), 'SAME_CALL_FRONTIER_REQUIRED')
    for key, record in sorted(frontier.items(), key=lambda item: int(item[0])):
        quantities = record['quantities']
        _require(key == str(len(quantities)) and record['actual_k'] == len(quantities), 'FRONTIER_CARDINALITY_BINDING')
        assessed = score(quantities)
        _require(_number(record['notional']) == assessed['notional']
                 and _number(record['fees']) == assessed['notional'] * fee
                 and _number(record['residual_cash']) == assessed['residual'], 'FRONTIER_FINANCIAL_BINDING')
        _require(math.isclose(record['training_mean_net_log_wealth'], assessed['mean_log'],
                             rel_tol=0, abs_tol=1e-12), 'FRONTIER_MEAN_LOG_BINDING')
        if record.get('training_gross_growth_product') is not None:
            _require(_number(record['training_gross_growth_product']) == assessed['product'], 'FRONTIER_PRODUCT_BINDING')
        raw_records[_signature(quantities)] = record
        clipped = _signature({sid: min(quantity, int(equity / (2 * prices[sid])))
                              for sid, quantity in quantities.items()})
        if clipped not in cap_scores:
            cap_scores[clipped], origins[clipped] = score(dict(clipped)), int(key)
    original_signature = _signature(selected['target_quantities'])
    _require(original_signature in raw_records
             and raw_records[original_signature] == result['selected'], 'ORIGINAL_SELECTED_FRONTIER_RECORD')
    rank = lambda signature: (scores[signature]['product'], -scores[signature]['notional'], signature)
    _require(max(raw_records, key=rank) == original_signature, 'ORIGINAL_SELECTED_RANK_CHANGED')
    base = {sid: min(quantity, int(equity / (2 * prices[sid])))
            for sid, quantity in selected['target_quantities'].items()}
    incumbent = _signature(base)
    _require(incumbent in cap_scores, 'ORIGINAL_CAPPED_BASKET_MISSING')
    improved = [signature for signature, assessed in cap_scores.items()
                if assessed['product'] > cap_scores[incumbent]['product']]
    winner = max(improved, key=rank) if improved else incumbent
    proposed = dict(winner) if improved else base
    proposed_ids = sorted(sid for sid, quantity in proposed.items() if quantity)
    required_ids = sorted(set(proposed_ids) | {sid for sid, quantity in held.items() if quantity})
    proposed_securities = []
    required_securities = []
    for sid in required_ids:
        item, mark = identity(sid, held_only=sid not in proposed_ids)
        identity_status = ('CANDIDATE_METADATA_BOUND' if sid in metadata
                           else 'HELD_ONLY_ISSUER_UNAVAILABLE_REQUIRES_ADMISSION')
        required_securities.append(dict(security_id=sid, ticker=item['ticker'], issuer_id=item['issuer_id'],
            identity_status=identity_status, original_held_quantity=held.get(sid, 0),
            proposed_quantity=proposed.get(sid, 0), mark=deepcopy(mark)))
        if sid in proposed_ids:
            proposed_securities.append(dict(security_id=sid, ticker=item['ticker'], issuer_id=item['issuer_id'],
                                            quantity=proposed[sid], mark=deepcopy(mark)))
    proof = dict(strict_improvement=bool(improved), unique_capped_baskets=len(cap_scores),
        additional_scored_baskets=len(cap_scores), source_cardinality=origins[winner],
        base_product_sha256=_product_hash(cap_scores[incumbent]['product']),
        selected_product_sha256=_product_hash(cap_scores[winner]['product']))
    payload = dict(schema=SCHEMA, original_target=original, source_target_id=original['target_id'],
        source_decision_id=decision['decision_id'], source_input_id=selected['input_id'],
        target_month=monthly['target_month'], fee_bps=deepcopy(arguments['fee_bps']), monthly_cap_fraction='1/2',
        base_capped_target_quantities=base, proposed_target_quantities=proposed,
        proposed_security_ids=proposed_ids, required_security_ids=required_ids,
        proposed_securities=proposed_securities, required_securities=required_securities, proof=proof,
        admission_required=['SOURCE_BYTES_AND_RUNTIME', 'NORMAL_MONTHLY_PUBLICATION', 'EXECUTION_AND_RISK_DOMAIN'],
        source_bytes_verified=False, production_admitted=False)
    return dict(status='READ_ONLY_FRONTIER_PROPOSAL', proposal_id=_digest(payload), payload=payload,
                source_bytes_verified=False, production_admitted=False, orders_created=False,
                account_mutated=False, new_searches=0, new_candidate_generation=0)
