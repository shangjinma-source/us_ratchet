"""R36 actual four-column DOM review. V1 financial checks retained explicitly.

Monthly target is verified against signed proposal maps; DOM only displays its
note when it differs from effective target. No synthetic seven-column evidence.
Only exact unreviewed AI placeholder is in scope. Not AI economic acceptance.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re

HEADERS = ['股票', '持仓 → 目标', '今日建议', '原因与 AI 复核']
UNREVIEWED = '未复核，不代表无风险'
POLICY = 'SAVED_FRONTIER_CAP50_EXIT20_V1'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def review(capture):
    require(capture.get('capture_schema') == 'DAILY_FOUR_COLUMN_DOM_CAPTURE_V2', 'FOUR_COLUMN_CAPTURE_REQUIRED')
    require(capture.get('table_headers') == HEADERS, 'CURRENT_DOM_TABLE_HEADER_REQUIRED')
    controls=capture.get('ui_controls')
    require(isinstance(controls,dict) and controls.get('cash_button_text')=='更新现金并查看建议' and controls.get('cash_button_disabled') is False and controls.get('refresh_button_disabled') is False, 'DOM_UI_NOT_SETTLED')
    require('state' not in capture and 'visible_rows' not in capture, 'EXTERNAL_API_EVIDENCE_REQUIRED')
    api_state = capture.get('api_state')
    require(isinstance(api_state,dict), 'EXTERNAL_API_EVIDENCE_REQUIRED')
    # API data is separately captured, never claimed as browser application state.
    state = dict(deepcopy(api_state), busy=False, error=None)
    require(api_state.get('busy') in (None,False) and not api_state.get('error'), 'API_STATE_INVALID')
    target, account, daily = state.get('target') or {}, state.get('account') or {}, state.get('daily') or {}
    identities = {}
    for row in list(target.get('proposal_targets') or []) + list(account.get('holdings') or []):
        ticker, sid = row.get('ticker'), row.get('security_id')
        require(isinstance(ticker,str) and bool(ticker) and isinstance(sid,str) and bool(sid), 'API_TICKER_IDENTITY_REQUIRED')
        require(ticker not in identities or identities[ticker]==sid, 'AMBIGUOUS_TICKER_IDENTITY')
        identities[ticker] = sid
    dom_rows = capture.get('dom_rows')
    require(isinstance(dom_rows,list) and bool(dom_rows) and capture.get('dom_row_count')==len(dom_rows), 'DOM_ROWS_REQUIRED')
    require(len({r.get('ticker') for r in dom_rows})==len(dom_rows), 'DUPLICATE_DOM_TICKER')
    rows = []
    for row in dom_rows:
        require(row.get('ticker') in identities, 'DOM_SECURITY_OUTSIDE_API_DOMAIN')
        sid=identities[row['ticker']]
        rows.append(dict(deepcopy(row), security_id=sid, dom_match_count=1,
                         orders=[deepcopy(order) for order in daily.get('new_orders',[]) if order['security_id']==sid],
                         explanation=(row.get('dom_parts') or {}).get('reason')))
    capture = dict(deepcopy(capture), state=state, visible_rows=rows)
    require(isinstance(rows, list) and bool(rows), 'VISIBLE_ROWS_REQUIRED')
    page = ''.join(capture.get('page_text', '').split())
    require(page.count(''.join(''.join(HEADERS).split())) == 1, 'PAGE_HEADER_MISMATCH')
    for row in rows:
        cells, parts = row.get('dom_cells'), row.get('dom_parts')
        require(isinstance(cells, list) and len(cells) == 4 and all(isinstance(v,str) for v in cells), 'FOUR_DOM_CELLS_REQUIRED')
        require(isinstance(parts, dict) and set(parts) == {'position','monthly_note','actions','limits','reason','ai_label','ai_text'}, 'DOM_PARTS_REQUIRED')
        require(all(isinstance(parts[k],str) for k in ('position','monthly_note','reason','ai_label','ai_text')), 'DOM_TEXT_REQUIRED')
        require(all(isinstance(parts[k],list) and all(isinstance(v,str) for v in parts[k]) for k in ('actions','limits')), 'DOM_ADVICE_REQUIRED')
        require(parts['ai_label'] == 'AI 复核 · 研究预览' and parts['ai_text'] == UNREVIEWED, 'NEWS_REVIEW_STATE_OUTSIDE_ACCEPTANCE_SCOPE')
        require(cells[0] == (row.get('ticker') or row['security_id']), 'DOM_TICKER_MISMATCH')
        require(cells[1] == parts['position'] + parts['monthly_note'], 'DOM_POSITION_TEXT_MISMATCH')
        advice = ''.join(a + (parts['limits'][i] if i < len(parts['limits']) else '') for i,a in enumerate(parts['actions']))
        require(len(parts['limits']) <= len(parts['actions']) and cells[2] == advice, 'DOM_ADVICE_TEXT_MISMATCH')
        require(bool(parts['reason'].strip()) and cells[3] == parts['reason'] + parts['ai_label'] + parts['ai_text'] and row.get('explanation') == parts['reason'], 'DOM_REASON_TEXT_MISMATCH')
        require(page.count(''.join(''.join(cells).split())) == 1, 'PAGE_ROW_MISMATCH')
    state = capture['state']
    require(isinstance(state,dict), 'UI_CAPTURE_STATE_REQUIRED')
    target, daily = state.get('target'), state.get('daily')
    require(isinstance(target,dict) and bool(target), 'UI_CAPTURE_TARGET_REQUIRED')
    require(isinstance(daily,dict) and bool(daily), 'UI_CAPTURE_DAILY_REQUIRED')
    require(daily.get('policy_id') == POLICY, 'FRONTIER_POLICY_MISMATCH')
    proposal = target.get('proposal_id')
    require(isinstance(proposal,str) and re.fullmatch('[0-9a-f]{64}',proposal) and daily.get('proposal_id') == proposal, 'FRONTIER_PROPOSAL_BINDING')
    targets = target.get('proposal_targets')
    require(isinstance(targets,list) and bool(targets), 'FRONTIER_PROPOSAL_TARGETS_REQUIRED')
    quantities = {}
    for item in targets:
        sid, quantity = item.get('security_id'), item.get('quantity')
        require(isinstance(sid,str) and bool(sid) and sid not in quantities and type(quantity) is int and quantity >= 0, 'FRONTIER_PROPOSAL_TARGETS_INVALID')
        quantities[sid] = quantity
    for item in (target,daily):
        values = item.get('risk_monthly_targets')
        require(isinstance(values,dict) and values == quantities and all(type(v) is int for v in values.values()), 'FRONTIER_QUANTITIES_BINDING')
    if daily.get('status') not in ('READY','CONDITIONAL_PREVIEW_READY'):
        require(not any(row.get('orders') for row in rows), 'UNEXPECTED_VISIBLE_ORDER')
    normalized = deepcopy(capture)
    normalized['state']['target']['targets'] = deepcopy(targets)
    old = {row['security_id'] for row in state['account']['holdings']} - set(quantities)
    normalized['state']['target']['targets'].extend(dict(security_id=sid,quantity=0) for sid in sorted(old))
    result = _financial_review(normalized)
    return dict(result, acceptance_version=6, unified_table_columns=4, proposal_id=proposal,
                monthly_display_policy=POLICY, proposal_calculation_independently_verified=False,
                ai_risk_plan_accepted=False, news_column_scope='Exact unreviewed placeholder only',
                monthly_display_scope='Signed map checked; DOM monthly note only when different from effective target',
                evidence_scope='Actual DOM text matched to separately captured API account/target/preview; not browser hidden-state binding or cash-button execution')


from datetime import datetime
from fractions import Fraction
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo


def _financial_review(capture):
    def require(condition, reason):
        if not condition: raise ValueError(reason)
    state=capture['state'];daily=state.get('daily') or {}
    require(capture['account_before']==capture['account_after'], 'ACCOUNT_CHANGED')
    require(state['account']==capture['account_after'], 'UI_ACCOUNT_MISMATCH')
    require(capture.get('scope')=='READ_ONLY_PAGE_CAPTURE' and capture['cash_posts_intercepted']==0 and not capture['unexpected_writes'], 'WRITE_SCOPE')
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
        rendered=next(row for row in capture['visible_rows'] if row['security_id']==sid)
        parts=rendered['dom_parts']
        require(parts['position']==str(held)+' → '+str(target),'DOM_HELD_OR_EFFECTIVE_TARGET_MISMATCH')
        month=monthly.get(sid)
        expected_note='本月目标 '+str(month)+' 股' if month is not None and month!=target else ''
        require(parts['monthly_note']==expected_note,'DOM_MONTHLY_NOTE_MISMATCH')
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
                    len(cells)==4 and rendered['dom_parts']['actions']==['无需操作'] and not rendered['dom_parts']['limits'] and
                    bool(rendered['explanation'].strip()),
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
        require(rendered.get('dom_match_count')==1 and len(cells)==4,'MISSING_DOM_ROW')
        require(rendered['dom_parts']['actions']==[('买入' if side=='BUY' else '卖出')+' '+str(quantity)+' 股'],'DOM_ACTION_MISMATCH')
        price=Fraction(order['limit_price'])
        rounded=(Decimal(price.numerator)/Decimal(price.denominator)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
        require(rendered['dom_parts']['limits']==['限价 $'+format(rounded,',.2f')],'DOM_PRICE_MISMATCH')
        require(rendered['dom_parts']['reason']==rendered['explanation'],'DOM_REASON_MISMATCH')
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
        require(rendered.get('dom_match_count')==1 and len(cells)==4,'MISSING_DOM_ROW')
        require(bool(rendered['explanation'].strip()),'MISSING_VISIBLE_REASON')
        if sid in seen:continue
        held=holdings.get(sid,0)
        require(row.get('held')==held,'NONTRADING_HELD_MISMATCH')
        target=effective.get(sid,row.get('effective_target'))
        check_numeric_cells(cells,sid,held,target if target is not None else '—')
        require(row.get('action') in ('BUY','SELL','HOLD','WAIT'),'NONTRADING_ACTION_INVALID')
        if row.get('action')=='HOLD':
            require(target==held,'NONTRADING_HOLD_TARGET_MISMATCH')
            action='无需操作'
        else:action='等待'
        require(not rendered.get('orders') and rendered['dom_parts']['actions']==[action] and not rendered['dom_parts']['limits'],'NONTRADING_DOM_ACTION_MISMATCH')
    require(not any(r.get('orders') for r in capture['visible_rows'] if r['security_id'] not in seen),
            'UNEXPECTED_VISIBLE_ORDER')
    require(buy_cash<=Fraction(state['account']['available_cash']),'USES_UNFILLED_SALE_CASH')
    return dict(status='INTRADAY_UI_CHECKS_PASS',orders=len(orders),buy_cash=str(buy_cash),scope='Captured UI/account/order consistency only; not strategy optimality or complete goal acceptance')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture_path', type=Path)
    arguments = parser.parse_args()
    print(json.dumps(review(json.loads(arguments.capture_path.read_bytes())), ensure_ascii=False, indent=2))
