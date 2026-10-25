"""Independent ordinary-dividend cash audit; no production ledger calls.

Execution is reconstructed from declared provider orders. Selection proof can be
checked separately; this is not certification of the risk/provider algorithm.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction as F
from backtest.capped_frontier_independent_review import review_selection


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def amount(value):
    require(not isinstance(value, bool), 'BOOLEAN_AMOUNT')
    value = F(str(value))
    require(value >= 0, 'NEGATIVE_AMOUNT')
    return value


def review(book, assembled, bars, *, initial_cash, dividend_events,
           initial_shares=None, verify_selections=True, expected_fee_bps, expected_slippage_bps):
    require(book['status'] == 'COMPLETE', 'COMPLETE_REQUIRED')
    require(not any(assembled.get(k) for k in ('distribution_events', 'cash_stock_merger_events')), 'CORPORATE_ACTION_UNSUPPORTED')
    sessions = assembled['session_dates']
    require(sessions == sorted(set(sessions)), 'SESSION_ORDER')
    splits = assembled.get('actions', [])
    require(all(a.get('type') == 'split' for a in splits), 'CORPORATE_ACTION_UNSUPPORTED')
    require(assembled.get('provider_actions', []) == splits, 'SPLIT_PROVIDER_ACTION_MISMATCH')
    seen_splits = set()
    for action in splits:
        require(action['date'] in sessions[1:], 'SPLIT_SESSION')
        key = (action['date'], action['security_id'])
        require(key not in seen_splits, 'DUPLICATE_SPLIT')
        seen_splits.add(key)
        require(isinstance(action.get('source_references'), list) and action['source_references']
                and all(isinstance(r, str) and r for r in action['source_references']), 'SPLIT_EVIDENCE_REQUIRED')
        require(amount(action['new_shares']) > 0 and amount(action['old_shares']) > 0, 'SPLIT_RATIO')
    events = {}
    for e in dividend_events:
        require(set(e) == {'event_id','security_id','ex_date','payment_date',
            'amount_per_share','withholding_rate','assumption','currency'}, 'EVENT_SCHEMA')
        for k in ('event_id','security_id','assumption'):
            require(isinstance(e[k],str) and bool(e[k]), 'EVENT_IDENTITY')
        for k in ('ex_date','payment_date'):
            if e[k] is not None:
                require(date.fromisoformat(e[k]).isoformat() == e[k], 'DATE_FORMAT')
        require(e['ex_date'] in sessions[1:], 'EX_SESSION')
        require((e['ex_date'], e['security_id']) not in seen_splits, 'DIVIDEND_SPLIT_SAME_DAY_UNSUPPORTED')
        require(e['payment_date'] is None or e['payment_date'] >= e['ex_date'], 'PAY_DATE')
        require(e['currency'] == 'USD', 'CURRENCY')
        require(amount(e['withholding_rate']) <= 1, 'TAX_RATE')
        amount(e['amount_per_share'])
        require(e['event_id'] not in events, 'DUPLICATE_EVENT')
        events[e['event_id']] = e
    cash = amount(initial_cash)
    shares = dict(initial_shares or {})
    require(all(type(q) is int and q >= 0 for q in shares.values()), 'QUANTITY')
    initial = cash + sum((q*amount(assembled['close_prices'][s][sessions[0]]) for s,q in shares.items()),F(0))
    require(initial > 0, 'INITIAL_EQUITY')
    peak, dd, fees = initial, F(0), F(0)
    accrued, paid = {}, {}
    rows, audits = book['daily_ledger'], book['provider_audit']
    require([r['date'] for r in rows] == sessions[1:] and len(audits)==len(rows), 'ROW_DATES')
    require(amount(book['fee_bps']) == amount(expected_fee_bps) and amount(book['slippage_bps']) == amount(expected_slippage_bps), 'EXPECTED_COSTS')
    fee, slip = amount(expected_fee_bps)/10000, amount(expected_slippage_bps)/10000
    checked_selections = 0
    expected_selection_dates = {p['decision_date'] for p in assembled.get('monthly_inputs', [])}
    observed_selection_dates = set()
    require(slip < 1, 'SLIPPAGE')
    for day, row, audit in zip(sessions[1:],rows,audits):
        for key,e in events.items():
            if e['ex_date'] == day:
                accrued[key] = shares.get(e['security_id'],0)*amount(e['amount_per_share'])*(1-amount(e['withholding_rate']))
        selected = audit.get('selection')
        if selected is not None and verify_selections:
            decision = sessions[sessions.index(day)-1]
            require(decision in expected_selection_dates and decision not in observed_selection_dates, 'SELECTION_SCHEDULE')
            observed_selection_dates.add(decision)
            checked_selections += 1
            review_selection(selected,rerank_enabled=True)
            binding = selected['raw_selection']['binding']
            require(amount(binding['available_cash']) == cash and binding['shares'] == shares, 'SELECTION_ACCOUNT')
            plan = next(p for p in assembled['monthly_inputs'] if p['decision_date'] == decision)
            require(binding['decision_date'] == decision and binding['source_hashes'] == plan['source_hashes'], 'SELECTION_SOURCE_BINDING')
            expected_search = dict(plan['search_arguments'])
            expected_search.pop('quote_as_of')
            basis = expected_search.pop('price_basis')
            capital = cash + sum((q * amount(assembled['close_prices'][sid][decision]) for sid,q in shares.items() if q), F(0))
            expected_search['entered_cash'] = str(capital)
            require(binding['search_arguments'] == expected_search, 'SELECTION_SEARCH_BINDING')
            expected_quotes = {q['security_id']: dict(price=str(F(q['price'])), as_of=q['as_of'],
                price_basis=q['price_basis'], source_references=q['source_references']) for q in plan['valuation_quotes']}
            require(binding['valuation_quotes'] == expected_quotes and all(q['price_basis'] == basis for q in expected_quotes.values()), 'SELECTION_QUOTES_BINDING')
        orders = deepcopy(audit['orders'])
        require(len({o['security_id'] for o in orders}) == len(orders), 'DUPLICATE_ORDER_SECURITY')
        for o in orders:
            require(o['active_date']==day and type(o['quantity']) is int and o['quantity']>0 and o['side'] in ('BUY','SELL'), 'ORDER')
        for action in splits:
            if action['date'] != day:
                continue
            sid = action['security_id']
            ratio = amount(action['new_shares']) / amount(action['old_shares'])
            transformed = shares.get(sid, 0) * ratio
            require(transformed.denominator == 1, 'FRACTIONAL_SPLIT_HOLDING_UNSUPPORTED')
            if shares.get(sid, 0) or any(o['security_id'] == sid for o in orders):
                shares[sid] = int(transformed)
            for order in orders:
                if order['security_id'] != sid:
                    continue
                transformed_order = order['quantity'] * ratio
                require(transformed_order.denominator == 1, 'FRACTIONAL_SPLIT_ORDER_UNSUPPORTED')
                order['quantity'] = int(transformed_order)
                if 'decision_mark' in order:
                    order['decision_mark'] = str(amount(order['decision_mark']) / ratio)
        for o in sorted((o for o in orders if o['side']=='SELL'),key=lambda o:o['id']):
            s,q=o['security_id'],o['quantity'];require(q<=shares.get(s,0),'OVERSELL')
            price=amount(bars[s][day]['open'])*(1-slip);charge=q*price*fee
            cash+=q*price-charge;fees+=charge;shares[s]-=q
        buys=sorted((o for o in orders if o['side']=='BUY'),key=lambda o:o['id'])
        cost=sum((o['quantity']*amount(bars[o['security_id']][day]['open'])*(1+slip)*(1+fee) for o in buys),F(0))
        factor=min(F(1),cash/cost) if cost else F(0)
        for o in buys:
            s=o['security_id'];q=int(o['quantity']*factor);price=amount(bars[s][day]['open'])*(1+slip);charge=q*price*fee
            cash-=q*price+charge;fees+=charge;shares[s]=shares.get(s,0)+q
        for key,net in accrued.items():
            due=events[key]['payment_date']
            if key not in paid and due is not None and due<=day:
                cash+=net;paid[key]=day
        pending=sum((v for k,v in accrued.items() if k not in paid),F(0))
        stock=sum((q*amount(bars[s][day]['close']) for s,q in shares.items() if q),F(0))
        equity=cash+stock+pending;peak=max(peak,equity);dd=max(dd,1-equity/peak)
        require(amount(row['cash'])==cash and row['shares']==shares,'CASH_SHARES')
        require(amount(row.get('receivable','0'))==0 and not row.get('distribution_rights') and not row.get('merger_entitlements'),'UNSUPPORTED_RIGHTS')
        require(amount(row.get('dividend_receivable','0'))==pending,'DIVIDEND_RECEIVABLE')
        require(amount(row['stock_value'])==stock and amount(row['equity'])==equity,'WEALTH')
    require(amount(book['cash'])==cash and book['shares']==shares and amount(book['fees'])==fees,'TERMINAL')
    require(F(book['total_return'])==equity/initial-1 and F(book['drawdown']['maximum_close_drawdown'])==dd,'PERFORMANCE')
    require(amount(book.get('receivable','0')) == 0 and amount(book['dividend_receivable']) == pending and amount(book['total_receivable']) == pending, 'TERMINAL_RECEIVABLES')
    if verify_selections:
        require(observed_selection_dates == expected_selection_dates, 'MISSING_SELECTION_PROOF')
    dl=book['dividend_ledger'];require(set(dl['events'])==set(accrued),'ACCRUAL_SET')
    for key,net in accrued.items():
        require(dl['events'][key]['event']==events[key] and amount(dl['events'][key]['net'])==net,'ACCRUAL_RECORD')
    payments=list(dl['payments'].values())
    require(len(payments)==len(paid) and {p['event_id'] for p in payments}==set(paid),'PAYMENT_SET')
    require(all(p['session_date']==paid[p['event_id']] for p in payments),'PAYMENT_TIMING')
    require(amount(dl['receivable'])==pending and amount(dl['paid_cash'])==sum((accrued[k] for k in paid),F(0)),'DIVIDEND_TOTALS')
    return dict(status='REVIEWED_ORDINARY_DIVIDEND_ACCOUNT',final_equity=str(equity),maximum_drawdown=str(dd),
        selection_proof_checked=bool(verify_selections and checked_selections), selection_proofs_checked=checked_selections,
        expected_selection_proofs=len(expected_selection_dates), costs_checked=True, ordinary_splits_checked=len(splits), fractional_split_cash_supported=False, risk_provider_certified=False)
