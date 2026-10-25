"""Cash-change-only reselection versus the unchanged monthly target."""
from copy import deepcopy
from fractions import Fraction

from backtest.dynamic_historical_inputs import build_historical_inputs
from backtest.dynamic_post_close_snapshot import decision_snapshot
from backtest.dynamic_risk_units import reviewed_split_schedule, migrate_risk_splits
from data.dynamic_switch_risk_comparison import compare_with_monthly_exit


def build_cash_policy_provider(*, bundle, seed, mode, flow_dates, selector,
                               selection_recorder, input_builder=None):
    if mode not in ('KEEP_MONTHLY', 'RESELECT_ON_FLOW'):
        raise ValueError('EXPLICIT_CASH_POLICY_REQUIRED')
    targets = deepcopy(seed['monthly_targets'])
    events = reviewed_split_schedule(bundle['risk_events'])
    risk = None
    previous = None
    searched_dates = set()
    audit = []

    def select(**arguments):
        day = arguments['decision_date']
        if mode == 'RESELECT_ON_FLOW' and day in flow_dates:
            if day in searched_dates:
                raise ValueError('DUPLICATE_CASH_RESELECTION')
            searched_dates.add(day)
            return selector(**arguments)
        return {'selected': {'quantities': deepcopy(targets)}}

    builder = input_builder or build_historical_inputs(
        bundle, selector=select, selection_recorder=selection_recorder)

    def provider(*, decision_date, active_date, state):
        nonlocal targets, risk, previous
        if state['asof'] != decision_date or active_date <= decision_date:
            raise ValueError('CASH_POLICY_CAUSAL_CLOCK_REQUIRED')
        if previous is not None and decision_date <= previous:
            raise ValueError('CASH_POLICY_CLOCK_MUST_ADVANCE')
        if previous is None and decision_date != seed['date']:
            raise ValueError('CASH_POLICY_SEED_DATE_MISMATCH')
        actual = deepcopy(state)
        post_close = []
        if state.get('pending_post_close_coordinates'):
            state, post_close = decision_snapshot(state, decision_date=decision_date,
                                                  reviewed_events=bundle['distribution_events'])
        for event in events:
            if previous is not None and previous < event['date'] <= decision_date:
                sid = event['security_id']
                successor = event.get('new_security_id', sid)
                if sid in targets:
                    if successor != sid and targets.get(successor, 0):
                        raise ValueError('CASH_TARGET_SUCCESSOR_COLLISION')
                    quantity = targets.pop(sid)
                    targets[successor] = int(quantity*Fraction(event['new_shares'])/Fraction(event['old_shares']))
        for event in bundle['distribution_events']:
            if previous is not None and previous < event['effective_date'] <= decision_date:
                sid = event['parent_sid']
                if sid in targets and (event['post_parent_sid'] != sid or Fraction(event['parent_ratio']) != 1):
                    raise ValueError('CASH_POLICY_PARENT_TARGET_MIGRATION_REVIEW_REQUIRED')
        migrated, migrations = migrate_risk_splits(risk, through_date=decision_date, events=events)
        inputs = builder(decision_date=decision_date, state=deepcopy(state), prior_risk_state=risk)
        anchor = inputs['history_inputs']['base_target']['monthly_decision_date']
        if anchor != seed['risk_state']['decision_date']:
            raise ValueError('CASH_POLICY_CANNOT_RESET_MONTHLY_RISK')
        holdings = {sid: quantity for sid, quantity in state['shares'].items()
                    if sid not in state.get('terminated_security_ids', [])}
        comparison = compare_with_monthly_exit(cash=state['cash'], holdings=holdings,
                                               prior_risk_state=migrated, **inputs)
        nontradable = Fraction(0)
        if state.get('distribution_rights') or state.get('merger_entitlements') or Fraction(state.get('receivable', '0')):
            ledger = state['daily_ledger'][-1]
            if ledger['date'] != decision_date or ledger['cash'] != state['cash']:
                raise ValueError('CASH_POLICY_ENTITLEMENT_SNAPSHOT_MISMATCH')
            nontradable = sum((Fraction(ledger[key]) for key in
                ('receivable', 'distribution_entitlement_value', 'nontradable_entitlement_value')), Fraction(0))
        risk = deepcopy(comparison['risk_state'])
        if previous is None:
            original = seed['risk_state']
            for sid in original['peaks']:
                for key in ('peaks', 'last_closes'):
                    if Fraction(risk[key][sid]) != Fraction(original[key][sid]):
                        raise ValueError('CASH_POLICY_INITIAL_RISK_HISTORY_MISMATCH')
                if (sid in risk['exited']) != (sid in original['exited']):
                    raise ValueError('CASH_POLICY_INITIAL_EXIT_LATCH_MISMATCH')
        reselected = mode == 'RESELECT_ON_FLOW' and decision_date in flow_dates
        if reselected:
            targets = deepcopy(inputs['candidate'])
        effective = {sid: 0 if sid in risk['exited'] else quantity for sid, quantity in targets.items()}
        orders = []
        for sid in sorted(set(holdings) | set(effective)):
            difference = effective.get(sid, 0)-holdings.get(sid, 0)
            if difference:
                orders.append(dict(id='cash-policy:'+decision_date+':'+sid,
                    security_id=sid, decision_date=decision_date, active_date=active_date,
                    decision_mark=inputs['prices'][sid], quantity=abs(difference),
                    side='BUY' if difference > 0 else 'SELL'))
        audit.append(dict(date=decision_date, mode=mode, reselected=reselected,
            input_account=actual, decision_account=deepcopy(state),
            targets=deepcopy(targets), effective_targets=effective, risk_state=deepcopy(risk),
            capital_basis=dict(tradable_equity=comparison['candidate_comparison']['equity'],
                               nontradable_equity_excluded_from_selection=str(nontradable)),
            migrated_events=migrations, post_close_events=post_close, orders=deepcopy(orders)))
        previous = decision_date
        return dict(status='READY', orders=orders, research_only=True)

    return provider, audit
