"""Fixed historical reentry research; no production integration."""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json


def need(ok, why):
    if not ok:raise ValueError(why)


class ReentryRepair:
    def __init__(self, *, close_prices, verify_interval, source_hashes=None):
        need(callable(verify_interval),'REFERENCE_COVERAGE_REQUIRED')
        self.prices=close_prices;self.verify_interval=verify_interval
        self.reference_binding=sha256(json.dumps(dict(close_prices=close_prices,source_hashes=source_hashes or {}),sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.locks={};self.seen=set();self.audit=[]

    def adjust(self,result,*,state,decision_date,active_date):
        out=deepcopy(result)
        if result.get('status')!='READY':return out
        rs=result.get('risk_overlay',{}).get('state',{})
        for sid in rs.get('exited',[]):
            key=(rs['decision_date'],sid)
            if key in self.seen:continue
            self.seen.add(key)
            if state['shares'].get(sid,0)<=0:continue
            need(any(o['security_id']==sid and o['side']=='SELL' for o in result.get('orders',[])), 'EXIT_INTENT_REQUIRED')
            price=F(self.prices[sid][decision_date]);need(price>0,'EXIT_REFERENCE_PRICE')
            self.locks[sid]=dict(security_id=sid,exit_date=decision_date,reference_price=str(price),epoch=rs['decision_date'],reference_inputs_sha256=self.reference_binding)
        before=deepcopy(self.locks);reviews=[]
        # Each potentially affected BUY must certify old and successor identity
        # paths, even when the old SID has been absent from positions for months.
        buys={o['security_id'] for o in result.get('orders',[]) if o['side']=='BUY'}
        for old,lock in list(self.locks.items()):
            if lock['exit_date']==decision_date:continue
            proof=self.verify_interval(deepcopy(lock),decision_date,buys)
            need(proof.get('status') in ('VERIFIED','NOT_CURRENT_BUY'),'REFERENCE_COVERAGE_NOT_VERIFIED')
            if proof['status']=='NOT_CURRENT_BUY':continue
            rows=proof['completed_rows'];need(rows and rows[-1]['date']==decision_date,'REFERENCE_INTERVAL_INCOMPLETE')
            ref=F(lock['reference_price']);sid=old;recovered=None;last=lock['exit_date']
            for row in rows:
                need(last<row['date']<=decision_date,'REFERENCE_CAUSAL_ORDER');last=row['date']
                if row.get('conversion'):
                    c=row['conversion'];need(c['old_sid']==sid and c['kind']=='REVIEWED_INTEGER_SPLIT','REFERENCE_CONVERSION_UNSUPPORTED')
                    ratio=F(c['ratio']);need(ratio>0 and ratio.denominator==1,'REFERENCE_SPLIT_RATIO')
                    ref/=ratio;sid=c['new_sid']
                need(row['security_id']==sid and F(row['close'])>0,'REFERENCE_PRICE_IDENTITY')
                if F(row['close'])>=ref:recovered=row['date'];break
            reviews.append(dict(lock=lock,proof=proof,recovered_at=recovered))
            if recovered:del self.locks[old]
            # Keep original coordinates until next full interval review, avoiding
            # double split conversion or erasing evidence while still locked.
        blocked=set()
        for review in reviews:
            if review['recovered_at'] is None:blocked.add(review['proof']['current_security_id'])
        out['orders']=[o for o in out.get('orders',[]) if not(o['side']=='BUY' and o['security_id'] in blocked)]
        self.audit.append(dict(decision_date=decision_date,active_date=active_date,actual_cash=state.get('cash'),actual_shares=deepcopy(state['shares']),original=deepcopy(result),adjusted=deepcopy(out),locks_before=before,locks_after=deepcopy(self.locks),interval_reviews=reviews))
        return out

def run_reentry(*,assembled,verify_interval,selector,decision_callback=None,baseline=False,execution_guard=None,**kwargs):
    """Dedicated-process hook; original risk and kernel remain unchanged."""
    from backtest import historical_dividend_frontier_research as f
    need(not kwargs.get('verified_prefix'),'EXACT_ARGUMENT_SELECTOR_CACHE_REQUIRED')
    engine=ReentryRepair(close_prices=assembled['close_prices'],verify_interval=verify_interval,source_hashes=assembled['source_hashes'])
    old=(f.decide_continuous_guided_for_account,f.rerank,f.run_next_open_book);arguments={}
    def select(**args):
        arguments[args['decision_date']]=deepcopy(args)
        return selector(**args)
    def rerank(raw):
        selected=old[1](raw)
        if decision_callback:decision_callback(deepcopy(arguments[raw['decision_date']]),deepcopy(selected))
        return selected
    def book(**args):
        original=args['order_provider']
        def provider(**state):
            result={}
            try:
                if execution_guard:execution_guard()
                result=original(**state)
                if execution_guard:execution_guard()
                if baseline:return result
                return engine.adjust(result,**state)
            except (ValueError,KeyError,TypeError) as error:
                engine.audit.append(dict(decision_date=state['decision_date'],status='BLOCKED',reason=str(error),locks=deepcopy(engine.locks)))
                return dict(status='BLOCKED',orders=[],reason=str(error),underlying_provider=result)
        args['order_provider']=provider
        return old[2](**args)
    try:
        f.decide_continuous_guided_for_account=select;f.rerank=rerank;f.run_next_open_book=book
        output=f.run_frontier_capped_next_open(assembled=assembled,**kwargs)
    finally:f.decide_continuous_guided_for_account,f.rerank,f.run_next_open_book=old
    output['reentry_audit']=engine.audit;output['reentry_locks']=engine.locks;output['reentry_research_only']=True
    return output
