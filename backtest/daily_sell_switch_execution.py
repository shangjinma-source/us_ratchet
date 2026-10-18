"""Pure phased daily sell execution, without selection, actions or valuation."""
from fractions import Fraction as F


def execute_day(*, orders, ohlc, cash, shares, fee_bps, slippage_bps, mode):
    def value(x):
        if isinstance(x,bool):raise ValueError('BOOLEAN_AMOUNT')
        return F(str(x))
    if mode not in ('BASELINE_OPEN','PREMIUM_DAY'):raise ValueError('INVALID_MODE')
    if value(slippage_bps)!=0:raise ValueError('NONZERO_SLIPPAGE_UNSUPPORTED')
    cash=value(cash);rate=value(fee_bps)/10000
    if cash<0 or not 0<=rate<=1:raise ValueError('INVALID_CASH_OR_FEE')
    held=dict(shares);logs=[];fees=F(0);seen=set();sells=[];buys=[];bars={}
    if any(type(q)is not int or q<0 for q in held.values()):raise ValueError('INVALID_SHARES')
    for original in orders:
        o=dict(original);sid=o['security_id'];q=o['quantity']
        if o['id'] in seen or type(q)is not int or q<=0 or o['side'] not in ('BUY','SELL'):raise ValueError('INVALID_ORDER')
        seen.add(o['id'])
        if sid not in bars:
            b={k:value(ohlc[sid][k]) for k in ('open','high','low','close')}
            if not 0<b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']:raise ValueError('INVALID_OHLC')
            bars[sid]=b
        if o['side']=='SELL':
            o['limit']=value(o['limit'])
            if o['limit']<=0:raise ValueError('INVALID_LIMIT')
            sells.append(o)
        else:buys.append(o)
    for sid in {o['security_id'] for o in sells}:
        if sum(o['quantity'] for o in sells if o['security_id']==sid)>held.get(sid,0):raise ValueError('SELL_EXCEEDS_HOLDINGS')
    if {o['security_id'] for o in sells}&{o['security_id'] for o in buys}:raise ValueError('OPPOSITE_ORDERS_SAME_SECURITY')
    def sell(o,price,phase):
        nonlocal cash,fees
        q=o['quantity'];fee=q*price*rate;cash+=q*price-fee;fees+=fee;held[o['security_id']]-=q
        logs.append(dict(id=o['id'],security_id=o['security_id'],side='SELL',event='FILLED',phase=phase,quantity=q,price=str(price),fee=str(fee),cash_after=str(cash)))
    pending=[]
    for o in sorted(sells,key=lambda x:x['id']):
        price=bars[o['security_id']]['open']
        if mode=='BASELINE_OPEN' or price>o['limit']:sell(o,price,'OPEN_SELL')
        else:pending.append(o)
    required=sum((o['quantity']*bars[o['security_id']]['open']*(1+rate) for o in buys),F(0))
    factor=min(F(1),cash/required) if required else F(0)
    for o in sorted(buys,key=lambda x:x['id']):
        q=int(o['quantity']*factor);price=bars[o['security_id']]['open'];fee=q*price*rate
        cash-=q*price+fee;fees+=fee;held[o['security_id']]=held.get(o['security_id'],0)+q
        if q:logs.append(dict(id=o['id'],security_id=o['security_id'],side='BUY',event='FILLED',phase='OPEN_BUY',quantity=q,price=str(price),fee=str(fee),cash_after=str(cash)))
        if q<o['quantity']:logs.append(dict(id=o['id'],event='UNFILLED_CASH_RATIONED_INTEGER_FLOOR',phase='OPEN_BUY',quantity=o['quantity']-q))
    for o in pending:
        if bars[o['security_id']]['high']>o['limit']:sell(o,o['limit'],'INTRADAY_SELL')
        else:logs.append(dict(id=o['id'],security_id=o['security_id'],side='SELL',event='EXPIRED_UNSOLD',phase='DAY_END',quantity=o['quantity']))
    if cash<0 or any(q<0 for q in held.values()):raise AssertionError('CONSERVATION')
    return dict(cash=str(cash),shares=held,fees=str(fees),log=logs,buy_allocation_factor=str(factor),research_only=True)
