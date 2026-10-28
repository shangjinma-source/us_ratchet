"""Independent reference-lock/order reconstruction plus original financial proof."""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from threading import RLock
from backtest import historical_dividend_identity_independent_review_v1 as ledger

LOCK=RLock()
def need(ok,reason):
    if not ok:raise ValueError(reason)

def reference_path(lock,end,buy_sids,context):
    """Recompute interval evidence from pinned source inputs, never candidate proof."""
    doc=context['document'];domain=doc['assembled'];start=lock['exit_date'];old=lock['security_id'];sid=old;changes=[]
    for event in sorted(domain['actions'],key=lambda e:e['date']):
        if not start<event['date']<=end or event['security_id']!=sid:continue
        need(set(event)=={'type','date','security_id','new_security_id','old_shares','new_shares','source_references'},'INDEPENDENT_ACTION_SCHEMA')
        need(event['type']=='split_identity' and event['date']=='2024-10-01' and sid=='security:0001375365:86800U104' and event['new_security_id']=='security:0001375365:86800U302' and F(event['old_shares'])==1 and F(event['new_shares'])==10 and event['source_references'],'INDEPENDENT_ACTION_UNSUPPORTED')
        changes.append(dict(date=event['date'],old_sid=sid,new_sid=event['new_security_id'],ratio='10',kind='REVIEWED_INTEGER_SPLIT',source_references=event['source_references']));sid=event['new_security_id']
    successors={old,sid}
    for event in sorted(doc.get('dated_identity_transitions',[]),key=lambda e:e['date']):
        if start<event['date']<=end and event['old_sid'] in successors:successors.add(event['new_sid'])
    if not successors.intersection(buy_sids):return None
    need(successors<={old,sid},'INDEPENDENT_UNKNOWN_SUCCESSOR')
    for scope_sid in sorted({old,sid}):
        args={'decision_date':start,'account_state':{'shares':{scope_sid:1}}};selected={'target_quantities':{scope_sid:1}}
        if context['window']=='2024_2026':
            from scripts.assemble_old_continuous_inputs_v1 import exposure_gate
            from scripts.run_old_continuous_probe_v4 import admit_reviewed_dividends,admit_period_absence
            gate=exposure_gate(doc,args,selected,end,end)
            gate=admit_period_absence(admit_reviewed_dividends(gate,context['action_review'],doc['dividend_events']),context['action_review'])
            if context.get('legacy_admit'):gate=context['legacy_admit'](gate)
        else:
            from scripts.run_recent_continuous_probe import exposed_action_blockers
            gate=exposed_action_blockers(args,selected,end,context['prices'],context['action_review'],end,doc['dividend_events'])
        need(not gate['missing_action_streams'],'INDEPENDENT_REFERENCE_MISSING_STREAM')
        for event in gate['unmapped_events']:
            ok=False
            if event.get('kind')=='dividends':
                matches=[r for r in context.get('cash_review',{}).get('rows',[]) if r.get('status')=='REVIEWED_REFERENCE_ONLY_ORDINARY_CASH_DIVIDEND' and r.get('security_id')==scope_sid and r.get('ex_date')==event['date'] and event in r.get('observed_provider_events',[]) and r.get('cash_credit_authorized') is False and r.get('reference_price_adjustment')=='NONE_NOMINAL_CLOSE_RULE']
                ok=len(matches)==1
            for change in changes:
                if change['date']!=event.get('date'):continue
                if event.get('kind')=='splits':
                    payload=event['provider_payload'];ok=event.get('ticker')=='SMCI' and F(payload['numerator'])/F(payload['denominator'])==10
                elif event.get('kind')=='IDENTITY_CONVERSION':ok=event.get('old_sid')==change['old_sid'] and event.get('new_sid')==change['new_sid'] and F(event['share_ratio'])==10 and event.get('coupled_distribution') is False
            need(ok,'INDEPENDENT_REFERENCE_UNREVIEWED_ACTION')
    days=[d for d in domain['session_dates'] if start<d<=end];need(days and days[-1]==end,'INDEPENDENT_REFERENCE_DATE_RANGE')
    rows=[];sid=old
    for day in days:
        change=next((c for c in changes if c['date']==day),None)
        if change:sid=change['new_sid']
        value=domain['close_prices'].get(sid,{}).get(day);need(value is not None and F(value)>0,'INDEPENDENT_REFERENCE_PRICE_MISSING')
        rows.append(dict(date=day,security_id=sid,close=value,conversion=change))
    return dict(current_security_id=sid,completed_rows=rows)

class ReferenceOrderVerifier:
    def __init__(self,assembled,context):
        self.assembled=assembled;self.context=context;self.seen=set();self.locks={};self.count=0;self.blocked_buys=0
        self.binding=sha256(json.dumps(dict(close_prices=assembled['close_prices'],source_hashes=assembled['source_hashes']),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def verify(self,item,original,decision,active,shares):
        need(item['decision_date']==decision and item['active_date']==active,'INDEPENDENT_AUDIT_CLOCK')
        need(item['original']==original,'INDEPENDENT_ORIGINAL_PROVIDER')
        need(item['actual_shares']==shares,'INDEPENDENT_ACTUAL_SHARES')
        need(F(item['actual_cash'])==F(original['unreserved_cash']),'INDEPENDENT_ACTUAL_CASH')
        risk=original['risk_overlay']['state']
        for sid in risk.get('exited',[]):
            episode=(risk['decision_date'],sid)
            if episode in self.seen:continue
            self.seen.add(episode)
            if shares.get(sid,0)<=0:continue
            need(any(o['side']=='SELL' and o['security_id']==sid for o in original['orders']),'INDEPENDENT_EXIT_INTENT')
            price=F(self.assembled['close_prices'][sid][decision]);need(price>0,'INDEPENDENT_EXIT_PRICE')
            self.locks[sid]=dict(security_id=sid,exit_date=decision,reference_price=str(price),epoch=risk['decision_date'],reference_inputs_sha256=self.binding)
        need(item['locks_before']==self.locks,'INDEPENDENT_LOCK_BEFORE')
        buy_sids={o['security_id'] for o in original['orders'] if o['side']=='BUY'};blocked=set();expected_reviews=[]
        for old,lock in list(self.locks.items()):
            if lock['exit_date']==decision:continue
            proof=reference_path(lock,decision,buy_sids,self.context)
            if proof is None:continue
            reference=F(lock['reference_price']);restored=None
            for row in proof['completed_rows']:
                if row['conversion']:reference/=F(row['conversion']['ratio'])
                if F(row['close'])>=reference:restored=row['date'];break
            expected_reviews.append((deepcopy(lock),proof,restored))
            if restored:del self.locks[old]
            else:blocked.add(proof['current_security_id'])
        need(len(item['interval_reviews'])==len(expected_reviews),'INDEPENDENT_INTERVAL_COUNT')
        for reported,(lock,proof,restored) in zip(item['interval_reviews'],expected_reviews):
            need(reported['lock']==lock and reported['recovered_at']==restored and reported['proof']['status']=='VERIFIED' and reported['proof']['current_security_id']==proof['current_security_id'] and reported['proof']['completed_rows']==proof['completed_rows'],'INDEPENDENT_REFERENCE_PATH')
        expected=[o for o in original['orders'] if not(o['side']=='BUY' and o['security_id'] in blocked)]
        need(item['adjusted']==dict(original,orders=expected),'INDEPENDENT_BUY_FILTER_OR_SELL_MUTATION')
        need(item['locks_after']==self.locks,'INDEPENDENT_LOCK_AFTER');self.count+=1;self.blocked_buys+=len(original['orders'])-len(expected)
        return expected

def review(book,assembled,bars,*,initial_cash,dividend_events,expected_fee_bps,expected_slippage_bps,reference_context,verify_selections=True,verify_risk_provider=True):
    need(verify_selections and verify_risk_provider,'INDEPENDENT_FULL_ACCOUNT_PROOF_REQUIRED')
    entries=[a for a in book['reentry_audit'] if a.get('status')!='BLOCKED'];stage={a['decision_date']:a for a in entries};need(len(stage)==len(entries),'INDEPENDENT_DUPLICATE_AUDIT')
    local=dict(book);local['provider_audit']=[];sessions=assembled['session_dates'];executed=set(sessions[:-1]);checker=ReferenceOrderVerifier(assembled,reference_context)
    for decision,original in zip(sessions,book['provider_audit']):
        if decision in stage:
            item=stage[decision];need(item['original']==original,'INDEPENDENT_ORIGINAL_PROVIDER');local['provider_audit'].append(item['adjusted'])
        else:
            need(original.get('action')=='WAIT_POST_ACTION_MARK','INDEPENDENT_MISSING_AUDIT');local['provider_audit'].append(original)
    need(set(stage)<=executed,'INDEPENDENT_EXTRA_EXECUTION_AUDIT')
    fee,slip=F(expected_fee_bps)/10000,F(expected_slippage_bps)/10000
    checked_fills=set()
    original_check=ledger._review_risk_orders
    def checked(audit,decision,active,shares,prices,splits,targets,risk_state):
        if decision not in stage:
            need(audit.get('action')=='WAIT_POST_ACTION_MARK','INDEPENDENT_MISSING_RISK_AUDIT')
            return original_check(audit,decision,active,shares,prices,splits,targets,risk_state)
        item=stage[decision];original=item['original']
        original_check(original,decision,active,shares,prices,splits,targets,risk_state)
        expected=checker.verify(item,original,decision,active,shares)
        need(audit==dict(original,orders=expected),'INDEPENDENT_EXECUTED_AUDIT')
        index=sessions.index(decision)
        cash=F(initial_cash) if index==0 else F(book['daily_ledger'][index-1]['cash'])
        need(F(item['actual_cash'])==cash,'INDEPENDENT_ACCOUNT_CASH')
        orders=deepcopy(expected)
        for event in splits:
            if event['date']!=active:continue
            for order in orders:
                if order['security_id']!=event['security_id']:continue
                quantity=order['quantity']*F(event['new_shares'])/F(event['old_shares'])
                need(quantity.denominator==1,'INDEPENDENT_FRACTIONAL_ORDER')
                order.update(quantity=int(quantity),security_id=event.get('new_security_id',event['security_id']))
        sells=sorted((o for o in orders if o['side']=='SELL'),key=lambda o:o['id'])
        buys=sorted((o for o in orders if o['side']=='BUY'),key=lambda o:o['id'])
        for group in (sells,buys):
            cost=sum((o['quantity']*F(bars[o['security_id']][active]['open'])*(1+slip)*(1+fee) for o in group),F(0))
            scale=min(F(1),cash/cost) if cost and group is buys else F(1)
            for order in group:
                quantity=int(order['quantity']*scale)
                price=F(bars[order['security_id']][active]['open'])*(1+slip if order['side']=='BUY' else 1-slip)
                charge=quantity*price*fee
                cash+=quantity*price*(-1 if order['side']=='BUY' else 1)-charge
                logs=[r for r in book['order_log'] if r.get('event')=='ASSUMED_NEXT_OPEN_FILLED' and r.get('id')==order['id']]
                if quantity==0:need(not logs,'INDEPENDENT_ZERO_FILL_LOG');continue
                need(len(logs)==1,'INDEPENDENT_FILL_LOG_COUNT');r=logs[0]
                need(r['date']==active and r['security_id']==order['security_id'] and r['side']==order['side'] and r['quantity']==quantity and F(r['price'])==price and F(r['fee'])==charge and F(r['cash_after'])==cash,'INDEPENDENT_FILL_LOG')
                checked_fills.add(order['id'])
    with LOCK:
        try:
            ledger._review_risk_orders=checked
            proof=ledger.review(local,assembled,bars,initial_cash=initial_cash,dividend_events=dividend_events,expected_fee_bps=expected_fee_bps,expected_slippage_bps=expected_slippage_bps,verify_selections=True,verify_risk_provider=True)
        finally:ledger._review_risk_orders=original_check
    need(len(checked_fills)==len([r for r in book['order_log'] if r.get('event')=='ASSUMED_NEXT_OPEN_FILLED']),'INDEPENDENT_EXTRA_FILL_LOG')
    # Prefix compatibility callers retain trailing blocked audit; terminal locks
    # there may include the unexecuted decision and are deliberately not certified.
    if not any(a.get('status')=='BLOCKED' for a in book['reentry_audit']):need(book['reentry_locks']==checker.locks,'INDEPENDENT_TERMINAL_LOCKS')
    proof.update(independently_rebuilt_reference_sessions=checker.count,independently_rejected_buy_orders=checker.blocked_buys,reference_order_rule_verified=True)
    return proof
