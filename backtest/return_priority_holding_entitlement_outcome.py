"""Frozen holding adapter for one cash-and-stock merger; no reinvestment or IO.

Ordinary windows delegate to the unchanged nominal holding kernel. A mixed
merger window delegates its prefix, then values economic rights separately.
No source qualification or effective-time inference occurs in this component.
"""
from copy import deepcopy
from fractions import Fraction
from backtest.return_priority_frozen_nominal_outcome import frozen_nominal_outcome
from backtest.return_priority_cash_stock_entitlements import (
    convert_cash_stock_entitlement, value_cash_stock_entitlements,
)


def frozen_holding_with_entitlements(*, target_weights, nominal_prices, metadata,
                                    session_dates, decision_date, end_date,
                                    entered_cash='20000', fee_bps='0', split_events=(),
                                    cash_merger_events=(), unmodelled_action_events=(),
                                    cash_stock_merger_events=(), fractional_settlements=None,
                                    price_source_references=None):
    """Mixed events/settlements use cash_stock_entitlements schemas unchanged.

    nominal_prices retains old {sid:{date:{open,close}}} schema and must also
    include successor Close for valuation after conversion. Each valued SID
    requires price_source_references[sid] (a nonempty reference list).
    Effective merger timing must be explicitly confirmed by the caller. Entire
    day marks use an end-of-session entitlement, never claim intraday execution.
    At most one mixed event is supported; unsupported events block explicitly.
    """
    ordinary = dict(target_weights=target_weights, nominal_prices=nominal_prices, metadata=metadata,
                    session_dates=session_dates, decision_date=decision_date, end_date=end_date,
                    entered_cash=entered_cash, fee_bps=fee_bps, split_events=split_events,
                    cash_merger_events=cash_merger_events, unmodelled_action_events=unmodelled_action_events)
    relevant = []
    for event in cash_stock_merger_events:
        when = event['effective_date']
        if when > end_date:
            continue
        if event['old_sid'] in target_weights and Fraction(target_weights[event['old_sid']]) > 0:
            relevant.append(event)
    if not relevant:
        result = frozen_nominal_outcome(**ordinary)
        result['adapter_role'] = 'UNCHANGED_NOMINAL_KERNEL_NO_MIXED_EVENT'
        result['return_fraction'] = result['return']
        result['execution_blocked'] = True
        return result
    base = dict(status='BLOCKED', return_fraction=None, return_value=None, daily_ledger=[], actions=[],
                research_only=True, execution_blocked=True, real_orders=False, external_flow='0',
                conditional_price_basis=True, taxes_and_other_costs_modelled=False)
    if len(relevant) != 1:
        return dict(base, blocked_reason='MULTIPLE_MIXED_EVENTS_NOT_SUPPORTED')
    event = relevant[0]
    effective = event['effective_date']
    if session_dates != sorted(set(session_dates)) or decision_date not in session_dates or end_date not in session_dates:
        raise ValueError('Explicit ordered market calendar required')
    days = [day for day in session_dates if decision_date < day <= end_date]
    if not days:
        raise ValueError('No holding sessions')
    if effective <= days[0]:
        return dict(base, blocked_reason='TERMINATED_BEFORE_OR_AT_ENTRY')
    if effective not in days:
        return dict(base, blocked_reason='INVALID_MIXED_EVENT_SESSION')
    event_index = days.index(effective)
    prefix_end = days[event_index - 1]
    prefix = frozen_nominal_outcome(**dict(ordinary, end_date=prefix_end))
    if prefix['status'] != 'COMPLETE':
        return dict(prefix, adapter_role='PREFIX_BLOCKED_BEFORE_MIXED_EVENT', return_fraction=None, execution_blocked=True)
    ledger = deepcopy(prefix['daily_ledger'])
    actions = deepcopy(prefix['actions'])
    state = dict(cash=prefix['cash'], shares=deepcopy(prefix['final_shares']))
    additional_receivable = Fraction(prefix['receivable'])
    budget = Fraction(entered_cash)
    peak = budget
    maximum_dd = Fraction(0)
    for row in ledger:
        equity = Fraction(row['equity'])
        peak = max(peak, equity)
        maximum_dd = max(maximum_dd, 1 - equity / peak)

    def result(status, day, reason=None):
        equity = ledger[-1]['equity'] if ledger else str(budget)
        return dict(status=status, blocked_reason=reason, decision_date=decision_date, end_date=end_date,
                    entry_date=days[0], state_date=day, last_valued_date=ledger[-1]['date'],
                    entered_cash=str(budget), cash=state['cash'], initial_shares=prefix['initial_shares'],
                    final_shares=deepcopy(state['shares']), entitlement_state=deepcopy(state),
                    legacy_cash_receivable=str(additional_receivable), fees=prefix['fees'],
                    daily_ledger=deepcopy(ledger), actions=deepcopy(actions), equity=equity,
                    return_fraction=str(Fraction(equity) / budget - 1) if status == 'COMPLETE' else None,
                    maximum_drawdown=str(maximum_dd), research_only=True, execution_blocked=True,
                    external_flow='0', real_orders=False, taxes_and_other_costs_modelled=False,
                    limitations=['Unpaid cash and undelivered shares remain nontradable economic rights.',
                                 'Successor marks and contractual fractional reference retain caller source limitations.',
                                 'No dividend, tax, withholding, trading or payment model after merger.'])

    for day in days[event_index:]:
        for other in cash_stock_merger_events:
            if other['effective_date'] > day or other['effective_date'] <= prefix_end or other is event:
                continue
            exposed = {sid for sid, q in state['shares'].items() if q}
            if day == effective and state['shares'].get(event['old_sid'], 0):
                exposed.add(event['new_sid'])
            exposed.update(right['new_sid'] for right in state.get('merger_entitlements', [])
                           if right['pending_whole_shares'] or Fraction(right['fractional_share_entitlement']))
            if other['old_sid'] in exposed:
                return result('BLOCKED', day, 'INVALID_SUBSEQUENT_MIXED_EVENT_SESSION' if other['effective_date'] not in days
                              else 'SUBSEQUENT_MIXED_EVENT_ON_ENTITLEMENT_NOT_SUPPORTED')
        # Do not silently drop later company actions on existing shares/rights.
        for group in (split_events, cash_merger_events, unmodelled_action_events):
            for other in group:
                if not prefix_end < other['date'] <= day:
                    continue
                sid = other['security_id']
                if state['shares'].get(sid, 0) or sid == event['new_sid']:
                    return result('BLOCKED', day, 'POST_MIXED_ACTION_REQUIRES_EXPLICIT_EXTENSION')
        if day == effective:
            try:
                state = convert_cash_stock_entitlement(state=state, event=event, as_of=day)
            except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
                return result('BLOCKED', day, dict(reason='MIXED_CONVERSION_UNRESOLVED', detail=str(error)))
            actions.append(dict(date=day, event='CASH_STOCK_ENTITLEMENT_CONVERSION', details=deepcopy(event)))
        marks = {}
        needed = {sid for sid, q in state['shares'].items() if q}
        needed.update(r['new_sid'] for r in state.get('merger_entitlements', []) if r['pending_whole_shares'])
        for sid in needed:
            row = nominal_prices.get(sid, {}).get(day, {})
            if row.get('close') is not None:
                marks[sid] = dict(date=day, price=row['close'], source_references=(price_source_references or {}).get(sid, []))
        valued = value_cash_stock_entitlements(state=state, marks=marks, as_of=day,
                                              fractional_settlements=fractional_settlements)
        if valued['status'] == 'BLOCKED':
            return result('BLOCKED', day, dict(reason='ECONOMIC_ENTITLEMENT_VALUATION_BLOCKED', details=valued['blockers']))
        equity = Fraction(valued['total_equity']) + additional_receivable
        peak = max(peak, equity)
        maximum_dd = max(maximum_dd, 1 - equity / peak)
        ledger.append(dict(date=day, cash=state['cash'], shares=deepcopy(state['shares']),
                           equity=str(equity), external_flow='0', valuation=valued,
                           legacy_cash_receivable=str(additional_receivable)))
    return result('COMPLETE', end_date)
