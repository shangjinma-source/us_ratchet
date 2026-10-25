"""Independent fixed MA9+SMA20 half-exposure exploration; sealed baseline unchanged."""
from copy import deepcopy
from fractions import Fraction
from datetime import datetime
from zoneinfo import ZoneInfo
from backtest.current_quantity_v2_daily_next_open import drawdown_summary
from backtest.current_quantity_v2_next_open_book import run_next_open_book
from backtest.ma9_sma20_half import ma9_sma20_half_target
from backtest.continuous_guided_cost_monthly_provider import build_cost_monthly_quantity_provider
from backtest.continuous_guided_account_decision import decide_continuous_guided_for_account, VERSION


def run_cost_ma9_sma20_half_next_open(*, assembled, ohlc, initial_cash, fee_bps,
                       slippage_bps, history_resolver, progress=None):
    policy = 'CONTINUOUS32_MA9_SMA20_HALF_RESEARCH'
    if (str(fee_bps), str(slippage_bps)) not in {('0', '5'), ('1', '10')}:
        raise ValueError('DECLARED_COST_SCENARIO_REQUIRED')
    if any(str(plan['search_arguments']['fee_bps']) != str(fee_bps) for plan in assembled['monthly_inputs']):
        raise ValueError('MONTHLY_EXECUTION_FEE_MISMATCH')
    audit = []
    selection_attempts = []
    selection_account_states = []

    def overlay(day, target, monthly):
        count = 20
        inputs = deepcopy(history_resolver(decision_date=day,
            target_quantities=deepcopy(target), monthly_decision_date=monthly, count=count))
        observed = datetime.fromisoformat(inputs['observed_at'])
        if observed.tzinfo is None or observed.utcoffset() is None or observed.astimezone(ZoneInfo('America/New_York')).date().isoformat() != day:
            raise ValueError('OBSERVATION_NOT_DECISION_DAY')
        base = inputs['base_target']
        if base['quantities'] != target or base['monthly_decision_date'] != monthly:
            raise ValueError('RESOLVER_TARGET_MISMATCH')
        # Calendar future entries are irrelevant to this decision; histories
        # themselves must already be exact completed windows, never repaired.
        inputs['session_dates'] = [session for session in inputs['session_dates'] if session <= day]
        for sid, quantity in target.items():
            if not quantity:
                continue
            rows = inputs['histories'][sid]['closes']
            if not rows or rows[-1]['date'] != day:
                raise ValueError('HISTORY_LAST_SESSION_MISMATCH')
            if Fraction(str(rows[-1]['close'])) != Fraction(str(assembled['close_prices'][sid][day])):
                raise ValueError('HISTORY_CURRENT_NOMINAL_UNIT_MISMATCH')
        function = ma9_sma20_half_target
        risk = function(signal_date=day, **inputs)
        if any(sid not in target or type(q) is not int or q < 0 or q > target[sid]
               for sid, q in risk['target_quantities'].items()):
            raise ValueError('OVERLAY_EXCEEDS_MONTHLY_TARGET')
        return risk

    def monthly_decide(**kwargs):
        state = deepcopy(kwargs['account_state'])
        selection_account_states.append(deepcopy(kwargs))
        if progress is not None:
            progress(dict(event='MONTHLY_SEARCH_STARTED',decision_date=kwargs['decision_date'],account_state=state))
        raw = decide_continuous_guided_for_account(**kwargs)
        if progress is not None:
            progress(dict(event='MONTHLY_SEARCH_FINISHED',decision_date=kwargs['decision_date'],decision_id=raw.get('decision_id')))
        selection_attempts.append(deepcopy(raw))
        return raw

    provider = build_cost_monthly_quantity_provider(session_dates=assembled['session_dates'],
        monthly_inputs=assembled['monthly_inputs'], close_prices=assembled['close_prices'],
        actions=assembled['provider_actions'], decide=monthly_decide)

    def callback(**kwargs):
        result = None
        try:
            result = provider(**kwargs)
            if result['status'] != 'READY' or result.get('action') == 'WAIT_POST_ACTION_MARK':
                audit.append(deepcopy(result))
                return result
            ceiling = deepcopy(result['target_shares'])
            risk = None
            target = ceiling
            risk = overlay(kwargs['decision_date'], ceiling, result['target_decision_date'])
            target = risk['target_quantities']
            shares = kwargs['state']['shares']
            orders = []
            for sid in sorted(set(shares) | set(target)):
                delta = target.get(sid, 0) - shares.get(sid, 0)
                if not delta:
                    continue
                mark = Fraction(str(assembled['close_prices'][sid][kwargs['decision_date']]))
                if mark <= 0:
                    raise ValueError('NONPOSITIVE_CURRENT_MARK')
                orders.append(dict(id=policy + ':' + kwargs['decision_date'] + ':' + sid,
                    security_id=sid, side='BUY' if delta > 0 else 'SELL', quantity=abs(delta),
                    decision_date=kwargs['decision_date'], active_date=kwargs['active_date'],
                    decision_mark=str(mark)))
            selected = result.get('selection') or {}
            result = dict(result, orders=orders, target_shares=deepcopy(target),
                monthly_ceiling=ceiling, risk_overlay=risk or selected.get('risk_overlay'),
                reserved_cash='0', unreserved_cash=kwargs['state']['cash'], wait_cash=[],
                action='NEXT_OPEN_RISK_DIFFERENCES' if orders else 'NO_ACTION', time_in_force='NEXT_OPEN_MODEL')
        except (ValueError, KeyError, TypeError, ZeroDivisionError, AttributeError) as error:
            result = dict(status='BLOCKED', orders=[], reason=dict(code='RISK_HISTORY_OR_OVERLAY_UNAVAILABLE',
                detail=str(error)), underlying_provider=deepcopy(result), research_only=True)
        audit.append(deepcopy(result))
        if progress is not None:
            progress(dict(decision_date=kwargs['decision_date'], status=result['status']))
        return result

    result = run_next_open_book(session_dates=assembled['session_dates'], ohlc=ohlc,
        initial_cash=initial_cash, fee_bps=fee_bps, slippage_bps=slippage_bps,
        order_provider=callback, events=assembled['actions'],
        cash_stock_merger_events=assembled['cash_stock_merger_events'],
        fractional_settlements=assembled['fractional_settlements'],
        price_source_references=assembled['price_source_references'],
        distribution_events=assembled['distribution_events'],
        distribution_fractional_cash_values=assembled['distribution_fractional_cash_values'],
        account_model=assembled.get('account_model'))
    equity = [dict(date=assembled['session_dates'][0], equity=str(initial_cash))] + result['daily_ledger']
    result.update(selection_method=VERSION, continuous_iterations=32, policy=policy, provider_audit=audit, raw_selection_attempts=selection_attempts, selection_account_states=selection_account_states,
                  drawdown=drawdown_summary(equity),
                  research_only=True, performance_validated=False, pullback_performance=False,
                  total_return=str(Fraction(equity[-1]['equity']) / Fraction(str(initial_cash)) - 1)
                  if result['status'] == 'COMPLETE' else None)
    return result
