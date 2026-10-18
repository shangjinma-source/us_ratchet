"""Isolated R1/R2 research composition over unchanged V2/provider/open book."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from backtest.current_quantity_v2_daily_next_open import drawdown_summary
from backtest.current_quantity_v2_next_open_book import run_next_open_book
from backtest.current_quantity_v2_risk_overlays import volatility20_target20, sma20_target
from backtest.return_priority_monthly_quantity_provider_v4 import build_monthly_quantity_provider_v4
from data.current_research_capital_decision_v2 import decide_quantity_v2_for_account


def run_risk_next_open(*, policy, assembled, ohlc, initial_cash, fee_bps,
                       slippage_bps, history_resolver, progress=None):
    if policy not in ('R1', 'R2'):
        raise ValueError('EXPLICIT_R1_OR_R2_REQUIRED')
    audit = []
    selection_attempts = []

    def overlay(day, target, monthly):
        count = 21 if policy == 'R1' else 20
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
        function = volatility20_target20 if policy == 'R1' else sma20_target
        risk = function(signal_date=day, **inputs)
        if any(sid not in target or type(q) is not int or q < 0 or q > target[sid]
               for sid, q in risk['target_quantities'].items()):
            raise ValueError('OVERLAY_EXCEEDS_MONTHLY_TARGET')
        return risk

    def monthly_decide(**kwargs):
        raw = decide_quantity_v2_for_account(**kwargs)
        selection_attempts.append(deepcopy(raw))
        if policy == 'R2' or raw.get('target_quantities') is None:
            return raw
        # Provider freezes this scaled target. Its future split/identity
        # migration operates on the scaled units, not the original selection.
        risk = overlay(kwargs['decision_date'], raw['target_quantities'], kwargs['decision_date'])
        result = deepcopy(raw)
        result.update(target_quantities=deepcopy(risk['target_quantities']),
                      raw_v2_selection=deepcopy(raw), risk_overlay=deepcopy(risk),
                      overlay_execution_target=deepcopy(risk['target_quantities']),
                      base_decision_id=raw['decision_id'],
                      base_search_metrics_scope='UNSCALED_V2_ONLY_NOT_OVERLAY_OBJECTIVE',
                      target_policy='R1_MONTHLY_SCALED_FREEZE')
        result['overlay_decision_id'] = hashlib.sha256(json.dumps(
            dict(base_decision_id=raw['decision_id'], risk=risk), sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()
        return result

    provider = build_monthly_quantity_provider_v4(session_dates=assembled['session_dates'],
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
            if policy == 'R2':
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
    result.update(policy=policy, provider_audit=audit, raw_selection_attempts=selection_attempts,
                  drawdown=drawdown_summary(equity),
                  research_only=True, performance_validated=False, pullback_performance=False,
                  total_return=str(Fraction(equity[-1]['equity']) / Fraction(str(initial_cash)) - 1)
                  if result['status'] == 'COMPLETE' else None)
    return result
