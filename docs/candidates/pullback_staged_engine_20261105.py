"""Fixed staged proxy: initial stop until 3R; remainder trails from next session."""
from copy import deepcopy
from fractions import Fraction as F
from backtest.historical_dividend_ledger_research import create,accrue,pay
from docs.candidates.momentum_cash_merger_settlement_20261105 import Settlement

def need(ok,reason):
    if not ok:raise ValueError(reason)

def run_account(*,session_dates,ohlc,signals,actions,dividend_events,gate,variant,settlement_delay=0,initial_cash='20000'):
    need(variant=='staged_3r','FIXED_VARIANT')
    days=session_dates;need(days==sorted(set(days)) and len(days)>1,'CALENDAR')
    cash=F(initial_cash);positions={};dividends=create();merger=F(0);settlement=Settlement(days,actions,settlement_delay)
    ledger=[];fills=[];audit=[];peak=cash;drawdown=F(0);blocked=None
    dividends_by_day={}
    for e in dividend_events:
        accrue(create(),e,session_date=e['ex_date'],opening_quantity=0)
        dividends_by_day.setdefault(e['ex_date'],[]).append(e)
    def close_position(s,quantity,price,day,reason,phase):
        nonlocal cash
        need(type(quantity) is int and 0<quantity<=positions[s]['quantity'],'SELL_QUANTITY')
        actual=F(price)*F(1999,2000);cash+=quantity*actual;positions[s]['quantity']-=quantity
        fills.append(dict(date=day,security_id=s,side='SELL',quantity=quantity,price=str(actual),fee='0',cash_after=str(cash),reason=reason,phase=phase))
        if positions[s]['quantity']==0:del positions[s]
    for index,day in enumerate(days[1:],1):
        previous=days[index-1];signal=signals[previous];entries=deepcopy(signal['entries']);eligible=set(signal.get('effective_eligible',signal['eligible']))
        prior_equity=cash+sum((p['quantity']*F(ohlc[s][previous]['close']) for s,p in positions.items()),F(0))
        try:
            # Unknown source/action coverage stops before creating an entitlement or order.
            evidence=gate(previous,day,{s:p['quantity'] for s,p in positions.items()},[])
            audit.append(dict(decision_date=previous,active_date=day,gate=evidence,signal=signal,tradable_equity=str(prior_equity)))
            need(evidence['admitted'],'ACTION_GATE:'+previous)
            for e in dividends_by_day.get(day,[]):dividends=accrue(dividends,e,session_date=day,opening_quantity=positions.get(e['security_id'],{}).get('quantity',0))
            # Tighten solely with the completed prior bar; a close-known stop acts next session.
            for s,p in positions.items():
                if p.get('profit_stage',False) and s in signal['ema9']:p['stop']=max(p['stop'],F(signal['ema9'][s]))
            for e in actions:
                if e['date']!=day:continue
                s=e['security_id']
                if e['type']=='merger':
                    if s in positions:settlement.accrue(e,positions[s]['quantity']);merger+=positions[s]['quantity']*F(e['share_cash']);del positions[s]
                    entries=[x for x in entries if x['security_id']!=s]
                elif e['type'] in ('split','split_identity'):
                    ratio=F(e['new_shares'])/F(e['old_shares']);n=e.get('new_security_id',s)
                    if s in positions:
                        p=positions.pop(s);q=p['quantity']*ratio;need(q.denominator==1 and n not in positions,'SPLIT_POSITION_CONFLICT');p['quantity']=int(q)
                        for field in ('stop','entry','risk_per_share','take_profit'):p[field]/=ratio
                        positions[n]=p
                    for entry in entries:
                        if entry['security_id']==s:entry['security_id']=n;entry['stop']=str(F(entry['stop'])/ratio)
                    if s in eligible:eligible.remove(s);eligible.add(n)
                else:
                    need(s not in positions and all(x['security_id']!=s for x in entries),'UNSUPPORTED_EXPOSED_ACTION')
            # Open gap exits fund only later opening entries, never retroactive day-low exits.
            stopped=set()
            for s in sorted(list(positions)):
                opening=F(ohlc[s][day]['open']);p=positions[s]
                if s not in eligible or opening<=p['stop']:
                    close_position(s,p['quantity'],opening,day,'DOMAIN_EXIT' if s not in eligible else 'STOP_GAP','OPEN');stopped.add(s)
            open_budget=cash
            entries.sort(key=lambda x:(-F(x['rank_return']),x['security_id']))
            for entry in entries:
                s=entry['security_id']
                if s in positions or s in stopped or len(positions)>=10:continue
                issuer=entry.get('issuer_id',s)
                if any(p.get('issuer_id')==issuer for p in positions.values()):continue
                opening=F(ohlc[s][day]['open']);stop=F(entry['stop']);distance=opening-stop
                if not 0<distance<=opening*F(3,100):continue
                price=opening*F(2001,2000)
                # Include entry/stop slippage in planned risk; gaps can still exceed it.
                risk=price-stop*F(1999,2000)
                quantity=min(int(prior_equity*F(1,200)//risk),int(open_budget//price))
                if quantity<=0:continue
                planned={**entry,'quantity':quantity}
                entry_evidence=gate(previous,day,{k:v['quantity'] for k,v in positions.items()},[planned])
                audit.append(dict(decision_date=previous,active_date=day,phase='ACTUAL_PLANNED_ENTRY',planned_entry=planned,gate=entry_evidence,tradable_equity=str(prior_equity)))
                need(entry_evidence['admitted'],'ENTRY_ACTION_GATE:'+previous+':'+s)
                cash-=quantity*price;open_budget-=quantity*price
                positions[s]=dict(quantity=quantity,entry=price,stop=stop,risk_per_share=risk,take_profit=price+3*risk,partial_taken=False,profit_stage=False,issuer_id=issuer)
                fills.append(dict(date=day,security_id=s,side='BUY',quantity=quantity,price=str(price),fee='0',cash_after=str(cash),reason='PRIOR_BAR_PULLBACK',phase='OPEN',initial_stop=str(stop),planned_risk=str(quantity*risk)))
            # OHLC cannot establish high/low ordering: stop wins every ambiguous bar.
            for s in sorted(list(positions)):
                p=positions[s];bar=ohlc[s][day];low=F(bar['low']);high=F(bar['high']);opening=F(bar['open'])
                need(low<=min(opening,F(bar['close']))<=max(opening,F(bar['close']))<=high,'INVALID_BAR')
                if low<=p['stop']:
                    close_position(s,p['quantity'],min(opening,p['stop']),day,'STOP_INTRADAY','INTRADAY_STOP_FIRST')
                elif variant=='staged_3r' and not p['profit_stage'] and high>=p['take_profit']:
                    q=p['quantity']//2
                    if q:close_position(s,q,p['take_profit'],day,'HALF_3R','INTRADAY_AFTER_STOP_CHECK')
                    if s in positions:
                        positions[s]['profit_stage']=True
                        positions[s]['partial_taken']=bool(q)
            paid_before=F(dividends['paid_cash']);already={p['event_id'] for p in dividends['payments'].values()}
            for key,record in list(dividends['events'].items()):
                due=record['event']['payment_date']
                if key not in already and due is not None and due<=day:dividends=pay(dividends,event_id=key,payment_id='research:'+key,session_date=day)
            cash+=F(dividends['paid_cash'])-paid_before;cash,merger=settlement.close(day,cash,merger)
            stock=sum((p['quantity']*F(ohlc[s][day]['close']) for s,p in positions.items()),F(0));equity=cash+stock+merger+F(dividends['receivable']);peak=max(peak,equity);drawdown=max(drawdown,1-equity/peak)
            need(cash>=0 and len(positions)<=10,'CASH_POSITION_CAP')
            ledger.append(dict(date=day,cash=str(cash),shares={s:p['quantity'] for s,p in positions.items()},positions=deepcopy(positions),stock_value=str(stock),merger_receivable=str(merger),dividend_receivable=dividends['receivable'],equity=str(equity)))
        except (ValueError,KeyError,TypeError,ZeroDivisionError) as error:blocked=dict(date=day,error=str(error));break
    return dict(status='BLOCKED' if blocked else 'COMPLETE',reason=blocked,variant=variant,settlement_delay=settlement_delay,initial_cash=str(initial_cash),daily_ledger=ledger,order_log=fills,provider_audit=audit,dividend_ledger=dividends,merger_releases=settlement.log,maximum_drawdown=str(drawdown),total_return=str(F(ledger[-1]['equity'])/F(initial_cash)-1) if ledger and not blocked else None,limitations=['Daily OHLC proxy; simultaneous triggers conservatively stop first. No minute execution guarantee.','Risk .5% is planned adverse-fill risk, not a cap on gap losses. No shorting or margin.','No volume/marketcap filter unless separately source-certified.'])
