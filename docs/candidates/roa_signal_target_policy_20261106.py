"""Build once per admitted signal event; not an ordinary quote-refresh hook."""
from copy import deepcopy
from fractions import Fraction

from core.strategy_account_difference import require


def build_target_policy(*, signal, account, marks, execution_prices, stopped, pending,
                        strategy_epoch, signal_at, valid_from, valid_until):
    """Caller must authenticate signal, event state and nominal live quotes.

    Returns research-only builder policy. Persist its quantities unchanged for
    cash/quote refresh. Only an admitted monthly/regime event may call again.
    """
    require(type(signal['market_state']['risk_on']) is bool, 'MARKET_STATE_REQUIRED')
    weights={sid:Fraction(w) for sid,w in signal['selected_weights'].items()}
    require(len(weights)<=10 and all(0<w<=Fraction(1,10) for w in weights.values()), 'WEIGHT_CAP')
    require(type(stopped) is set and type(pending) is set, 'EXPLICIT_RISK_STATE_REQUIRED')
    require(account['cash_confirmation_valid'], 'CASH_RECONFIRMATION_REQUIRED')
    holdings=account['shares']
    require(all(type(q) is int and q>=0 for q in holdings.values()), 'INTEGER_HOLDINGS_REQUIRED')
    equity=Fraction(account['total_uninvested_cash'])
    for sid,quantity in holdings.items():
        if not quantity:continue
        require(sid in marks, 'HELD_MARK_REQUIRED')
        require(not isinstance(marks[sid]['price'],bool), 'POSITIVE_MARK_REQUIRED')
        price=Fraction(marks[sid]['price'])
        require(price>0, 'POSITIVE_MARK_REQUIRED')
        equity+=quantity*price
    require(equity>0, 'POSITIVE_TRADABLE_EQUITY_REQUIRED')
    targets={}
    if signal['market_state']['risk_on']:
        for sid,weight in weights.items():
            if sid in stopped:continue
            require(sid in execution_prices, 'EXECUTION_PRICE_REQUIRED')
            require(not isinstance(execution_prices[sid],bool), 'POSITIVE_EXECUTION_PRICE_REQUIRED')
            price=Fraction(execution_prices[sid])
            require(price>0, 'POSITIVE_EXECUTION_PRICE_REQUIRED')
            # Same 5bp sizing reserve as integer historical OPEN allocation.
            quantity=int(equity*weight/(price*Fraction(2001,2000)))
            if sid in pending:quantity=min(quantity,holdings.get(sid,0))
            targets[sid]=quantity
    return dict(strategy_epoch=strategy_epoch,weights=deepcopy(signal['selected_weights']),
        target_quantities=targets,signal_at=signal_at,valid_from=valid_from,valid_until=valid_until)
