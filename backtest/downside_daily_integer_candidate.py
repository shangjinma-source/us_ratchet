"""Exact common-denominator daily return arithmetic; no candidate generation."""
from fractions import Fraction
from math import lcm
import sys


class ExactDailyReturnIntegers:
    def __init__(self, *, prices, equity, stock_returns):
        capital=Fraction(equity)
        if capital<=0 or set(prices)!=set(stock_returns) or not prices:
            raise ValueError('COMMON_DOMAIN_AND_POSITIVE_EQUITY_REQUIRED')
        marks={s:Fraction(p) for s,p in prices.items()}
        if any(p<=0 for p in marks.values()):raise ValueError('POSITIVE_PRICES_REQUIRED')
        size=len(next(iter(stock_returns.values())))
        if size!=252 or any(len(row)!=size for row in stock_returns.values()):
            raise ValueError('252_COMMON_ORDERED_RETURNS_REQUIRED')
        returns={s:tuple(Fraction(x) for x in row) for s,row in stock_returns.items()}
        if any(x<=-1 for row in returns.values() for x in row):raise ValueError('POSITIVE_GROSS_REQUIRED')
        self.domain=frozenset(prices);self.rows=[]
        for index in range(size):
            coefficients={s:marks[s]*returns[s][index]/capital for s in marks}
            denominator=lcm(*(x.denominator for x in coefficients.values()))
            integers={s:x.numerator*(denominator//x.denominator) for s,x in coefficients.items()}
            self.rows.append((denominator,integers))
        self.diagnostics=dict(max_denominator_bits=max(d.bit_length() for d,_ in self.rows),
            max_coefficient_bits=max(abs(v).bit_length() for _,row in self.rows for v in row.values()),
            integer_payload_bytes=sum(sys.getsizeof(d)+sum(sys.getsizeof(v) for v in row.values()) for d,row in self.rows),
            container_bytes=sys.getsizeof(self.rows)+sum(sys.getsizeof(pair)+sys.getsizeof(pair[1]) for pair in self.rows),
            securities=len(prices),days=size)

    def portfolio_returns(self, quantities):
        if type(quantities)is not dict or any(s not in self.domain or type(q)is not int or q<0 for s,q in quantities.items()):
            raise ValueError('NONNEGATIVE_INTEGER_COMMON_DOMAIN_REQUIRED')
        active=[(s,q) for s,q in quantities.items() if q]
        return [Fraction(sum(q*integers[s] for s,q in active),denominator) for denominator,integers in self.rows]
