"""Cent-grid last-price limit for approved USD stocks >= $1 only."""
from fractions import Fraction


def cent_last_price_limit(last_price,phase):
    if phase not in ('OPEN','CLOSE'):raise ValueError('LIMIT_PHASE_INVALID')
    if type(last_price) not in (str,int,Fraction):raise ValueError('EXACT_LIMIT_PRICE_REQUIRED')
    price=Fraction(last_price)
    if price<1:raise ValueError('CENT_POLICY_REQUIRES_PRICE_AT_LEAST_ONE_DOLLAR')
    cents=(price.numerator*200+price.denominator)//(price.denominator*2)
    value=f'{cents//100}.{cents%100:02d}'
    return {'buy':value,'sell':value}
