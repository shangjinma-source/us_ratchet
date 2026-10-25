"""Saved-book arithmetic review, independent of execution and selection modules.

Only the frozen split/distribution/ADS event family is supported. No search,
execution-kernel replay, delivery assumption or parameter adjustment occurs.
"""
from copy import deepcopy
from fractions import Fraction as F
from functools import lru_cache
from math import prod


def require(condition, detail):
    if not condition:
        raise ValueError('INDEPENDENT_REVIEW: '+str(detail))


def positions(value):
    return {sid: quantity for sid, quantity in value.items() if quantity}


def review_account(bundle, document):
    book, audits = document['book'], document['audit']
    dates, bars = bundle['session_dates'], bundle['ohlc']
    require(book['status'] == 'COMPLETE', 'incomplete book')
    require(not bundle.get('cash_stock_merger_events'), 'unsupported mixed merger')
    require(len(audits) == len(book['daily_ledger']) == len(dates)-1, 'length')
    cash, shares, rights = F(bundle['initial_cash']), dict(bundle['initial_shares']), []
    fee_rate, slip = F(bundle['fee_bps'])/10000, F(bundle['slippage_bps'])/10000
    fees = turnover = slippage = F(0)
    fills_count = cash_only_days = 0
    initial = cash+sum((q*F(bars[s][dates[0]]['close']) for s, q in shares.items() if q), F(0))
    wealth = [(dates[0], initial)]
    previous_close_rights = []

    def add_right(event, kind, sid, units, origin=None):
        if not units:
            return
        right = dict(event_id=event['event_id'], kind=kind, security_id=sid,
                     units=str(units), effective_date=event.get('effective_date', event.get('date')),
                     source_references=event['source_references'], delivery_date=None,
                     payment_date=None, tradable=False)
        if origin:
            right['origin'] = origin
        rights.append(right)

    def distribute(event):
        old, new, child = event['parent_sid'], event['post_parent_sid'], event['child_sid']
        quantity = shares.get(old, 0)
        child_total, parent_total = quantity*F(event['child_ratio']), quantity*F(event['parent_ratio'])
        add_right(event, 'CHILD_PENDING_WHOLE', child, F(int(child_total)))
        add_right(event, 'CHILD_FRACTIONAL_CASH_RIGHT', child, child_total-int(child_total))
        if old != new:
            require(not shares.get(new, 0), 'successor collision')
            shares[old] = 0
        shares[new] = int(parent_total)
        add_right(event, 'PARENT_FRACTIONAL_CASH_RIGHT', new, parent_total-int(parent_total))

    def value_rights(items, day):
        amount = F(0)
        for right in items:
            sid, units = right['security_id'], F(right['units'])
            require(right['effective_date'] <= day and right['tradable'] is False, 'rights date/availability')
            if right['kind'] == 'CHILD_PENDING_WHOLE':
                amount += units*F(bars[sid][day]['close'])
            else:
                value = bundle['distribution_fractional_cash_values'][right['event_id']][right['kind']]
                require(value['known_asof'] <= day and value['security_id'] == sid
                        and F(value['units']) == units and value['source_references'], 'fraction evidence')
                amount += F(value['amount'])
        return amount

    for index, (audit, ledger) in enumerate(zip(audits, book['daily_ledger']), 1):
        day, decision = dates[index], dates[index-1]
        require(ledger['date'] == day, 'ledger date')
        actual, selected_account = audit['input_account'], audit['decision_account']
        require(actual['asof'] == decision and F(actual['cash']) == cash
                and positions(actual['shares']) == positions(shares)
                and actual['distribution_rights'] == rights, 'input account '+day)
        prior_after = [e for e in bundle.get('distribution_events', [])
                       if e['effective_date'] == decision and e['timing'] == 'AFTER_CLOSE']
        require(audit['post_close_events_replayed'] == [e['event_id'] for e in prior_after], 'after-close binding')
        decision_rights = previous_close_rights if prior_after else rights
        require(selected_account['distribution_rights'] == decision_rights
                and positions(selected_account['shares']) == positions(shares)
                and F(selected_account['cash']) == cash, 'decision snapshot')
        tradable = cash+sum((q*F(bars[s][decision]['close']) for s, q in shares.items() if q), F(0))
        require(F(audit['capital_basis']['tradable_equity']) == tradable, 'selection capital')
        require(F(audit['capital_basis']['nontradable_equity_excluded_from_selection'])
                == value_rights(decision_rights, decision), 'excluded capital')
        signal = audit['signal']
        require(signal['signal_date'] == decision, 'signal date')
        targets = signal['targets']
        differences = [dict(security_id=s, side='BUY' if targets.get(s, 0) > shares.get(s, 0) else 'SELL',
                            quantity=abs(targets.get(s, 0)-shares.get(s, 0)))
                       for s in sorted(set(targets) | set(shares)) if targets.get(s, 0) != shares.get(s, 0)]
        require(differences == signal['target_differences'], 'target differences')
        orders = [dict(row, id='dynamic:'+decision+':'+row['security_id']) for row in differences]
        distributions = [e for e in bundle.get('distribution_events', []) if e['effective_date'] == day]
        cancelled = {s for e in distributions if e['timing'] == 'BEFORE_OPEN'
                     for s in (e['parent_sid'], e['post_parent_sid'], e['child_sid'])}
        orders = [o for o in orders if o['security_id'] not in cancelled]
        for event in distributions:
            if event['timing'] == 'BEFORE_OPEN':
                distribute(event)
        for event in bundle.get('actions', []):
            if event['date'] != day:
                continue
            sid, kind = event['security_id'], event['type']
            require(kind in ('split', 'split_identity', 'ads_conversion'), 'unsupported action '+kind)
            new = event.get('new_security_id', sid)
            ratio = F(event['new_shares'])/F(event['old_shares'])
            amount = shares.get(sid, 0)*ratio
            if kind == 'ads_conversion':
                orders = [o for o in orders if o['security_id'] != sid]
                require(not shares.get(new, 0), 'ADS successor collision')
                shares[sid], shares[new] = 0, int(amount)
                add_right(event, 'PARENT_FRACTIONAL_CASH_RIGHT', new, amount-int(amount), 'ADS_CONVERSION')
            else:
                require(amount.denominator == 1, 'fractional split')
                shares[sid] = 0 if sid != new else int(amount)
                shares[new] = int(amount)
                for order in orders:
                    if order['security_id'] == sid:
                        quantity = order['quantity']*ratio
                        require(quantity.denominator == 1, 'fractional split order')
                        order.update(quantity=int(quantity), security_id=new)
        expected = []
        for side in ('SELL', 'BUY'):
            active = sorted((o for o in orders if o['side'] == side), key=lambda o: o['id'])
            required = sum((o['quantity']*F(bars[o['security_id']][day]['open'])*(1+slip)*(1+fee_rate)
                            for o in active), F(0)) if side == 'BUY' else F(0)
            factor = min(F(1), cash/required) if required else F(0)
            for order in active:
                sid = order['security_id']
                quantity = order['quantity'] if side == 'SELL' else int(order['quantity']*factor)
                if not quantity:
                    continue
                opening = F(bars[sid][day]['open'])
                price = opening*(1-slip if side == 'SELL' else 1+slip)
                fee = quantity*price*fee_rate
                direction = -1 if side == 'SELL' else 1
                shares[sid] = shares.get(sid, 0)+direction*quantity
                cash -= direction*quantity*price+fee
                require(cash >= 0 and shares[sid] >= 0, 'negative capital')
                fees += fee
                turnover += quantity*price
                slippage += quantity*opening*slip
                expected.append((order['id'], sid, side, quantity, price, fee, cash))
        actual_fills = [(r['id'], r['security_id'], r['side'], r['quantity'], F(r['price']), F(r['fee']), F(r['cash_after']))
                        for r in book['order_log'] if r['date'] == day and r['event'] == 'ASSUMED_NEXT_OPEN_FILLED']
        require(expected == actual_fills, 'fills '+day)
        fills_count += len(expected)
        stock = sum((q*F(bars[s][day]['close']) for s, q in shares.items() if q), F(0))
        pending = value_rights(rights, day)
        require(positions(shares) == positions(ledger['shares']) and rights == ledger['distribution_rights'], 'ledger assets')
        require(F(ledger['cash']) == cash and F(ledger['stock_value']) == stock
                and F(ledger['distribution_entitlement_value']) == pending
                and F(ledger['equity']) == cash+stock+pending, 'ledger wealth '+day)
        require(not ledger['merger_entitlements'] and all(F(ledger[k]) == 0 for k in
                ('receivable', 'external_flow', 'reserved_cash_end', 'nontradable_entitlement_value')), 'unexpected capital')
        wealth.append((day, cash+stock+pending))
        cash_only_days += not bool(positions(shares))
        previous_close_rights = deepcopy(rights)
        for event in distributions:
            if event['timing'] == 'AFTER_CLOSE':
                require(event['parent_sid'] == event['post_parent_sid'] and F(event['parent_ratio']) == 1,
                        'unsupported after-close parent change')
                distribute(event)
    require(fees == F(book['fees']) and F(book['cash']) == cash
            and positions(book['shares']) == positions(shares) and book['distribution_rights'] == rights,
            'terminal reconciliation')
    require(book['terminal_state_valuation_synchronized'], 'unsynchronized terminal')
    peak, peak_day, drawdown, interval = initial, dates[0], F(0), [dates[0], dates[0]]
    for day, value in wealth:
        if value > peak:
            peak, peak_day = value, day
        decline = 1-value/peak
        if decline > drawdown:
            drawdown, interval = decline, [peak_day, day]
    return dict(interval_return=str(wealth[-1][1]/initial-1), max_close_drawdown=str(drawdown),
                drawdown_dates=interval, initial_equity=str(initial), final_equity=str(wealth[-1][1]),
                fills=fills_count, turnover=str(turnover), slippage_amount=str(slippage), fees=str(fees),
                cash_only_sessions=cash_only_days, sessions=len(wealth)-1,
                final_nontradable_value=str(value_rights(rights, dates[-1])))


def review_selection_inputs(bundle, document, selections):
    """Independently rebuild dated scenarios, cap, common scores and risk peaks."""
    fills = {r['id']: r for r in document['book']['order_log'] if r['event'] == 'ASSUMED_NEXT_OPEN_FILLED'}
    reentry_ids = set()
    for audit in document['audit']:
        signal, account = audit['signal'], audit['decision_account']
        day = signal['signal_date']
        saved = selections(day)
        args = saved['arguments']
        eligible = bundle['eligibility'][day]
        require(set(args['prices']) == set(eligible), 'candidate eligibility')
        for key, value in bundle['search_template'].items():
            require(args[key] == value, 'search template '+key)
        end = bundle['calendar'].index(day)
        dates = bundle['calendar'][end-252:end+1]
        require(len(dates) == 253 and args['scenario_dates'] == dates[21::21]
                and args['decision_date'] == day, 'training dates')
        equity = F(audit['capital_basis']['tradable_equity'])
        require(F(args['entered_cash']) == equity, 'optimizer capital')
        require(args['metadata'] == {s: bundle['metadata'][s] for s in eligible}, 'metadata')
        for sid in eligible:
            require(F(args['prices'][sid]) == F(bundle['ohlc'][sid][day]['close']), 'decision price')
        @lru_cache(maxsize=None)
        def scenarios(sid):
            series = bundle['training_series'][sid]
            return [F(series[dates[i+21]])/F(series[dates[i]]) for i in range(0, 252, 21)]
        require(len(args['training_scenarios']) == 12, 'scenario count')
        for i, row in enumerate(args['training_scenarios']):
            require(set(row) == set(eligible) and all(F(row[s]) == scenarios(s)[i] for s in eligible), 'scenario values')
        comparison, risk = signal['comparison'], signal['comparison']['risk_state']
        anchor = max(d for d in bundle['reset_dates'] if d <= day)
        require(signal['risk_anchor'] == risk['decision_date'] == anchor and risk['session_date'] == day, 'risk dates')
        entries = audit['reentry_execution_inputs'].get('executed_reentries', [])
        for entry in entries:
            fill = fills[entry['execution_id']]
            require(fill['side'] == 'BUY' and fill['date'] == entry['date']
                    and anchor <= entry['exit_date'] < entry['date'] <= day, 'reentry causal fill')
            sid, price = fill['security_id'], F(fill['price'])
            for event in bundle['risk_events']:
                if fill['date'] < event['date'] <= day and event['security_id'] == sid:
                    price *= F(event['old_shares'])/F(event['new_shares'])
                    sid = event.get('new_security_id', sid)
            require(sid == entry['security_id'] and price == F(entry['price']), 'reentry units')
            reentry_ids.add(entry['execution_id'])
        expected_exited = set()
        for sid in risk['peaks']:
            peak, exited = F(0), False
            for historical in bundle['session_dates']:
                if not anchor <= historical <= day:
                    continue
                matching = [e for e in entries if e['security_id'] == sid and e['date'] == historical]
                if matching:
                    require(exited and len(matching) == 1, 'reentry prior latch')
                    peak, exited = F(matching[0]['price']), False
                old, factor = sid, F(1)
                for event in reversed(bundle['risk_events']):
                    if historical < event['date'] <= day and event.get('new_security_id', event['security_id']) == old:
                        factor *= F(event['old_shares'])/F(event['new_shares'])
                        old = event['security_id']
                close = F(bundle['ohlc'][old][historical]['close'])*factor
                peak = max(peak, close)
                exited = exited or close <= peak*F(4, 5)
            require(F(risk['peaks'][sid]) == peak and F(risk['last_closes'][sid]) == close, 'risk peak '+sid)
            if exited:
                expected_exited.add(sid)
        require(expected_exited == set(risk['exited']), 'risk latches')
        allowed = audit['reentry_execution_inputs'].get('eligible_reentries', {})
        for sid, exit_day in allowed.items():
            require(anchor <= exit_day < day and not account['shares'].get(sid, 0), 'early reentry eligibility')
        if document['book_id'].endswith('-A'):
            require(not entries and not allowed, 'control reentry forbidden')
        raw = saved['selection']['selected']['quantities']
        require(set(raw) <= set(eligible), 'selected eligibility')
        candidate = {s: min(q, int(equity/(2*F(args['prices'][s])))) for s, q in raw.items()}
        expected_candidate = {s: 0 if s in expected_exited and s not in allowed else q for s, q in candidate.items()}
        retained = {s: 0 if s in expected_exited else q for s, q in account['shares'].items()
                    if s not in account.get('terminated_security_ids', [])}
        require(expected_candidate == comparison['candidate_targets'] and retained == comparison['retain_targets'], 'risk targets')
        def score(target):
            domain = {s for p in (target, account['shares']) for s, q in p.items() if q}
            marks = {s: F(bundle['ohlc'][s][day]['close']) for s in domain}
            buys = sum((max(target.get(s, 0)-account['shares'].get(s, 0), 0)*marks[s] for s in domain), F(0))
            sells = sum((max(account['shares'].get(s, 0)-target.get(s, 0), 0)*marks[s] for s in domain), F(0))
            slip = F(bundle['slippage_bps'])/10000
            residual = F(account['cash'])+sells*(1-slip)-buys*(1+slip)
            if residual < 0:
                return None
            growth = [(residual+sum((target.get(s, 0)*marks[s]*scenarios(s)[i] for s in domain), F(0)))/equity for i in range(12)]
            return prod(growth)
        left, right = score(expected_candidate), score(retained)
        ranking = 'UNAFFORDABLE' if left is None or right is None else 'SWITCH_HIGHER' if left > right else 'RETAIN_HIGHER' if left < right else 'TIE'
        require(comparison['ranking'] == ranking and signal['targets'] == (expected_candidate if ranking == 'SWITCH_HIGHER' else retained), 'score decision')
    return dict(reentries_observed=len(reentry_ids), selection_days=len(document['audit']))


def review_reentry_journal(bundle, document):
    """Rebuild eligibility from prior risk-exit orders and actual fills, including final day."""
    exits, entries, open_episodes = [], [], {}
    second_exits = 0
    events = sorted(bundle.get('risk_events', []), key=lambda e: e['date'])
    fills = {r['id']: r for r in document['book']['order_log'] if r['event'] == 'ASSUMED_NEXT_OPEN_FILLED'}
    def normalized(record, through):
        result = dict(record)
        for event in events:
            if record['date'] < event['date'] <= through and event['security_id'] == result['security_id']:
                result['security_id'] = event.get('new_security_id', result['security_id'])
                result['unit_id'] = event['new_unit_id']
                if 'price' in result:
                    result['price'] = str(F(result['price'])*F(event['old_shares'])/F(event['new_shares']))
        return result
    for index, audit in enumerate(document['audit']):
        signal = audit['signal']
        day, anchor = signal['signal_date'], signal['risk_anchor']
        active_day = bundle['session_dates'][index+1]
        holdings = audit['decision_account']['shares']
        eligible = {r['security_id']: r['date'] for raw in exits for r in [normalized(raw, day)]
                    if anchor <= r['date'] < day and not holdings.get(r['security_id'], 0)}
        expected = dict(eligible_reentries=eligible,
                        executed_reentries=[normalized(r, day) for r in entries if r['exit_date'] >= anchor])
        if audit['reentry_policy'] == 'LATER_CLOSE':
            require(audit['reentry_execution_inputs'] == expected, 'execution journal '+day)
        else:
            require(not audit['reentry_execution_inputs'], 'control journal')
            eligible = {}
        for order in signal['target_differences']:
            sid = order['security_id']
            identifier = 'dynamic:'+day+':'+sid
            fill = fills.get(identifier)
            if fill is None:
                continue
            require(fill['date'] == active_day and fill['side'] == order['side'], 'journal fill date')
            source = dict(security_id=sid, date=day, unit_id=signal['comparison']['risk_state']['unit_ids'][sid])
            converted = normalized(source, active_day)
            actual_sid = converted['security_id']
            require(actual_sid == fill['security_id'], 'journal security')
            if order['side'] == 'SELL' and sid in signal['comparison']['risk_state']['exited']:
                require(not document['book']['daily_ledger'][index]['shares'].get(actual_sid, 0), 'risk sell not flat')
                exits = [r for r in exits if normalized(r, active_day)['security_id'] != actual_sid]
                exits.append(dict(security_id=actual_sid, date=active_day, unit_id=converted['unit_id']))
                for previous_sid, episode in list(open_episodes.items()):
                    if normalized(episode, active_day)['security_id'] == actual_sid:
                        second_exits += 1
                        del open_episodes[previous_sid]
            # A prior month's exit can fill on the new anchor. Its journal
            # record alone cannot make an ordinary purchase a latch release.
            if (order['side'] == 'BUY' and sid in eligible
                    and sid in signal['comparison']['risk_state']['exited']):
                entry = dict(security_id=actual_sid, date=active_day, price=fill['price'],
                             execution_id=identifier, unit_id=converted['unit_id'], exit_date=eligible[sid])
                entries.append(entry)
                open_episodes[actual_sid] = entry
                exits = [r for r in exits if normalized(r, active_day)['security_id'] != actual_sid]
            elif order['side'] == 'SELL':
                # A voluntary full exit ends this episode; later unrelated purchases
                # must not be counted as the same reentry's second risk exit.
                if not document['book']['daily_ledger'][index]['shares'].get(actual_sid, 0):
                    for previous_sid, episode in list(open_episodes.items()):
                        if normalized(episode, active_day)['security_id'] == actual_sid:
                            del open_episodes[previous_sid]
    return dict(reentry_fills=len(entries), reentry_followed_by_risk_exit=second_exits)
