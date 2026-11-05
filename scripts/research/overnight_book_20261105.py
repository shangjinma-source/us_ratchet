"""Isolated fixed-roster auction model. No broker, selector, or production imports."""
from fractions import Fraction as F


def run_book(*, days, prices, rosters, dividends=(), splits=(), mode='overnight',
             slippage_bps=5, commission_bps=0, initial_cash=20000, exposure_check=None,
             retry_until_first_fill=False):
    if mode not in ('overnight', 'monthly_hold'):
        raise ValueError('MODE')
    if days != sorted(set(days)) or len(days) < 3:
        raise ValueError('SESSION_DOMAIN')
    slip, commission = F(slippage_bps, 10000), F(commission_bps, 10000)
    cash, holdings, receivables, orders, rejects, ledger, actions = F(initial_cash), {}, [], [], [], [], []
    turnover = F(0)
    peak, maximum_drawdown = F(initial_cash), F(0)
    last_decision = None
    ever_bought = False

    def price(sid, day, field):
        value = F(prices[sid][day][field])
        if value <= 0:
            raise ValueError('NONPOSITIVE_PRICE')
        return value

    def equity(day, field):
        return cash + sum(q * price(s, day, field) for s, q in holdings.items() if q) + sum(r['amount'] for r in receivables)

    def mark(day, phase, value):
        nonlocal peak, maximum_drawdown
        peak = max(peak, value)
        maximum_drawdown = max(maximum_drawdown, 1-value/peak)
        ledger.append(dict(day=day, phase=phase, equity=str(value), cash=str(cash),
                           holdings=dict(holdings), receivable=str(sum(r['amount'] for r in receivables))))

    def sell_all(day):
        nonlocal cash, turnover
        for sid, quantity in sorted(holdings.items()):
            if not quantity:
                continue
            fill = price(sid, day, 'open')*(1-slip)
            gross = quantity*fill
            fee = gross*commission
            cash += gross-fee
            turnover += gross
            orders.append(dict(day=day, phase='OPEN', side='SELL', sid=sid, quantity=quantity,
                               price=str(fill), commission=str(fee)))
        holdings.clear()

    for index in range(1, len(days)):
        day, previous = days[index], days[index-1]
        eligible = [r for r in rosters if r['decision'] <= previous]
        if not eligible:
            raise ValueError('ROSTER_NOT_KNOWN_BEFORE_CLOSE_ORDER')
        roster = max(eligible, key=lambda r:r['decision'])
        if len(roster['selected']) > 10 or len(set(roster['selected'])) != len(roster['selected']):
            raise ValueError('ROSTER_SIZE_OR_DUPLICATE')
        # Independently supplied action gate covers actual previous-close holdings,
        # including monthly control; it must not reuse overnight clearance blindly.
        if exposure_check:
            exposure_check(previous, day, dict(holdings))
        for event in splits:
            if event['date'] != day:
                continue
            old, new = event['old_sid'], event['new_sid']
            quantity = holdings.pop(old, 0)
            if quantity:
                converted = quantity*F(event['ratio'])
                if converted.denominator != 1:
                    raise ValueError('FRACTIONAL_SPLIT_UNSUPPORTED')
                holdings[new] = holdings.get(new, 0)+int(converted)
                actions.append(dict(day=day, old_sid=old, new_sid=new, old_quantity=quantity,
                                    new_quantity=int(converted)))
        for event in dividends:
            quantity = holdings.get(event['sid'], 0)
            if event['ex_date'] == day and quantity:
                receivables.append(dict(amount=quantity*F(event['amount']), pay=event.get('payment_date'),
                                        sid=event['sid'], ex_date=day))
        mark(day, 'OPEN_BEFORE_ORDERS', equity(day, 'open'))
        rebalance = roster['decision'] != last_decision
        final = index == len(days)-1
        if mode == 'overnight' or rebalance or final:
            sell_all(day)
        mark(day, 'OPEN_AFTER_ORDERS', equity(day, 'open'))
        if not final and (mode == 'overnight' or rebalance or (retry_until_first_fill and not ever_bought)):
            # Entire order vector fixed before observing today's close. Slots have
            # independent cash reserves, preventing execution order dependence.
            slots = len(roster['selected'])
            allocation = cash/slots if slots else F(0)
            submitted = [(sid, int(allocation/(price(sid, previous, 'close')*(1+slip)*(1+commission))))
                         for sid in roster['selected']]
            for sid, quantity in submitted:
                if quantity == 0:
                    rejects.append(dict(day=day, sid=sid, reason='ZERO_INTEGER_QUANTITY'))
                    continue
                fill = price(sid, day, 'close')*(1+slip)
                gross = quantity*fill
                fee = gross*commission
                if gross+fee > allocation:
                    rejects.append(dict(day=day, sid=sid, quantity=quantity, reason='FIXED_SLOT_CASH_EXCEEDED'))
                    continue
                cash -= gross+fee
                holdings[sid] = holdings.get(sid, 0)+quantity
                ever_bought = True
                turnover += gross
                orders.append(dict(day=day, phase='CLOSE', side='BUY', sid=sid, quantity=quantity,
                                   sizing_previous_close=str(price(sid, previous, 'close')),
                                   price=str(fill), commission=str(fee), decision=roster['decision']))
        # Known issuer pay date credited only after close orders; unknown stays locked.
        outstanding = []
        for item in receivables:
            if item['pay'] is not None and item['pay'] <= day:
                cash += item['amount']
            else:
                outstanding.append(item)
        receivables = outstanding
        if cash < 0:
            raise ValueError('NEGATIVE_CASH')
        mark(day, 'CLOSE', equity(day, 'close'))
        last_decision = roster['decision']
    return dict(status='COMPLETE', terminal_equity=ledger[-1]['equity'], drawdown=str(maximum_drawdown),
                cash=str(cash), holdings=holdings, receivables=[dict(x, amount=str(x['amount'])) for x in receivables],
                orders=orders, rejections=rejects, ledger=ledger, splits=actions, turnover=str(turnover),
                mode=mode, slippage_bps=slippage_bps, commission_bps=commission_bps,
                execution_assumption='FIXED_PREVIOUS_CLOSE_QUANTITY_SLOT_REJECTION_IDEAL_AUCTION_MODEL')
