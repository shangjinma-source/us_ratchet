"""Exact lexicographic lattice domain, not an investment/action policy.

q1,q2 are positive integers and a*q1+b*q2 <= budget. No IO, market data,
search/risk/account execution, economic quantity cap or policy registration.
Integers and Fraction objects are exact. Decimal strings are canonical plain
notation: no exponent, padding, plus sign, leading zeros or trailing fractional
zeros. A negative budget is mathematically an empty domain, not a withdrawal.
Ranks are zero-based; engineering page limits never change the full domain.
"""
from fractions import Fraction
from math import lcm
import re

MAX_PAGE_SIZE=10000
_DECIMAL=re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?\Z')

def require(ok,message):
    if not ok:raise ValueError(message)

def _rational(value):
    if type(value)is Fraction:return value
    if type(value)is int:return Fraction(value)
    require(type(value)is str and _DECIMAL.fullmatch(value)is not None and value!='-0','Exact Fraction/int or canonical plain decimal required')
    return Fraction(value)

def _integer(value,name,minimum=0):
    require(type(value)is int and value>=minimum,name+' must be an exact integer in range')
    return value

def _domain(a,b,budget):
    a,b,budget=map(_rational,(a,b,budget))
    require(a>0 and b>0,'Both unit costs must be strictly positive')
    scale=lcm(a.denominator,b.denominator,budget.denominator)
    first=int(a*scale);second=int(b*scale);available=int(budget*scale)
    last=max(0,(available-second)//first)
    return first,second,available,last

def _floor_sum(n,modulus,slope,intercept):
    """Sum floor((slope*i+intercept)/modulus), i=0..n-1, nonnegative args.

    Each reciprocal step reduces the Euclidean pair; runtime does not scale
    with n. The caller ensures positive modulus and nonnegative intercept.
    """
    answer=0
    while True:
        quotient,slope=divmod(slope,modulus)
        answer+=n*(n-1)//2*quotient
        quotient,intercept=divmod(intercept,modulus)
        answer+=n*quotient
        top=slope*n+intercept
        if top<modulus:return answer
        n,intercept=divmod(top,modulus)
        modulus,slope=slope,modulus

def _prefix(first,second,available,last,n):
    n=min(n,last)
    if n<=0:return 0
    # Reverse q=1..n, giving slope*i+(available-first*n), i=0..n-1.
    return _floor_sum(n,second,first,available-first*n)

def count_points(*,a,b,budget):
    first,second,available,last=_domain(a,b,budget)
    return _prefix(first,second,available,last,last)

def prefix_count(*,a,b,budget,max_q1):
    """Number of valid pairs whose first coordinate is <= max_q1."""
    _integer(max_q1,'max_q1')
    return _prefix(*_domain(a,b,budget),max_q1)

def rank_point(*,a,b,budget,q1,q2):
    _integer(q1,'q1',1);_integer(q2,'q2',1)
    first,second,available,last=_domain(a,b,budget)
    require(first*q1+second*q2<=available,'Point outside complete budget domain')
    return _prefix(first,second,available,last,q1-1)+q2-1

def _unrank(first,second,available,last,total,rank):
    require(rank<total,'Rank outside complete budget domain')
    lo,hi=1,last
    while lo<hi:
        mid=(lo+hi)//2
        if _prefix(first,second,available,last,mid)>rank:hi=mid
        else:lo=mid+1
    return lo,rank-_prefix(first,second,available,last,lo-1)+1

def unrank_point(*,a,b,budget,rank):
    _integer(rank,'rank')
    first,second,available,last=_domain(a,b,budget)
    total=_prefix(first,second,available,last,last)
    return _unrank(first,second,available,last,total,rank)

def page_points(*,a,b,budget,start,limit):
    _integer(start,'start');_integer(limit,'limit',1)
    require(limit<=MAX_PAGE_SIZE,'Engineering page size exceeded; domain is unchanged')
    first,second,available,last=_domain(a,b,budget)
    total=_prefix(first,second,available,last,last)
    require(start<=total,'Page start outside complete budget domain')
    stop=min(total,start+limit);rows=[]
    if start<stop:
        q1,q2=_unrank(first,second,available,last,total,start)
        for rank in range(start,stop):
            rows.append(dict(rank=rank,q1=q1,q2=q2))
            q2+=1
            if first*q1+second*q2>available:q1+=1;q2=1
    return dict(schema='EXACT_TWO_POSITIVE_INTEGER_BUDGET_PAGE_V1',order='Q1_ASCENDING_THEN_Q2_ASCENDING',total_count=total,start=start,stop=stop,returned_count=len(rows),rows=rows,empty_domain=total==0,has_more=stop<total,full_domain_truncated=False,economic_policy_registered=False,risk_evaluated=False,account_executed=False)
