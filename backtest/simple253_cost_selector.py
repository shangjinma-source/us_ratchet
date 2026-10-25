"""Isolated fee-aware simple253 comparator; no IO or execution-price selection."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from backtest.current_quantity_v2_simple253 import positive, validate_training
from data.current_research_capital_decision import decide_quantity_for_account

VERSION = 'SIMPLE253_COST_AFFORDABLE_ENDPOINT_TOP1_V1'

def select_cost_simple253(*,window,calendar,arguments):
    ratios=validate_training(window=window,arguments=arguments,calendar=calendar)
    cash=positive(arguments['entered_cash'])
    if type(arguments['fee_bps']) is bool or str(arguments['fee_bps']) not in {'0','1'} or isinstance(arguments['minimum_cash_buffer'],bool) or Fraction(str(arguments['minimum_cash_buffer']))!=0:
        raise ValueError('DECLARED_FEE_ZERO_BUFFER_REQUIRED')
    fee_rate=Fraction(str(arguments['fee_bps']))/10000
    unit_cost={sid:positive(arguments['prices'][sid])*(1+fee_rate) for sid in ratios}
    affordable=[sid for sid in ratios if unit_cost[sid]<=cash]
    winner=min(affordable,key=lambda sid:(-ratios[sid],sid)) if affordable else None
    quantities={winner:int(cash//unit_cost[winner])} if winner else {}
    notional=sum((q*positive(arguments['prices'][sid]) for sid,q in quantities.items()),Fraction(0))
    return dict(status='SELECTOR_COMPLETE',method=VERSION,decision_date=arguments['decision_date'],entered_cash=str(cash),
        selected=dict(quantities=quantities,actual_k=len(quantities),notional=str(notional),fees=str(notional*fee_rate),
                      residual_cash=str(cash-notional*(1+fee_rate)),actual_weights={sid:str(q*positive(arguments['prices'][sid])/cash) for sid,q in quantities.items()}),
        winner=winner,endpoint_ratios={sid:str(value) for sid,value in ratios.items()},
        core_calls=0,selector_calls=1,ranking='DESC_ENDPOINT_RATIO_THEN_ASC_SID_AMONG_FEE_INCLUSIVE_AFFORDABLE')


def make_cost_simple_decider(*,training_windows):
    windows={w['decision_cutoff']:deepcopy(w) for w in training_windows}
    if len(windows)!=len(training_windows):raise ValueError('DUPLICATE_TRAINING_MONTH')
    calendar=sorted({day for w in training_windows for day in w['training_dates']})
    def decide(**kwargs):
        observed=[]
        def selection(**arguments):
            result=select_cost_simple253(window=windows[arguments['decision_date']],calendar=calendar,arguments=arguments)
            observed.append(result)
            return dict(result,status='LOCAL_NEIGHBORHOODS_EXHAUSTED')
        result=decide_quantity_for_account(**kwargs,search=selection)
        result.update(core_calls=0,selector_calls=1,method=VERSION,search_result=observed[0])
        result['binding']['selection_method']=VERSION
        result['binding']['training_window_sha256']=hashlib.sha256(json.dumps(windows[kwargs['decision_date']],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        digest=hashlib.sha256(json.dumps(result['binding'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        result.update(decision_id=digest,research_id=digest[:24])
        return result
    return decide

