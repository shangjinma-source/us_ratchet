"""Offline first-unit diagnostics only. No allocation, state, API or order access."""
from decimal import Context, Decimal, InvalidOperation, localcontext
from copy import deepcopy

TOLERANCE = Decimal('0.01')
FRONTEND_MAPPING = {
    'side': 'renderBuyPlan: side === BUY',
    'source': 'renderBuyPlan: exclude ratchet_next',
    'action': 'renderBuyPlan: BUY_NOW or PLACE_LIMIT',
    'share_plan_eligible': 'renderBuyPlan: explicit false excludes; missing is UNKNOWN here',
    'position_kind': 'renderBuyPlan: reported_closed excludes; pending_entry requires tactical_limit',
    'gap_positive': 'renderBuyPlan: real position gap_amount > 0',
    'price': 'plannerItemPrice: non-null limit precedes live_price',
    'budget': 'plannerCanFundFirstUnit: original amount positive and covers unit notional + 0.01 tolerance',
    'gap': 'plannerCanFundFirstUnit: real gap covers unit notional + 0.01 tolerance',
    'cash': 'plannerCanFundFirstUnit: unit notional + max(min_fee, notional*fee_bps/10000) <= cash + 0.01',
    'scope': 'No priority, duplicate-item selection, max_names, max_single_amount or portfolio allocation reproduced',
}


def decimal_or_none(value, *, positive=False):
    if type(value) not in (str, int, float, Decimal):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not result.is_finite() or result < 0 or (positive and result == 0):
        return None
    return result


def gate(known, passed, failure, unknown):
    return dict(status='UNKNOWN' if not known else 'PASS' if passed else 'FAIL',
        code=unknown if not known else None if passed else failure)


def diagnose(*, execution_items, gap_rows, research_cash_usd, policy, snapshot_reference=None):
    """Use exact finite-decimal arithmetic independent of the caller's context.

    The largest expression multiplies three inputs, divides by 10000 and adds
    another input. Three times the input digit span plus guard digits covers it.
    Unreasonably large spans are rejected explicitly instead of rounded.
    """
    if type(execution_items) is not list or type(gap_rows) is not list or type(policy) is not dict:
        raise ValueError('Explicit item list, gap list and policy dictionary required')
    if any(type(x) is not dict for x in execution_items + gap_rows):
        raise ValueError('Items and gaps must be dictionaries')
    values=[research_cash_usd, policy.get('lot_size'), policy.get('fee_bps'), policy.get('min_fee'), TOLERANCE, 10000]
    values.extend(item.get(key) for item in execution_items for key in ('limit', 'live_price', 'amount'))
    values.extend(row.get('gap_amount') for row in gap_rows)
    numbers=[number for value in values if (number := decimal_or_none(value)) is not None]
    span=max(number.adjusted() for number in numbers)-min(number.as_tuple().exponent for number in numbers)+1
    precision=max(28, 3*span+16)
    if precision > 10000 or any(abs(number.as_tuple().exponent)>10000 for number in numbers):
        raise ValueError('Numeric range exceeds offline diagnostic arithmetic contract')
    with localcontext(Context(prec=precision)):
        return _diagnose(execution_items=execution_items, gap_rows=gap_rows,
            research_cash_usd=research_cash_usd, policy=policy, snapshot_reference=snapshot_reference)


def _diagnose(*, execution_items, gap_rows, research_cash_usd, policy, snapshot_reference=None):
    """Each input item remains a row; cash is independently compared, never allocated.

    policy requires explicit allow_fractional, lot_size, fee_bps and min_fee.
    Missing/invalid fields yield UNKNOWN, not zero or a default eligibility pass.
    Cash must already be the caller's explicit research spending ceiling.
    """
    if type(execution_items) is not list or type(gap_rows) is not list or type(policy) is not dict:
        raise ValueError('Explicit item list, gap list and policy dictionary required')
    if any(type(x) is not dict for x in execution_items + gap_rows):
        raise ValueError('Items and gaps must be dictionaries')
    cash=decimal_or_none(research_cash_usd)
    lot=decimal_or_none(policy.get('lot_size'),positive=True)
    fee_bps=decimal_or_none(policy.get('fee_bps')); minimum=decimal_or_none(policy.get('min_fee'))
    fractional=policy.get('allow_fractional')
    rows=[]
    for ordinal,item in enumerate(execution_items):
        ticker=item.get('ticker'); ticker_known=type(ticker) is str and bool(ticker) and not any(character.isspace() for character in ticker)
        symbol=ticker.upper() if ticker_known else None
        matches=[r for r in gap_rows if type(r.get('ticker')) is str and r['ticker'].upper()==symbol] if ticker_known else []
        position=matches[0] if len(matches)==1 else None
        gap=decimal_or_none(position.get('gap_amount')) if position else None
        kind=position.get('position_kind') if position else None
        kind_known=kind in ('real_position','pending_entry','reported_closed')
        source=item.get('source'); source_known=type(source) is str and bool(source)
        side=item.get('side'); action=item.get('action'); eligible=item.get('share_plan_eligible')
        selected_price=item.get('limit') if item.get('limit') is not None else item.get('live_price')
        price=decimal_or_none(selected_price,positive=True)
        budget=decimal_or_none(item.get('amount'))
        unit_notional=price*lot if price is not None and lot is not None else None
        one_share_fee=max(minimum,price*fee_bps/Decimal(10000)) if price is not None and minimum is not None and fee_bps is not None else None
        unit_fee=max(minimum,unit_notional*fee_bps/Decimal(10000)) if unit_notional is not None and minimum is not None and fee_bps is not None else None
        unit_cash=unit_notional+unit_fee if unit_fee is not None else None
        gates={
            'ticker':gate(ticker_known,True,'INVALID_TICKER','TICKER_UNKNOWN'),
            'side':gate(type(side) is str,side=='BUY','NOT_BUY','SIDE_UNKNOWN'),
            'source':gate(source_known,source!='ratchet_next','DEEP_RATCHET_EXCLUDED','SOURCE_UNKNOWN'),
            'action':gate(type(action) is str,action in ('BUY_NOW','PLACE_LIMIT'),'ACTION_NOT_BUY_OR_LIMIT','ACTION_UNKNOWN'),
            'share_plan_eligible':gate(type(eligible) is bool,eligible is True,'SHARE_PLAN_INELIGIBLE','SHARE_PLAN_ELIGIBILITY_UNKNOWN'),
            'gap_row':gate(len(matches)==1,True,'GAP_ROW_INVALID','GAP_ROW_AMBIGUOUS' if len(matches)>1 else 'GAP_ROW_MISSING'),
            'position_kind':gate(kind_known,kind!='reported_closed','REPORTED_CLOSED_EXCLUDED','POSITION_KIND_UNKNOWN'),
            'pending_source':gate(kind_known and (kind!='pending_entry' or source_known),kind!='pending_entry' or source=='tactical_limit','PENDING_ENTRY_REQUIRES_TACTICAL_SOURCE','PENDING_SOURCE_UNKNOWN'),
            'gap_positive':gate(gap is not None,gap is not None and gap>0,'NO_POSITIVE_REAL_GAP','GAP_AMOUNT_UNKNOWN'),
            'price':gate(price is not None,True,'PRICE_INVALID','PRICE_UNKNOWN_OR_INVALID'),
            'whole_unit_policy':gate(type(fractional) is bool and fractional is False and lot is not None,lot is not None and lot==lot.to_integral_value(),'NON_INTEGER_LOT_IN_WHOLE_SHARE_MODE','FRACTIONAL_POLICY_NOT_MODELLED' if fractional is True else 'WHOLE_UNIT_POLICY_UNKNOWN'),
            'budget':gate(budget is not None and unit_notional is not None,budget is not None and budget>0 and unit_notional is not None and unit_notional<=budget+TOLERANCE,'STRATEGY_BUDGET_BELOW_ONE_UNIT','STRATEGY_BUDGET_OR_UNIT_UNKNOWN'),
            'gap':gate(gap is not None and unit_notional is not None,gap is not None and unit_notional is not None and unit_notional<=gap+TOLERANCE,'REAL_GAP_BELOW_ONE_UNIT','REAL_GAP_OR_UNIT_UNKNOWN'),
            'cash':gate(cash is not None and unit_cash is not None,cash is not None and unit_cash is not None and unit_cash<=cash+TOLERANCE,'RESEARCH_CASH_INSUFFICIENT_INCLUDING_FEE','RESEARCH_CASH_OR_FEE_UNKNOWN'),
        }
        failed=[g['code'] for g in gates.values() if g['status']=='FAIL']; unknown=[g['code'] for g in gates.values() if g['status']=='UNKNOWN']
        status='BLOCKED' if failed else 'UNKNOWN' if unknown else 'FIRST_UNIT_GATES_PASS_NOT_ALLOCATION'
        def text(v):return str(v) if v is not None else None
        rows.append(dict(item_ordinal=ordinal,ticker=deepcopy(ticker),strategy_budget=deepcopy(item.get('amount')),
            strategy_budget_usd=text(budget),observation_limit=deepcopy(item.get('limit')),
            selected_price_usd=text(price),price_field_used='limit' if item.get('limit') is not None else 'live_price',
            source=deepcopy(source),action=deepcopy(action),snapshot_item=deepcopy(item),real_gap_row=deepcopy(position),
            one_share_notional_usd=text(price),one_share_fee_usd=text(one_share_fee),
            one_share_cash_required_usd=text(price+one_share_fee) if one_share_fee is not None else None,
            lot_size=text(lot),one_unit_notional_usd=text(unit_notional),one_unit_fee_usd=text(unit_fee),one_unit_cash_required_usd=text(unit_cash),
            real_gap_usd=text(gap),research_cash_usd=text(cash),gates=gates,blocking_codes=failed,unknown_codes=unknown,
            status=status,first_unit_affordable=False if failed else None if unknown else True,
            allocated_shares=None,order_authorized=False,strategy_budget_expanded=False))
    return dict(schema='OFFLINE_FUND_SIGNAL_FIRST_UNIT_DIAGNOSTIC_V1',rows=rows,input_item_count=len(execution_items),
        snapshot_reference=deepcopy(snapshot_reference),research_cash_input=deepcopy(research_cash_usd),policy=deepcopy(policy),
        source_semantics='CALLER_SUPPLIED_SNAPSHOT_NOT_VERIFIED_LIVE_STATE',frontend_mapping=deepcopy(FRONTEND_MAPPING),
        arithmetic='DECIMAL_WITH_FRONTEND_0_01_COMPARISON_TOLERANCE_NOT_JS_BINARY_REPLAY',
        fee_semantics='PER_TICKER_ORDER_MAX_MINIMUM_OR_PROPORTIONAL_NOT_PER_SHARE_MULTIPLIED',
        independent_row_cash_checks_are_not_joint_allocation=True,research_only=True,
        missing_fields_defaulted=False,strategy_budget_expanded=False,live_state_read=False,live_state_written=False,
        api_called=False,order_authorized=False,portfolio_allocation_performed=False,core_deployment_planner_called=False,
        dynamic_optimization_performed=False,current_account_readiness_verified=False)
