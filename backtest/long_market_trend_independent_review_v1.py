"""Independent trend decision dispatch and complete supported-account reconstruction."""
from fractions import Fraction as F
from hashlib import sha256
import json
from backtest.capped_frontier_independent_review import review_selection as original_review_selection
from backtest.long_market_trend_research_v1 import OFF_SCHEMA


def review_trend_decision(selection, *, arguments, signal_input, signal_source_hashes):
    rows = signal_input['completed_month_end_prices']
    dates = [row['date'] for row in rows]
    if len(rows)!=10 or dates!=sorted(set(dates)) or dates[-1]!=arguments['decision_date']:
        raise ValueError('REVIEW_SIGNAL_DATES')
    months=[date.fromisoformat(day).year*12+date.fromisoformat(day).month for day in dates]
    if months!=list(range(months[0],months[0]+10)):raise ValueError('REVIEW_CONSECUTIVE_MONTHS')
    if any(isinstance(row['close'],bool) or not row['source'] for row in rows):raise ValueError('REVIEW_SIGNAL_SOURCE_PRICE')
    values=[F(str(row['close'])) for row in rows]
    if any(value<=0 for value in values):raise ValueError('REVIEW_SIGNAL_PRICE')
    on=10*values[-1]>sum(values)
    expected_proof=dict(decision_date=arguments['decision_date'],rule='QQQ_MONTH_END_CLOSE_GT_10_MONTH_SMA_PRICE',completed_month_end_prices=rows,average=str(sum(values)/10),last_close=str(values[-1]),risk_on=on)
    if any(row['source'] not in signal_source_hashes for row in rows):raise ValueError('SIGNAL_SOURCE_PIN')
    if on:
        if selection.get('trend_signal')!=expected_proof or selection.get('trend_signal_source_hashes')!=signal_source_hashes:raise ValueError('ON_SIGNAL_PROOF')
        if selection.get('schema')==OFF_SCHEMA:raise ValueError('OFF_ON_POSITIVE_TREND')
        return original_review_selection(selection,rerank_enabled=True)
    if selection.get('schema')!=OFF_SCHEMA:raise ValueError('OFF_SCHEMA_REQUIRED')
    binding=selection['binding']; proof=binding['signal']
    if binding['arguments']!=arguments or proof['completed_month_end_prices']!=rows:
        raise ValueError('OFF_ARGUMENT_BINDING')
    if binding.get('signal_source_hashes')!=signal_source_hashes or proof!=expected_proof:raise ValueError('OFF_SIGNAL_SOURCE_PIN')
    if proof['risk_on'] is not False or F(proof['average'])!=sum(values)/10 or F(proof['last_close'])!=values[-1]:
        raise ValueError('OFF_SIGNAL_PROOF')
    encoded=json.dumps(binding,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    if sha256(encoded.encode()).hexdigest()!=selection['decision_id']:raise ValueError('OFF_DECISION_HASH')
    quotes={row['security_id']:row for row in arguments['valuation_quotes']}; account=arguments['account_state']
    capital=F(account['cash'])+sum((quantity*F(quotes[sid]['price']) for sid,quantity in account['shares'].items() if quantity),F(0))
    if selection['target_quantities']!={} or selection['optimizer_calls']!=0 or F(selection['investable_equity'])!=capital:
        raise ValueError('OFF_TARGET_OR_CAPITAL')
    return dict(target_quantities={},status='OFF_DECISION_REVIEW_PASS',optimizer_calls=0)


"""Independent dividend audit plus integer identity split with same-day full liquidation.

Execution is reconstructed independently. Optional selection and monthly peak
exit checks certify only the explicitly supported dividend and split paths.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction as F
from backtest.capped_frontier_independent_review import review_selection as original_review_selection


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def amount(value):
    require(not isinstance(value, bool), 'BOOLEAN_AMOUNT')
    value = F(str(value))
    require(value >= 0, 'NEGATIVE_AMOUNT')
    return value


def review(book, assembled, bars, *, initial_cash, dividend_events,
           initial_shares=None, verify_selections=True, verify_risk_provider=False, expected_fee_bps, expected_slippage_bps, signals=None, signal_source_hashes=None):
    require(book['status'] == 'COMPLETE', 'COMPLETE_REQUIRED')
    require(signals is not None and signal_source_hashes, 'TREND_SIGNALS_REQUIRED')
    def review_selection(selected, **ignored):
        day = selected['decision_date'] if selected.get('schema') == OFF_SCHEMA else selected['raw_selection']['decision_date']
        if selected.get('schema') == OFF_SCHEMA:
            return review_trend_decision(selected, arguments=selected['binding']['arguments'], signal_input=signals[day], signal_source_hashes=signal_source_hashes)
        return review_trend_decision(selected, arguments={'decision_date':day}, signal_input=signals[day], signal_source_hashes=signal_source_hashes)
    if not dividend_events:
        book = deepcopy(book)
        for key in ('dividend_receivable', 'total_receivable'):
            require(amount(book.get(key, '0')) == 0, 'UNEXPECTED_DIVIDEND_TOTAL')
            book.setdefault(key, '0')
        if 'dividend_ledger' in book:
            dl = book['dividend_ledger']
            require(set(dl) <= {'schema','events','payments','paid_cash','receivable','integrated'}
                and {'events','payments','paid_cash','receivable'} <= set(dl), 'EMPTY_DIVIDEND_SCHEMA')
            require(dl['events'] == {} and dl['payments'] == {} and amount(dl['paid_cash']) == 0
                and amount(dl['receivable']) == 0, 'UNEXPECTED_DIVIDEND_LEDGER')
        else:
            book['dividend_ledger'] = dict(events={}, payments={}, paid_cash='0', receivable='0')
    require(not any(assembled.get(k) for k in ('distribution_events', 'cash_stock_merger_events')), 'CORPORATE_ACTION_UNSUPPORTED')
    sessions = assembled['session_dates']
    require(sessions == sorted(set(sessions)), 'SESSION_ORDER')
    splits = assembled.get('actions', [])
    require(all(a.get('type') in ('split', 'split_identity') for a in splits), 'CORPORATE_ACTION_UNSUPPORTED')
    require(assembled.get('provider_actions', []) == splits, 'SPLIT_PROVIDER_ACTION_MISMATCH')
    seen_splits = set()
    for action in splits:
        if action['type'] == 'split_identity':
            require(isinstance(action.get('new_security_id'), str) and action['new_security_id']
                    and action['new_security_id'] != action['security_id'], 'IDENTITY_SUCCESSOR')
        require(action['date'] in sessions[1:], 'SPLIT_SESSION')
        key = (action['date'], action['security_id'])
        require(key not in seen_splits, 'DUPLICATE_SPLIT')
        seen_splits.add(key)
        require(isinstance(action.get('source_references'), list) and action['source_references']
                and all(isinstance(r, str) and r for r in action['source_references']), 'SPLIT_EVIDENCE_REQUIRED')
        require(amount(action['new_shares']) > 0 and amount(action['old_shares']) > 0, 'SPLIT_RATIO')
    require(not verify_risk_provider or verify_selections, 'RISK_REQUIRES_SELECTION_PROOF')
    risk_state = dict(baseline=None, peaks={}, exited=set(), month=None)
    risk_checked = 0
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
    terminated = set()
    unexposed_identity_count = 0
    identity_liquidation_count = 0
    for day, row, audit in zip(sessions[1:],rows,audits):
        require(not any(shares.get(sid, 0) for sid in terminated), 'TERMINATED_POSITION_REAPPEARED')
        require(not any(o['security_id'] in terminated for o in audit['orders']), 'TERMINATED_ORDER_REAPPEARED')
        for key,e in events.items():
            if e['ex_date'] == day:
                accrued[key] = shares.get(e['security_id'],0)*amount(e['amount_per_share'])*(1-amount(e['withholding_rate']))
        selected = audit.get('selection')
        if selected is not None and verify_selections:
            decision = sessions[sessions.index(day)-1]
            require(decision in expected_selection_dates and decision not in observed_selection_dates, 'SELECTION_SCHEDULE')
            observed_selection_dates.add(decision)
            checked_selections += 1
            rebuilt_selection = review_selection(selected,rerank_enabled=True)
            plan = next(p for p in assembled['monthly_inputs'] if p['decision_date'] == decision)
            if selected.get('schema') == OFF_SCHEMA:
                args = dict(decision_date=decision,
                    account_state=dict(asof=decision, revision='synthetic-book:'+decision, cash=str(cash), shares=dict(shares), reserved_cash='0'),
                    valuation_quotes=deepcopy(plan['valuation_quotes']), search_arguments=deepcopy(plan['search_arguments']), source_hashes=deepcopy(plan['source_hashes']))
                review_trend_decision(selected, arguments=args, signal_input=signals[decision], signal_source_hashes=signal_source_hashes)
            else:
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
        if verify_risk_provider:
            decision = sessions[sessions.index(day)-1]
            selected_targets = rebuilt_selection['target_quantities'] if selected is not None else None
            _review_risk_orders(audit, decision, day, shares, assembled['close_prices'], splits, selected_targets, risk_state)
            risk_checked += 1
        orders = deepcopy(audit['orders'])
        require(len({o['security_id'] for o in orders}) == len(orders), 'DUPLICATE_ORDER_SECURITY')
        for o in orders:
            require(o['active_date']==day and type(o['quantity']) is int and o['quantity']>0 and o['side'] in ('BUY','SELL'), 'ORDER')
        for action in splits:
            if action['date'] != day:
                continue
            sid = action['security_id']
            successor = action.get('new_security_id') if action['type'] == 'split_identity' else sid
            if successor != sid:
                require(successor not in terminated, 'TERMINATED_SUCCESSOR')
                if (not shares.get(sid, 0) and not shares.get(successor, 0)
                        and not any(o['security_id'] in (sid, successor) for o in orders)):
                    terminated.add(sid)
                    unexposed_identity_count += 1
                    continue
                require(selected is not None, 'IDENTITY_REQUIRES_MONTHLY_SELECTION')
                require(isinstance(successor, str) and successor and successor != sid, 'IDENTITY_SUCCESSOR')
                require(shares.get(sid, 0) > 0 and not shares.get(successor, 0), 'IDENTITY_POSITION_CONFLICT')
                target = review_selection(selected, rerank_enabled=True)['target_quantities']
                require(not target.get(sid, 0) and not target.get(successor, 0), 'IDENTITY_FULL_LIQUIDATION_ONLY')
                related = [o for o in orders if o['security_id'] == sid]
                require(len(related) == 1 and related[0]['side'] == 'SELL' and related[0]['quantity'] == shares[sid], 'IDENTITY_FULL_SELL_REQUIRED')
                require(not any(o['security_id'] == successor for o in orders), 'SUCCESSOR_ORDER_CONFLICT')
                identity_liquidation_count += 1
            ratio = amount(action['new_shares']) / amount(action['old_shares'])
            transformed = shares.get(sid, 0) * ratio
            require(transformed.denominator == 1, 'FRACTIONAL_SPLIT_HOLDING_UNSUPPORTED')
            if shares.get(sid, 0) or any(o['security_id'] == sid for o in orders):
                shares[sid] = 0 if successor != sid else int(transformed)
                shares[successor] = int(transformed)
            if successor != sid:
                terminated.add(sid)
            for order in orders:
                if order['security_id'] != sid:
                    continue
                transformed_order = order['quantity'] * ratio
                require(transformed_order.denominator == 1, 'FRACTIONAL_SPLIT_ORDER_UNSUPPORTED')
                order['quantity'] = int(transformed_order)
                order['security_id'] = successor
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
        unexposed_identity_events_checked=unexposed_identity_count,
        expected_selection_proofs=len(expected_selection_dates), costs_checked=True, ordinary_splits_checked=sum(a['type']=='split' for a in splits), integer_identity_liquidations_checked=identity_liquidation_count, identity_scope='ZERO_EXPOSURE_OR_MONTHLY_SELECTION_BEFORE_OPEN_INTEGER_FULL_LIQUIDATION_ONLY', fractional_split_cash_supported=False, risk_provider_certified=bool(verify_risk_provider and risk_checked == len(rows) and risk_checked), risk_sessions_checked=risk_checked)


def _review_risk_orders(audit, decision, active, shares, prices, splits, selected_targets, state):
    """Independent monthly peak/latched exit arithmetic, not the risk kernel."""
    require('drift_overlay' not in audit and audit.get('action') != 'WAIT_POST_ACTION_MARK', 'UNSUPPORTED_RISK_PATH')
    if selected_targets is not None:
        state.update(baseline=dict(selected_targets), peaks={}, exited=set(), month=decision)
    else:
        require(state['baseline'] is not None, 'INITIAL_SELECTION_REQUIRED')
        for e in splits:
            if e['date'] == decision and e['security_id'] in state['baseline']:
                sid=e['security_id'];ratio=amount(e['new_shares'])/amount(e['old_shares'])
                target=state['baseline'][sid]*ratio
                require(target.denominator==1,'FRACTIONAL_RISK_TARGET')
                state['baseline'][sid]=int(target)
                if sid in state['peaks']:state['peaks'][sid]/=ratio
    baseline=state['baseline']
    require(audit['monthly_ceiling']==baseline,'RISK_CEILING')
    for sid in baseline:
        close=amount(prices[sid][decision]);require(close>0,'RISK_PRICE')
        state['peaks'][sid]=max(state['peaks'].get(sid,close),close)
        if close*5 <= state['peaks'][sid]*4:state['exited'].add(sid)
    expected={sid:0 if sid in state['exited'] else q for sid,q in baseline.items()}
    require(audit['target_shares']==expected,'RISK_EFFECTIVE_TARGET')
    risk=audit['risk_overlay']
    if baseline:
        rs=risk['state']
        require(rs['decision_date']==state['month'] and rs['session_date']==decision,'RISK_CLOCK')
        require({s:F(v) for s,v in rs['peaks'].items()}==state['peaks'] and set(rs['exited'])==state['exited'],'RISK_STATE')
        require(risk['effective_target_quantities']==expected,'RISK_OVERLAY_TARGET')
    else:require(risk=={'empty_target':True},'EMPTY_RISK')
    wanted=sorted((sid,'BUY' if expected.get(sid,0)>shares.get(sid,0) else 'SELL',abs(expected.get(sid,0)-shares.get(sid,0))) for sid in set(expected)|set(shares) if expected.get(sid,0)!=shares.get(sid,0))
    require(sorted((o['security_id'],o['side'],o['quantity']) for o in audit['orders'])==wanted,'RISK_ORDER_SOURCE')
    for o in audit['orders']:
        require(o['decision_date']==decision and o['active_date']==active and amount(o['decision_mark'])==amount(prices[o['security_id']][decision]),'RISK_ORDER_TIME_PRICE')
