"""New candidate cash arithmetic, derived from sealed cost reviewer without modifying it."""
from fractions import Fraction
from hashlib import sha256
import json

def require_quantities(value):
    if type(value) is not dict or any(type(sid) is not str or type(q) is not int or q < 0
                                      for sid, q in value.items()):
        raise ValueError('NONINTEGER_QUANTITY_MAP')


COSTS = {'slippage5': ('0', '5'), 'fee1_slippage10': ('1', '10')}


def review_cash(*, assembled, ohlc, outcome, scenario, expected_pins, arm, initial_cash):
    def require(condition, reason):
        if not condition:
            raise ValueError(reason)
    def number(value):
        require(not isinstance(value, bool), 'BOOLEAN_AMOUNT')
        return Fraction(str(value))
    require(scenario in COSTS and arm == 'continuous32_ma9_sma20_half', 'UNKNOWN_STRESS_ARM')
    require(expected_pins and all(isinstance(p, str) and isinstance(h, str) and len(h) == 64
                                 for p, h in expected_pins.items()), 'EXPECTED_PINS_REQUIRED')
    fee, slip = map(lambda value: Fraction(value)/10000, COSTS[scenario])
    binding = outcome['cost_stress_binding']
    expected_binding = dict(schema='COST_STRESS_ARM_BINDING_V1', arm=arm, scenario=scenario,
        initial_cash=str(initial_cash), continuous_iterations=32, max_objective_evaluations=8192,
        source_hashes=expected_pins, fee_bps=COSTS[scenario][0], slippage_bps=COSTS[scenario][1])
    require(binding == expected_binding, 'ARM_BINDING_MISMATCH')
    binding_hash = sha256(json.dumps(binding, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    require(outcome['cost_stress_binding_sha256'] == binding_hash, 'ARM_BINDING_HASH_MISMATCH')
    require(outcome['cost_stress_arm'] == arm and outcome['cost_stress_scenario'] == scenario, 'ARM_LABEL_MISMATCH')
    require(outcome['status'] == 'COMPLETE', 'INCOMPLETE_OUTCOME')
    require(number(outcome['fee_bps'])/10000 == fee and number(outcome['slippage_bps'])/10000 == slip,
            'EXECUTION_COST_MISMATCH')
    require(number(outcome['external_flows']) == 0, 'EXTERNAL_FLOW_UNSUPPORTED')
    noncash_events = {'FROZEN_TARGET_FOR_NEXT_OPEN', 'CANCELLED_CONDITIONAL_MIXED_SESSION',
        'CANCELLED_DISTRIBUTION_SESSION', 'CANCELLED_ADS_CONVERSION', 'CONDITIONAL_DTC_CONVERSION',
        'SPLIT_QUANTITY_AND_MARK_ADJUSTED', 'CANCELLED_TERMINATION', 'CORPORATE_ACTION',
        'DISTRIBUTION_APPLIED', 'CONDITIONAL_END_SESSION_ENTITLEMENT',
        'UNFILLED_CASH_RATIONED_INTEGER_FLOOR'}
    # This kernel leaves cash entitlements as receivables/rights. It does not
    # credit settlements into spendable cash; do not extrapolate that to a new kernel.
    def unsupported(reason, event=None):
        return dict(status='UNSUPPORTED_CASH_EVENT_REVIEW_REQUIRED', reason=reason,
                    event=event, full_ledger_independently_replayed=False, performance_validated=False)
    for event in outcome['order_log']:
        if event['event'] == 'ASSUMED_NEXT_OPEN_FILLED':
            continue
        if event['event'] not in noncash_events:
            return unsupported('UNRECOGNIZED_NONFILL_EVENT', event['event'])
        if any(number(event.get(key, '0')) != 0 for key in ('cash_credited', 'cash_debited', 'cash_delta')):
            return unsupported('INTERNAL_CASH_SETTLEMENT_NOT_IMPLEMENTED', event['event'])
        if event['event'] == 'CORPORATE_ACTION' and event.get('type') not in {
                'split', 'split_identity', 'ads_conversion', 'cash_stock_merger', 'merger', 'distribution'}:
            return unsupported('UNRECOGNIZED_CORPORATE_CASH_SEMANTICS', event.get('type'))
    sessions = assembled['session_dates']
    ledger = outcome['daily_ledger']
    require([row['date'] for row in ledger] == sessions[1:], 'DAILY_LEDGER_COVERAGE_MISMATCH')
    cash, fees, slippage_notional, turnover = number(initial_cash), Fraction(0), Fraction(0), Fraction(0)
    fills = [row for row in outcome['order_log'] if row['event'] == 'ASSUMED_NEXT_OPEN_FILLED']
    require([row['date'] for row in fills] == sorted(row['date'] for row in fills), 'FILL_ORDER_INVALID')
    require(len({(row['date'], row['id']) for row in fills}) == len(fills), 'DUPLICATE_FILL')
    require(all(row['date'] in sessions[1:] for row in fills), 'FILL_DATE_OUTSIDE_WINDOW')
    cash_by_day = {sessions[0]: cash}
    for daily in ledger:
        for fill in (row for row in fills if row['date'] == daily['date']):
            quantity = fill['quantity']; side = fill['side']
            require(type(quantity) is int and quantity > 0 and side in ('BUY', 'SELL'), 'INVALID_FILL_QUANTITY_SIDE')
            opening = number(ohlc[fill['security_id']][fill['date']]['open'])
            require(opening > 0, 'INVALID_OPEN')
            price = opening * (1 + slip if side == 'BUY' else 1 - slip)
            charge = quantity * price * fee
            require(number(fill['price']) == price and number(fill['fee']) == charge, 'FILL_PRICE_OR_FEE_MISMATCH')
            cash += quantity*price-charge if side == 'SELL' else -quantity*price-charge
            require(cash >= 0 and number(fill['cash_after']) == cash, 'FILL_CASH_MISMATCH')
            fees += charge; turnover += quantity*price; slippage_notional += quantity*abs(price-opening)
        require(number(daily['cash']) == cash, 'DAILY_CASH_MISMATCH')
        cash_by_day[daily['date']] = cash
    require(number(outcome['cash']) == cash and number(outcome['fees']) == fees, 'TERMINAL_CASH_OR_FEES_MISMATCH')
    for after in outcome.get('after_close_records', []):
        if number(after['cash']) != cash_by_day.get(after['date']):
            return unsupported('AFTER_CLOSE_CASH_CHANGE_NOT_IMPLEMENTED', after.get('phase'))
    plans = {row['decision_date']:row for row in assembled['monthly_inputs']}
    states = outcome['selection_account_states']
    require([row['decision_date'] for row in states] == list(plans), 'MONTHLY_SELECTION_COVERAGE_MISMATCH')
    expected_monthly = []
    ledger_by_day = {row['date']:row for row in ledger}
    after_close = {row['date']:row for row in outcome.get('after_close_records', [])}
    selections = {row['selection']['binding']['decision_date']:row['selection']
                  for row in outcome['provider_audit'] if row.get('selection')}
    for row in states:
        day = row['decision_date']; state = row['account_state']
        expected_sources = dict(plans[day]['source_hashes'])
        for name, digest in expected_pins.items():
            require(name not in expected_sources or expected_sources[name] == digest, 'SOURCE_PIN_CONFLICT')
            expected_sources[name] = digest
        require(row['source_hashes'] == expected_sources, 'MONTHLY_SOURCE_BINDING_MISMATCH')
        require(number(row['search_arguments']['fee_bps']) == number(COSTS[scenario][0])
                and row['search_arguments']['max_objective_evaluations'] == 8192, 'MONTHLY_COST_BUDGET_MISMATCH')
        require(state['asof'] == day and number(state['cash']) == cash_by_day[day], 'MONTHLY_ACTUAL_CASH_MISMATCH')
        book = after_close.get(day, ledger_by_day.get(day, {'shares':{}}))
        require_quantities(book['shares'])
        require_quantities(selections[day]['binding']['shares'])
        require(state['shares'] == book['shares'], 'MONTHLY_REPORTED_HOLDINGS_MISMATCH')
        require(all(type(q) is int and q >= 0 for q in state['shares'].values()), 'NONINTEGER_HOLDINGS')
        equity = number(state['cash']) + sum((q*number(assembled['close_prices'][sid][day])
                                             for sid,q in state['shares'].items() if q), Fraction(0))
        selection = selections[day]
        require(selection['binding']['source_hashes'] == expected_sources, 'DECISION_SOURCE_BINDING_MISMATCH')
        require(number(selection['investable_equity']) == equity, 'MONTHLY_EQUITY_MISMATCH')
        require(selection['binding']['shares'] == state['shares']
                and number(selection['binding']['available_cash']) == number(state['cash']),
                'DECISION_ACCOUNT_BINDING_MISMATCH')
        quantities = selection['target_quantities']
        require(all(type(q) is int and q > 0 for q in quantities.values()), 'NONINTEGER_TARGET')
        notional = sum((q*number(assembled['close_prices'][sid][day]) for sid,q in quantities.items()), Fraction(0))
        residual = equity-notional*(1+fee)
        require(residual >= 0 and (not quantities or residual >=
                number(row['search_arguments']['minimum_cash_buffer'])), 'MONTHLY_TARGET_OVER_BUDGET')
        expected_monthly.append(dict(arm_binding_sha256=binding_hash, decision_date=day, account_state=state))
    require(outcome['cost_stress_monthly_bindings'] == expected_monthly, 'MONTHLY_ARM_LINK_MISMATCH')
    return dict(status='CASH_COST_BINDINGS_VERIFIED', fill_count=len(fills), monthly_count=len(states),
                fees=str(fees), modeled_slippage_notional=str(slippage_notional), turnover_notional=str(turnover),
                full_ledger_independently_replayed=False, performance_validated=False,
                limitations=['Cash reconstructed from initial cash and fills under the current kernel: rights remain non-spendable and known corporate events credit no cash. Unknown cash events require separate review.',
                             'Monthly holdings compared with reported ledger and after-close records; corporate actions, rights and holdings are not independently replayed.',
                             'Does not certify fill completeness against intended orders, selection optimality, source authenticity, NAV, return or drawdown.'])

ARM = 'continuous32_ma9_sma20_half'
CONTRACT = 'research_contracts/continuous_guided_ma9_sma20_half_execution_20261019_v1.json'
CONTRACT_SHA = 'cacd6e055725e5e26e4f6a35735c08961932d8464ac324f4e4eafdb829ab69bc'


def review_targets(*, assembled, outcome):
    """Reconstruct target ceilings and latches; never call production latch code.

    Diagnostics are saved signal evidence, not independently recomputed histories.
    Corporate target adjustments are checked against supplied action ratios.
    """
    def require(ok, reason):
        if not ok: raise ValueError(reason)
    sessions = assembled['session_dates']
    audit = outcome['provider_audit']
    require(len(audit) == len(sessions)-1, 'LATCH_AUDIT_COVERAGE')
    plans = {r['decision_date'] for r in assembled['monthly_inputs']}
    ceiling, month = {}, None
    changes = 0
    books = {r['date']: r for r in outcome.get('daily_ledger', [])}
    after = {r['date']: r for r in outcome.get('after_close_records', [])}
    for day, row in zip(sessions[:-1], audit):
        require(row['status'] == 'READY', 'LATCH_NONREADY')
        selection = row.get('selection')
        adjustments = row.get('target_adjustments', [])
        book = after.get(day, books.get(day, {'shares': {}}))
        holdings = book['shares']
        require_quantities(holdings)
        require_quantities(row['target_shares'])
        index = sessions.index(day)
        previous = sessions[index-1] if index else day
        shadow = dict(ceiling)
        expected_actions = []
        for action in assembled['provider_actions']:
            if not previous < action['date'] <= day: continue
            sid = action['security_id']
            if not shadow.get(sid, 0) and not holdings.get(sid, 0): continue
            expected_actions.append((action['date'], sid))
            kind = action['type']; before = shadow.pop(sid, 0)
            if kind == 'cash_stock_merger': continue
            if kind == 'distribution':
                successor = action['post_parent_sid']; ratio = Fraction(action['parent_ratio'])
            elif kind in ('split', 'split_identity', 'ads_conversion'):
                successor = action.get('new_security_id', sid)
                ratio = Fraction(str(action['new_shares'])) / Fraction(str(action['old_shares']))
            else: raise ValueError('UNSUPPORTED_TARGET_ACTION')
            shadow[successor] = int(before * ratio)
        require([(a['date'], a['security_id']) for a in adjustments] == expected_actions, 'ADJUSTMENT_COMPLETENESS')
        pending = day in after and after[day].get('phase') == 'AFTER_CLOSE_UNVALUED_STATE'
        require((row.get('action') == 'WAIT_POST_ACTION_MARK') == pending, 'WAIT_COORDINATE_EVIDENCE')
        for adjustment in adjustments:
            old = adjustment['security_id']; new = adjustment.get('new_security_id', old)
            action_day = adjustment['date']
            index = sessions.index(day)
            require((sessions[index-1] if index else day) < action_day <= day, 'ADJUSTMENT_DATE')
            matches = [a for a in assembled['provider_actions'] if a['date']==action_day and a['security_id']==old]
            require(len(matches)==1, 'ADJUSTMENT_ACTION_BINDING')
            action=matches[0]; kind=action['type']; before=ceiling.get(old,0)
            if kind == 'cash_stock_merger':
                expected=0; expected_new=old
            elif kind == 'distribution':
                expected=Fraction(before)*Fraction(action['parent_ratio']);expected_new=action['post_parent_sid']
            elif kind in ('split','split_identity','ads_conversion'):
                expected=Fraction(before)*Fraction(str(action['new_shares']))/Fraction(str(action['old_shares']))
                expected_new=action.get('new_security_id',old)
            else: raise ValueError('UNSUPPORTED_TARGET_ACTION')
            require(new==expected_new and type(adjustment['target_after']) is int, 'ADJUSTMENT_IDENTITY')
            require((kind=='ads_conversion' or expected.denominator==1) if isinstance(expected,Fraction) else True, 'FRACTIONAL_TARGET')
            require(adjustment['target_after']==int(expected), 'ADJUSTMENT_CEILING')
            if 'target_before' in adjustment:
                require(type(adjustment['target_before']) is int and adjustment['target_before']==before,'ADJUSTMENT_BEFORE')
            ceiling.pop(old,None)
            if kind != 'cash_stock_merger': ceiling[new]=int(expected)
        if selection:
            require(day in plans and selection['binding']['decision_date']==day, 'LATCH_RESET_WITHOUT_MONTHLY_SELECTION')
            require(month is None or day>month,'LATCH_MONTH_NONMONOTONIC')
            require_quantities(selection['target_quantities'])
            month=day;ceiling=dict(selection['target_quantities'])
        if row.get('action')=='WAIT_POST_ACTION_MARK':
            require(not selection and not row['orders'] and row['target_shares']==ceiling,'LATCH_WAIT_INVALID')
            continue
        require(month is not None and row['target_decision_date']==month,'LATCH_MONTH_MISMATCH')
        require_quantities(row['monthly_ceiling'])
        require(row['monthly_ceiling']==ceiling,'LATCH_CEILING_MISMATCH')
        risk=row['risk_overlay']
        require_quantities(risk['base_target']['quantities'])
        require_quantities(risk['target_quantities'])
        require(risk['signal_date']==day and risk['base_target']['quantities']==ceiling
                and risk['base_target']['monthly_decision_date']==month,'LATCH_SIGNAL_BINDING')
        expected_target={}
        for sid,quantity in ceiling.items():
            require(type(quantity) is int and quantity>=0,'LATCH_NONINTEGER_CEILING')
            if quantity:
                diagnostic=risk['diagnostics'][sid]
                require(all(type(diagnostic[key]) is bool for key in ('on', 'on_sma9', 'on_sma20')), 'LATCH_INVALID_SIGNAL')
                require(type(diagnostic['monthly_ceiling']) is int, 'LATCH_NONINTEGER_DIAGNOSTIC')
                require(diagnostic['on']==(Fraction(diagnostic['close'])>Fraction(diagnostic['sma20']) and Fraction(diagnostic['close'])>Fraction(diagnostic['sma9'])),'LATCH_SIGNAL_COMPARISON')
                require(Fraction(diagnostic['close'])==Fraction(str(assembled['close_prices'][sid][day]))
                        and diagnostic['monthly_ceiling']==quantity,'LATCH_CURRENT_MARK')
                expected = quantity if diagnostic['on'] else quantity // 2
                changes += not diagnostic['on']
            else:
                expected = 0
            expected_target[sid] = expected
        require(risk['target_quantities']==expected_target and row['target_shares']==expected_target,'LATCH_TARGET_MISMATCH')
        expected_orders = {}
        for sid in sorted(set(holdings) | set(expected_target)):
            delta = expected_target.get(sid, 0) - holdings.get(sid, 0)
            if delta:
                expected_orders[sid] = ('BUY' if delta > 0 else 'SELL', abs(delta))
        orders = row['orders']
        require(len({o['security_id'] for o in orders}) == len(orders), 'DUPLICATE_TARGET_ORDER')
        require({o['security_id']:(o['side'],o['quantity']) for o in orders} == expected_orders, 'TARGET_ORDER_COMPLETENESS')
        for order in orders:
            require(type(order['quantity']) is int and order['quantity'] > 0, 'NONINTEGER_ORDER_QUANTITY')
            require(order['decision_date'] == day and order['active_date'] == sessions[index+1], 'TARGET_ORDER_DATE')
            require(Fraction(order['decision_mark']) == Fraction(str(assembled['close_prices'][order['security_id']][day])), 'TARGET_ORDER_MARK')
    return dict(status='SAVED_DUAL_MA_TARGETS_ACTIONS_ORDERS_VERIFIED',sessions=len(audit),weak_security_decisions=changes,
                raw_signal_histories_independently_recomputed=False)


def review(*, assembled, ohlc, outcome, scenario, expected_pins, expected_receipt_sha256, metrics=None):
    import re
    if not re.fullmatch('[0-9a-f]{64}',expected_receipt_sha256): raise ValueError('EXPECTED_RECEIPT_REQUIRED')
    expected=dict(receipt_sha256=expected_receipt_sha256,contract_path=CONTRACT,contract_sha256=CONTRACT_SHA,candidate=ARM)
    if outcome.get('research_run_binding') != expected or expected_pins.get(CONTRACT)!=CONTRACT_SHA:
        raise ValueError('RESEARCH_RUN_BINDING_MISMATCH')
    cash=review_cash(assembled=assembled,ohlc=ohlc,outcome=outcome,scenario=scenario,
        expected_pins=expected_pins,arm=ARM,initial_cash='20000')
    if cash['status']!='CASH_COST_BINDINGS_VERIFIED': raise ValueError('CASH_REVIEW_UNSUPPORTED')
    latch=review_targets(assembled=assembled,outcome=outcome)
    from scripts.review_cost_stress_saved_ledger import review as review_ledger
    ledger=review_ledger(outcome=outcome,session_dates=assembled['session_dates'],ohlc=ohlc,
        initial_cash='20000',fee_bps=COSTS[scenario][0],slippage_bps=COSTS[scenario][1])
    if ledger['status']!='SUPPORTED_SAVED_LEDGER_REPLAY_VERIFIED': raise ValueError('LEDGER_REVIEW_UNSUPPORTED')
    result=dict(status='MA9_SMA20_SAVED_EVIDENCE_VERIFIED',candidate=ARM,scenario=scenario,
        receipt_sha256=expected_receipt_sha256,cash_cost_review=cash,target_review=latch,ledger_review=ledger,
        source_authenticity_certified=False,independent_out_of_sample=False)
    if metrics is not None:
        from scripts.review_cost_stress_nav_metrics import review as review_nav
        result['nav_review']=review_nav(outcome=outcome,metrics=metrics,assembled=assembled,ohlc=ohlc,initial_cash='20000')
    return result

