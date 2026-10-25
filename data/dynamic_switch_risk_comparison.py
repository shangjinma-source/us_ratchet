"""Research comparison preserving the existing monthly exit epoch.

Full history replay admits newly considered securities without resetting old
peaks. No state persistence, orders, or automatic switching threshold.
"""
from fractions import Fraction
from core.monthly_peak_exit import advance_monthly_exit
from core.strategy_switch_comparison import compare_switch
from data.monthly_peak_exit_history import monthly_exit_observations


def compare_with_monthly_exit(*, account_id, prior_risk_state, history_inputs,
                              cash, holdings, candidate, prices, scenarios,
                              scenario_dates, slippage_bps, eligible_reentries=None,
                              executed_reentries=()):
    anchor = history_inputs['base_target']['monthly_decision_date']
    day = history_inputs['signal_date']
    if prior_risk_state is not None:
        if prior_risk_state['account_id'] != account_id or prior_risk_state['decision_date'] != anchor:
            raise ValueError('DYNAMIC_SELECTION_CANNOT_RESET_RISK_EPOCH')
        if prior_risk_state['session_date'] > day:
            raise ValueError('RISK_CLOCK_BACKWARDS')
    domain = set(holdings) | set(candidate)
    if prior_risk_state:
        domain |= set(prior_risk_state['peaks'])
    if not domain <= set(history_inputs['histories']):
        raise ValueError('HELD_CANDIDATE_AND_TRACKED_HISTORY_REQUIRED')
    observations = monthly_exit_observations(**history_inputs)
    reentries = {}
    seen_execution_ids = set()
    for entry in executed_reentries:
        sid, entry_day = entry['security_id'], entry['date']
        if (not entry['execution_id'] or entry['execution_id'] in seen_execution_ids
                or not anchor <= entry['exit_date'] < entry_day <= day
                or sid not in domain or Fraction(entry['price']) <= 0
                or entry_day not in {row['session_date'] for row in observations}):
            raise ValueError('INVALID_EXECUTED_REENTRY')
        key = (entry_day, sid)
        if key in reentries:
            raise ValueError('DUPLICATE_REENTRY_SESSION')
        reentries[key] = entry
        seen_execution_ids.add(entry['execution_id'])
    state = None
    checked_prior = prior_risk_state is None
    for row in observations:
        for sid in row['closes']:
            entry = reentries.get((row['session_date'], sid))
            if entry is not None:
                if state is None or sid not in state['exited']:
                    raise ValueError('REENTRY_REQUIRES_PRIOR_EXIT_LATCH')
                if entry['unit_id'] != row['unit_ids'][sid]:
                    raise ValueError('REENTRY_FILL_UNIT_MISMATCH')
                state['peaks'][sid] = str(Fraction(entry['price']))
                state['exited'].remove(sid)
        outcome = advance_monthly_exit(state=state, account_id=account_id,
            decision_date=anchor, session_date=row['session_date'], closes=row['closes'],
            unit_ids=row['unit_ids'], baseline_targets={sid: 0 for sid in row['closes']})
        state = outcome['state']
        if prior_risk_state and row['session_date'] == prior_risk_state['session_date']:
            old_domain = set(prior_risk_state['peaks'])
            for key in ('peaks', 'last_closes', 'unit_ids'):
                if any(state[key][sid] != prior_risk_state[key][sid] for sid in old_domain):
                    raise ValueError('PRIOR_RISK_HISTORY_CHANGED')
            if set(state['exited']) & old_domain != set(prior_risk_state['exited']):
                raise ValueError('PRIOR_EXIT_HISTORY_CHANGED')
            checked_prior = True
    if not checked_prior:
        raise ValueError('PRIOR_RISK_SESSION_MISSING')
    if any(sid not in prices or Fraction(prices[sid]) != Fraction(state['last_closes'][sid]) for sid in domain):
        raise ValueError('RISK_COMPARISON_PRICE_MISMATCH')
    exited = set(state['exited'])
    allowed = set()
    for sid, exit_date in (eligible_reentries or {}).items():
        if not anchor <= exit_date < day or holdings.get(sid, 0):
            raise ValueError('REENTRY_REQUIRES_LATER_CLOSE_AND_FLAT_POSITION')
        if sid in exited:
            allowed.add(sid)
    arguments = dict(cash=cash, holdings=holdings, prices=prices, scenarios=scenarios,
                     scenario_dates=scenario_dates, decision_date=day, slippage_bps=slippage_bps)
    retained = {sid: 0 if sid in exited else q for sid, q in holdings.items()}
    proposed = {sid: 0 if sid in exited and sid not in allowed else q for sid, q in candidate.items()}
    baseline = compare_switch(candidate=retained, **arguments)
    alternative = compare_switch(candidate=proposed, **arguments)
    ranking = 'UNAFFORDABLE'
    if baseline['candidate'] is not None and alternative['candidate'] is not None:
        left = Fraction(alternative['candidate']['product'])
        right = Fraction(baseline['candidate']['product'])
        ranking = 'SWITCH_HIGHER' if left > right else 'RETAIN_HIGHER' if left < right else 'TIE'
    return dict(risk_state=state, retain_targets=retained, candidate_targets=proposed,
                reentry_candidates=sorted(allowed & set(candidate)),
                retain_comparison=baseline, candidate_comparison=alternative, ranking=ranking,
                trigger_defined=False, production_changes=False)
