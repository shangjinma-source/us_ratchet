"""Fixed target cap on total tradable equity, residual stays cash."""
from fractions import Fraction as F
CAP=F(1,5)
def capped(quantities,arguments):
 equity=F(arguments['entered_cash'])
 if equity<=0:raise ValueError('POSITIVE_TRADABLE_EQUITY_REQUIRED')
 if any(s not in arguments['prices'] or type(q) is not int or q<0 for s,q in quantities.items()):raise ValueError('INVALID_INTEGER_QUANTITIES')
 prices={s:F(arguments['prices'][s]) for s in quantities}
 if any(p<=0 for p in prices.values()):raise ValueError('POSITIVE_PRICE_REQUIRED')
 result={s:min(q,int(equity*CAP//prices[s])) for s,q in quantities.items()}
 return {s:q for s,q in result.items() if q}
