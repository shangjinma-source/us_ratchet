"""Execution activity statistics only; not a strategy acceptance or profitability proof."""
from collections import Counter
from fractions import Fraction as F

def activity(book,assembled):
    fills=[r for r in book['order_log'] if r.get('event')=='ASSUMED_NEXT_OPEN_FILLED']
    previous={};switches=[]
    for row in fills:
        sid=row['security_id'];side=row['side']
        if sid in previous and previous[sid]!=side:switches.append({'date':row['date'],'security_id':sid,'from':previous[sid],'to':side})
        previous[sid]=side
    audit_by_day={r['active_date']:r for r in book.get('execution_stage_audit',[])}
    orders={o['id']:o for row in book['provider_audit'] for o in row.get('orders',[])}
    orders.update({o['id']:o for row in audit_by_day.values() for o in row['adjusted']['orders']})
    unfilled=[r for r in book['order_log'] if r.get('event')=='UNFILLED_CASH_RATIONED_INTEGER_FLOOR']
    counts=Counter(orders.get(r['id'],{}).get('security_id','UNKNOWN') for r in unfilled)
    exposure=[]
    if book.get('execution_stage_mode')=='CAP_SELL_TWO_OPENS':
        for row in book['daily_ledger']:
            audit=audit_by_day.get(row['date'])
            if not audit:continue
            ceilings=dict(audit['original'].get('monthly_ceiling',{}))
            for action in assembled.get('actions',[]):
                if action['date']==row['date'] and action['security_id'] in ceilings:
                    old=action['security_id'];new=action.get('new_security_id',old)
                    q=F(ceilings.pop(old))*F(action['new_shares'])/F(action['old_shares'])
                    ceilings[new]=q
            for sid,h in row['shares'].items():
                if sid not in ceilings:continue
                excess=max(F(0),F(h)-F(ceilings[sid]))
                if excess:
                    exposure.append({'date':row['date'],'security_id':sid,'excess_shares':str(excess),'close_notional':str(excess*F(assembled['close_prices'][sid][row['date']]))})
    return {'filled_order_count':len(fills),'buy_fills':sum(r['side']=='BUY' for r in fills),'sell_fills':sum(r['side']=='SELL' for r in fills),'buy_sell_direction_switch_count':len(switches),'direction_switches':switches,'partially_or_fully_cash_unfilled_order_count':len(unfilled),'cash_unfilled_count_by_security':dict(counts),'repeated_cash_unfilled_beyond_first_by_security':sum(max(0,n-1) for n in counts.values()),'unfilled_definition':'Cash-rationed integer shortfalls including partial fills; repetition across whole window, not same advice ID','above_branch_monthly_quantity_cap':exposure,'above_cap_session_count':len({r['date'] for r in exposure}),'maximum_above_cap_close_notional':str(max((sum(F(r['close_notional']) for r in exposure if r['date']==d) for d in {r['date'] for r in exposure}),default=F(0))),'limitations':['Execution staging may increase fills; slower execution is not fewer trades.','Cap is monthly quantity ceiling, not a daily marked-value 50 percent guarantee.','No candidate economic acceptance is implied by activity counts.']}
