"""Conditional daily execution experiment; no production or minute-limit semantics.

Selection sees only completed-close state. Opening prices may ration execution,
never change the selected target. Exposed unsupported actions stop the series.
"""
from copy import deepcopy
from fractions import Fraction
from backtest.continuous_guided_account_decision import decide_continuous_guided_for_account, VERSION
from backtest.return_priority_monthly_quantity_provider_v4 import build_monthly_quantity_provider_v4
from backtest.current_quantity_v2_next_open_book import run_next_open_book


def number(value):
    if isinstance(value, bool):
        raise ValueError('BOOLEAN_NUMBER')
    value = Fraction(str(value))
    if value < 0:
        raise ValueError('NEGATIVE_NUMBER')
    return value


def drawdown_summary(equities):
    peak = number(equities[0]['equity'])
    peak_day = equities[0]['date']
    worst = Fraction(0)
    trough = peak_day
    underwater_start = None
    longest = 0
    completed = []
    for index, row in enumerate(equities):
        value = number(row['equity'])
        if value >= peak:
            if underwater_start is not None:
                completed.append(index - underwater_start)
            underwater_start = None
            peak, peak_day = value, row['date']
        else:
            if underwater_start is None:
                underwater_start = index
            longest = max(longest, index - underwater_start + 1)
            loss = 1 - value / peak if peak else Fraction(0)
            if loss > worst:
                worst, trough = loss, row['date']
    return dict(maximum_close_drawdown=str(worst), trough_date=trough,
                longest_underwater_observations=longest,
                recovered_at_end=underwater_start is None,
                current_underwater_observations=0 if underwater_start is None else len(equities)-underwater_start,
                completed_recovery_observations=completed)


def run_continuous_guided_next_open(*, assembled, ohlc, initial_cash, fee_bps, slippage_bps, progress=None):
    """Use V2 plus 32 continuous proposal steps and V4 actions, with open execution.

    Assembled comes from assemble_monthly_execution_inputs_v4 with current V2
    source pins explicitly added by the caller. No files or network are read.
    """
    selection_account_states=[]
    def decide(**arguments):
        selection_account_states.append(deepcopy(arguments))
        if progress is not None:progress(dict(stage='MONTHLY_SEARCH_STARTED',decision_date=arguments['search_arguments']['decision_date'],account_state=deepcopy(arguments['account_state'])))
        result=decide_continuous_guided_for_account(**arguments)
        if progress is not None:progress(dict(stage='MONTHLY_SEARCH_COMPLETED',decision_date=arguments['search_arguments']['decision_date'],target=result.get('target_quantities')))
        return result
    provider = build_monthly_quantity_provider_v4(
        session_dates=assembled['session_dates'], monthly_inputs=assembled['monthly_inputs'],
        close_prices=assembled['close_prices'], actions=assembled['provider_actions'],
        decide=decide)
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

    result = run_next_open_book(session_dates=assembled['session_dates'],ohlc=ohlc,
        initial_cash=initial_cash,fee_bps=fee_bps,slippage_bps=slippage_bps,
        order_provider=full_difference,events=assembled['actions'],
        cash_stock_merger_events=assembled['cash_stock_merger_events'],
        fractional_settlements=assembled['fractional_settlements'],
        price_source_references=assembled['price_source_references'],
        distribution_events=assembled['distribution_events'],
        distribution_fractional_cash_values=assembled['distribution_fractional_cash_values'],
        account_model=assembled.get('account_model'))
    equity=[dict(date=assembled['session_dates'][0],equity=str(number(initial_cash)))]+result['daily_ledger']
    result.update(selection_account_states=selection_account_states,provider_audit=audit,drawdown=drawdown_summary(equity),
        selection_method=VERSION,
        pullback_performance=False, independent_oos=False, point_in_time_certified=False,
        total_return=str(number(equity[-1]['equity'])/number(initial_cash)-1) if result['status']=='COMPLETE' else None)
    return result


