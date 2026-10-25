"""Exploratory fixed9+20 filter; reuse strict completed20 evidence validation."""
from copy import deepcopy
from fractions import Fraction
from backtest.partial_trend_exposure import partial_sma20_target


def ma9_sma20_half_target(**kwargs):
    result = deepcopy(partial_sma20_target(**kwargs))
    for sid, diagnostic in result['diagnostics'].items():
        rows = kwargs['histories'][sid]['closes']
        # The preceding existing validator requires the exact completed20 window.
        if len(rows) != 20:
            raise ValueError('EXACT20_REQUIRED_FOR_MA9_SUFFIX')
        average9 = sum((Fraction(str(row['close'])) for row in rows[-9:]), Fraction(0)) / 9
        on20 = diagnostic['on']
        on9 = Fraction(diagnostic['close']) > average9
        diagnostic.update(sma9=str(average9), on_sma20=on20, on_sma9=on9, on=on20 and on9)
        ceiling = diagnostic['monthly_ceiling']
        result['target_quantities'][sid] = ceiling if diagnostic['on'] else ceiling // 2
    result['policy'] = 'SMA9_AND_SMA20_HALF_OFF_EXPLORATORY'
    return result
