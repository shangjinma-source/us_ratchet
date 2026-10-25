"""Read-only review of a captured cash-button browser run; WAIT is not acceptance."""
from datetime import datetime
from fractions import Fraction
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo


def review(capture):
    def require(condition, reason):
        if not condition: raise ValueError(reason)
    state=capture['state'];daily=state.get('daily') or {}
    require(capture['account_before']==capture['account_after'], 'ACCOUNT_CHANGED')
    require(state['account']==capture['account_after'], 'UI_ACCOUNT_MISMATCH')
    require(capture['cash_posts_intercepted']==1 and not capture['unexpected_writes'], 'WRITE_SCOPE')
    require(not state['busy'] and not state.get('error'), 'UI_NOT_SETTLED')
    require(daily.get('account_revision')==state['account']['revision'] and daily.get('target_id')==state['target']['target_id'], 'STALE_BINDING')
    observed=datetime.fromisoformat(capture['observed_at'].replace('Z','+00:00'))
    require(observed.tzinfo is not None,'AWARE_TIME_REQUIRED')
    orders=daily.get('new_orders',[])
    if daily['status'] not in ('READY','CONDITIONAL_PREVIEW_READY','HOLD'):
        require(not orders,'WAIT_WITH_ORDERS')
        return dict(status='NOT_ACCEPTED_WAIT',reason=daily.get('reason',daily['status']),orders=0)
    local=observed.astimezone(ZoneInfo('America/New_York'))
    require(local.weekday()<5 and (9,30)<=(local.hour,local.minute)<(16,0),'OUTSIDE_REGULAR_SESSION')
    require(daily['status']!='HOLD' or not orders,'HOLD_WITH_ORDERS')
    require(daily['status']=='HOLD' or bool(orders),'READY_WITHOUT_ORDERS')
    holdings={r['security_id']:r['quantity'] for r in state['account']['holdings']}
    monthly={r['security_id']:r['quantity'] for r in state['target'].get('targets',[])}
    def check_numeric_cells(cells,sid,held,target):
        require(cells[1]==str(held),'DOM_HELD_MISMATCH')
        require(cells[2]==str(monthly.get(sid,'—')),'DOM_MONTHLY_TARGET_MISMATCH')
        require(cells[3]==str(target),'DOM_EFFECTIVE_TARGET_MISMATCH')
    if daily['status']=='HOLD':
        gate=daily.get('daily_gate') or {}
        require(gate.get('status')=='DAILY_TARGET_READY','HOLD_WITHOUT_VALIDATED_TARGET')
        gate_rows=gate.get('rows',[])
        domain=set(holdings)|{r['security_id'] for r in state['target'].get('targets',[])}
        require(bool(domain) and len(gate_rows)==len(domain) and
                {r['security_id'] for r in gate_rows}==domain,'HOLD_DOMAIN_MISMATCH')
        visible=capture['visible_rows']
        for row in gate_rows:
            sid=row['security_id'];held=holdings.get(sid,0)
            require(row.get('action')=='HOLD' and row.get('held')==held and
                    row.get('effective_target')==held,'HOLD_TARGET_MISMATCH')
            matches=[r for r in visible if r['security_id']==sid]
            require(len(matches)==1,'HOLD_VISIBLE_DOMAIN_MISMATCH')
            rendered=matches[0];cells=rendered.get('dom_cells',[])
            require(not rendered.get('orders') and rendered.get('dom_match_count')==1 and
                    len(cells)==7 and cells[4]==('空仓，无需操作' if held==0 else '持有，无需操作') and
                    bool(cells[6].strip()) and cells[6]==rendered.get('explanation'),
                    'HOLD_DOM_MISMATCH')
            check_numeric_cells(cells,sid,held,held)
        return dict(status='HOLD_UI_CHECKS_PASS',orders=0,
                    scope='Visible hold and account/target consistency only; not fresh trade quote acceptance')
    effective=daily['effective_target_quantities'];seen=set();buy_cash=Fraction(0)
    gate=daily.get('daily_gate') or {}
    require(gate.get('status')=='DAILY_TARGET_READY','ORDER_WITHOUT_VALIDATED_TARGET')
    gate_rows=gate.get('rows',[])
    visible={r['security_id']:r for r in capture['visible_rows']}
    for order in orders:
        sid=order['security_id'];side=order['side'];quantity=order['quantity']
        require(sid not in seen,'DUPLICATE_ORDER');seen.add(sid)
        require(type(quantity) is int and quantity>0,'INVALID_QUANTITY')
        require(sid in visible and bool(visible[sid]['explanation'].strip()),'MISSING_VISIBLE_REASON')
        require(visible[sid]['orders']==[order],'VISIBLE_ORDER_MISMATCH')
        rendered=visible[sid]
        cells=rendered.get('dom_cells',[])
        require(rendered.get('dom_match_count')==1 and len(cells)==7,'MISSING_DOM_ROW')
        require(cells[4]==('买入' if side=='BUY' else '卖出')+' '+str(quantity)+' 股','DOM_ACTION_MISMATCH')
        price=Fraction(order['limit_price'])
        rounded=(Decimal(price.numerator)/Decimal(price.denominator)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
        require(cells[5]=='$'+format(rounded,',.2f'),'DOM_PRICE_MISMATCH')
        require(cells[6]==rendered['explanation'],'DOM_REASON_MISMATCH')
        quote=daily['reference_quotes'][sid]
        quote_time=datetime.fromisoformat(quote['observed_at'].replace('Z','+00:00'))
        require(quote_time.tzinfo is not None,'AWARE_QUOTE_TIME_REQUIRED')
        require(0 <= (observed-quote_time).total_seconds() <= 120,'STALE_OR_FUTURE_QUOTE')
        # Both source and displayed order must remain valid. An order's later
        # expiry cannot extend the underlying quote's lifetime.
        for value in (quote['reference_valid_until'],order.get('reference_valid_until',quote['reference_valid_until'])):
            expiry=datetime.fromisoformat(value.replace('Z','+00:00'))
            require(expiry.tzinfo is not None,'AWARE_EXPIRY_REQUIRED')
            require(expiry>observed,'EXPIRED_PRICE')
        require(Fraction(order['limit_price'])>0,'INVALID_PRICE')
        require(side in ('BUY','SELL'),'INVALID_SIDE')
        require(Fraction(order['limit_price'])==Fraction(quote[side.lower()]),'QUOTE_PRICE_MISMATCH')
        held=holdings.get(sid,0);target=effective[sid]
        check_numeric_cells(cells,sid,held,target)
        matching=[row for row in gate_rows if row.get('security_id')==sid]
        require(len(matching)==1 and matching[0].get('action')==side and
                matching[0].get('held')==held and matching[0].get('effective_target')==target,
                'ORDER_TARGET_GATE_MISMATCH')
        if side=='SELL': require(quantity<=held and quantity<=held-target,'EXCESS_SELL')
        elif side=='BUY':
            require(quantity<=target-held,'EXCESS_BUY')
            cost=-Fraction(order['estimated_cash_change']);require(cost>=quantity*Fraction(order['limit_price']),'BUY_COST_INVALID');buy_cash+=cost
        else: require(False,'INVALID_SIDE')
    # Order checks alone cannot prove that existing holdings and non-trading
    # targets remain visible with a reason. Review the full authoritative domain.
    domain=set(holdings)|set(monthly)
    require(len(gate_rows)==len(domain) and {r['security_id'] for r in gate_rows}==domain,
            'ORDER_DOMAIN_MISMATCH')
    for row in gate_rows:
        sid=row['security_id']
        matches=[r for r in capture['visible_rows'] if r['security_id']==sid]
        require(len(matches)==1,'VISIBLE_DOMAIN_MISMATCH')
        rendered=matches[0];cells=rendered.get('dom_cells',[])
        require(rendered.get('dom_match_count')==1 and len(cells)==7,'MISSING_DOM_ROW')
        require(bool(cells[6].strip()) and cells[6]==rendered.get('explanation'),'MISSING_VISIBLE_REASON')
        if sid in seen:continue
        held=holdings.get(sid,0)
        require(row.get('held')==held,'NONTRADING_HELD_MISMATCH')
        target=effective.get(sid,row.get('effective_target'))
        check_numeric_cells(cells,sid,held,target if target is not None else '—')
        require(row.get('action') in ('BUY','SELL','HOLD','WAIT'),'NONTRADING_ACTION_INVALID')
        if row.get('action')=='HOLD':
            require(target==held,'NONTRADING_HOLD_TARGET_MISMATCH')
            action='空仓，无需操作' if held==0 else '持有，无需操作'
        else:action='等待'
        require(not rendered.get('orders') and cells[4]==action,'NONTRADING_DOM_ACTION_MISMATCH')
    require(not any(r.get('orders') for r in capture['visible_rows'] if r['security_id'] not in seen),
            'UNEXPECTED_VISIBLE_ORDER')
    require(buy_cash<=Fraction(state['account']['available_cash']),'USES_UNFILLED_SALE_CASH')
    return dict(status='INTRADAY_UI_CHECKS_PASS',orders=len(orders),buy_cash=str(buy_cash),scope='Captured UI/account/order consistency only; not strategy optimality or complete goal acceptance')
