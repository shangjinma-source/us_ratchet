"""End-of-observation settlement only; no decisions, bootstrap or new calendar.

Caller supplies a replay-valid SimulationStore, expected identity/revision and
registered evaluation end. Actual clock defaults to UTC now (injected only for
isolated tests/embedding). Existing evidence and operation records are retained.
This gate does not authenticate origin or defend against malicious DB replacement.
"""
from copy import deepcopy
from datetime import datetime, timezone

from backtest.current_quantity_v2_daily_settlement_simulation import prepare_daily_settlement, apply_daily_settlement
from backtest.current_quantity_v2_simulated_settlement import _rebuild, record_close
from data.current_quantity_v2_minute_close_marks import build_marks
from data.current_quantity_v2_difference_plan import require, stamp
from data.quantity_v2_simulation_account_binding import validate_account_binding


def finalize_registered_paper(*, store, simulation_id, account_id, expected_revision,
                              evaluation_end, capture_arguments, settlement_review,
                              close_arguments, clock=None):
    """Sequentially settle through the declared end after its true close.

    Incomplete minutes persist UNKNOWN, leave orders open and stop before NAV.
    Missing close evidence also stops without overwriting or inventing a value.
    Post-write errors propagate with Store/capture evidence preserved for review.
    Completed retries use the current revision, not an obsolete CAS revision.
    """
    clock=clock or (lambda:datetime.now(timezone.utc))
    current=store.read(simulation_id)
    require(current['revision']==expected_revision,'STALE_SIMULATION_REVISION')
    def identity(state):
        validate_account_binding(bootstrap=dict(simulation_id=simulation_id,account_id=account_id),simulation=state)
    identity(current['simulation'])
    simulation,_,last_at=_rebuild(current['simulation'])
    require('valuation' in simulation,'VALUATION_REGISTRATION_REQUIRED')
    calendar=simulation['valuation']['registration']['calendar']
    dates=calendar['session_dates']
    require(type(evaluation_end) is str and evaluation_end in dates,'EVALUATION_END_NOT_REGISTERED')
    end_index=dates.index(evaluation_end)
    require(len(simulation['valuation']['records'])<=end_index+1,'VALUATION_AFTER_REGISTERED_END')
    end_close=stamp(calendar['closes'][evaluation_end])
    last=[last_at]
    def actual_clock():
        value=stamp(clock().isoformat())
        require(value>=end_close,'EVALUATION_END_NOT_CLOSED')
        require(value>=last[0],'SETTLEMENT_CLOCK_ROLLBACK')
        last[0]=value
        return value
    actual_clock()
    require(stamp(simulation['chain']['ledger']['last_effective_at'])<=end_close,
            'LEDGER_ALREADY_AFTER_EVALUATION_END')
    for order in simulation['chain']['ledger']['orders'].values():
        require(stamp(order['accepted_at'])<=end_close,'ORDER_ACCEPTED_AFTER_EVALUATION_END')
    inventory=store.inspect_operations(simulation_id)
    require(all(op['status']=='COMPLETE' for op in inventory['operations']),
            'SETTLEMENT_RECOVERY_REQUIRED_NO_AUTOMATIC_RETRY')
    completed={op['operation_id'] for op in inventory['operations']}
    def result(status):return dict(current,settlement_status=status,evaluation_end=evaluation_end,
        new_decisions=0,observed_at=actual_clock().isoformat())
    if any(row['status']!='COMPLETE' for row in simulation['valuation']['records']):
        return result('BLOCKED_PRIOR_CLOSE_EVIDENCE')
    remaining=dates[len(simulation['valuation']['records']):end_index+1]
    if not remaining:return result('ALREADY_FINALIZED')
    revision=current['revision']
    def read_current():
        value=store.read(simulation_id)
        require(value['revision']==revision,'STALE_SIMULATION_REVISION')
        identity(value['simulation'])
        actual_clock()
        return value
    for day in remaining:
        current=read_current();state=current['simulation']
        require(stamp(calendar['closes'][day])<=actual_clock(),'FUTURE_CLOSE_NOT_OBSERVED')
        orders=[o for o in state['chain']['ledger']['orders'].values() if not o['closed']]
        if orders:
            require(all(stamp(o['session_close'])==stamp(calendar['closes'][day]) for o in orders),
                    'UNRESOLVED_ORDER_SESSION_MISMATCH')
            operation_id=simulation_id+':daily-settlement:'+day
            if operation_id not in completed:
                args=capture_arguments(deepcopy(state),day)
                read_current()
                prepared=prepare_daily_settlement(store=store,simulation_id=simulation_id,
                    expected_revision=revision,session=day,clock=actual_clock,**args)
                review=settlement_review(deepcopy(state),deepcopy(prepared))
                read_current()
                current=apply_daily_settlement(store=store,prepared=prepared,
                    evaluated_at=actual_clock().isoformat(),**review)
                revision=current['revision'];identity(current['simulation']);state=current['simulation']
            if any(not o['closed'] for o in state['chain']['ledger']['orders'].values()):
                return result('UNKNOWN_UNRESOLVED_ORDERS')
        supplied=close_arguments(deepcopy(state),day)
        read_current()
        if supplied.get('status')=='MISSING_CLOSE_EVIDENCE':
            return result('BLOCKED_MISSING_CLOSE_EVIDENCE')
        source=build_marks(chain=state['chain'],session=day,session_close=calendar['closes'][day],
            observed_at=actual_clock().isoformat(),**supplied)
        marks=source['marks'];observed=actual_clock().isoformat()
        request=dict(kind='ISOLATED_DAILY_CLOSE_V1',session=day,marks=marks,observed_at=observed,source_result=source)
        current=store.apply(simulation_id=simulation_id,expected_revision=revision,
            operation_id=simulation_id+':daily-close:'+day,request=request,
            transform=lambda value:record_close(simulation=value,session=day,marks=marks,observed_at=observed))
        revision=current['revision'];identity(current['simulation'])
        if current['simulation']['valuation']['records'][-1]['status']!='COMPLETE':
            return result('BLOCKED_CLOSE_EVIDENCE')
    return result('FINALIZED_DECLARED_END')
