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
    require(scenario in COSTS and arm == 'simple253_cost', 'UNKNOWN_STRESS_ARM')
    require(expected_pins and all(isinstance(p, str) and isinstance(h, str) and len(h) == 64
                                 for p, h in expected_pins.items()), 'EXPECTED_PINS_REQUIRED')
    fee, slip = map(lambda value: Fraction(value)/10000, COSTS[scenario])
    binding = outcome['cost_stress_binding']
    expected_binding = dict(schema='COST_STRESS_ARM_BINDING_V1', arm=arm, scenario=scenario,
        initial_cash=str(initial_cash), selector_method=arm, optimizer_calls=0,
        source_hashes=expected_pins, fee_bps=COSTS[scenario][0], slippage_bps=COSTS[scenario][1])
    require(json.dumps(binding,sort_keys=True,separators=(',',':'),allow_nan=False) == json.dumps(expected_binding,sort_keys=True,separators=(',',':'),allow_nan=False), 'ARM_BINDING_MISMATCH')
    binding_hash = sha256(json.dumps(binding, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    require(outcome['cost_stress_binding_sha256'] == binding_hash, 'ARM_BINDING_HASH_MISMATCH')
    require(outcome['cost_stress_arm'] == arm and outcome['cost_stress_scenario'] == scenario, 'ARM_LABEL_MISMATCH')
    require(outcome['status'] == 'COMPLETE', 'INCOMPLETE_OUTCOME')
    require(outcome.get('automatic_promotion') is False and outcome.get('costs_are_research_assumptions') is True, 'RESEARCH_FLAGS_REQUIRED')
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

ARM = 'simple253_cost'
CONTRACT = 'research_contracts/simple253_cost_execution_20261019_v1.json'
CONTRACT_SHA = 'f43ee53e1e3f7da1545a9d0c945c166d3bbd74d43ca65368f02815d691d9fe2d'


def review_targets(*, assembled, outcome):
    """Reconstruct full monthly targets and daily difference orders independently.

    Corporate target adjustments are checked against supplied action ratios.
    Endpoint ranking is independently recomputed by review_selection.
    """
    def require(ok, reason):
        if not ok: raise ValueError(reason)
    sessions = assembled['session_dates']
    audit = outcome['provider_audit']
    require(len(audit) == len(sessions)-1, 'LATCH_AUDIT_COVERAGE')
    plans = {r['decision_date'] for r in assembled['monthly_inputs']}
    ceiling, month = {}, None
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
        expected_target=dict(ceiling)
        require(row['target_shares']==expected_target,'FULL_TARGET_MISMATCH')
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
    return dict(status='SAVED_SIMPLE_TARGETS_ACTIONS_ORDERS_VERIFIED',sessions=len(audit),
                endpoint_selection_verified_separately=True)


def review(*, assembled, ohlc, outcome, scenario, expected_pins, expected_receipt_sha256, training_windows, metrics=None):
    import re
    if not re.fullmatch('[0-9a-f]{64}',expected_receipt_sha256): raise ValueError('EXPECTED_RECEIPT_REQUIRED')
    expected=dict(receipt_sha256=expected_receipt_sha256,contract_path=CONTRACT,contract_sha256=CONTRACT_SHA,candidate=ARM)
    if outcome.get('research_run_binding') != expected or expected_pins.get(CONTRACT)!=CONTRACT_SHA:
        raise ValueError('RESEARCH_RUN_BINDING_MISMATCH')
    cash=review_cash(assembled=assembled,ohlc=ohlc,outcome=outcome,scenario=scenario,
        expected_pins=expected_pins,arm=ARM,initial_cash='20000')
    if cash['status']!='CASH_COST_BINDINGS_VERIFIED': raise ValueError('CASH_REVIEW_UNSUPPORTED')
    signal=review_selection(assembled=assembled,outcome=outcome,training_windows=training_windows,scenario=scenario)
    latch=review_targets(assembled=assembled,outcome=outcome)
    from scripts.review_cost_stress_saved_ledger import review as review_ledger
    ledger=review_ledger(outcome=outcome,session_dates=assembled['session_dates'],ohlc=ohlc,
        initial_cash='20000',fee_bps=COSTS[scenario][0],slippage_bps=COSTS[scenario][1])
    if ledger['status']!='SUPPORTED_SAVED_LEDGER_REPLAY_VERIFIED': raise ValueError('LEDGER_REVIEW_UNSUPPORTED')
    result=dict(status='SIMPLE253_SAVED_EVIDENCE_VERIFIED',candidate=ARM,scenario=scenario,
        receipt_sha256=expected_receipt_sha256,cash_cost_review=cash,selection_review=signal,target_review=latch,ledger_review=ledger,
        source_authenticity_certified=False,independent_out_of_sample=False)
    if metrics is not None:
        from scripts.review_cost_stress_nav_metrics import review as review_nav
        result['nav_review']=review_nav(outcome=outcome,metrics=metrics,assembled=assembled,ohlc=ohlc,initial_cash='20000')
    return result



def review_selection(*, assembled, outcome, training_windows, scenario):
    """Independent exact endpoint ranking and fee-inclusive sizing, no selector call."""
    def require(ok,reason):
        if not ok:raise ValueError(reason)
    def number(v):
        require(not isinstance(v,bool),'BOOLEAN_SIGNAL_AMOUNT')
        return Fraction(str(v))
    def digest(v):
        return sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    windows={w['decision_cutoff']:w for w in training_windows}
    plans={p['decision_date']:p for p in assembled['monthly_inputs']}
    require(len(windows)==len(training_windows) and set(windows)==set(plans),'TRAINING_MONTH_COVERAGE')
    calendar=sorted({d for w in training_windows for d in w['training_dates']})
    selections=[r['selection'] for r in outcome['provider_audit'] if r.get('selection')]
    require([s['decision_date'] for s in selections]==list(plans),'SELECTION_COVERAGE')
    fee=Fraction(COSTS[scenario][0])/10000
    for sel in selections:
        require(type(sel.get('core_calls')) is int and sel['core_calls']==0 and type(sel.get('selector_calls')) is int and sel['selector_calls']==1,'SELECTION_CALLS')
        day=sel['decision_date'];w=windows[day];args=plans[day]['search_arguments'];b=sel['binding']
        end=calendar.index(day);dates=w['training_dates']
        require(len(dates)==253 and dates==calendar[end-252:end+1] and dates[-1]==day,'TRAINING_CAUSAL_WINDOW')
        require(args['scenario_dates']==dates[21::21] and len(args['training_scenarios'])==12,'SCENARIO_DATES')
        rows={r['security_id']:r for r in w['candidates'] if r['status']=='READY_CONDITIONAL'}
        require(len(rows)==len(w['candidates']) and set(rows)==set(args['prices'])==set(args['metadata']),'TRAINING_DOMAIN')
        ratios={}
        for sid,r in rows.items():
            require(not r.get('blockers') and not r.get('missing_training_dates'),'TRAINING_BLOCKED')
            require({k:r[k] for k in ('ticker','issuer_id')}==args['metadata'][sid],'TRAINING_IDENTITY')
            values=list(map(number,r['training_close']))
            require(len(values)==253 and all(v>0 for v in values),'TRAINING_PRICES')
            require(number(r['decision_cost'])==number(args['prices'][sid]),'TRAINING_COST')
            for j,i in enumerate(range(0,252,21)):
                require(set(args['training_scenarios'][j])==set(rows) and values[i+21]/values[i]==number(args['training_scenarios'][j][sid]),'TRAINING_SCENARIO_RATIO')
            ratios[sid]=values[-1]/values[0]
        expected_args=dict(args);expected_args.pop('quote_as_of');expected_args.pop('price_basis')
        expected_args.update(entered_cash=b['investable_equity'],fee_bps=COSTS[scenario][0])
        require(b['search_arguments']==expected_args,'SEARCH_ARGUMENT_BINDING')
        require(b['selection_method']=='SIMPLE253_COST_AFFORDABLE_ENDPOINT_TOP1_V1' and b['training_window_sha256']==digest(w),'TRAINING_BINDING')
        require(sel['decision_id']==digest(b) and sel['research_id']==digest(b)[:24],'DECISION_HASH')
        equity=number(sel['investable_equity'])
        affordable=[sid for sid in rows if number(args['prices'][sid])*(1+fee)<=equity]
        winner=min(affordable,key=lambda sid:(-ratios[sid],sid)) if affordable else None
        quantities={winner:int(equity//(number(args['prices'][winner])*(1+fee)))} if winner else {}
        require_quantities(sel['target_quantities']);require(sel['target_quantities']==quantities,'SIMPLE_TARGET')
        result=sel['search_result'];selected=result['selected']
        require(result['winner']==winner and result['endpoint_ratios']=={sid:str(v) for sid,v in ratios.items()},'SIMPLE_RANKING')
        require(result['method']==b['selection_method'] and result['decision_date']==day and number(result['entered_cash'])==equity,'SIMPLE_RESULT_BINDING')
        require(type(result['core_calls']) is int and result['core_calls']==0 and type(result['selector_calls']) is int and result['selector_calls']==1,'SIMPLE_CALLS')
        require_quantities(selected['quantities'])
        require(selected['quantities']==quantities and type(selected['actual_k']) is int and selected['actual_k']==len(quantities),'SIMPLE_SELECTED')
        notional=sum((q*number(args['prices'][sid]) for sid,q in quantities.items()),Fraction(0))
        require(number(selected['notional'])==notional and number(selected['fees'])==notional*fee and number(selected['residual_cash'])==equity-notional*(1+fee),'SIMPLE_ACCOUNTING')
        require(selected['actual_weights']=={sid:str(q*number(args['prices'][sid])/equity) for sid,q in quantities.items()},'SIMPLE_WEIGHTS')
    return dict(status='SIMPLE253_RANKING_AFFORDABILITY_RECOMPUTED',months=len(selections),selector_called=False,source_authenticity_certified=False)
