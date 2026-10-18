"""Pure single-entry nominal-price holding diagnostic; no execution or IO."""
from fractions import Fraction


def _number(value, positive=False):
    if isinstance(value, bool):
        raise ValueError('Boolean numeric value')
    number = Fraction(str(value))
    if number < 0 or (positive and number == 0):
        raise ValueError('Invalid nonnegative amount')
    return number


def frozen_nominal_outcome(*, target_weights, nominal_prices, metadata,
                           session_dates, decision_date, end_date,
                           entered_cash='20000', fee_bps='0', split_events=(),
                           cash_merger_events=(), unmodelled_action_events=()):
    """Prices: {sid: {ISOdate: {'open': value, 'close': value}}}.

    Events require security_id, date, source_references (nonempty list).
    Splits require new_shares/old_shares; mergers require share_cash.
    Caller supplies complete ordered market sessions. Events apply before Open.
    No payment-date model: merger proceeds remain nontradable receivables.
    """
    budget = _number(entered_cash, True)
    if _number(fee_bps) != 0:
        raise ValueError('Only explicit zero fees supported')
    if session_dates != sorted(set(session_dates)) or decision_date >= end_date:
        raise ValueError('Invalid dates')
    if decision_date not in session_dates or end_date not in session_dates:
        raise ValueError('Decision and end must be supplied sessions')
    days = [day for day in session_dates if decision_date < day <= end_date]
    weights = {sid: _number(weight) for sid, weight in target_weights.items()}
    weights = {sid: weight for sid, weight in weights.items() if weight}
    if sum(weights.values()) > 1:
        raise ValueError('No leverage')
    issuers = [metadata[sid]['issuer_id'] for sid in weights]
    if len(issuers) != len(set(issuers)):
        raise ValueError('At most one class per issuer')
    schedule = {}
    for kind, events in [('unmodelled', unmodelled_action_events),
                         ('split', split_events), ('merger', cash_merger_events)]:
        for event in events:
            day = event['date']
            if not decision_date < day <= end_date:
                continue  # Future event contents are deliberately not read.
            sid = event['security_id']
            if sid not in weights:
                continue
            refs = event.get('source_references')
            if not isinstance(refs, list) or not refs or not all(refs):
                raise ValueError('Event requires explicit source references')
            if day not in days:
                raise ValueError('Event date must be an explicit session; no date guessing')
            key = (day, sid)
            if key in schedule:
                raise ValueError('Duplicate or simultaneous actions require explicit resolution')
            schedule[key] = (kind, event)
    cash, receivable = budget, Fraction(0)
    positions, initial, ledger, actions = {}, {}, [], []
    peak, maximum_drawdown = budget, Fraction(0)
    state_date = decision_date

    def result(status, reason=None):
        equity = ledger[-1]['equity'] if ledger else str(budget)
        return {'status': status, 'blocked_reason': reason, 'entry_date': days[0],
                'decision_date': decision_date, 'end_date': end_date,
                'last_valued_date': ledger[-1]['date'] if ledger else decision_date,
                'state_date': state_date,
                'entered_cash': str(budget), 'cash': str(cash), 'receivable': str(receivable),
                'initial_shares': dict(initial), 'final_shares': dict(positions),
                'fees': '0', 'daily_ledger': ledger, 'actions': actions,
                'equity': equity, 'return': str(Fraction(equity) / budget - 1) if status == 'COMPLETE' else None,
                'maximum_drawdown': str(maximum_drawdown),
                'not_real_orders': True, 'research_only': True,
                'receivable_is_tradable_cash': False, 'taxes_and_other_costs_modelled': False,
                'valuation_scope': 'Nominal marks plus gross nontradable merger receivables; unknown payment date retained through end.'}

    for day in days:
        state_date = day
        if day == days[0]:
            for sid in sorted(weights):
                action = schedule.get((day, sid))
                if action and action[0] == 'merger':
                    return result('BLOCKED', {'date': day, 'security_id': sid,
                                             'reason': 'TERMINATED_BEFORE_ENTRY'})
            # Entry-day splits are already reflected in nominal Open; no old
            # shares or pre-entry spinoff entitlements are owned by this book.
        # Validate all action effects before mutating this day's position state.
        pending = []
        for sid, quantity in sorted(positions.items()):
            if not quantity or (day, sid) not in schedule:
                continue
            kind, event = schedule[(day, sid)]
            if kind == 'unmodelled':
                return result('BLOCKED', {'date': day, 'security_id': sid, 'reason': 'UNMODELLED_HELD_ACTION', 'event': dict(event)})
            if kind == 'split':
                new_quantity = quantity * _number(event['new_shares'], True) / _number(event['old_shares'], True)
                if new_quantity.denominator != 1:
                    return result('BLOCKED', {'date': day, 'security_id': sid, 'reason': 'FRACTIONAL_SPLIT_ENTITLEMENT', 'entitlement': str(new_quantity)})
                pending.append((sid, kind, int(new_quantity), event))
            else:
                pending.append((sid, kind, quantity * _number(event['share_cash']), event))
        for sid, kind, value, event in pending:
            old = positions[sid]
            if kind == 'split':
                positions[sid] = value
            else:
                positions[sid] = 0
                receivable += value
            actions.append({'date': day, 'security_id': sid, 'kind': kind, 'shares_before': old,
                            'shares_after': positions[sid], 'receivable_added': str(value) if kind == 'merger' else '0',
                            'source_references': list(event['source_references'])})
        if day == days[0]:
            proposed, spent = {}, Fraction(0)
            for sid, weight in sorted(weights.items()):
                try:
                    price = _number(nominal_prices[sid][day]['open'], True)
                except (KeyError, ValueError, TypeError, ZeroDivisionError):
                    return result('BLOCKED', {'date': day, 'security_id': sid, 'reason': 'MISSING_OR_INVALID_ENTRY_OPEN'})
                proposed[sid] = int(budget * weight // price)
                spent += proposed[sid] * price
            positions.update(proposed)
            initial.update(proposed)
            cash -= spent
        stock_value = Fraction(0)
        marks = {}
        for sid, quantity in sorted(positions.items()):
            if quantity == 0:
                continue
            try:
                price = _number(nominal_prices[sid][day]['close'], True)
            except (KeyError, ValueError, TypeError, ZeroDivisionError):
                return result('BLOCKED', {'date': day, 'security_id': sid, 'reason': 'MISSING_OR_INVALID_HELD_CLOSE'})
            marks[sid] = str(price)
            stock_value += quantity * price
        equity = cash + stock_value + receivable
        peak = max(peak, equity)
        maximum_drawdown = max(maximum_drawdown, 1 - equity / peak)
        ledger.append({'date': day, 'shares': dict(positions), 'close_marks': marks,
                       'cash': str(cash), 'stock_value': str(stock_value),
                       'receivable': str(receivable), 'equity': str(equity), 'external_flow': '0'})
    return result('COMPLETE')
