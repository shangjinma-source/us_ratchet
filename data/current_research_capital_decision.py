"""Research-only account-capital binding; no frequency policy or execution IO."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
import re

from backtest.return_priority_fresh_cash_quantity_search import search_fresh_cash_quantities


def decide_quantity_for_account(*, decision_date, account_state, valuation_quotes,
                                search_arguments, source_hashes,
                                search=search_fresh_cash_quantities):
    """Call the unchanged fresh-cash core once with marked account equity.

    Quotes: list of {security_id, as_of, price, price_basis, source_references}.
    search_arguments adds quote_as_of and price_basis to the exact core kwargs;
    these two provenance fields are validated and removed before calling core.
    source_hashes binds caller-authenticated sources, including the core source.
    The pure adapter does not authenticate filesystem bytes or settle rights.
    """
    def require(ok, reason):
        if not ok:
            raise ValueError(reason)

    def amount(value):
        require(not isinstance(value, bool) and isinstance(value, (str, int, float, Fraction)), 'INVALID_AMOUNT')
        parsed = Fraction(str(value))
        require(parsed >= 0, 'NEGATIVE_AMOUNT')
        return parsed

    require(type(decision_date) is str and date.fromisoformat(decision_date).isoformat() == decision_date, 'INVALID_DECISION_DATE')
    require(isinstance(account_state, dict) and account_state.get('asof') == decision_date, 'STATE_DATE_MISMATCH')
    require(isinstance(account_state.get('revision'), str) and bool(account_state['revision'].strip()), 'STATE_REVISION_REQUIRED')
    require('reserved_cash' in account_state and amount(account_state['reserved_cash']) == 0, 'UNSETTLED_ORDER_RESERVATIONS_UNSUPPORTED')
    # This is a settled-position capital snapshot, not a cash-flow or rights engine.
    require(not account_state.get('pending_orders') and not account_state.get('receivables')
            and not account_state.get('undelivered_rights') and not account_state.get('pending_cash_flows'),
            'UNSETTLED_CAPITAL_COMPONENTS_UNSUPPORTED')
    cash = amount(account_state['cash'])
    shares = account_state['shares']
    require(isinstance(shares, dict) and all(isinstance(s, str) and s.strip() and type(q) is int and q >= 0
                                           for s, q in shares.items()), 'INVALID_WHOLE_SHARE_STATE')
    require(isinstance(source_hashes, dict) and bool(source_hashes) and all(
        isinstance(p, str) and p.strip() and isinstance(h, str) and re.fullmatch('[0-9a-f]{64}', h)
        for p, h in source_hashes.items()), 'SOURCE_HASHES_REQUIRED')
    require('backtest/return_priority_fresh_cash_quantity_search.py' in source_hashes, 'CORE_SOURCE_PIN_REQUIRED')
    args = deepcopy(search_arguments)
    require(args['decision_date'] == args.pop('quote_as_of') == decision_date, 'SEARCH_QUOTE_DATE_MISMATCH')
    basis = args.pop('price_basis')
    require(isinstance(basis, str) and bool(basis.strip()), 'PRICE_BASIS_REQUIRED')
    domain = set(args['prices'])
    require(domain and domain == set(args['metadata']), 'INCOMPLETE_CANDIDATE_DOMAIN')
    require(isinstance(args['training_scenarios'], list) and bool(args['training_scenarios'])
            and all(set(scenario) == domain for scenario in args['training_scenarios']), 'INCOMPLETE_SCENARIO_DOMAIN')
    require(len(args['scenario_dates']) == len(args['training_scenarios'])
            and args['scenario_dates'] == sorted(set(args['scenario_dates']))
            and all(type(day) is str and date.fromisoformat(day).isoformat() == day and day <= decision_date
                    for day in args['scenario_dates']), 'IMMATURE_OR_INVALID_SCENARIOS')
    require(isinstance(valuation_quotes, list), 'EXPLICIT_VALUATION_QUOTES_REQUIRED')
    marks, quote_binding = {}, {}
    for row in valuation_quotes:
        sid = row['security_id']
        require(isinstance(sid, str) and sid.strip() and sid not in marks, 'DUPLICATE_OR_INVALID_QUOTE_SID')
        require(row['as_of'] == decision_date and row['price_basis'] == basis, 'QUOTE_DATE_OR_COORDINATE_MISMATCH')
        references = row['source_references']
        require(isinstance(references, list) and bool(references)
                and all(isinstance(ref, str) and ref in source_hashes for ref in references), 'QUOTE_SOURCE_NOT_PINNED')
        marks[sid] = amount(row['price'])
        require(marks[sid] > 0, 'NONPOSITIVE_QUOTE')
        quote_binding[sid] = dict(price=str(marks[sid]), as_of=decision_date,
                                  price_basis=basis, source_references=list(references))
    needed = domain | {sid for sid, q in shares.items() if q}
    require(needed <= set(marks), 'MISSING_CANDIDATE_OR_HELD_QUOTE')
    require(all(amount(args['prices'][sid]) == marks[sid] for sid in domain), 'SEARCH_PRICE_COORDINATE_MISMATCH')
    holding_values = {sid: q * marks[sid] for sid, q in shares.items() if q}
    equity = cash + sum(holding_values.values(), Fraction(0))
    require(equity > 0, 'NONPOSITIVE_INVESTABLE_EQUITY')
    args['entered_cash'] = str(equity)

    # Canonicalize exact numbers only for binding, never round the core inputs.
    def canonical(value):
        if isinstance(value, Fraction):
            return str(value)
        if isinstance(value, dict):
            return {key: canonical(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [canonical(item) for item in value]
        return value

    binding = dict(schema='CAPITAL_DECISION_MECHANIC_V1', decision_date=decision_date,
        state_revision=account_state['revision'], available_cash=str(cash), reserved_cash='0',
        shares=deepcopy(shares), valuation_quotes=quote_binding, investable_equity=str(equity),
        search_arguments=canonical(args), source_hashes=deepcopy(source_hashes))
    identifier = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(',', ':'),
                                           ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    result = search(**deepcopy(args))
    require(isinstance(result, dict) and result.get('decision_date') == decision_date
            and amount(result['entered_cash']) == equity, 'CORE_RESULT_INPUT_BINDING_MISMATCH')
    require('selected' in result, 'CORE_SELECTED_FIELD_REQUIRED')
    selected = result['selected']
    if selected is None:
        require(result.get('status') == 'INSUFFICIENT_BUDGET_FOR_ALL_K_INITIALIZATION',
                'INVALID_CORE_NO_SELECTION_STATUS')
    else:
        require(result.get('status') in ('BUDGET_STOPPED', 'LOCAL_NEIGHBORHOODS_EXHAUSTED'),
                'INVALID_CORE_TERMINAL_STATUS')
        require(isinstance(selected, dict), 'INVALID_CORE_SELECTION')
        quantities = selected['quantities']
        require(isinstance(quantities, dict) and set(quantities) <= domain
                and all(type(q) is int and q > 0 for q in quantities.values()), 'INVALID_CORE_QUANTITIES')
        issuers = [args['metadata'][sid]['issuer_id'] for sid in quantities]
        require(len(issuers) == len(set(issuers)), 'CORE_DUPLICATE_ISSUER')
        notional = sum((marks[sid] * q for sid, q in quantities.items()), Fraction(0))
        fees = notional * amount(args['fee_bps']) / 10000
        residual = equity - notional - fees
        require(residual >= 0 and (not quantities or residual >= amount(args['minimum_cash_buffer'])), 'CORE_BUDGET_OR_BUFFER_EXCEEDED')
        require(amount(selected['notional']) == notional and amount(selected['fees']) == fees
                and amount(selected['residual_cash']) == residual, 'CORE_ACCOUNTING_MISMATCH')
        require(type(selected['actual_k']) is int and selected['actual_k'] == len(quantities), 'CORE_K_MISMATCH')
        weights = selected['actual_weights']
        require(isinstance(weights, dict) and set(weights) == set(quantities)
                and all(amount(weights[sid]) == marks[sid] * q / equity for sid, q in quantities.items()),
                'CORE_WEIGHT_MISMATCH')
    return dict(research_id=identifier[:24], decision_id=identifier, decision_date=decision_date, state_revision=account_state['revision'],
        available_cash=str(cash), investable_equity=str(equity),
        holding_market_values={sid: str(value) for sid, value in holding_values.items()},
        target_quantities=deepcopy(result['selected']['quantities']) if result.get('selected') is not None else None,
        search_result=deepcopy(result), binding=binding, core_calls=1,
        research_only=True, execution_blocked=True, orders_created=False,
        validated_performance=False, policy_selected=False,
        limitations=['研究资本输入机制，不选择交易频率或证明策略有效。',
                    '持股仅用于估值，不限制核心选股；候选池外持股不扩入选股域。',
                    '核心目标按净值计算，执行买单只能使用实际现金，不预借未成交卖款。',
                    '只接受无预留和未结算权益的状态，这是机制边界，不是用户投资偏好。',
                    '来源哈希由调用方认证；本纯函数不读文件、不结算现金流或应收权益。'])
