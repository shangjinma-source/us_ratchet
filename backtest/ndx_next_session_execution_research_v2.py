"""Next-session close research with explicit split-only share accounting."""
import hashlib
import math
from pathlib import Path
from collections.abc import Mapping

import numpy as np
import pandas as pd

from backtest.ndx_integer_allocation_research import search_integer_allocation_domain, RISK_FIELDS
from backtest.ndx_whole_lot_rebalance import _constraint_snapshot
from backtest.ndx_split_accounting_research import apply_split_session

_PATHS = (Path(__file__).resolve(), Path(__file__).with_name('ndx_integer_allocation_research.py'),
          Path(__file__).with_name('ndx_whole_lot_rebalance.py'),
          Path(__file__).with_name('ndx_split_accounting_research.py'))


def _hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in _PATHS}


_LOADED_SOURCES = _hashes()


def _fill_frozen_plan(plan, shares, cash, marks, minimum_cash_buffer_usd):
    """No optimization here: either fill every frozen delta or reject all."""
    baseline_matches = shares == plan['baseline_shares'] and cash == plan['baseline_cash_usd']
    delta = plan['delta_shares']
    notional = sum(abs(delta[t])*marks[t] for t in shares)
    fees = notional*plan['transaction_cost_bps']/10000.
    after_cash = cash-sum(delta[t]*marks[t] for t in shares)-fees
    if not all(math.isfinite(x) for x in (notional, fees, after_cash)):
        raise ValueError('Fill arithmetic overflow')
    status = ('REJECTED_ACCOUNT_BASELINE_DRIFT' if not baseline_matches else
              'REJECTED_INSUFFICIENT_CASH_AT_FILL' if after_cash < minimum_cash_buffer_usd-1e-9 else
              'FILLED' if any(delta.values()) else 'NO_TRADE_REQUIRED')
    accepted = status in ('FILLED', 'NO_TRADE_REQUIRED')
    return dict(status=status, decision_date=plan['decision_date'],
        frozen_delta_shares=dict(delta), fill_prices=dict(marks),
        baseline_matched=baseline_matches, pretrade_shares=dict(shares), pretrade_cash_usd=cash,
        estimated_fill_fees_usd=fees, hypothetical_posttrade_cash_usd=after_cash,
        fees_usd=fees if accepted else 0., trade_notional_usd=notional if accepted else 0.,
        posttrade_shares={t: shares[t]+delta[t] for t in shares} if accepted else dict(shares),
        posttrade_cash_usd=after_cash if accepted else cash,
        model='NEXT_SESSION_CLOSE_SIMULATION', quantity_reoptimized_at_fill=False)


def simulate_next_session_execution_research_v2(*, prices, execution_calendar, schedule, corporate_actions,
        initial_cash, initial_shares, minimum_cash_buffer_usd, transaction_cost_bps,
        risk_chain_by_ticker, constraints, domain_radius,
        max_evaluations_per_rebalance, selection_policy):
    """Execute yesterday, mark risk, then freeze today's explicit scheduled plan.

    The caller must supply the complete intended exchange-session calendar.
    Calendar equality detects missing price rows, but does not authenticate an
    externally supplied calendar. No automatic drift-triggered trading occurs.
    """
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    sources = _hashes()
    require(sources == _LOADED_SOURCES, 'Sources changed since import')
    require(selection_policy in ('TRACKING_FIRST', 'FEES_FIRST'), 'Explicit selection policy required')
    require(type(domain_radius) is int and domain_radius >= 0, 'Invalid domain radius')
    require(type(max_evaluations_per_rebalance) is int and max_evaluations_per_rebalance > 0, 'Invalid search budget')
    require(isinstance(prices, pd.DataFrame) and not prices.empty and prices.columns.is_unique,
            'Invalid price panel')
    require(all(isinstance(t, str) and t and t == t.strip() for t in prices), 'Invalid ticker')
    names = sorted(prices)
    require(isinstance(execution_calendar, pd.DatetimeIndex) and len(execution_calendar) > 0
            and execution_calendar.tz is None and not execution_calendar.hasnans
            and execution_calendar.is_unique and execution_calendar.is_monotonic_increasing
            and execution_calendar.equals(execution_calendar.normalize()), 'Invalid declared execution calendar')
    require(isinstance(prices.index, pd.DatetimeIndex) and prices.index.equals(execution_calendar),
            'Price rows must exactly match complete declared execution calendar')
    values = prices.to_numpy()
    require(all(isinstance(v, (int, float, np.integer, np.floating))
                and not isinstance(v, (bool, np.bool_)) for v in values.flat)
            and np.isfinite(values.astype(float)).all() and (values.astype(float) > 0).all(), 'Invalid prices')
    require(isinstance(initial_shares, Mapping) and set(initial_shares) == set(names)
            and all(type(v) is int and v >= 0 for v in initial_shares.values()), 'Invalid initial shares')
    require(isinstance(constraints, Mapping) and set(constraints) == RISK_FIELDS
            and all(type(v) in (int, float) and math.isfinite(v) and 0 < v <= 1 for v in constraints.values())
            and constraints['min_single_weight'] <= constraints['max_single_weight'], 'Invalid risk contract')
    require(isinstance(risk_chain_by_ticker, Mapping) and set(risk_chain_by_ticker) == set(names)
            and all(isinstance(v, str) and v and v == v.strip() for v in risk_chain_by_ticker.values()),
            'Invalid risk identities')
    for value in (initial_cash, minimum_cash_buffer_usd, transaction_cost_bps):
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0, 'Invalid cash/fee contract')
    require(isinstance(schedule, (list, tuple)) and schedule, 'Explicit nonempty schedule required')
    items = []
    for date, weights in schedule:
        require(isinstance(date, (str, pd.Timestamp)), 'Invalid schedule date')
        date = pd.Timestamp(date)
        require(date in execution_calendar and date.tzinfo is None and date == date.normalize(), 'Schedule date missing')
        require(isinstance(weights, Mapping) and set(weights) == set(names)
                and all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in weights.values())
                and abs(sum(weights.values())-1) <= 1e-10, 'Invalid target weights')
        items.append((date, dict(weights)))
    require([d for d, _ in items] == sorted({d for d, _ in items}), 'Duplicate or unsorted schedule')
    require(type(corporate_actions) in (list, tuple), 'Explicit corporate_actions list required')
    events_by_session = {}
    calendar_strings = {str(d.date()) for d in execution_calendar}
    first_session = str(execution_calendar[0].date())
    for event in corporate_actions:
        require(isinstance(event, dict) and type(event.get('session')) is str
                and event['session'] in calendar_strings, 'Corporate action date outside calendar')
        require(event['session'] != first_session, 'Initial shares must already reflect first-session actions')
        require(type(event.get('ticker')) is str and event['ticker'] in names, 'Corporate action ticker absent')
        events_by_session.setdefault(event['session'], []).append(dict(event))
    # Validate all supplied event schemas, identities and duplicates before any
    # simulation. Zero shares permit validation without inventing entitlements.
    for session, events in events_by_session.items():
        apply_split_session(session=session, shares={t: 0 for t in names},
                            cash_usd=0., pending_plan=None, events=events)
    targets = dict(items)
    shares, cash = dict(initial_shares), float(initial_cash)
    initial_equity = cash+sum(shares[t]*float(prices.iloc[0][t]) for t in names)
    require(math.isfinite(initial_equity) and initial_equity > 0, 'Invalid initial equity')
    daily, decisions, executions = [], [], []
    corporate_action_ledger, cancelled_plans = [], []
    pending = None
    partial = unresolved = False
    for index, date in enumerate(execution_calendar):
        session = str(date.date())
        if session in events_by_session:
            transition = apply_split_session(session=session, shares=shares, cash_usd=cash,
                                              pending_plan=pending, events=events_by_session[session])
            shares, cash, pending = transition['shares'], transition['cash_usd'], transition['pending_plan']
            corporate_action_ledger.append(transition)
            if transition['cancelled_plan'] is not None:
                cancelled_plans.append(dict(session=session, status=transition['pending_plan_status'],
                    cancelled_plan=transition['cancelled_plan'], fees_usd=0., trade_notional_usd=0.))
        marks = {t: float(prices.loc[date, t]) for t in names}
        if pending is not None:
            fill = _fill_frozen_plan(pending, shares, cash, marks, minimum_cash_buffer_usd)
            fill['execution_date'] = str(date.date())
            executions.append(fill)
            shares, cash = dict(fill['posttrade_shares']), fill['posttrade_cash_usd']
            pending = None  # rejection never automatically retries
        notionals = {t: shares[t]*marks[t] for t in names}
        equity = cash+sum(notionals.values())
        require(math.isfinite(equity) and equity > 0, 'Invalid marked equity')
        snapshot = _constraint_snapshot(notionals, risk_chain_by_ticker=risk_chain_by_ticker, **constraints)
        passed = bool(snapshot['constraints_passed'] and min(shares.values()) >= 1
                      and cash >= minimum_cash_buffer_usd-1e-9)
        daily.append(dict(date=str(date.date()), shares=dict(shares), cash_usd=cash,
                          equity_usd=equity, risk_snapshot=snapshot,
                          security_weights={t: notionals[t]/sum(notionals.values())
                                            if sum(notionals.values()) > 0 else 0. for t in names},
                          minimum_one_share_passed=min(shares.values()) >= 1,
                          cash_buffer_passed=cash >= minimum_cash_buffer_usd-1e-9,
                          all_constraints_passed=passed))
        if date not in targets:
            continue
        investable = max(0., equity-minimum_cash_buffer_usd)
        floors = {t: math.floor(investable*targets[date][t]/marks[t]) for t in names}
        domains = {t: sorted(set(range(max(0, floors[t]-domain_radius), floors[t]+domain_radius+1)) | {shares[t]})
                   for t in names}
        search = search_integer_allocation_domain(prices=marks, target_weights=targets[date],
            current_shares=shares, current_cash=cash, transaction_cost_bps=transaction_cost_bps,
            minimum_cash_buffer_usd=minimum_cash_buffer_usd, risk_chain_by_ticker=risk_chain_by_ticker,
            constraints=constraints, share_domains=domains, max_evaluations=max_evaluations_per_rebalance)
        partial |= not search['pareto_complete_within_explicit_domain']
        decision = dict(decision_date=str(date.date()), target_weights=dict(targets[date]),
            decision_prices=marks, baseline_shares=dict(shares), baseline_cash_usd=cash,
            transaction_cost_bps=transaction_cost_bps,
            plan_source='EXPLICIT_SCHEDULE_AND_FINITE_INTEGER_DOMAIN', share_domains=domains,
            finite_domain_size=search['finite_domain_size'], evaluated=search['evaluated'],
            unexamined=search['unexamined'], feasible_evaluated=search['feasible_evaluated'],
            finite_domain_complete=search['pareto_complete_within_explicit_domain'])
        if not search['pareto']:
            unresolved = True
            decision['status'] = 'UNRESOLVED_NO_FEASIBLE_OBSERVED_NO_PLAN'
        else:
            fields = ('total_tracking_error_including_cash', 'fees_usd') if selection_policy == 'TRACKING_FIRST' else ('fees_usd', 'total_tracking_error_including_cash')
            chosen = min(search['pareto'], key=lambda r: (r[fields[0]], r[fields[1]], tuple(r['shares'][t] for t in names)))
            decision.update(target_shares=dict(chosen['shares']),
                delta_shares={t: chosen['shares'][t]-shares[t] for t in names},
                estimated_fees_usd=chosen['fees_usd'], estimated_posttrade_cash_usd=chosen['posttrade_cash_usd'],
                expected_execution_date=str(execution_calendar[index+1].date()) if index+1 < len(execution_calendar) else None,
                status='FROZEN_FOR_NEXT_SESSION' if index+1 < len(execution_calendar) else 'PENDING_OUTSIDE_EVALUATION')
            pending = dict(decision)
        decisions.append(decision)
    fees = sum(e['fees_usd'] for e in executions)
    peak, drawdown = initial_equity, 0.
    for row in daily:
        peak = max(peak, row['equity_usd'])
        drawdown = max(drawdown, 1-row['equity_usd']/peak)
    require(_hashes() == sources, 'Sources changed during simulation')
    return dict(schema='ndx_next_session_execution_research_v2',
        scope='FIXED_TICKER_EXECUTION_SUBPROBLEM_NOT_CARDINALITY_DECISION',
        execution_model='NEXT_SESSION_CLOSE_SIMULATION',
        event_order='APPLY_SPLITS_CANCEL_PENDING_THEN_EXECUTE_MARK_RISK_DECIDE', selection_policy=selection_policy,
        status='UNRESOLVED' if unresolved else 'PARTIAL_SEARCH_PATH' if partial else 'SIMULATION_COMPLETED',
        source_hashes=sources, daily=daily, decisions=decisions, executions=executions,
        date_start=str(execution_calendar[0].date()), date_end=str(execution_calendar[-1].date()),
        domain_radius=domain_radius, max_evaluations_per_rebalance=max_evaluations_per_rebalance,
        constraints=dict(constraints), risk_chain_by_ticker=dict(risk_chain_by_ticker),
        minimum_cash_buffer_usd=minimum_cash_buffer_usd, transaction_cost_bps=transaction_cost_bps,
        pending_plan=pending, any_partial_search=partial, any_unresolved_decision=unresolved,
        corporate_action_ledger=corporate_action_ledger, cancelled_plans=cancelled_plans,
        corporate_action_support='EXPLICIT_SPLITS_ONLY_NO_DIVIDEND_OR_CASH_IN_LIEU',
        corporate_action_evidence_authenticated=False, corporate_action_coverage_verified=False,
        initial_shares_basis='ALREADY_ADJUSTED_FOR_FIRST_SESSION_ACTIONS',
        cancelled_pending_plan_count=len(cancelled_plans),
        trade_execution_count=sum(e['status'] == 'FILLED' for e in executions),
        rejected_execution_count=sum(e['status'].startswith('REJECTED') for e in executions),
        all_days_constraints_passed=all(d['all_constraints_passed'] for d in daily),
        risk_failure_days=sum(not d['all_constraints_passed'] for d in daily),
        initial_equity_usd=initial_equity, terminal_equity_usd=daily[-1]['equity_usd'],
        terminal_cash_usd=cash, terminal_shares=shares, total_fees_usd=fees,
        path_return_net=daily[-1]['equity_usd']/initial_equity-1., path_max_drawdown=drawdown,
        drawdown_initial_peak='PRETRADE_INITIAL_MARKED_EQUITY_INCLUDING_INITIAL_SHARES',
        decision_precedes_fill=True, target_signal_provenance_verified=False,
        signal_timing_verified=False,
        quantity_decision_timing_verified=True,
        execution_fill_model_assumption='ATOMIC_NEXT_SESSION_CLOSE_WITH_SAME_BASKET_SALE_PROCEEDS',
        external_execution_calendar_verified=False, atomic_basket_execution_assumed=True,
        same_basket_sale_proceeds_available_assumed=True, broker_executability_proven=False,
        automatic_drift_trading=False, all_days_future_risk_guaranteed=False,
        global_allocation_optimality_claim_allowed=False, promotion_allowed=False, order_generation_allowed=False)


