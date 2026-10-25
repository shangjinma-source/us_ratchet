"""Build causal account-specific inputs from a frozen conditional daily bundle."""
from datetime import datetime, timedelta
from fractions import Fraction

from backtest.dynamic_risk_units import reviewed_split_schedule, migrate_risk_splits


def build_historical_inputs(bundle, *, selector, selection_recorder):
    events = reviewed_split_schedule(bundle['risk_events'])
    calendar = bundle['calendar']
    sessions = bundle['session_dates']
    clocks = bundle['session_close_times']

    def current_unit(sid, day):
        unit = 'nominal:'+sid+':initial'
        for event in events:
            if event['date'] <= day and event.get('new_security_id', event['security_id']) == sid:
                unit = event['new_unit_id']
        return unit

    def close_in_current_units(sid, day, decision):
        factor = Fraction(1)
        for event in reversed(events):
            successor = event.get('new_security_id', event['security_id'])
            if day < event['date'] <= decision and successor == sid:
                factor *= Fraction(event['old_shares']) / Fraction(event['new_shares'])
                sid = event['security_id']
        return str(Fraction(bundle['ohlc'][sid][day]['close']) * factor)

    def builder(*, decision_date, state, prior_risk_state):
        anchor = max(day for day in bundle['reset_dates'] if day <= decision_date)
        eligible = bundle['eligibility'][decision_date]
        current_risk = None
        if prior_risk_state and prior_risk_state['decision_date'] == anchor:
            current_risk, _ = migrate_risk_splits(prior_risk_state, through_date=decision_date, events=events)
        terminated = set(state.get('terminated_security_ids', []))
        held = {sid: quantity for sid, quantity in state['shares'].items() if sid not in terminated}
        domain = set(eligible) | set(held) | set((current_risk or {}).get('peaks', {}))
        assert domain and not domain & terminated
        prices = {sid: bundle['ohlc'][sid][decision_date]['close'] for sid in domain}
        equity = Fraction(state['cash']) + sum((quantity*Fraction(prices[sid]) for sid, quantity in held.items()), Fraction(0))
        end = calendar.index(decision_date)
        dates = calendar[end-252:end+1]
        if len(dates) != 253:
            raise ValueError('FULL_253_SESSION_WINDOW_REQUIRED')
        scenarios = [{sid: str(Fraction(bundle['training_series'][sid][dates[index+21]]) /
                               Fraction(bundle['training_series'][sid][dates[index]])) for sid in domain}
                     for index in range(0, 252, 21)]
        arguments = dict(bundle['search_template'], decision_date=decision_date, entered_cash=str(equity),
                         prices={sid: prices[sid] for sid in eligible},
                         metadata={sid: bundle['metadata'][sid] for sid in eligible},
                         training_scenarios=[{sid: row[sid] for sid in eligible} for row in scenarios],
                         scenario_dates=dates[21::21])
        selection = selector(**arguments)
        if selection.get('selected') is None:
            raise ValueError('NO_ADMISSIBLE_DYNAMIC_SELECTION')
        candidate = {sid: min(quantity, int(equity/(2*Fraction(prices[sid]))))
                     for sid, quantity in selection['selected']['quantities'].items()}
        history_days = sessions[sessions.index(anchor):sessions.index(decision_date)+1]
        units = {sid: current_unit(sid, decision_date) for sid in domain}
        histories = {sid: dict(units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',
            unit_asof=decision_date, currency='USD', basis_id=units[sid], review_reference='frozen-dynamic-bundle'),
            source_reference='frozen-conditional-execution-panel',
            closes=[dict(date=day, completed_at=clocks['closes'][day],
                         close=close_in_current_units(sid, day, decision_date)) for day in history_days]) for sid in domain}
        selection_recorder(decision_date, arguments, selection)
        return dict(account_id='fixed-dynamic-'+bundle['label'], candidate=candidate, prices=prices,
                    scenarios=scenarios, scenario_dates=dates[21::21], slippage_bps=bundle['slippage_bps'],
                    history_inputs=dict(base_target=dict(monthly_decision_date=anchor,
                        quantities={sid: 1 for sid in domain}, price_units=units, origin_reference='fixed-dynamic-bundle'),
                        signal_date=decision_date,
                        observed_at=(datetime.fromisoformat(clocks['closes'][decision_date])+timedelta(minutes=1)).isoformat(),
                        session_dates=history_days, session_close_times=dict(closes={day: clocks['closes'][day] for day in history_days},
                        review_reference=clocks['review_reference']), histories=histories))

    return builder
