"""Independent saved-event replay for fills, integer splits and unexposed distributions."""
from fractions import Fraction as F
from copy import deepcopy


def review(*, outcome, session_dates, ohlc, initial_cash, fee_bps, slippage_bps):
    def require(ok, reason):
        if not ok: raise ValueError(reason)
    def positions(values):
        require(all(type(q) is int and q>=0 for q in values.values()), 'INVALID_WHOLE_HOLDINGS')
        return {sid:q for sid,q in values.items() if q}
    def unsupported(event):
        return dict(status='UNSUPPORTED_EVENT_REQUIRES_REVIEW',event=event,
                    whole_ledger_verified=False, fills_verified=fills)
    require(outcome['status']=='COMPLETE' and F(outcome['external_flows'])==0,'INCOMPLETE_OR_EXTERNAL_FLOW')
    require(F(outcome['fee_bps'])==F(fee_bps) and F(outcome['slippage_bps'])==F(slippage_bps),'COST_MODEL_MISMATCH')
    cash=F(initial_cash); fee_rate=F(fee_bps)/10000; slip=F(slippage_bps)/10000
    holdings={};fees=F(0);fills=0;actions=0;orders={};filled={};unfilled={};cancelled=set()
    for audit in outcome['provider_audit']:
        for order in audit.get('orders',[]):
            require(order['id'] not in orders,'DUPLICATE_ORDER_ID')
            require(type(order['quantity']) is int and order['quantity']>0,'INVALID_ORDER_QUANTITY')
            index=session_dates.index(order['decision_date'])
            require(index+1<len(session_dates) and session_dates[index+1]==order['active_date'],'INVALID_ORDER_SESSION')
            orders[order['id']]=deepcopy(order)
    logs={}
    for row in outcome['order_log']:
        require(row['date'] in session_dates,'LOG_OUTSIDE_SESSIONS')
        logs.setdefault(row['date'],[]).append(row)
    rows=outcome['daily_ledger'];require([r['date'] for r in rows]==session_dates[1:],'LEDGER_COVERAGE')
    daily={row['date']:row for row in rows}
    for day in session_dates:
        phase=-1
        for log in logs.get(day,[]):
            event=log['event']
            if event=='FROZEN_TARGET_FOR_NEXT_OPEN':continue
            if event=='SPLIT_QUANTITY_AND_MARK_ADJUSTED':
                order=orders[log['id']]
                require(order['active_date']==day and log['side']==order['side'],'SPLIT_ORDER_BINDING')
                # Corporate-action ratio below independently validates this adjustment.
                order['_pre_split_quantity']=order['quantity'];order['quantity']=log['quantity_after']
            elif event=='CORPORATE_ACTION':
                action=log['action_details'];sid=log['security_id'];kind=log['type']
                if kind not in ('split','split_identity'):return unsupported(kind)
                require(phase==-1,'ACTION_AFTER_FILL')
                dest=action.get('new_security_id',sid) if kind=='split_identity' else sid
                ratio=F(action['new_shares'])/F(action['old_shares']);require(ratio>0,'INVALID_SPLIT_RATIO')
                quantity=holdings.get(sid,0)*ratio;require(quantity.denominator==1,'FRACTIONAL_SPLIT')
                if dest!=sid:require(not holdings.get(dest,0),'SPLIT_SUCCESSOR_CONFLICT')
                holdings[sid]=0;holdings[dest]=int(quantity)
                for order in orders.values():
                    if order['active_date']==day and order['security_id']==sid:
                        before=order.pop('_pre_split_quantity',None)
                        require(before is not None and F(before)*ratio==order['quantity'],'SPLIT_ORDER_RATIO_MISMATCH')
                        order['security_id']=dest
                actions+=1
            elif event=='DISTRIBUTION_APPLIED':
                action=log['action_details']
                if action['eligible_parent_quantity']!=0 or holdings.get(action['parent_sid'],0):return unsupported('EXPOSED_DISTRIBUTION')
                require(F(log['cash_credited'])==0,'UNSUPPORTED_INTERNAL_CASH_CREDIT');actions+=1
            elif event.startswith('CANCELLED_'):
                if event not in {'CANCELLED_CONDITIONAL_MIXED_SESSION','CANCELLED_DISTRIBUTION_SESSION','CANCELLED_ADS_CONVERSION','CANCELLED_TERMINATION'}:return unsupported(event)
                require(log['id'] in orders and orders[log['id']]['active_date']==day,'CANCELLATION_BINDING')
                cancelled.add(log['id'])
            elif event=='UNFILLED_CASH_RATIONED_INTEGER_FLOOR':
                require(log['id'] not in unfilled and type(log['quantity']) is int and log['quantity']>0,'INVALID_UNFILLED')
                unfilled[log['id']]=log['quantity']
                require(F(log['cash_after'])==cash,'UNFILLED_CASH_MISMATCH')
            elif event=='ASSUMED_NEXT_OPEN_FILLED':
                order=orders[log['id']];sid=log['security_id'];q=log['quantity'];side=log['side']
                require(log['id'] not in filled and log['id'] not in cancelled,'DUPLICATE_OR_CANCELLED_FILL')
                require(order['active_date']==day and order['security_id']==sid and order['side']==side,'FILL_BINDING')
                require(type(q) is int and 0<q<=order['quantity'],'FILL_QUANTITY')
                current=0 if side=='SELL' else 1;require(side in ('BUY','SELL') and current>=phase,'SELL_AFTER_BUY');phase=current
                price=F(ohlc[sid][day]['open'])*(1-slip if side=='SELL' else 1+slip)
                fee=q*price*fee_rate
                require(F(log['price'])==price and F(log['fee'])==fee,'FILL_PRICE_FEE')
                holdings[sid]=holdings.get(sid,0)+(-q if side=='SELL' else q)
                cash+=q*price-fee if side=='SELL' else -q*price-fee
                require(holdings[sid]>=0 and cash>=0 and F(log['cash_after'])==cash,'FILL_CONSERVATION')
                filled[log['id']]=q;fees+=fee;fills+=1
            else:return unsupported(event)
        for identity,order in orders.items():
            if order['active_date']==day and identity not in cancelled:
                require(filled.get(identity,0)+unfilled.get(identity,0)==order['quantity'],'ORDER_QUANTITY_UNACCOUNTED')
        if day in daily:
            row=daily[day]
            if row['merger_entitlements'] or row['distribution_rights'] or any(F(row[k]) for k in
                    ('receivable','nontradable_entitlement_value','distribution_entitlement_value')):
                return unsupported('NONZERO_RIGHTS')
            require(F(row['cash'])==cash and positions(row['shares'])==positions(holdings),'DAILY_STATE:'+day)
            value=sum((q*F(ohlc[sid][day]['close']) for sid,q in holdings.items() if q),F(0))
            require(F(row['stock_value'])==value and F(row['equity'])==cash+value,'DAILY_NAV:'+day)
    require(F(outcome['cash'])==cash and F(outcome['fees'])==fees and positions(outcome['shares'])==positions(holdings),'FINAL_STATE')
    return dict(status='SUPPORTED_SAVED_LEDGER_REPLAY_VERIFIED',whole_ledger_verified=True,
        sessions=len(rows),fills_verified=fills,actions_verified=actions,fees=str(fees),
        limitations=['Only fills, integer splits and zero-exposure distributions supported; other rights pause review.',
                     'Replays reported events and checks reported orders, not missing source actions, historical price authenticity, optimizer validity or independent OOS.'])
