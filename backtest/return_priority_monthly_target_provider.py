"""Causal monthly frozen-weight replay. No search, execution, or source IO."""
from fractions import Fraction


def amount(value):
    if isinstance(value, bool):
        raise ValueError('Boolean amount')
    result = Fraction(str(value))
    if result < 0:
        raise ValueError('Negative amount')
    return result


def build_monthly_target_provider(*, session_dates, monthly_decisions, close_prices, actions=()):
    """Return one stateful callback for one continuous book, never share it.

    close_prices={sid:{date: nominal Close}}; action schema matches limit book.
    State shares are already adjusted by the kernel through decision_date.
    Targets alone migrate here. Active-date orders remain decision-date units.
    Unpaid receivables and undelivered rights never enter sizing or cash reserves.
    """
    if len(session_dates) < 2 or session_dates != sorted(set(session_dates)):
        raise ValueError('Explicit unique ordered market calendar required')
    plans = {}
    for plan in monthly_decisions:
        day = plan['decision_date']
        if day not in session_dates[:-1] or day in plans:
            raise ValueError('Invalid or duplicate monthly decision')
        weights = {sid: amount(v) for sid, v in plan['target_weights'].items()}
        if sum(weights.values()) > 1:
            raise ValueError('Weights exceed one')
        plans[day] = {sid: value for sid, value in weights.items() if value}
    if session_dates[0] not in plans:
        raise ValueError('Initial close must freeze a target')
    target, previous_call = {}, None
    target_date = None

    def provider(*, decision_date, active_date, state):
        nonlocal target, previous_call, target_date

        def blocked(reason):
            return dict(status='BLOCKED', reason=reason, orders=[], target_shares=dict(target),
                        research_only=True, execution_blocked=True)

        try:
            index = session_dates.index(decision_date)
            if index >= len(session_dates)-1 or session_dates[index+1] != active_date or state['asof'] != decision_date:
                return blocked('INVALID_NEXT_SESSION_OR_STATE_DATE')
            if previous_call is not None and decision_date != session_dates[session_dates.index(previous_call)+1]:
                return blocked('PROVIDER_MUST_ADVANCE_ONE_SESSION_ONCE')
            if previous_call is None and decision_date != session_dates[0]:
                return blocked('PROVIDER_MUST_START_AT_INITIAL_CLOSE')
            shares = state['shares']
            if any(type(q) is not int or q < 0 for q in shares.values()):
                return blocked('INVALID_WHOLE_SHARE_STATE')
            cash = amount(state['cash'])
            next_target = dict(target)
            adjustments = []
            seen_actions = set()
            for action in actions:
                day = action['date']
                if day > decision_date or day <= (previous_call or session_dates[0]):
                    continue  # Never inspect future action payload or initial past units.
                sid = action['security_id']
                if not shares.get(sid, 0) and not next_target.get(sid, 0):
                    continue
                if day not in session_dates:
                    return blocked('OFF_SESSION_EXPOSED_ACTION')
                if (day, sid) in seen_actions:
                    return blocked('SIMULTANEOUS_EXPOSED_ACTIONS_UNSUPPORTED')
                seen_actions.add((day, sid))
                if action['type'] != 'split':
                    return blocked('UNSUPPORTED_EXPOSED_ACTION')
                if not isinstance(action.get('source_references'), list) or not action['source_references'] or not all(action['source_references']):
                    return blocked('ACTION_EVIDENCE_REQUIRED')
                numerator, denominator = amount(action['new_shares']), amount(action['old_shares'])
                if not numerator or not denominator:
                    return blocked('INVALID_SPLIT_RATIO')
                adjusted = next_target.get(sid, 0) * numerator / denominator
                if adjusted.denominator != 1:
                    return blocked('FRACTIONAL_SPLIT_TARGET_UNSUPPORTED')
                next_target[sid] = int(adjusted)
                adjustments.append(dict(security_id=sid, date=day, target_after=int(adjusted)))

            def close(sid):
                value = amount(close_prices[sid][decision_date])
                if value <= 0:
                    raise ValueError('Nonpositive decision Close')
                return value

            sizing_equity = None
            if decision_date in plans:
                sizing_equity = cash + sum((q * close(sid) for sid, q in shares.items() if q), Fraction(0))
                next_target = {sid: int(weight * sizing_equity // close(sid)) for sid, weight in plans[decision_date].items()}
            orders, deficits, waiting = [], [], []
            for sid in sorted(set(shares) | set(next_target)):
                delta = next_target.get(sid, 0) - shares.get(sid, 0)
                if not delta:
                    continue
                marked = close(sid)
                limit = Fraction(marked * 100 // 1, 100) if delta > 0 else Fraction(-(-marked * 100 // 1), 100)
                if limit <= 0:
                    return blocked('NONPOSITIVE_CENT_LIMIT')
                if delta > 0:
                    deficits.append((delta * limit, sid, delta, limit))
                else:
                    orders.append(dict(id=f'monthly:{decision_date}:{sid}:SELL', security_id=sid,
                        decision_date=decision_date, active_date=active_date, side='SELL', quantity=-delta, limit=str(limit)))
            remaining = cash
            for _, sid, deficit, limit in sorted(deficits, key=lambda item: (-item[0], item[1])):
                quantity = min(deficit, int(remaining // limit))
                if quantity:
                    orders.append(dict(id=f'monthly:{decision_date}:{sid}:BUY', security_id=sid,
                        decision_date=decision_date, active_date=active_date, side='BUY', quantity=quantity, limit=str(limit)))
                    remaining -= quantity * limit
                if quantity < deficit:
                    waiting.append(dict(security_id=sid, remaining_deficit=deficit-quantity, reason='WAIT_CASH'))
            target = next_target
            previous_call = decision_date
            if decision_date in plans:
                target_date = decision_date
            return dict(status='READY', orders=orders, target_shares=dict(target), target_decision_date=target_date,
                target_adjustments=adjustments, investable_equity_at_reset=str(sizing_equity) if sizing_equity is not None else None,
                cash_before=str(cash), reserved_cash=str(cash-remaining), unreserved_cash=str(remaining),
                wait_cash=waiting, action='ORDERS' if orders else 'WAIT_CASH' if waiting else 'NO_ACTION',
                time_in_force='DAY', expiry=active_date, research_only=True, execution_blocked=True,
                method='FROZEN_WEIGHT_REPLAY_NO_REOPTIMIZATION')
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
            return blocked(dict(reason='INVALID_OR_MISSING_CAUSAL_INPUT', detail=str(error)))

    return provider
