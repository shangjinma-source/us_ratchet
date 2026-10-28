"""Independent staged order arithmetic plus unchanged identity/account review."""
from copy import deepcopy
from fractions import Fraction as F
from threading import RLock
from backtest import historical_dividend_identity_independent_review_v1 as ledger

LOCK = RLock()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def opening_orders(orders, splits, active, staged_ids):
    """Convert unrelated integer action coordinates; full identity audit remains mandatory."""
    result=deepcopy(orders)
    for action in splits:
        if action['date']!=active:continue
        require(action['type'] in ('split','split_identity'),'STAGE_MIXED_ACTION_NOT_SUPPORTED')
        old=action['security_id'];new=action.get('new_security_id',old)
        ratio=F(action['new_shares'])/F(action['old_shares'])
        require(ratio>0,'STAGE_SPLIT_RATIO')
        for order in result:
            if order['security_id']!=old:continue
            require(order['id'] not in staged_ids,'STAGE_ACTIVE_ACTION_NOT_SUPPORTED')
            q=F(order['quantity'])*ratio
            require(q.denominator==1,'STAGE_FRACTIONAL_ACTION_NOT_SUPPORTED')
            order.update(quantity=int(q),security_id=new)
    return result


def review(book, assembled, bars, *, initial_cash, dividend_events,
           expected_fee_bps, expected_slippage_bps, **options):
    require(options.get('verify_selections', True) and options.get('verify_risk_provider', True), 'STAGE_FULL_PROOF_REQUIRED')
    mode = book['execution_stage_mode']
    require(mode in ('BASELINE', 'BUY_TWO_OPENS', 'CAP_SELL_TWO_OPENS'), 'STAGE_MODE')
    stages = {r['decision_date']: r for r in book['execution_stage_audit']}
    require(len(stages) == len(book['execution_stage_audit']), 'STAGE_DUPLICATE_DATE')
    local = dict(book)
    local['provider_audit'] = []
    sessions = assembled['session_dates']
    for day, original in zip(sessions, book['provider_audit']):
        stage = stages.get(day)
        if stage is None:
            require(original.get('action') == 'WAIT_POST_ACTION_MARK', 'STAGE_MISSING_AUDIT')
            local['provider_audit'].append(original)
        else:
            require(stage['original'] == original, 'STAGE_ORIGINAL_MISMATCH')
            wanted = dict(original, orders=stage['adjusted']['orders'])
            require(wanted == stage['adjusted'], 'STAGE_NONORDER_MUTATION')
            local['provider_audit'].append(wanted)
    episodes, winners = {}, {}
    epoch = None
    count = 0
    fee, slip = F(expected_fee_bps)/10000, F(expected_slippage_bps)/10000
    original_risk = ledger._review_risk_orders

    def check(audit, decision, active, shares, prices, splits, selected_targets, risk_state):
        nonlocal epoch, count
        item = stages[decision]
        original = item['original']
        original_risk(original, decision, active, shares, prices, splits, selected_targets, risk_state)
        require(item['actual_shares'] == shares, 'STAGE_START_SHARES')
        index = sessions.index(decision)
        cash = F(initial_cash) if index == 0 else F(book['daily_ledger'][index-1]['cash'])
        require(F(item['actual_cash']) == cash, 'STAGE_START_CASH')
        selected = original.get('selection')
        if selected is not None:
            raw = selected['raw_selection']; ra = selected['rerank_audit']
            source = raw['search_result']['best_by_k'][str(ra['source_cardinality'])]['quantities'] if ra['strict_improvement'] else raw['target_quantities']
            capital = F(raw['investable_equity']); pp = raw['binding']['search_arguments']['prices']
            capped = {s:min(q, int(capital/(2*F(pp[s])))) for s,q in source.items()}
            require({s:q for s,q in capped.items() if q} == {s:q for s,q in selected['target_quantities'].items() if q}, 'STAGE_WINNER_CAP')
            winners[decision] = dict(source)
        current = original['target_decision_date']
        if current != epoch:
            episodes.clear(); epoch = current
        target = original['target_shares']
        for change in original.get('target_adjustments', []):
            require(change['security_id'] not in episodes, 'STAGE_PENDING_ACTION')
        for sid in list(episodes):
            if not target.get(sid,0) or shares.get(sid,0) == target.get(sid,0):
                del episodes[sid]
        orders = []
        decision_rows = []
        staged_ids = set()
        for order in original['orders']:
            out = dict(order); sid = order['security_id']; held = shares.get(sid,0)
            effective = target.get(sid,0); noncap = 0
            eligible = mode == 'BUY_TWO_OPENS' and order['side'] == 'BUY'
            if mode == 'CAP_SELL_TWO_OPENS' and order['side'] == 'SELL' and effective > 0 and effective == original['monthly_ceiling'].get(sid):
                u = winners[current].get(sid,0)
                noncap = max(0,held-u); cap = max(0,min(held,u)-effective)
                eligible = cap > 0
            if eligible:
                if sid not in episodes:
                    first = order['quantity']//2 if mode == 'BUY_TWO_OPENS' else noncap+(cap+1)//2
                    episodes[sid] = dict(first=first, next_open=active, filled=False)
                e = episodes[sid]
                second = e['filled'] or (e['first']==0 and decision>=e['next_open'])
                q = order['quantity'] if second else min(order['quantity'],e['first'])
                if mode == 'CAP_SELL_TWO_OPENS':q=max(q,noncap)
                out.update(quantity=q,id='stage:'+mode+':'+str(current)+':'+decision+':'+sid)
                decision_rows.append((sid, order['quantity'], q, 2 if second else 1))
                staged_ids.add(out['id'])
                require(not any(a['date']==active and sid in (a['security_id'],a.get('new_security_id')) for a in splits), 'STAGE_ACTIVE_ACTION_NOT_SUPPORTED')
            if out['quantity']:orders.append(out)
        require(orders == audit['orders'], 'STAGE_ORDER_ARITHMETIC')
        require(decision_rows == [(r['security_id'],r['original_quantity'],r['staged_quantity'],r['phase']) for r in item['decisions']], 'STAGE_PHASE_AUDIT')
        # Independently reconstruct filled quantities. Full ledger below verifies
        # the opening cash, all prices, action transformations and terminal book.
        if staged_ids:
            executable_orders=opening_orders(orders,splits,active,staged_ids)
            fills = {}
            for order in executable_orders:
                if order['side']=='SELL':
                    fills[order['id']] = order['quantity']
                    cash += order['quantity']*F(bars[order['security_id']][active]['open'])*(1-slip)*(1-fee)
            buys=[o for o in executable_orders if o['side']=='BUY']
            cost=sum((o['quantity']*F(bars[o['security_id']][active]['open'])*(1+slip)*(1+fee) for o in buys),F(0))
            scale=min(F(1),cash/cost) if cost else F(0)
            for order in buys:fills[order['id']]=int(order['quantity']*scale)
            for order in orders:
                if order['id'] not in staged_ids:continue
                q=fills[order['id']]
                logs=[r for r in book['order_log'] if r.get('id')==order['id'] and r.get('event')=='ASSUMED_NEXT_OPEN_FILLED']
                require((not logs if q==0 else len(logs)==1 and logs[0]['quantity']==q and logs[0]['date']==active), 'STAGE_FILL_LOG')
                if q:episodes[order['security_id']]['filled']=True
        count += 1

    with LOCK:
        try:
            ledger._review_risk_orders=check
            result=ledger.review(local,assembled,bars,initial_cash=initial_cash,dividend_events=dividend_events,
                expected_fee_bps=expected_fee_bps,expected_slippage_bps=expected_slippage_bps,
                verify_selections=True,verify_risk_provider=True)
        finally:
            ledger._review_risk_orders=original_risk
    result.update(execution_stage_mode=mode, independently_rebuilt_stage_sessions=count,
                  staged_fill_cash_arithmetic_checked=True)
    return result
