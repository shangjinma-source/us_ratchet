"""Integer account execution adapter: prior-close decisions, real cash ledger."""
from copy import deepcopy
from fractions import Fraction as F
from backtest.historical_dividend_ledger_research import create, accrue, pay
from docs.candidates.momentum_cash_merger_settlement_20261105 import Settlement


def need(ok,reason):
    if not ok:raise ValueError(reason)


def run_account(*, session_dates, ohlc, signals, actions, dividend_events, gate,
                initial_cash='20000', settlement_delay=0):
    days=session_dates
    need(days==sorted(set(days)) and len(days)>1,'CALENDAR')
    cash=F(initial_cash);shares={};peaks={};pending=set();stopped=set()
    dividend=create();settlement=Settlement(days,actions,settlement_delay);receivable=F(0)
    ledger=[];fills=[];audit=[];blocked=None;last_month=None;last_risk=False
    def trade(sid,side,quantity,price,day,phase,reason):
        nonlocal cash
        actual=F(price)*(F(2001,2000) if side=='BUY' else F(1999,2000))
        if side=='BUY':
            quantity=min(quantity,int(cash//actual))
            if quantity<=0:return
            cash-=quantity*actual;shares[sid]=shares.get(sid,0)+quantity
        else:
            need(0<quantity<=shares[sid],'SELL_QUANTITY')
            cash+=quantity*actual;shares[sid]-=quantity
            if not shares[sid]:del shares[sid]
        need(cash>=0,'NEGATIVE_CASH')
        fills.append(dict(date=day,phase=phase,security_id=sid,side=side,quantity=quantity,
            price=str(actual),commission='0',cash_after=str(cash),reason=reason))
    for i,day in enumerate(days[1:],1):
        previous=days[i-1]
        try:
            signal=signals[previous];weights={s:F(w) for s,w in signal['weights'].items()}
            # Reapply dated identity mapping to the frozen roster every day;
            # position quantities themselves convert only on the event day.
            for event in sorted(actions,key=lambda e:e['date']):
                if event['date']>day:continue
                old=event['security_id'];new=event.get('new_security_id',old)
                if event['type']=='merger':weights.pop(old,None)
                elif event['type'] in ('split_identity','identity_alias') and old in weights and new!=old:
                    need(new not in weights,'TARGET_IDENTITY_CONFLICT');weights[new]=weights.pop(old)
            need(len(weights)<=10 and all(0<=w<=F(1,10) for w in weights.values()),'WEIGHT_CAP')
            need(signal['decision_date']<=previous,'FUTURE_SELECTION')
            risk=signal['risk_on'];need(type(risk) is bool,'MARKET_STATE')
            month=signal['decision_date'];rebalance=month!=last_month or risk!=last_risk
            evidence=gate(previous,day,deepcopy(shares),[])
            audit.append(dict(date=day,signal_date=previous,gate=evidence))
            need(evidence['admitted'],'ACTION_GATE_BLOCKED')
            # Validate every exposed or intended bar before changing account state.
            exposed=set(shares)|(set(weights) if risk else set())
            for event in actions:
                if event['date']==day and event['security_id'] in exposed:
                    if event['type'] in ('split_identity','identity_alias'):
                        exposed.discard(event['security_id']);exposed.add(event['new_security_id'])
                    elif event['type']=='merger':
                        need(not any(k in event for k in ('share_ratio','new_security_id','stock_ratio','new_shares')), 'MIXED_MERGER_UNSUPPORTED')
                        exposed.discard(event['security_id'])
            for sid in exposed:
                for field in ('open','close'):
                    price=ohlc[sid][day][field]
                    need(not isinstance(price,bool) and F(price)>0,'INVALID_'+field.upper())
            for event in dividend_events:
                if event['ex_date']==day:
                    need(not shares.get(event['security_id'],0) or not any(a['date']==day and a['security_id']==event['security_id'] and
                                 a['type'] in ('split','split_identity','identity_alias') for a in actions),
                         'SIMULTANEOUS_DIVIDEND_UNIT_REVIEW_REQUIRED')
                    dividend=accrue(dividend,event,session_date=day,opening_quantity=shares.get(event['security_id'],0))
            for event in actions:
                if event['date']!=day:continue
                old=event['security_id'];new=event.get('new_security_id',old)
                if event['type'] in ('split','split_identity','identity_alias'):
                    ratio=F(1) if event['type']=='identity_alias' else F(event['new_shares'])/F(event['old_shares'])
                    need(ratio>0 and (new==old or new not in shares),'ACTION_IDENTITY_CONFLICT')
                    if old in shares:
                        quantity=shares.pop(old)*ratio;need(quantity.denominator==1,'FRACTIONAL_SPLIT_UNSUPPORTED');shares[new]=int(quantity)
                    if old in peaks:peaks[new]=peaks.pop(old)/ratio
                    for group in (pending,stopped):
                        if old in group:group.remove(old);group.add(new)
                    if old in weights:
                        weight=weights.pop(old);need(new not in weights,'TARGET_IDENTITY_CONFLICT');weights[new]=weight
                elif event['type']=='merger':
                    if old in shares:
                        quantity=shares.pop(old);settlement.accrue(event,quantity);receivable+=quantity*F(event['share_cash'])
                    weights.pop(old,None);peaks.pop(old,None);pending.discard(old);stopped.discard(old)
                else:need(old not in shares and old not in weights,'UNSUPPORTED_EXPOSED_ACTION')
            if month!=last_month:
                stopped.clear()
                peaks={s:F(ohlc[s][day]['open']) for s in shares}
            if rebalance:
                equity=cash+sum((q*F(ohlc[s][day]['open']) for s,q in shares.items()),F(0))
                targets={s:int(equity*w//(F(ohlc[s][day]['open'])*F(2001,2000)))
                         for s,w in weights.items() if risk and s not in stopped}
                # Monthly/market targets have OPEN priority. Pending stops
                # prohibit top-up; only the remaining shares exit at CLOSE.
                for s in pending:
                    if s in shares and s in targets:targets[s]=min(targets[s],shares[s])
                for s,q in sorted(list(shares.items())):
                    if q>targets.get(s,0):trade(s,'SELL',q-targets.get(s,0),ohlc[s][day]['open'],day,'OPEN','TARGET_CHANGE')
                for s,target in sorted(targets.items()):
                    if target>shares.get(s,0):
                        if s not in shares and len(shares)>=10:continue
                        quantity=min(target-shares.get(s,0),int(cash//(F(ohlc[s][day]['open'])*F(2001,2000))))
                        if quantity<=0:continue
                        evidence=gate(previous,day,deepcopy(shares),[dict(security_id=s,quantity=quantity)])
                        audit.append(dict(date=day,signal_date=previous,planned_entry=dict(security_id=s,quantity=quantity),gate=evidence))
                        need(evidence['admitted'],'ENTRY_ACTION_GATE_BLOCKED')
                        trade(s,'BUY',quantity,ohlc[s][day]['open'],day,'OPEN','PRIOR_CLOSE_TARGET')
                        peaks.setdefault(s,F(ohlc[s][day]['open']))
            for s in sorted(pending):
                if s in shares:
                    trade(s,'SELL',shares[s],ohlc[s][day]['close'],day,'CLOSE','PRIOR_CLOSE_STOP')
                    stopped.add(s)
                peaks.pop(s,None)
            pending=set()
            for s in shares:
                close=F(ohlc[s][day]['close']);need(close>0,'INVALID_CLOSE')
                peaks[s]=max(peaks.get(s,close),close)
                if close<=peaks[s]*F(4,5):pending.add(s)
            paid=F(dividend['paid_cash']);already={p['event_id'] for p in dividend['payments'].values()}
            for key,record in list(dividend['events'].items()):
                due=record['event']['payment_date']
                if key not in already and due is not None and due<=day:
                    dividend=pay(dividend,event_id=key,payment_id='research:'+key,session_date=day)
            cash+=F(dividend['paid_cash'])-paid;cash,receivable=settlement.close(day,cash,receivable)
            equity=cash+receivable+F(dividend['receivable'])+sum((q*F(ohlc[s][day]['close']) for s,q in shares.items()),F(0))
            ledger.append(dict(date=day,cash=str(cash),shares=deepcopy(shares),equity=str(equity),
                dividend_receivable=dividend['receivable'],merger_receivable=str(receivable),pending=sorted(pending)))
            last_month=month;last_risk=risk
        except (ValueError,KeyError,TypeError,ZeroDivisionError) as error:
            blocked=dict(date=day,error=str(error));break
    return dict(status='BLOCKED' if blocked else 'COMPLETE',reason=blocked,daily_ledger=ledger,
        order_log=fills,provider_audit=audit,dividend_ledger=dividend,initial_cash=str(initial_cash),
        commission='0_USER_AUTHORIZED_RESEARCH_ASSUMPTION',slippage_bps='5',production_activated=False)
