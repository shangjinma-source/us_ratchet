"""Pure conditional paper DAY plan; no strategy approval, IO or account mutation."""
from datetime import date
from fractions import Fraction
import hashlib
import json
import re


def build_current_research_limit_plan(*, research_snapshot, quotes, available_cash, shares,
                                     account_revision, decision_date, active_date,
                                     calendar, strategy_version, target_quantities):
    """Snapshot: research_id/as_of/stocks[{security_id,ticker,close}]/source_hashes.

    quotes separately bind execution reference prices and may postdate selection.
    Direct differences preserve supplied frozen integer targets: no weight
    roundtrip, new optimization, or rescaling to changing available cash.
    """
    flags = dict(research_only=True, execution_blocked=True, adopted=False,
                 role='CONDITIONAL_PAPER_PLAN_NOT_STRATEGY_APPROVAL',
                 fee_scope=dict(commission_bps='0', commission_basis='USER_CONFIRMED',
                                other_fees='UNKNOWN_NOT_MODELLED', all_transaction_costs_zero=False))
    def blocked(reason):
        return dict(flags, status='BLOCKED', reason=reason, orders=[], plan_id=None)
    def money(value):
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Fraction)):
            raise ValueError('INVALID_MONEY_TYPE')
        parsed = Fraction(str(value))
        if parsed < 0:
            raise ValueError('NEGATIVE_MONEY')
        return parsed
    def quantities(value):
        if not isinstance(value, dict) or any(not isinstance(s, str) or not s.strip() or type(q) is not int or q < 0 for s,q in value.items()):
            raise ValueError('INVALID_WHOLE_SHARE_MAP')
        return dict(value)
    try:
        if not isinstance(calendar, list) or calendar != sorted(set(calendar)) or len(calendar)<2:
            raise ValueError('INVALID_EXPLICIT_CALENDAR')
        if any(type(d) is not str or date.fromisoformat(d).isoformat()!=d for d in calendar):
            raise ValueError('INVALID_SESSION_DATE')
        index = calendar.index(decision_date)
        if index+1 >= len(calendar) or calendar[index+1] != active_date:
            raise ValueError('ACTIVE_DATE_NOT_NEXT_SESSION')
        selection_date=research_snapshot['as_of']
        if type(selection_date) is not str or date.fromisoformat(selection_date).isoformat()!=selection_date or selection_date>decision_date:
            raise ValueError('INVALID_OR_FUTURE_SELECTION_DATE')
        research_id = research_snapshot['research_id']
        if not isinstance(research_id,str) or not re.fullmatch(r'[0-9a-f]{24}',research_id):
            raise ValueError('INVALID_RESEARCH_ID')
        if any(not isinstance(v,str) or not v.strip() for v in (account_revision,strategy_version)):
            raise ValueError('EXPLICIT_ACCOUNT_AND_STRATEGY_VERSION_REQUIRED')
        pins = research_snapshot['source_hashes']
        if not isinstance(pins,dict) or not pins or any(not isinstance(p,str) or not p.strip() or not isinstance(h,str) or not re.fullmatch(r'[0-9a-f]{64}',h) for p,h in pins.items()):
            raise ValueError('EXPLICIT_SOURCE_PINS_REQUIRED')
        prices, tickers, quote_evidence = {}, {}, {}
        stocks=research_snapshot['stocks']
        if not isinstance(stocks,list):
            raise ValueError('EXPLICIT_STOCK_PRICE_ROWS_REQUIRED')
        for stock in stocks:
            sid,ticker=stock['security_id'],stock['ticker']
            if not isinstance(sid,str) or not sid.strip() or sid in tickers:
                raise ValueError('DUPLICATE_OR_INVALID_SECURITY_ID')
            if not isinstance(ticker,str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,14}',ticker) or ticker in tickers.values():
                raise ValueError('DUPLICATE_OR_INVALID_TICKER')
            tickers[sid]=ticker
        if not isinstance(quotes,list):raise ValueError('EXPLICIT_QUOTE_ROWS_REQUIRED')
        for quote in quotes:
            sid=quote['security_id']
            if not isinstance(sid,str) or not sid.strip() or sid in prices:raise ValueError('DUPLICATE_OR_INVALID_QUOTE_ID')
            if quote['as_of']!=decision_date:raise ValueError('STALE_OR_FUTURE_PRICE_QUOTE')
            if not isinstance(quote['price'],str) or not re.fullmatch(r'\d+(?:\.\d+)?',quote['price']):raise ValueError('EXPLICIT_DECIMAL_QUOTE_REQUIRED')
            if quote['price_kind'] not in ('CENT_DISPLAY_REFERENCE','RAW_PROVIDER_CLOSE_DECIMAL','PROVIDER_REGULAR_MARKET_PRICE_DECIMAL','DECLARED_DECIMAL_REFERENCE'):raise ValueError('EXPLICIT_PRICE_KIND_REQUIRED')
            if not isinstance(quote['price_basis'],str) or not quote['price_basis'].strip():raise ValueError('PRICE_BASIS_REQUIRED')
            refs=quote['source_references']
            if not isinstance(refs,list) or not refs or any(not isinstance(r,str) or not r.strip() for r in refs):raise ValueError('QUOTE_SOURCE_REFERENCES_REQUIRED')
            if any(reference not in pins for reference in refs):
                raise ValueError('QUOTE_SOURCE_NOT_PINNED')
            price=money(quote['price'])
            if price<=0:
                raise ValueError('NONPOSITIVE_CLOSE')
            prices[sid]=price
            quote_evidence[sid]=dict(price=quote['price'],as_of=quote['as_of'],price_kind=quote['price_kind'],price_basis=quote['price_basis'],source_references=list(refs))
        cash=money(available_cash);held=quantities(shares);target=quantities(target_quantities)
        needed={s for mapping in (held,target) for s,q in mapping.items() if q}
        if not needed<=set(prices) or not needed<=set(tickers):
            raise ValueError('HELD_OR_TARGET_PRICE_MISSING')
        equity=cash+sum((q*prices[s] for s,q in held.items() if q),Fraction(0))
        target_value=sum((q*prices[s] for s,q in target.items() if q),Fraction(0))
        causal=dict(schema='CONDITIONAL_RESEARCH_DAY_PLAN_V1',research_id=research_id,
            research_snapshot=json.loads(json.dumps(research_snapshot,sort_keys=True,allow_nan=False)),
            selection_as_of=selection_date,price_as_of=decision_date,source_hashes=dict(sorted(pins.items())),
            securities=dict(sorted(tickers.items())),quotes={s:quote_evidence[s] for s in sorted(quote_evidence)},
            available_cash=str(cash),shares=dict(sorted(held.items())),target_quantities=dict(sorted(target.items())),
            account_revision=account_revision,decision_date=decision_date,active_date=active_date,
            calendar=list(calendar),strategy_version=strategy_version,fee_scope=flags['fee_scope'])
        plan_id=hashlib.sha256(json.dumps(causal,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        orders,deficits,waiting=[],[],[]
        def order(s,side,q,limit):
            return dict(order_id=f'{plan_id}:{s}:{side}',security_id=s,ticker=tickers[s],side=side,
                quantity=q,limit=str(limit),decision_date=decision_date,active_date=active_date,
                expires_session=active_date,time_in_force='DAY')
        for sid in sorted(set(held)|set(target)):
            delta=target.get(sid,0)-held.get(sid,0)
            if not delta:continue
            close=prices[sid]
            limit=Fraction(close*100//1,100) if delta>0 else Fraction(-(-close*100//1),100)
            if limit<=0:raise ValueError('NONPOSITIVE_CENT_LIMIT')
            if delta<0:orders.append(order(sid,'SELL',-delta,limit))
            else:deficits.append((delta*limit,sid,delta,limit))
        remaining=cash
        for _,sid,delta,limit in sorted(deficits,key=lambda row:(-row[0],row[1])):
            q=min(delta,int(remaining//limit))
            if q:orders.append(order(sid,'BUY',q,limit));remaining-=q*limit
            if q<delta:waiting.append(dict(security_id=sid,remaining_deficit=delta-q,reason='WAIT_CASH'))
        return dict(flags,status='READY',plan_id=plan_id,research_id=research_id,
            strategy_version=strategy_version,account_revision=account_revision,
            signal_asof=decision_date,active_date=active_date,expires_session=active_date,time_in_force='DAY',
            available_cash=str(cash),reserved_cash=str(cash-remaining),unreserved_cash=str(remaining),
            investable_equity=str(equity),target_notional=str(target_value),target_quantities=target,
            target_affordable_at_reference=target_value<=equity,
            orders=orders,wait_cash=waiting,action='ORDERS' if orders else 'WAIT_CASH' if waiting else 'NO_ACTION',
            causal_inputs=causal,limitations=['Session expiry only; market timezone/cutoff must be supplied before any live use.',
                'Source pins are declared inputs; this pure function does not authenticate source bytes.',
                'Unpaid rights excluded; unknown other fees are not reserved; sell proceeds never finance planned buys.'])
    except (KeyError,TypeError,ValueError,ZeroDivisionError,OverflowError) as error:
        return blocked(str(error))
