"""Independent adaptive V2 premium execution branch; no frozen B0 targets."""
from copy import deepcopy
from data.current_research_capital_decision_v2 import decide_quantity_v2_for_account
from backtest.return_priority_monthly_quantity_provider_v4 import build_monthly_quantity_provider_v4
from backtest.current_quantity_v2_daily_sell_book import run_daily_sell_book
from backtest.current_quantity_v2_daily_next_open import number,drawdown_summary

def run_adaptive_daily_premium(*, assembled, ohlc, initial_cash, fee_bps, slippage_bps, progress=None, decide=decide_quantity_v2_for_account):
    """Use unchanged V2 selection and V4 target/action state, with open execution.

    Assembled comes from assemble_monthly_execution_inputs_v4 with current V2
    source pins explicitly added by the caller. No files or network are read.
    """
    if number(fee_bps)!=0 or number(slippage_bps)!=0:
        raise ValueError('ONLY_EXPLICIT_ZERO_COST_EXPERIMENT_SUPPORTED')
    selection_calls = []
    def tracked_decide(**kwargs):
        day=kwargs['decision_date'];state=deepcopy(kwargs['account_state'])
        if progress is not None:progress(dict(event='MONTHLY_SEARCH_STARTED',decision_date=day,account_state=state))
        try:
            selected=decide(**kwargs)
        except Exception as error:
            if progress is not None:progress(dict(event='MONTHLY_SEARCH_FAILED',decision_date=day,error_type=type(error).__name__))
            raise
        selection_calls.append(dict(decision_date=day,account_state=state))
        if progress is not None:progress(dict(event='MONTHLY_SEARCH_FINISHED',decision_date=day,decision_id=selected.get('decision_id')))
        return selected
    provider = build_monthly_quantity_provider_v4(
        session_dates=assembled['session_dates'], monthly_inputs=assembled['monthly_inputs'],
        close_prices=assembled['close_prices'], actions=assembled['provider_actions'],
        decide=tracked_decide)
    audit = []

    def full_difference(**kwargs):
        result = provider(**kwargs)
        if progress is not None:
            progress(dict(decision_date=kwargs['decision_date'],active_date=kwargs['active_date'],
                          status=result['status'],selection_completed=result.get('selection') is not None))
        if result['status'] != 'READY' or result.get('action') == 'WAIT_POST_ACTION_MARK':
            audit.append(deepcopy(result))
            return result
        # Preserve target evolution/rights guards, discard legacy prior-close
        # cash clipping. This adapter sees no next-session price.
        shares = kwargs['state']['shares']
        target = result['target_shares']
        orders = []
        for sid in sorted(set(shares) | set(target)):
            delta = target.get(sid,0)-shares.get(sid,0)
            if not delta: continue
            mark = number(assembled['close_prices'][sid][kwargs['decision_date']])
            orders.append(dict(id='nextopen:'+kwargs['decision_date']+':'+sid,
                security_id=sid, side='BUY' if delta>0 else 'SELL',quantity=abs(delta),
                decision_date=kwargs['decision_date'],active_date=kwargs['active_date'],decision_mark=str(mark)))
        result = dict(result, orders=orders, reserved_cash='0',
                      unreserved_cash=kwargs['state']['cash'], wait_cash=[],
                      action='NEXT_OPEN_TARGET_DIFFERENCES' if orders else 'NO_ACTION',
                      time_in_force='NEXT_OPEN_MODEL',
                      sizing_note='Open cash rationing occurs only in execution; no proceeds reserved at Close.')
        audit.append(deepcopy(result))
        return result

    result = run_daily_sell_book(mode='PREMIUM_DAY',session_dates=assembled['session_dates'],ohlc=ohlc,
        initial_cash=initial_cash,fee_bps=fee_bps,slippage_bps=slippage_bps,
        order_provider=full_difference,events=assembled['actions'],
        cash_stock_merger_events=assembled['cash_stock_merger_events'],
        fractional_settlements=assembled['fractional_settlements'],
        price_source_references=assembled['price_source_references'],
        distribution_events=assembled['distribution_events'],
        distribution_fractional_cash_values=assembled['distribution_fractional_cash_values'],
        account_model=assembled.get('account_model'))
    equity=[dict(date=assembled['session_dates'][0],equity=str(number(initial_cash)))]+result['daily_ledger']
    result.update(provider_audit=audit,selection_account_states=selection_calls,
                  experiment_scope='ADAPTIVE_V2_DAILY_PREMIUM_RESEARCH_NOT_CURRENT_MINUTE_POLICY',
                  drawdown=drawdown_summary(equity),
        selection_method='EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2',
        pullback_performance=False, independent_oos=False, point_in_time_certified=False,
        total_return=str(number(equity[-1]['equity'])/number(initial_cash)-1) if result['status']=='COMPLETE' else None)
    return result


