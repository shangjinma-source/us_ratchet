"""Fixed 21-session holding lifecycle wrapper; research only, no IO."""
from copy import deepcopy
from fractions import Fraction

from backtest.return_priority_monthly_target_provider import build_monthly_target_provider


def build_holding_horizon_provider(*, session_dates, monthly_decisions, close_prices, actions=()):
    """Wrap one fresh base provider for one book. Never share callbacks across books.

    Only actual prior-close shares start or stop the entry clock. The wrapper
    never reads active-session prices, fills, or future action payloads.
    """
    base = build_monthly_target_provider(session_dates=session_dates,
        monthly_decisions=monthly_decisions, close_prices=close_prices, actions=actions)
    indices = {day: index for index, day in enumerate(session_dates)}
    monthly_dates = {plan['decision_date'] for plan in monthly_decisions}
    entries, triggers, previous_shares = {}, {}, {}
    previous_date = None

    def provider(*, decision_date, active_date, state):
        nonlocal entries, triggers, previous_shares, previous_date

        def blocked(reason):
            return dict(status='BLOCKED', reason=reason, orders=[],
                        research_only=True, execution_blocked=True)

        try:
            current = state['shares']
            if any(type(q) is not int or q < 0 for q in current.values()):
                return blocked('INVALID_WHOLE_SHARE_STATE')
            if previous_date is None and any(current.values()):
                return blocked('INITIAL_POSITION_ENTRY_UNKNOWN')
            if decision_date not in indices or (previous_date is not None and
                    indices[decision_date] != indices[previous_date] + 1):
                return blocked('HORIZON_PROVIDER_MUST_ADVANCE_ONE_SESSION_ONCE')
            response = base(decision_date=decision_date, active_date=active_date, state=state)
            if response.get('status') != 'READY':
                return response
            next_entries, next_triggers = dict(entries), dict(triggers)
            released = []
            for sid in set(current) | set(previous_shares) | set(next_entries) | set(next_triggers):
                quantity = current.get(sid, 0)
                if quantity and not previous_shares.get(sid, 0):
                    next_entries[sid] = decision_date
                elif not quantity:
                    next_entries.pop(sid, None)
                if not quantity and sid in next_triggers and decision_date in monthly_dates and decision_date > next_triggers[sid]:
                    del next_triggers[sid]
                    released.append(sid)
                if quantity:
                    if sid not in next_entries:
                        return blocked('HELD_POSITION_ENTRY_UNKNOWN')
                    age = indices[decision_date] - indices[next_entries[sid]] + 1
                    if age >= 21 and sid not in next_triggers:
                        next_triggers[sid] = decision_date

            target = dict(response['target_shares'])
            for sid in next_triggers:
                target[sid] = 0
            cash = Fraction(str(state['cash']))
            if isinstance(state['cash'], bool) or cash < 0:
                return blocked('INVALID_AVAILABLE_CASH')
            orders, deficits, waiting = [], [], []
            for sid in sorted(set(current) | set(target)):
                delta = target.get(sid, 0) - current.get(sid, 0)
                if not delta:
                    continue
                close = Fraction(str(close_prices[sid][decision_date]))
                if close <= 0:
                    return blocked('INVALID_DECISION_CLOSE')
                limit = Fraction(close * 100 // 1, 100) if delta > 0 else Fraction(-(-close * 100 // 1), 100)
                if limit <= 0:
                    return blocked('NONPOSITIVE_CENT_LIMIT')
                if delta > 0:
                    deficits.append((delta * limit, sid, delta, limit))
                else:
                    orders.append(dict(id=f'horizon21:{decision_date}:{sid}:SELL', security_id=sid,
                        decision_date=decision_date, active_date=active_date, side='SELL', quantity=-delta, limit=str(limit)))
            remaining = cash
            for _, sid, deficit, limit in sorted(deficits, key=lambda item: (-item[0], item[1])):
                quantity = min(deficit, int(remaining // limit))
                if quantity:
                    orders.append(dict(id=f'horizon21:{decision_date}:{sid}:BUY', security_id=sid,
                        decision_date=decision_date, active_date=active_date, side='BUY', quantity=quantity, limit=str(limit)))
                    remaining -= quantity * limit
                if quantity < deficit:
                    waiting.append(dict(security_id=sid, remaining_deficit=deficit-quantity, reason='WAIT_CASH'))
            entries, triggers = next_entries, next_triggers
            previous_shares, previous_date = dict(current), decision_date
            result = deepcopy(response)
            result.update(orders=orders, base_target_shares=dict(response['target_shares']),
                target_shares=target, effective_target_shares=dict(target),
                holding_entry_dates=dict(entries), holding_session_ages={sid: indices[decision_date]-indices[d]+1 for sid,d in entries.items()},
                exit_trigger_dates=dict(triggers), pending_exit_flags={sid: bool(current.get(sid, 0)) for sid in triggers},
                released_exit_latches=sorted(released), holding_sessions=21,
                reserved_cash=str(cash-remaining), unreserved_cash=str(remaining), wait_cash=waiting,
                action='ORDERS' if orders else 'WAIT_CASH' if waiting else 'NO_ACTION',
                method='FROZEN_WEIGHT_REPLAY_WITH_FIXED_21_SESSION_EXIT',
                hypothesis_role='ROOT_RESEARCH_NOT_USER_RISK_PREFERENCE')
            return result
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
            return blocked(dict(reason='INVALID_HORIZON_CAUSAL_INPUT', detail=str(error)))

    return provider
