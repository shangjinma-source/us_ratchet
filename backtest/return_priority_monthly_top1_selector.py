"""Frozen TOP1 research comparator, exact 12 mature price products; no IO."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
from data.current_research_capital_decision import decide_quantity_for_account

VERSION='MONTHLY_ACTUAL_EQUITY_EXACT_PRODUCT_TOP1_V1'

def select_top1_quantities(**arguments):
    args=deepcopy(arguments)
    prices,metadata,scenarios,dates=args['prices'],args['metadata'],args['training_scenarios'],args['scenario_dates']
    def amount(v):
        if isinstance(v,bool):raise ValueError('Boolean amount')
        return Fraction(str(v))
    decision=args['decision_date']
    if date.fromisoformat(decision).isoformat()!=decision:raise ValueError('Invalid decision')
    if len(scenarios)!=12 or len(dates)!=12 or dates!=sorted(set(dates)) or any(date.fromisoformat(d).isoformat()!=d or d>decision for d in dates):
        raise ValueError('Twelve mature common scenarios required')
    if not prices or set(prices)!=set(metadata) or any(set(s)!=set(prices) for s in scenarios):raise ValueError('Full candidate domain required')
    if any(amount(p)<=0 for p in prices.values()):raise ValueError('Positive prices required')
    cash=amount(args['entered_cash'])
    if cash<=0 or amount(args['fee_bps'])!=0 or amount(args['minimum_cash_buffer'])!=0:raise ValueError('Positive equity zero commission zero buffer required')
    products={}
    for sid in sorted(prices):
        value=Fraction(1)
        for scenario in scenarios:
            gross=amount(scenario[sid])
            if gross<=0:raise ValueError('Positive gross required')
            value*=gross
        products[sid]=value
    winner=min(products,key=lambda sid:(-products[sid],sid))
    q=int(cash//amount(prices[winner]));quantities={winner:q} if q else {}
    notional=q*amount(prices[winner])
    return dict(status='SELECTOR_COMPLETE',method=VERSION,decision_date=decision,entered_cash=str(cash),
        selected=dict(quantities=quantities,actual_k=len(quantities),notional=str(notional),fees='0',residual_cash=str(cash-notional),actual_weights={winner:str(notional/cash)} if q else {}),
        ranked_security_id=winner,training_gross_product=str(products[winner]),candidate_count=len(prices),
        ranking_rule='EXACT_PRODUCT_DESC_THEN_SID_ASC',core_calls=0,selector_calls=1,
        cash_scope='Residual only; insufficient one share does not select runner-up. No bearish signal or cash hurdle.',
        forecast_return=None,global_optimum_established=False)

def decide_top1_for_account(**kwargs):
    """Same capital binding/validation as quantity; honest selector call accounting.

    Capital validator's legacy status vocabulary is adapted internally only.
    Returned status and identifiers explicitly name this independent selector.
    """
    if 'search' in kwargs:raise ValueError('Selector cannot be replaced')
    if 'backtest/return_priority_monthly_top1_selector.py' not in kwargs['source_hashes']:
        raise ValueError('Selector source pin required')
    selected=[]
    def compatibility(**args):
        value=select_top1_quantities(**args)
        if not isinstance(value,dict) or value.get('status')!='SELECTOR_COMPLETE':
            raise ValueError('TOP1_SELECTOR_INCOMPLETE')
        selected.append(value)
        return dict(value,status='LOCAL_NEIGHBORHOODS_EXHAUSTED')
    result=decide_quantity_for_account(**kwargs,search=compatibility)
    result.update(core_calls=0,selector_calls=1,search_result=deepcopy(selected[0]),selector_result=deepcopy(selected[0]),method=VERSION)
    result['binding']['selection_method']=VERSION
    identifier=hashlib.sha256(json.dumps(result['binding'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    result.update(research_id=identifier[:24],decision_id=identifier)
    result['limitations'].append('Exact single-stock training ranking comparator; no quantity-core call or future return claim. Internal status compatibility does not assert neighborhood search.')
    return result
