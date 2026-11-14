"""Bounded synthetic cash-allocation comparison; no quotes, accounts or orders."""
from fractions import Fraction as F
import json
from core.usmart_standard_fees import affordable_integer_buy

def compare(deposit, broker, *, defensive=False, stopped=()):
    if type(deposit) is not int or deposit<=0 or broker not in {'USMART_STANDARD','HSBC_EXHAUSTED','HSBC_CONFIRMED_FREE'}:
        raise ValueError('INVALID_SCENARIO')
    prices={str(i):F(200 if i==0 else 100) for i in range(10)}
    held={s:10 for s in prices};equity=sum(held[s]*prices[s] for s in prices)+F(deposit)
    full={s:int(equity/10/(prices[s]*F('1.0005'))) for s in prices}
    additions={};fees=F(0)
    for sid,price in prices.items():
        budget=F(deposit)/10
        if defensive or sid in stopped:
            additions[sid]=0;continue
        cap=max(0,full[sid]-held[sid])
        if broker=='USMART_STANDARD':
            order=affordable_integer_buy(cash_usd=str(budget),target_quantity=cap,limit_price_usd=str(price),other_fee_reserve_usd='0')
            quantity=order['quantity'];fee=F(order['estimated_cash_required'])-quantity*price
        else:
            fee=F(18 if broker=='HSBC_EXHAUSTED' else 0)
            quantity=min(cap,max(0,int((budget-fee)//price)))
            if not quantity:fee=F(0)
        additions[sid]=quantity;fees+=fee
    spend=sum(additions[s]*prices[s] for s in prices)
    assert spend+fees<=F(deposit)
    assert all(additions.get(s,0)==0 for s in stopped)
    assert not defensive or not spend
    return dict(deposit=deposit,broker=broker,defensive=defensive,stopped=list(stopped),
                wait_new_orders=0,full_rebalance_sell_shares=sum(max(0,held[s]-full[s]) for s in prices),
                incremental_buy_orders=sum(q>0 for q in additions.values()),incremental_shares=additions,
                incremental_notional=str(spend),base_fees=str(fees),remaining_cash=str(F(deposit)-spend-fees),
                base_fee_percent=float(fees/spend*100) if spend else None)

def run():
    rows=[compare(amount,broker) for amount in (100,1000,5000,10000) for broker in ('HSBC_EXHAUSTED','HSBC_CONFIRMED_FREE','USMART_STANDARD')]
    rows.extend([compare(5000,'HSBC_EXHAUSTED',defensive=True),compare(5000,'HSBC_EXHAUSTED',stopped=('0','1'))])
    return dict(scope='SYNTHETIC_MECHANICS_NOT_RETURN_BACKTEST',assumptions=['Ten equal target weights, integer shares, no outstanding orders','Synthetic prices 200 for one stock, 100 for nine stocks; initially ten shares each','User-supplied fee plans; additional fees, spread and execution risk excluded','Fee-free case requires confirmed remaining allowance; no actual allowance assumed','Incremental rule spends at most one tenth of deposit per eligible stock, does not redistribute stopped weights'],cases=rows)
if __name__=='__main__':print(json.dumps(run(),indent=2))
