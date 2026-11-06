"""Isolated proposal: audit unexplained cash; never classify flows or calculate returns."""
from fractions import Fraction as F
from core.strategy_account_ledger import replay, apply_event


def audit_cash_changes(*, baseline, current):
    for state in (baseline,current):
        if replay(state['account_id'],[r['payload'] for r in state['events']])!=state:
            raise ValueError('ACCOUNT_REPLAY_MISMATCH')
    if baseline['account_id']!=current['account_id'] or current['events'][:len(baseline['events'])]!=baseline['events']:
        raise ValueError('ACCOUNT_HISTORY_FORK')
    # A fill invalidates manual cash. Reconstruct the theoretical balance since
    # the last authoritative confirmation, including fills already in baseline.
    expected=F(0)
    for row in baseline['events']:
        if row['payload']['kind']=='CASH_CONFIRM':
            # Prefix replay also restores the exact reservation snapshot.
            prefix=baseline['events'][:baseline['events'].index(row)+1]
            expected=F(replay(baseline['account_id'],[r['payload'] for r in prefix])['total_uninvested_cash'])
        else:expected+=F(row['effect']['cash_delta'])
    state=baseline;rows=[];trade_since_confirmation=F(0)
    for record in current['events'][len(baseline['events']):]:
        event=record['payload'];before=state
        state,effect=apply_event(state,event,expected_revision=state['revision'])
        if event['kind']=='CASH_CONFIRM':
            actual=F(state['total_uninvested_cash']);difference=actual-expected
            rows.append(dict(event_id=event['event_id'],received_at=None,
                received_at_scope='NOT_PRESENT_IN_REPLAYED_STATE',
                previous_available_cash=before['available_cash'],
                confirmed_available_cash=state['available_cash'],
                reserved_before=before['reserved_cash'],reserved_at_confirmation=state['reserved_cash'],
                expected_total_uninvested_cash=str(expected),confirmed_total_uninvested_cash=str(actual),
                recorded_trade_cash_since_audit_start_or_last_confirmation=str(trade_since_confirmation),
                unexplained_net_change=str(difference),
                status='UNEXPLAINED_CHANGE' if difference else 'RECONCILED',
                classification=None))
            expected=actual;trade_since_confirmation=F(0)
        else:
            delta=F(effect['cash_delta']);expected+=delta;trade_since_confirmation+=delta
    return dict(status='CASH_DIFFERENCE_AUDIT_ONLY',account_id=current['account_id'],
                baseline_revision=baseline['revision'],current_revision=current['revision'],
                confirmations=rows,account_mutated=False,returns_computed=False,
                limitation='Unexplained changes are not classified as deposits, withdrawals, income or corrections. Recording timestamps are unavailable in reducer state.')
