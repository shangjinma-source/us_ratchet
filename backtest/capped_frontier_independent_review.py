"""Independent saved-frontier/cash/risk reviewer; stdlib only, no optimizer imports.

Monthly targets are rebuilt from the same call's original saved baskets. The
account replay retains V2's explicit unexposed after-close wait checks.
"""
from datetime import date
from fractions import Fraction as F
from hashlib import sha256
import json
import math


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value):
    _require(type(value) in (str, int, float, F), 'NONBOOLEAN_FINITE_NUMBER_REQUIRED')
    return F(str(value))


def _signature(quantities):
    return tuple(sorted((sid, quantity) for sid, quantity in quantities.items() if quantity))


def _product_hash(value):
    return sha256(f'{value.numerator:x}/{value.denominator:x}'.encode()).hexdigest()


def _binding(raw):
    binding = raw['binding']
    identifier = sha256(json.dumps(binding, sort_keys=True, separators=(',', ':'),
                                  ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    _require(identifier == raw['decision_id'], 'RAW_DECISION_ID_BINDING')
    args, result = binding['search_arguments'], raw['search_result']
    decision = raw['decision_date']
    _require(date.fromisoformat(decision).isoformat() == decision, 'DECISION_DATE')
    _require(binding['decision_date'] == args['decision_date'] == result['decision_date'] == decision,
             'DECISION_DATE_BINDING')
    _require(raw['method'] == result['method_version'] == binding['selection_method']
             == 'FAIR_K_V2_PLUS_CONTINUOUS32_EXPERIMENT_V1', 'ORIGINAL_METHOD_BINDING')
    _require(result['objective'] == 'TRAINING_PRICE_SCENARIO_MEAN_NET_LOG_WEALTH'
             and result['fee_scope'] == 'INITIAL_BUY_ONLY_NO_TERMINAL_LIQUIDATION', 'TRAINING_OBJECTIVE_BINDING')
    _require(_number(binding['reserved_cash']) == 0, 'NO_RESERVED_CASH')
    _require(all(type(quantity) is int and quantity >= 0 for quantity in binding['shares'].values()), 'WHOLE_HELD_QUANTITIES')
    cash = _number(binding['available_cash'])
    _require(cash >= 0, 'NONNEGATIVE_CASH')
    equity = cash + sum((quantity * _number(binding['valuation_quotes'][sid]['price'])
                         for sid, quantity in binding['shares'].items() if quantity), F(0))
    _require(equity == _number(args['entered_cash']) == _number(binding['investable_equity'])
             == _number(raw['investable_equity']) and equity > 0, 'INVESTABLE_EQUITY_BINDING')
    _require(_number(raw['available_cash']) == cash and raw['state_revision'] == binding['state_revision'],
             'RAW_ACCOUNT_BINDING')
    _require(set(args['prices']) == set(args['metadata']) and bool(args['prices']), 'COMPLETE_DOMAIN')
    for sid, price in args['prices'].items():
        quote = binding['valuation_quotes'][sid]
        _require(_number(price) == _number(quote['price']) > 0 and quote['as_of'] == decision, 'PRICE_BINDING')
        _require(quote['source_references'] and all(path in binding['source_hashes']
                 for path in quote['source_references']), 'QUOTE_SOURCE_BINDING')
    dates = args['scenario_dates']
    _require(dates == sorted(set(dates)) and len(dates) == len(args['training_scenarios']) > 0
             and all(date.fromisoformat(day).isoformat() == day and day <= decision for day in dates), 'MATURE_SCENARIOS')
    _require(result['scenario_dates'] == dates, 'RESULT_SCENARIO_BINDING')
    for key in ('entered_cash', 'fee_bps', 'minimum_cash_buffer'):
        _require(_number(result[key]) == _number(args[key]), 'RESULT_FINANCIAL_BINDING')
    _require(result['selected']['quantities'] == raw['target_quantities'], 'ORIGINAL_TARGET_BINDING')
    return args


def review_selection(selection, *, rerank_enabled):
    """Return independently reconstructed target and compact exact-score proof."""
    raw = selection['raw_selection']
    args = _binding(raw)
    capital = _number(args['entered_cash'])
    prices = {sid: _number(value) for sid, value in args['prices'].items()}
    fee, buffer = _number(args['fee_bps']) / 10000, _number(args['minimum_cash_buffer'])
    _require(0 <= fee < 1 and buffer >= 0, 'COST_OR_BUFFER')
    _require(_number(selection['investable_equity']) == capital, 'POLICY_CAPITAL_BINDING')
    _require(selection['monthly_cap_fraction'] == '1/2', 'FIXED_CAP_BINDING')
    base = {sid: min(quantity, int(capital / (2 * prices[sid])))
            for sid, quantity in raw['target_quantities'].items()}
    if not rerank_enabled:
        _require(selection['target_quantities'] == base, 'BASE_CAP_TARGET')
        return dict(target_quantities=base, strict_improvement=False, rescored_baskets=0)

    # Independent affine-wealth coefficients preserve exact comparisons while
    # avoiding repeated Fraction additions for every basket in the saved set.
    growth_coefficients = []
    for scenario in args['training_scenarios']:
        _require(set(scenario) == set(prices), 'SCENARIO_DOMAIN')
        relatives = {sid: _number(value) for sid, value in scenario.items()}
        _require(all(value > 0 for value in relatives.values()), 'POSITIVE_SCENARIOS')
        coefficients = {sid: prices[sid] * (relatives[sid] - 1 - fee) / capital for sid in prices}
        denominator = math.lcm(*(value.denominator for value in coefficients.values()))
        growth_coefficients.append((denominator, {sid: value.numerator * (denominator // value.denominator)
                                                for sid, value in coefficients.items()}))
    scores = {}

    def score(quantities):
        _require(all(sid in prices and type(quantity) is int and quantity > 0
                     for sid, quantity in quantities.items()), 'POSITIVE_WHOLE_BASKET')
        signature = _signature(quantities)
        if signature in scores:
            return scores[signature]
        _require(len({args['metadata'][sid]['issuer_id'] for sid in quantities}) == len(quantities), 'ONE_CLASS_PER_ISSUER')
        notional = sum((prices[sid] * quantity for sid, quantity in quantities.items()), F(0))
        residual = capital - notional * (1 + fee)
        _require(residual >= 0 and (not quantities or residual >= buffer), 'AFFORDABLE_BASKET')
        growth = [F(denominator + sum(coefficients[sid] * quantity for sid, quantity in quantities.items()), denominator)
                  for denominator, coefficients in growth_coefficients]
        _require(all(value > 0 for value in growth), 'POSITIVE_WEALTH')
        product = math.prod(growth)
        mean_log = sum(math.log(value.numerator) - math.log(value.denominator) for value in growth) / len(growth)
        result = dict(product=product, notional=notional, residual=residual, mean_log=mean_log)
        scores[signature] = result
        return result

    result = raw['search_result']
    raw_records, capped_scores, origins = {}, {}, {}
    for key, record in sorted(result['best_by_k'].items(), key=lambda item: int(item[0])):
        quantities = record['quantities']
        _require(key == str(len(quantities)) and record['actual_k'] == len(quantities), 'FRONTIER_CARDINALITY')
        assessed = score(quantities)
        _require(_number(record['notional']) == assessed['notional']
                 and _number(record['fees']) == assessed['notional'] * fee
                 and _number(record['residual_cash']) == assessed['residual'], 'FRONTIER_ACCOUNTING')
        _require(math.isclose(record['training_mean_net_log_wealth'], assessed['mean_log'], rel_tol=0, abs_tol=1e-12),
                 'FRONTIER_MEAN_LOG')
        if record.get('training_gross_growth_product') is not None:
            _require(_number(record['training_gross_growth_product']) == assessed['product'], 'FRONTIER_EXACT_PRODUCT')
        signature = _signature(quantities)
        raw_records[signature] = record
        reduced = {sid: min(quantity, int(capital / (2 * prices[sid]))) for sid, quantity in quantities.items()}
        reduced_signature = _signature(reduced)
        if reduced_signature not in capped_scores:
            capped_scores[reduced_signature] = score(dict(reduced_signature))
            origins[reduced_signature] = int(key)
    original = _signature(raw['target_quantities'])
    _require(original in raw_records and raw_records[original] == result['selected'], 'ORIGINAL_FRONTIER_RECORD')
    original_rank = (score(dict(original))['product'], -score(dict(original))['notional'], original)
    _require(all((score(dict(signature))['product'], -score(dict(signature))['notional'], signature) <= original_rank
                 for signature in raw_records), 'ORIGINAL_WINNER_RANK')
    incumbent = _signature(base)
    _require(incumbent in capped_scores, 'INCUMBENT_MISSING')
    improved = [signature for signature, assessed in capped_scores.items()
                if assessed['product'] > capped_scores[incumbent]['product']]
    winner = max(improved, key=lambda signature: (capped_scores[signature]['product'],
                 -capped_scores[signature]['notional'], signature)) if improved else incumbent
    target = dict(winner) if improved else base
    _require(selection['method'] == 'SAME_CALL_SAVED_FRONTIER_CAP50_STRICT_RERANK_V1'
             and selection['base_capped_target_quantities'] == base and selection['target_quantities'] == target,
             'RERANK_TARGET_MISMATCH')
    audit = selection['rerank_audit']
    _require(audit['strict_improvement'] is bool(improved), 'STRICT_IMPROVEMENT_FLAG')
    _require(audit['unique_capped_baskets'] == audit['additional_scored_baskets'] == len(capped_scores), 'SCORED_COUNT')
    _require(audit['source_cardinality'] == origins[winner], 'WINNER_SOURCE_CARDINALITY')
    _require(audit['base_product_sha256'] == _product_hash(capped_scores[incumbent]['product'])
             and audit['selected_product_sha256'] == _product_hash(capped_scores[winner]['product']), 'EXACT_PRODUCT_HASH')
    _require(_number(audit['selected_residual_cash']) == capped_scores[winner]['residual'], 'RERANK_RESIDUAL')
    _require(audit['candidate_generation_calls'] == 0
             and audit['original_generation_budget'] == args['max_objective_evaluations']
             and audit['original_continuous_steps'] == raw['binding']['continuous_iterations'], 'GENERATION_SCOPE')
    for field, signature in (('base_training_mean_log', incumbent), ('selected_training_mean_log', winner)):
        _require(math.isclose(audit[field], capped_scores[signature]['mean_log'], rel_tol=0, abs_tol=1e-12), 'RERANK_MEAN_LOG')
    canonical = lambda value: sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                                ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    expected_binding = dict(schema=selection['method'], original_decision_id=raw['decision_id'],
        original_raw_selection_sha256=canonical(raw), target_quantities=target,
        base_capped_target_quantities=base, monthly_cap_fraction='1/2', rerank_audit=audit)
    _require(selection['rerank_binding'] == expected_binding
             and selection['rerank_decision_id'] == canonical(expected_binding), 'RERANK_DECISION_BINDING')
    return dict(target_quantities=target, strict_improvement=bool(improved), rescored_baskets=len(capped_scores),
                selected_product_sha256=_product_hash(capped_scores[winner]['product']))


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


def review_book(book, assembled, bars, *, rerank_enabled):
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
    rerank_months, rescored_baskets = [], 0
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
            reconstructed = review_selection(selected, rerank_enabled=rerank_enabled)
            baseline = reconstructed['target_quantities']
            binding = selected['raw_selection']['binding']
            assert F(binding['available_cash']) == cash
            assert binding['shares'] == arguments['account_state']['shares']
            assert binding['state_revision'] == arguments['account_state']['revision']
            assert binding['source_hashes'] == arguments['source_hashes']
            expected_arguments = dict(arguments['search_arguments'])
            expected_arguments.pop('quote_as_of')
            basis = expected_arguments.pop('price_basis')
            expected_arguments['entered_cash'] = str(equity)
            assert binding['search_arguments'] == expected_arguments
            expected_quotes = {quote['security_id']: dict(price=str(F(quote['price'])),
                as_of=quote['as_of'], price_basis=quote['price_basis'], source_references=quote['source_references'])
                for quote in arguments['valuation_quotes']}
            assert binding['valuation_quotes'] == expected_quotes
            assert all(quote['price_basis'] == basis for quote in expected_quotes.values())
            rescored_baskets += reconstructed['rescored_baskets']
            if reconstructed['strict_improvement']:
                rerank_months.append(decision)
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
        assert 'drift_overlay' not in audit, 'DRIFT_OVERLAY_NOT_IN_THIS_CONTRACT'
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
    return dict(status='INDEPENDENT_FRONTIER_ACCOUNT_RISK_REVIEW_PASS', review_version=1, fills=count,
                rerank_months=rerank_months, rescored_baskets=rescored_baskets,
                close_observations=len(rows), reductions=reduction_count,
                final_equity=str(cash + stock), fees=str(total_fees),
                interval_return=str((cash + stock) / 20000 - 1), max_close_drawdown=str(maximum_drawdown),
                limitation='No market-data authentication, PIT, OOS or actual execution guarantee')
