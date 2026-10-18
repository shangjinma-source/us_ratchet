"""Independent arithmetic and binding checks; not a full corporate-action replay."""
from fractions import Fraction
from hashlib import sha256
import json

COSTS = {'slippage5': ('0', '5'), 'fee1_slippage10': ('1', '10')}


def review(*, assembled, ohlc, outcome, scenario, expected_pins, arm, initial_cash):
    def require(condition, reason):
        if not condition:
            raise ValueError(reason)
    def number(value):
        require(not isinstance(value, bool), 'BOOLEAN_AMOUNT')
        return Fraction(str(value))
    require(scenario in COSTS and arm in ('continuous32', 'continuous32_half'), 'UNKNOWN_STRESS_ARM')
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
