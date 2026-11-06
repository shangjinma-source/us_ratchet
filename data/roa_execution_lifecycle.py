"""Persisted ROA event lifecycle; no fills, cash changes, or broker orders inferred."""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
from core.strategy_account_difference import require,timestamp


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def positive(value):
    require(type(value) in (str,int),'EXACT_PRICE_REQUIRED')
    result=F(value);require(result>0,'POSITIVE_PRICE_REQUIRED');return result


class RoaExecutionLifecycle:
    def __init__(self, *, path, account_id, strategy_epoch, contract_sha256):
        self.path=Path(path);self.account_id=account_id;self.epoch=strategy_epoch;self.contract=contract_sha256
        self.lock=RLock()

    def read(self):
        if not self.path.exists():
            return dict(schema='ROA_LIFECYCLE_V1',account_id=self.account_id,strategy_epoch=self.epoch,
                contract_sha256=self.contract,version=0,decision_date=None,risk_on=None,peaks={},stopped=[],pending=[],events=[])
        require(not self.path.is_symlink(),'LIFECYCLE_SYMLINK')
        document=json.loads(self.path.read_text(encoding='utf8'));state=document['state']
        require(digest(state)==document['sha256'],'LIFECYCLE_HASH')
        require((state['account_id'],state['strategy_epoch'],state['contract_sha256'])==
            (self.account_id,self.epoch,self.contract),'LIFECYCLE_SCOPE')
        return state

    def _save(self,state):
        state=deepcopy(state);state['version']+=1
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_suffix('.new')
        require(not self.path.is_symlink() and not temporary.is_symlink(),'LIFECYCLE_SYMLINK')
        temporary.write_text(json.dumps({'state':state,'sha256':digest(state)},sort_keys=True),encoding='utf8')
        temporary.replace(self.path)
        return deepcopy(state)

    def plan(self, *, signal, session, open_at, open_until, close_at, close_until):
        """Server-verified prior-close signal. Does not pretend opening prices exist."""
        require(signal['signal_date']<session and signal['decision_date']<=signal['signal_date'],'FUTURE_SIGNAL')
        require(type(signal['risk_on']) is bool,'MARKET_STATE')
        weights=signal['weights'];require(len(weights)<=10 and all(0<=F(w)<=F(1,10) for w in weights.values()),'WEIGHT_CAP')
        require(timestamp(open_at)<timestamp(open_until)<=timestamp(close_at)<timestamp(close_until),'PHASE_WINDOWS')
        with self.lock:
            state=self.read()
            reason='STRATEGY_ACTIVATION' if state['risk_on'] is None else 'MONTHLY_TARGET' if state['decision_date']!=signal['decision_date'] else 'MARKET_SWITCH' if state['risk_on']!=signal['risk_on'] else None
            phases=[]
            if reason:phases.append(('OPEN',reason,open_at,open_until))
            if any(s not in state.get('missed_exits',[]) for s in state['pending']):phases.append(('CLOSE','PRIOR_CLOSE_STOP',close_at,close_until))
            for phase,why,start,end in phases:
                event=dict(strategy_epoch=self.epoch,contract_sha256=self.contract,signal_id=signal['signal_id'],
                    signal_date=signal['signal_date'],decision_date=signal['decision_date'],session=session,
                    phase=phase,reason=why,valid_from=start,valid_until=end,risk_on=signal['risk_on'],
                    weights=deepcopy(weights),pending=[s for s in state['pending'] if s not in state.get('missed_exits',[])],targets=None,materialized_revision=None)
                event['event_id']=digest(event)
                # Refreshing the same signal never creates another allocation.
                if not any(e['event_id']==event['event_id'] for e in state['events']):state['events'].append(event)
            return self._save(state) if phases and state!=self.read() else state

    def materialize_open(self, *, event_id, account, opening_prices, now):
        with self.lock:
            state=self.read();event=next(e for e in state['events'] if e['event_id']==event_id)
            require(event['phase']=='OPEN','OPEN_EVENT_REQUIRED')
            require(timestamp(event['valid_from'])<=timestamp(now)<timestamp(event['valid_until']),'OPEN_PHASE_MISSED')
            require(account['account_id']==self.account_id and account['cash_confirmation_valid'],'ACCOUNT_CASH_REQUIRED')
            if event['targets'] is not None:return deepcopy(event)
            held=account['shares'];needed={s for s,q in held.items() if q}|(set(event['weights']) if event['risk_on'] else set())
            require(needed<=set(opening_prices),'OPENING_PRICES_REQUIRED')
            prices={s:positive(opening_prices[s]) for s in needed}
            equity=F(account['total_uninvested_cash'])+sum((q*prices[s] for s,q in held.items() if q),F(0))
            require(equity>0,'POSITIVE_TRADABLE_EQUITY_REQUIRED')
            newmonth=state['decision_date']!=event['decision_date']
            if newmonth:state['stopped']=[]
            targets={s:int(equity*F(w)//(prices[s]*F(2001,2000))) for s,w in event['weights'].items()
                if event['risk_on'] and s not in state['stopped']}
            for s in state['pending']:
                if s in held and s in targets:targets[s]=min(targets[s],held[s])
            event['targets']=targets;event['materialized_revision']=account['revision'];event['opening_prices']={s:str(p) for s,p in prices.items()}
            event['materialized_at']=now
            if newmonth:state['peaks']={s:str(prices[s]) for s,q in held.items() if q}
            state['decision_date']=event['decision_date'];state['risk_on']=event['risk_on']
            self._save(state);return deepcopy(event)

    def close_observation(self, *, session, shares, closing_prices):
        """Trusted completed session only; actual holdings determine stop completion."""
        with self.lock:
            state=self.read()
            require(state.get('last_close') is None or session>=state['last_close'],'CLOSE_ORDER')
            if state.get('last_close')==session:
                require(state.get('close_shares')=={s:q for s,q in shares.items() if q},'CLOSE_ACCOUNT_CHANGED_REVIEW_REQUIRED')
                return state
            for event in state['events']:
                if event['phase']=='CLOSE' and event['session']==session:
                    for sid in event['pending']:
                        # A completed real exit, not a hypothetical order.
                        if shares.get(sid,0)==0 and not any(e['phase']=='OPEN' and e['session']==session and e['risk_on'] is False for e in state['events']):
                            if sid not in state['stopped']:state['stopped'].append(sid)
            missed={s for s in state.get('missed_exits',[]) if shares.get(s,0)>0}
            for event in state['events']:
                if event['phase']=='CLOSE' and event['session']<=session:
                    completed=set(event.get('completed_sids',[]))
                    completed.update(s for s in event['pending'] if shares.get(s,0)==0)
                    event['completed_sids']=sorted(completed)
                    missed.update(s for s in event['pending'] if s not in completed and shares.get(s,0)>0)
            pending=list(missed);peaks={}
            for sid,quantity in shares.items():
                if not quantity:continue
                close=positive(closing_prices[sid])
                opening=[e['opening_prices'][sid] for e in state['events'] if e['phase']=='OPEN' and e['session']==session and (e.get('targets') or {}).get(sid,0)>0 and sid in e.get('opening_prices',{})]
                starting=F(state['peaks'].get(sid,opening[-1] if opening else str(close)))
                peak=max(starting,close)
                peaks[sid]=str(peak)
                if close<=peak*F(4,5) and sid not in pending:pending.append(sid)
            state.update(peaks=peaks,pending=sorted(pending),missed_exits=sorted(missed),last_close=session,close_shares={s:q for s,q in shares.items() if q})
            return self._save(state)

    def event_view(self, *, now):
        state=self.read();events=state['events']
        if not events:return dict(status='WAIT_SIGNAL',phase=None,event=None,executable=False)
        current=events[-1]
        # OPEN takes precedence until its window ends when both phases exist.
        for event in reversed(events):
            if event['session']==current['session'] and event['phase']=='OPEN' and timestamp(now)<timestamp(event['valid_until']):current=event;break
        if timestamp(now)<timestamp(current['valid_from']):status='PENDING_'+current['phase']
        elif timestamp(now)>=timestamp(current['valid_until']):status='MISSED'
        else:status='WINDOW_OPEN'
        return dict(status=status,phase=current['phase'],event=deepcopy(current),executable=False)
