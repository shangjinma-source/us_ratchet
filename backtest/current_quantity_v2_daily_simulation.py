"""Thin explicit dispatcher over the isolated simulation services.

No source defaults, scheduler activation, automatic failure retries or new
economic rules. Providers supply inputs to existing capture/review services.
"""
from copy import deepcopy
from zoneinfo import ZoneInfo

from backtest.current_quantity_v2_daily_settlement_simulation import prepare_daily_settlement, apply_daily_settlement
from backtest.current_quantity_v2_continuation_simulation import apply_continuation
from backtest.current_quantity_v2_monthly_simulation import apply_monthly
from backtest.current_quantity_v2_simulated_settlement import _rebuild, record_close
from data.current_quantity_v2_minute_close_marks import build_marks
from data.current_quantity_v2_monthly_retarget import active_proposal
from data.current_quantity_v2_difference_plan import require, stamp


def run_daily(*, store, simulation_id, session, triggered_at, clock,
              capture_arguments, settlement_review, close_arguments,
              continuation_arguments, monthly_arguments):
    trigger = stamp(triggered_at); local = trigger.astimezone(ZoneInfo('America/New_York'))
    require(local.date().isoformat() == session and (local.hour, local.minute) == (10, 0),
            'SIMULATION_TRIGGER_OUTSIDE_WINDOW')
    inventory = store.inspect_operations(simulation_id)
    for operation in inventory['operations']:
        if operation['status'] == 'COMPLETE': continue
        require(operation['status'] == 'PREPARED', 'SIMULATION_OPERATION_INCOMPLETE_NO_AUTOMATIC_RETRY')
        store.recover(simulation_id=simulation_id, expected_revision=operation['expected_revision'],
                      operation_id=operation['operation_id'], request=operation['request'])
    current = store.read(simulation_id)
    simulation, _, last_at = _rebuild(current['simulation'])
    require('valuation' in simulation, 'VALUATION_REGISTRATION_REQUIRED')
    calendar = simulation['valuation']['registration']['calendar']
    require(session in calendar['session_dates'], 'SIMULATION_SESSION_NOT_REGISTERED')
    last_clock = [max(trigger, last_at)]
    def actual_clock():
        value = stamp(clock())
        require(last_clock[0] <= value < stamp(calendar['closes'][session]), 'SIMULATION_CLOCK_OUTSIDE_SESSION')
        last_clock[0] = value
        return value
    actual_clock()
    identifiers = [simulation_id+':daily-continuation:'+session, simulation_id+':daily-monthly:'+session]
    completed = {o['operation_id'] for o in store.inspect_operations(simulation_id)['operations'] if o['status']=='COMPLETE'}
    if completed.intersection(identifiers+[simulation_id+':daily-late:'+session]):
        return dict(current, daily_status='ALREADY_COMPLETED', session=session)
    remaining = calendar['session_dates'][len(simulation['valuation']['records']):]
    for day in remaining:
        if day >= session: break
        current = store.read(simulation_id); state = current['simulation']
        open_orders = [o for o in state['chain']['ledger']['orders'].values() if not o['closed']]
        if open_orders:
            require(all(stamp(o['session_close']) == stamp(calendar['closes'][day]) for o in open_orders),
                    'UNRESOLVED_ORDER_SESSION_MISMATCH')
            settlement_id = simulation_id+':daily-settlement:'+day
            if settlement_id not in completed:
                args = capture_arguments(deepcopy(state), day)
                prepared = prepare_daily_settlement(store=store, simulation_id=simulation_id,
                    expected_revision=current['revision'], session=day, clock=actual_clock, **args)
                review = settlement_review(deepcopy(state), deepcopy(prepared))
                current = apply_daily_settlement(store=store, prepared=prepared,
                    evaluated_at=actual_clock().isoformat(), **review)
                state = current['simulation']
            if any(not o['closed'] for o in state['chain']['ledger']['orders'].values()):
                return dict(store.read(simulation_id), daily_status='BLOCKED_UNRESOLVED_ORDERS', session=session)
        supplied = close_arguments(deepcopy(state), day)
        if supplied.get('status') == 'MISSING_CLOSE_EVIDENCE':
            require(type(supplied.get('reason')) is str and supplied['reason'].strip(), 'MISSING_CLOSE_REASON_REQUIRED')
            marks = {}; source_result = deepcopy(supplied)
        else:
            source_result = build_marks(chain=state['chain'], session=day,
                session_close=calendar['closes'][day], observed_at=actual_clock().isoformat(), **supplied)
            marks = source_result['marks']
        observed = actual_clock().isoformat()
        close_request = dict(kind='ISOLATED_DAILY_CLOSE_V1',session=day, marks=marks,
                             observed_at=observed, source_result=source_result)
        current = store.apply(simulation_id=simulation_id, expected_revision=current['revision'],
            operation_id=simulation_id+':daily-close:'+day, request=close_request,
            transform=lambda value:record_close(simulation=value,session=day,marks=marks,observed_at=observed))
    current = store.read(simulation_id); state = current['simulation']
    require(not any(not o['closed'] for o in state['chain']['ledger']['orders'].values()), 'PRIOR_ORDERS_OPEN')
    def late_result(decision_time):
        request = dict(kind='ISOLATED_DAILY_LATE_V1', session=session, observed_at=decision_time.isoformat())
        result = store.apply(simulation_id=simulation_id, expected_revision=current['revision'],
            operation_id=simulation_id+':daily-late:'+session, request=request, transform=lambda value:value)
        return dict(result,daily_status='LATE_NO_NEW_DECISION',session=session)
    decision_time = actual_clock().astimezone(ZoneInfo('America/New_York'))
    if (decision_time.hour, decision_time.minute) != (10, 0):
        return late_result(decision_time)
    same_month = active_proposal(state['chain']['ledger'])['target_month'] == session[:7]
    provider = continuation_arguments if same_month else monthly_arguments
    arguments = provider(deepcopy(state), session)
    decision_time = actual_clock().astimezone(ZoneInfo('America/New_York'))
    if (decision_time.hour, decision_time.minute) != (10, 0):
        return late_result(decision_time)
    function = apply_continuation if same_month else apply_monthly
    result = function(store=store, simulation_id=simulation_id, expected_revision=current['revision'],
        operation_id=identifiers[0 if same_month else 1], session=session,
        triggered_at=triggered_at, clock=actual_clock, **arguments)
    return dict(result, daily_status='CONTINUATION_COMPLETE' if same_month else 'MONTHLY_COMPLETE', session=session)
