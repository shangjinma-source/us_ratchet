"""Research-only market gate after unchanged V27 monthly exit state."""
from copy import deepcopy
from decimal import Decimal
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter


class Ema20MarketAdapter(MonthlyExitCoreResearchAdapter):
    def __init__(self, *, signals, month_ends, mode, actions=()):
        super().__init__(actions)
        if mode not in ('daily', 'monthly_reentry'):
            raise ValueError('UNKNOWN_MARKET_REENTRY_MODE')
        self.signals=deepcopy(signals)
        self.month_ends=frozenset(month_ends)
        self.mode=mode
        self.market_on=None
        self.market_audit=[]

    def apply(self, *, day, month, target, closes, adjustments=()):
        signal=self.signals.get(day)
        if signal is None:
            raise ValueError('QQQ_COMPLETED_SIGNAL_REQUIRED')
        close,ema=Decimal(signal['close']),Decimal(signal['ema'])
        if not close.is_finite() or not ema.is_finite() or min(close,ema)<=0:
            raise ValueError('POSITIVE_FINITE_QQQ_SIGNAL_REQUIRED')
        raw_on=close>ema
        if type(signal['on']) is not bool or signal['on']!=raw_on:
            raise ValueError('QQQ_SIGNAL_COMPARISON_MISMATCH')
        next_on=self.market_on
        if self.mode=='daily' or next_on is None:
            next_on=raw_on
        elif not raw_on:
            next_on=False
        elif day in self.month_ends:
            next_on=True
        # Never send the zeroed market target into the monthly exit core.
        # It must keep original ceilings, peaks and month-local exit locks.
        effective,diagnostics=super().apply(day=day,month=month,target=deepcopy(target),
                                           closes=closes,adjustments=adjustments)
        gated=effective if next_on else {sid:0 for sid in effective}
        self.market_on=next_on
        review=dict(signal_date=day,mode=self.mode,market_on=next_on,
                    qqq_above_ema20=raw_on,monthly_ceiling=deepcopy(target),
                    original_exit_effective=deepcopy(effective),effective=deepcopy(gated))
        self.market_audit.append(review)
        diagnostics['market_gate']=deepcopy(review)
        return gated,diagnostics
