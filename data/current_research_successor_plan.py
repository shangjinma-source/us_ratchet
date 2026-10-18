"""Pure bridge from a verified paper account to one capital-aware DAY plan."""
from copy import deepcopy
from datetime import date, datetime
from fractions import Fraction
from zoneinfo import ZoneInfo

from backtest.return_priority_fresh_cash_quantity_search import search_fresh_cash_quantities
from data.current_research_capital_decision import decide_quantity_for_account
from data.current_research_fill_ledger import review_paper_ledger
from data.current_research_limit_plan import build_current_research_limit_plan
from backtest.return_priority_monthly_top1_selector import decide_top1_for_account, VERSION as TOP1_METHOD

QUANTITY_METHOD = 'ACTUAL_EQUITY_FRESH_QUANTITY_MONTHLY'


def _capital_method(capital_decision, search):
    decision = decide_quantity_for_account if capital_decision is None else capital_decision
    _require(decision is decide_quantity_for_account or decision is decide_top1_for_account,
             'UNSUPPORTED_CAPITAL_DECISION_ADAPTER')
    if decision is decide_top1_for_account:
        _require(search is search_fresh_cash_quantities, 'CUSTOM_SEARCH_AND_CAPITAL_DECISION_CONFLICT')
        return decision, TOP1_METHOD
    return decision, QUANTITY_METHOD


def _decimal_reference(value):
    value = Fraction(value)
    denominator, twos, fives = value.denominator, 0, 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise ValueError('NONTERMINATING_DECIMAL_REFERENCE_UNSUPPORTED')
    places = max(twos, fives)
    scaled = value.numerator * (10 ** places // value.denominator)
    digits = str(scaled).zfill(places + 1)
    return digits if not places else digits[:-places] + '.' + digits[-places:]


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _review_roll_state(state, expected_revision, decision_date, active_date, calendar):
    require = _require
    reviewed = review_paper_ledger(state)
    require(expected_revision == reviewed['revision'], 'STALE_ACCOUNT_REVISION')
    require(all(type(day) is str and date.fromisoformat(day).isoformat() == day for day in [decision_date, active_date]), 'INVALID_DECISION_OR_ACTIVE_DATE')
    require(all(row['unfilled_quantity'] == 0 or row['order_status'] in ('CANCEL', 'EXPIRE')
                for row in reviewed['orders']), 'OLD_PLAN_HAS_OPEN_ORDERS')
    require(decision_date >= state['plan']['active_date'], 'NEW_PLAN_BEFORE_OLD_ACTIVE_SESSION')
    require(isinstance(calendar, list) and all(type(day) is str and date.fromisoformat(day).isoformat() == day for day in calendar) and calendar == sorted(set(calendar))
            and decision_date in calendar and calendar.index(decision_date)+1 < len(calendar)
            and calendar[calendar.index(decision_date)+1] == active_date, 'INVALID_EXPLICIT_NEXT_SESSION')
    return reviewed


def _bind_monthly_session(snapshot, *, target_month, market_session, active_date, source_hashes):
    """Bind metadata before the plan builder hashes its complete causal inputs."""
    _require((target_month is None) == (market_session is None), 'TARGET_MONTH_AND_SESSION_REQUIRED_TOGETHER')
    snapshot.pop('market_session', None)
    snapshot.pop('target_month', None)
    if target_month is None:
        return
    _require(target_month == active_date[:7] and isinstance(market_session, dict)
             and market_session.get('date') == active_date
             and market_session.get('timezone') == 'America/New_York', 'MONTH_OR_MARKET_SESSION_MISMATCH')
    ny = ZoneInfo('America/New_York')
    opening = datetime.fromisoformat(market_session['open_at'])
    closing = datetime.fromisoformat(market_session['close_at'])
    for stamp in (opening, closing):
        _require(stamp.tzinfo is not None and stamp.date().isoformat() == active_date
                 and stamp.astimezone(ny).date().isoformat() == active_date
                 and stamp.utcoffset() == stamp.astimezone(ny).utcoffset(), 'MARKET_SESSION_NOT_NEW_YORK_AWARE')
    _require(opening < closing, 'INVALID_MARKET_SESSION_RANGE')
    references = market_session.get('source_references', [])
    _require(isinstance(references, list), 'MARKET_SESSION_SOURCE_REQUIRED')
    references = list(references)
    if 'source' in market_session:
        references.append(market_session['source'])
    _require(references and all(isinstance(ref, str) and ref in source_hashes for ref in references), 'MARKET_SESSION_SOURCE_NOT_PINNED')
    snapshot.update(target_month=target_month, market_session=deepcopy(market_session))


def build_research_successor_plan(state, *, expected_revision, decision_date, active_date, calendar,
                                 valuation_quotes, search_arguments, source_hashes,
                                 held_unit_continuity,
                                 target_month=None, market_session=None,
                                 search=search_fresh_cash_quantities, capital_decision=None):
    """No activation, IO, frequency policy, price rounding or weight rescaling.

    Caller activates the returned plan explicitly with activate_paper_plan.
    Existing state must already reflect effective actions in its share units.
    """
    def require(ok, message):
        if not ok:
            raise ValueError(message)

    decision_adapter, method = _capital_method(capital_decision, search)
    reviewed = _review_roll_state(state, expected_revision, decision_date, active_date, calendar)
    merged_sources = dict(state['plan']['causal_inputs']['source_hashes'])
    for path, digest in source_hashes.items():
        require(path not in merged_sources or merged_sources[path] == digest, 'CONFLICTING_SOURCE_PIN')
        merged_sources[path] = digest
    source_hashes = merged_sources
    session_metadata = {}
    _bind_monthly_session(session_metadata, target_month=target_month, market_session=market_session,
                          active_date=active_date, source_hashes=source_hashes)
    require(not isinstance(search_arguments['fee_bps'], bool)
            and Fraction(str(search_arguments['fee_bps'])) == 0, 'PLAN_REQUIRES_ZERO_COMMISSION')
    require(isinstance(held_unit_continuity, dict), 'HELD_UNIT_CONTINUITY_REQUIRED')
    # Held exits keep their saved identity even when absent from the new pool.
    tickers = {sid: row['ticker'] for sid, row in search_arguments['metadata'].items()}
    for sid, quantity in reviewed['shares'].items():
        if not quantity:
            continue
        saved = {plan['causal_inputs']['securities'][sid] for plan in state['plans']
                 if sid in plan['causal_inputs']['securities']}
        require(len(saved) == 1, 'HELD_SECURITY_IDENTITY_MISSING_OR_CONFLICTING')
        saved_ticker = saved.pop()
        require(sid not in tickers or tickers[sid] == saved_ticker, 'HELD_TICKER_CHANGED')
        tickers[sid] = saved_ticker
        old_quote = state['plan']['causal_inputs']['quotes'].get(sid)
        new_quotes = [quote for quote in valuation_quotes if quote['security_id'] == sid]
        require(old_quote is not None and len(new_quotes) == 1, 'HELD_UNIT_QUOTES_REQUIRED')
        basis = old_quote['price_basis']
        require(new_quotes[0]['price_basis'] == basis == search_arguments['price_basis'], 'HELD_PRICE_UNIT_CHANGED')
        declaration = held_unit_continuity.get(sid)
        require(isinstance(declaration, dict)
                and declaration.get('from_date') == state['plan']['causal_inputs']['decision_date']
                and declaration.get('to_date') == decision_date
                and declaration.get('price_basis') == basis
                and declaration.get('status') == 'NO_UNPROCESSED_ACTIONS', 'HELD_UNIT_CONTINUITY_REQUIRED')
        refs = declaration.get('source_references')
        require(isinstance(refs, list) and refs and all(isinstance(ref, str) and ref in source_hashes for ref in refs), 'HELD_UNIT_CONTINUITY_SOURCE_REQUIRED')
    require(len(set(tickers.values())) == len(tickers), 'DUPLICATE_TICKER_ACROSS_SECURITY_IDS')
    # Check decimal representability before spending any core evaluation budget.
    for quote in valuation_quotes:
        _decimal_reference(quote['price'])
    account = dict(asof=decision_date, revision=reviewed['revision'], cash=reviewed['cash'],
                   shares=deepcopy(reviewed['shares']), reserved_cash=reviewed['reserved_cash'])
    decision_arguments = dict(decision_date=decision_date, account_state=account,
        valuation_quotes=valuation_quotes, search_arguments=search_arguments,
        source_hashes=source_hashes)
    if method == QUANTITY_METHOD:
        decision_arguments['search'] = search
    capital = decision_adapter(**decision_arguments)
    if method == TOP1_METHOD:
        require(capital.get('method') == method and capital.get('core_calls') == 0
                and capital.get('selector_calls') == 1, 'CAPITAL_METHOD_RESULT_MISMATCH')
    require(capital['target_quantities'] is not None, 'CAPITAL_SEARCH_HAS_NO_SELECTED_TARGET')
    quotes = [dict(security_id=sid, price=_decimal_reference(row['price']), as_of=row['as_of'],
                   price_kind='DECLARED_DECIMAL_REFERENCE', price_basis=row['price_basis'],
                   source_references=list(row['source_references']))
              for sid, row in capital['binding']['valuation_quotes'].items() if sid in tickers]
    snapshot = dict(research_id=capital['research_id'], as_of=decision_date,
        stocks=[dict(security_id=sid, ticker=ticker) for sid, ticker in sorted(tickers.items())],
        source_hashes=deepcopy(source_hashes), capital_decision_id=capital['decision_id'],
        selection_method=method,
        held_unit_continuity=deepcopy(held_unit_continuity))
    snapshot.update(session_metadata)
    plan = build_current_research_limit_plan(research_snapshot=snapshot, quotes=quotes,
        available_cash=reviewed['cash'], shares=deepcopy(reviewed['shares']),
        account_revision=reviewed['revision'], decision_date=decision_date, active_date=active_date,
        calendar=calendar, strategy_version='CAPITAL_AWARE_SUCCESSOR_RESEARCH_V1',
        target_quantities=deepcopy(capital['target_quantities']))
    require(plan['status'] == 'READY', 'SUCCESSOR_PLAN_BLOCKED:' + str(plan.get('reason')))
    return dict(capital_decision=capital, plan=plan, research_only=True,
                execution_blocked=True, activation_performed=False)


def roll_research_plan(state, *, expected_revision, decision_date, active_date, calendar,
                       valuation_quotes, source_hashes, held_unit_continuity,
                       target_month=None, market_session=None):
    """Reprice DAY differences against the unchanged monthly integer target.

    Continuity declarations cover positive targets as well as actual holdings.
    No search or activation occurs. Evidence authenticity belongs to caller.
    """
    require = _require
    reviewed = _review_roll_state(state, expected_revision, decision_date, active_date, calendar)
    old = state['plan']
    snapshot = deepcopy(old['causal_inputs']['research_snapshot'])
    merged = dict(snapshot['source_hashes'])
    require(isinstance(source_hashes, dict), 'SOURCE_HASHES_REQUIRED')
    for path, digest in source_hashes.items():
        require(path not in merged or merged[path] == digest, 'CONFLICTING_SOURCE_PIN')
        merged[path] = digest
    require(isinstance(valuation_quotes, list) and isinstance(held_unit_continuity, dict), 'EXPLICIT_QUOTES_AND_CONTINUITY_REQUIRED')
    tickers = old['causal_inputs']['securities']
    indexed, quotes = {}, []
    for row in valuation_quotes:
        sid = row['security_id']
        require(sid in tickers and sid not in indexed, 'UNKNOWN_OR_DUPLICATE_QUOTE_ID')
        require(row.get('ticker', tickers[sid]) == tickers[sid], 'QUOTE_TICKER_CHANGED')
        require(row['as_of'] == decision_date, 'QUOTE_DATE_MISMATCH')
        refs = row['source_references']
        require(isinstance(refs, list) and refs and all(isinstance(ref, str) and ref in source_hashes for ref in refs), 'NEW_QUOTE_SOURCE_NOT_PINNED')
        indexed[sid] = row
        quotes.append(dict(security_id=sid, price=_decimal_reference(row['price']), as_of=decision_date,
            price_kind='DECLARED_DECIMAL_REFERENCE', price_basis=row['price_basis'], source_references=list(refs)))
    needed = {sid for mapping in (reviewed['shares'], old['target_quantities']) for sid, q in mapping.items() if q}
    for sid in needed:
        require(sid in indexed and sid in old['causal_inputs']['quotes'], 'HELD_OR_TARGET_QUOTE_MISSING')
        saved_tickers = {p['causal_inputs']['securities'][sid] for p in state['plans'] if sid in p['causal_inputs']['securities']}
        require(saved_tickers == {tickers[sid]}, 'HELD_OR_TARGET_TICKER_CONFLICT')
        basis = old['causal_inputs']['quotes'][sid]['price_basis']
        require(indexed[sid]['price_basis'] == basis, 'HELD_OR_TARGET_PRICE_UNIT_CHANGED')
        declaration = held_unit_continuity.get(sid)
        require(isinstance(declaration, dict) and declaration.get('from_date') == old['causal_inputs']['decision_date']
                and declaration.get('to_date') == decision_date and declaration.get('price_basis') == basis
                and declaration.get('status') == 'NO_UNPROCESSED_ACTIONS', 'HELD_OR_TARGET_UNIT_CONTINUITY_REQUIRED')
        refs = declaration.get('source_references')
        require(isinstance(refs, list) and refs and all(isinstance(ref, str) and ref in source_hashes for ref in refs), 'NEW_CONTINUITY_SOURCE_NOT_PINNED')
    snapshot.update(source_hashes=merged, roll_parent_plan_id=old['plan_id'],
                    held_unit_continuity=deepcopy(held_unit_continuity))
    _bind_monthly_session(snapshot, target_month=target_month, market_session=market_session,
                          active_date=active_date, source_hashes=merged)
    plan = build_current_research_limit_plan(research_snapshot=snapshot, quotes=quotes,
        available_cash=reviewed['cash'], shares=deepcopy(reviewed['shares']), account_revision=reviewed['revision'],
        decision_date=decision_date, active_date=active_date, calendar=calendar,
        strategy_version=old['strategy_version'], target_quantities=deepcopy(old['target_quantities']))
    require(plan['status'] == 'READY', 'ROLL_PLAN_BLOCKED:' + str(plan.get('reason')))
    return dict(plan=plan, research_only=True, execution_blocked=True, search_calls=0,
                activation_performed=False, target_reselected=False)
