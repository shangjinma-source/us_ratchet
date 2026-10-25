"""V2 independent review: explicit unexposed AFTER_CLOSE wait semantics.

Frozen v1 is retained unchanged, including its failed original research record.
This version performs no selection or execution and imports no strategy kernel.
"""
from fractions import Fraction as F


def _review_unexposed_after_close_wait(book, assembled, audit, row, decision, cash, shares, baseline, peaks):
    """A declared wait suppresses orders; it does not restore the monthly size.

    Accept only a pinned after-close distribution outside the held/target/risk
    domain. Explicitly verify the saved post-close state and next ledger state.
    Other exposed actions require a separate reviewer rather than a bypass.
    """
    events = [event for event in assembled['distribution_events']
              if event['effective_date'] == decision and event['timing'] == 'AFTER_CLOSE']
    assert events, 'WAIT_REQUIRES_AFTER_CLOSE_EVENT'
    identifiers = [event['event_id'] for event in events]
    assert len(identifiers) == len(set(identifiers)), 'DUPLICATE_WAIT_EVENT'
    proof = audit['post_close_review']
    assert proof['status'] == 'UNEXPOSED_RISK_DOMAIN_UNCHANGED'
    assert proof['decision_date'] == decision and proof['orders_permitted'] is False
    assert sorted(proof['event_ids']) == sorted(identifiers), 'WAIT_EVENT_BINDING'
    affected = set()
    for event in events:
        assert event['source_references'], 'WAIT_EVENT_EVIDENCE_REQUIRED'
        affected.update(event[key] for key in ('parent_sid', 'post_parent_sid', 'child_sid'))
    tracked = {sid for sid, quantity in shares.items() if quantity} | set(baseline) | set(peaks)
    assert not affected & tracked, 'EXPOSED_WAIT_REQUIRES_SEPARATE_REVIEW'
    assert not audit['orders'] and 'drift_overlay' not in audit, 'WAIT_CANNOT_SUBMIT_OR_RESET_DRIFT'
    records = [record for record in book['after_close_records'] if record['date'] == decision]
    assert len(records) == 1, 'WAIT_POST_CLOSE_RECORD_REQUIRED'
    record = records[0]
    assert record['phase'] == 'AFTER_CLOSE_UNVALUED_STATE' and record['post_event_equity'] is None
    assert not record['distribution_rights'], 'WAIT_NONTRADABLE_RIGHTS_UNSUPPORTED'
    nonzero = lambda quantities: {sid: quantity for sid, quantity in quantities.items() if quantity}
    assert nonzero(record['shares']) == nonzero(shares) == nonzero(row['shares']), 'WAIT_SHARES_CHANGED'
    assert F(record['cash']) == cash == F(row['cash']), 'WAIT_CASH_CHANGED'
    assert not any(item['date'] == row['date'] and item['event'] == 'ASSUMED_NEXT_OPEN_FILLED'
                   for item in book['order_log']), 'WAIT_EXECUTION_FORBIDDEN'


def review_book(book, assembled, bars, *, drift_enabled):
    if not __debug__:
        raise RuntimeError('INDEPENDENT_REVIEW_REQUIRES_ASSERTIONS_ENABLED')
    if book['status'] != 'COMPLETE':
        raise ValueError('COMPLETE_BOOK_REQUIRED')
    if (str(book['fee_bps']), str(book['slippage_bps'])) != ('1', '10'):
        raise ValueError('REGISTERED_COSTS_REQUIRED')
    sessions = assembled['session_dates']
    rows, audits = book['daily_ledger'], book['provider_audit']
    assert [row['date'] for row in rows] == sessions[1:]
    assert len(audits) == len(rows)
    plans = {row['decision_date']: row for row in assembled['monthly_inputs']}
    selections = iter(book['selection_account_states'])
    cash, shares, total_fees = F(20000), {}, F(0)
    baseline, month, ceilings, peaks, exited = {}, None, {}, {}, set()
    units = {}
    peak_equity, maximum_drawdown = cash, F(0)
    fee_rate, slip = F(book['fee_bps']) / 10000, F(book['slippage_bps']) / 10000
    count, reduction_count = 0, 0
    for index, (audit, row) in enumerate(zip(audits, rows)):
        decision, day = sessions[index], row['date']
        before = dict(shares)
        if decision in plans:
            arguments = next(selections)
            assert arguments['decision_date'] == decision
            assert F(arguments['account_state']['cash']) == cash
            assert arguments['account_state']['asof'] == decision
            assert {s: q for s, q in arguments['account_state']['shares'].items() if q} == {s: q for s, q in shares.items() if q}
            for key in ('valuation_quotes', 'search_arguments', 'source_hashes'):
                assert arguments[key] == plans[decision][key]
            selected = audit['selection']
            equity = cash + sum((q * F(assembled['close_prices'][s][decision])
                                 for s, q in shares.items() if q), F(0))
            assert F(selected['investable_equity']) == equity
            raw = selected['raw_selection']['target_quantities']
            baseline = {s: min(q, int(equity / (2 * F(assembled['close_prices'][s][decision]))))
                        for s, q in raw.items()}
            assert baseline == selected['target_quantities']
            month, ceilings, peaks, exited = decision, dict(baseline), {}, set()
            units = {sid: 'research-nominal:' + sid for sid in baseline}
        else:
            assert audit.get('selection') is None
            changed = set()
            for change in audit.get('target_adjustments', ()):
                assert change['date'] == decision and change['security_id'] not in changed
                changed.add(change['security_id'])
                matches = [a for a in assembled['provider_actions']
                           if (a['date'], a['security_id']) == (decision, change['security_id'])]
                assert len(matches) == 1
                action = matches[0]
                assert action['type'] == 'split' and change['new_security_id'] == action['security_id']
                assert action['source_references']
                sid = action['security_id']
                ratio = F(action['new_shares']) / F(action['old_shares'])
                assert (baseline[sid] * ratio).denominator == 1
                baseline[sid] = int(baseline[sid] * ratio)
                ceilings[sid] = int(ceilings[sid] * ratio)
                if sid in peaks:
                    peaks[sid] /= ratio
                    units[sid] += ':' + decision
        assert baseline == audit['monthly_ceiling']
        for sid in baseline:
            close = F(assembled['close_prices'][sid][decision])
            peaks[sid] = max(peaks.get(sid, close), close)
            if close * 5 <= peaks[sid] * 4:
                exited.add(sid)
        risk = audit['risk_overlay']
        expected = {sid: 0 if sid in exited else q for sid, q in baseline.items()}
        if baseline:
            assert risk['state']['decision_date'] == month
            assert risk['state']['session_date'] == decision
            assert {sid: F(value) for sid, value in risk['state']['peaks'].items()} == peaks
            assert risk['state']['unit_ids'] == units
            assert {sid: F(value) for sid, value in risk['state']['last_closes'].items()} == {
                sid: F(assembled['close_prices'][sid][decision]) for sid in baseline}
            assert set(risk['state']['exited']) == exited
            assert expected == risk['effective_target_quantities']
        else:
            assert risk == {'empty_target': True}
        if drift_enabled and audit['action'] != 'WAIT_POST_ACTION_MARK':
            equity = cash + sum((q * F(assembled['close_prices'][sid][decision])
                                 for sid, q in shares.items() if q), F(0))
            reductions = []
            for sid, monthly_quantity in baseline.items():
                ceilings[sid] = min(ceilings[sid], monthly_quantity)
                close = F(assembled['close_prices'][sid][decision])
                if shares.get(sid, 0) * close > equity / 2:
                    reduced = int(equity / (2 * close))
                    if reduced < ceilings[sid]:
                        reductions.append(dict(security_id=sid, before=ceilings[sid], after=reduced,
                            held=shares[sid], close=str(close), weight=str(shares[sid] * close / equity)))
                        reduction_count += 1
                        ceilings[sid] = reduced
                expected[sid] = min(expected[sid], ceilings[sid])
            assert audit['drift_overlay']['ceiling'] == ceilings
            assert F(audit['drift_overlay']['tradable_equity']) == equity
            assert audit['drift_overlay']['effective_targets'] == expected
            assert audit['drift_overlay']['reductions'] == reductions
            assert audit['drift_overlay']['day'] == decision and audit['drift_overlay']['month'] == month
        assert audit['target_shares'] == expected
        if audit['action'] == 'WAIT_POST_ACTION_MARK':
            assert not audit['orders']
            _review_unexposed_after_close_wait(book, assembled, audit, row, decision, cash, shares, baseline, peaks)
        else:
            required_orders = sorted((sid, 'BUY' if expected.get(sid, 0) > shares.get(sid, 0) else 'SELL',
                                      abs(expected.get(sid, 0) - shares.get(sid, 0)))
                                     for sid in set(expected) | set(shares)
                                     if expected.get(sid, 0) != shares.get(sid, 0))
            assert sorted((o['security_id'], o['side'], o['quantity']) for o in audit['orders']) == required_orders
        orders = [dict(order) for order in audit['orders']]
        for event in assembled['actions']:
            if event['date'] != day:
                continue
            sid = event['security_id']
            if not shares.get(sid, 0) and not any(o['security_id'] == sid for o in orders):
                continue
            assert event['type'] == 'split', 'UNSUPPORTED_EXPOSED_ACTION'
            ratio = F(event['new_shares']) / F(event['old_shares'])
            quantity = shares.get(sid, 0) * ratio
            assert quantity.denominator == 1
            shares[sid] = int(quantity)
            for order in orders:
                if order['security_id'] == sid:
                    quantity = order['quantity'] * ratio
                    assert quantity.denominator == 1
                    order['quantity'] = int(quantity)
        expected_fills = []
        for side in ('SELL', 'BUY'):
            batch = sorted((o for o in orders if o['side'] == side), key=lambda o: o['id'])
            required = sum((o['quantity'] * F(bars[o['security_id']][day]['open']) * (1 + slip) * (1 + fee_rate)
                            for o in batch), F(0)) if side == 'BUY' else F(0)
            factor = min(F(1), cash / required) if required else F(0)
            for order in batch:
                assert order['decision_date'] == decision < day == order['active_date']
                sid = order['security_id']
                quantity = order['quantity'] if side == 'SELL' else int(order['quantity'] * factor)
                if not quantity:
                    continue
                price = F(bars[sid][day]['open']) * (1 - slip if side == 'SELL' else 1 + slip)
                fee = quantity * price * fee_rate
                direction = -1 if side == 'SELL' else 1
                shares[sid] = shares.get(sid, 0) + direction * quantity
                cash -= direction * quantity * price + fee
                total_fees += fee
                assert shares[sid] >= 0 and cash >= 0
                expected_fills.append((order['id'], sid, side, quantity, price, fee, cash))
        actual_fills = [(o['id'], o['security_id'], o['side'], o['quantity'], F(o['price']), F(o['fee']), F(o['cash_after']))
                        for o in book['order_log'] if o['date'] == day and o['event'] == 'ASSUMED_NEXT_OPEN_FILLED']
        assert expected_fills == actual_fills, day
        count += len(actual_fills)
        for event in assembled['distribution_events']:
            if event['effective_date'] == day:
                assert not shares.get(event['parent_sid'], 0), 'EXPOSED_DISTRIBUTION_REQUIRES_REVIEW'
        assert {s: q for s, q in shares.items() if q} == {s: q for s, q in row['shares'].items() if q}
        assert cash == F(row['cash'])
        stock = sum((q * F(bars[sid][day]['close']) for sid, q in shares.items() if q), F(0))
        assert stock == F(row['stock_value']) and stock + cash == F(row['equity'])
        assert F(row['receivable']) == F(row['external_flow']) == 0
        assert not row['distribution_rights'] and not row['merger_entitlements']
        peak_equity = max(peak_equity, stock + cash)
        maximum_drawdown = max(maximum_drawdown, 1 - (stock + cash) / peak_equity)
    assert next(selections, None) is None
    assert total_fees == F(book['fees'])
    assert count == sum(o['event'] == 'ASSUMED_NEXT_OPEN_FILLED' for o in book['order_log'])
    assert book['state_date'] == book['last_valued_date'] == sessions[-1]
    assert book['terminal_state_valuation_synchronized'] is True
    assert book['final_wealth_basis'] == 'REGULAR_CLOSE_CURRENT_STATE'
    assert F(book['cash']) == cash
    assert {s: q for s, q in book['shares'].items() if q} == {s: q for s, q in shares.items() if q}
    assert F(book['receivable']) == F(book['external_flows']) == 0
    assert not book['distribution_rights'] and not book['merger_entitlements']
    assert F(book['total_return']) == (cash + stock) / 20000 - 1
    assert F(book['drawdown']['maximum_close_drawdown']) == maximum_drawdown
    return dict(status='INDEPENDENT_ACCOUNT_RISK_DRIFT_REVIEW_PASS', review_version=2, fills=count,
                close_observations=len(rows), reductions=reduction_count,
                final_equity=str(cash + stock), fees=str(total_fees),
                interval_return=str((cash + stock) / 20000 - 1), max_close_drawdown=str(maximum_drawdown),
                limitation='No market-data authentication, PIT, OOS or actual execution guarantee')
