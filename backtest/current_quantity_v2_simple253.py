"""Isolated simple endpoint comparator, no IO or future execution prices."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
from data.current_research_capital_decision import decide_quantity_for_account

VERSION='SIMPLE253_AFFORDABLE_ENDPOINT_TOP1_V1'


def positive(value):
    if isinstance(value,bool):raise ValueError('BOOLEAN_PRICE')
    value=Fraction(str(value))
    if value<=0:raise ValueError('NONPOSITIVE_VALUE')
    return value


def validate_training(*,window,arguments,calendar):
    days=window['training_dates'];decision=arguments['decision_date']
    if calendar!=sorted(set(calendar)) or any(date.fromisoformat(x).isoformat()!=x for x in calendar):
        raise ValueError('INVALID_SUPPLIED_CALENDAR')
    if decision not in calendar:raise ValueError('MISSING_DECISION_SESSION')
    end=calendar.index(decision)
    if len(days)!=253 or end<252 or days!=calendar[end-252:end+1] or window['decision_cutoff']!=decision:
        raise ValueError('253_CONTIGUOUS_COMPLETED_CLOSES_REQUIRED')
    if arguments['scenario_dates']!=days[21::21] or len(arguments['training_scenarios'])!=12:
        raise ValueError('SCENARIO_BOUNDARY_MISMATCH')
    candidates=window['candidates']
    ready=[row for row in candidates if row['status']=='READY_CONDITIONAL']
    rows={row['security_id']:row for row in ready};domain=set(arguments['prices'])
    if len(rows)!=len(ready) or set(rows)!=domain or domain!=set(arguments['metadata']):
        raise ValueError('TRAINING_DOMAIN_MISMATCH')
    if any(set(x)!=domain for x in arguments['training_scenarios']):raise ValueError('SCENARIO_DOMAIN_MISMATCH')
    ratios={}
    for sid,row in rows.items():
        if row.get('blockers') or row.get('missing_training_dates'):raise ValueError('BLOCKED_TRAINING')
        if {'ticker':row['ticker'],'issuer_id':row['issuer_id']}!=arguments['metadata'][sid]:raise ValueError('IDENTITY_MISMATCH')
        closes=list(map(positive,row['training_close']))
        if len(closes)!=253:raise ValueError('253_PRICES_REQUIRED')
        if positive(row['decision_cost'])!=positive(arguments['prices'][sid]):raise ValueError('DECISION_COST_MISMATCH')
        # Prepared training returns may use a reviewed common share coordinate
        # (e.g. SPECIAL_AZN), while cost is historical nominal execution units.
        # Exact scenario equivalence plus archive pins binds this existing basis;
        # equating the two prices would incorrectly reject a constant unit scale.
        for j,i in enumerate(range(0,252,21)):
            if closes[i+21]/closes[i]!=positive(arguments['training_scenarios'][j][sid]):
                raise ValueError('ENDPOINT_SCENARIO_MISMATCH')
        ratios[sid]=closes[-1]/closes[0]
    return ratios


def select_simple253(*,window,calendar,arguments):
    ratios=validate_training(window=window,arguments=arguments,calendar=calendar)
    cash=positive(arguments['entered_cash'])
    if Fraction(str(arguments['fee_bps']))!=0 or Fraction(str(arguments['minimum_cash_buffer']))!=0:
        raise ValueError('ZERO_SELECTION_FEE_BUFFER_REQUIRED')
    affordable=[sid for sid in ratios if positive(arguments['prices'][sid])<=cash]
    winner=min(affordable,key=lambda sid:(-ratios[sid],sid)) if affordable else None
    quantities={winner:int(cash//positive(arguments['prices'][winner]))} if winner else {}
    notional=sum((q*positive(arguments['prices'][sid]) for sid,q in quantities.items()),Fraction(0))
    return dict(status='SELECTOR_COMPLETE',method=VERSION,decision_date=arguments['decision_date'],entered_cash=str(cash),
        selected=dict(quantities=quantities,actual_k=len(quantities),notional=str(notional),fees='0',
                      residual_cash=str(cash-notional),actual_weights={sid:str(q*positive(arguments['prices'][sid])/cash) for sid,q in quantities.items()}),
        winner=winner,endpoint_ratios={sid:str(value) for sid,value in ratios.items()},
        core_calls=0,selector_calls=1,ranking='DESC_ENDPOINT_RATIO_THEN_ASC_SID_AMONG_AFFORDABLE')


def make_simple_decider(*,training_windows):
    windows={w['decision_cutoff']:deepcopy(w) for w in training_windows}
    if len(windows)!=len(training_windows):raise ValueError('DUPLICATE_TRAINING_MONTH')
    calendar=sorted({day for w in training_windows for day in w['training_dates']})
    def decide(**kwargs):
        observed=[]
        def selection(**arguments):
            result=select_simple253(window=windows[arguments['decision_date']],calendar=calendar,arguments=arguments)
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


def compare_saved_v2_states(*,outcome,training_windows):
    """No V2 recomputation: evaluate simple rule on each saved V2 decision state."""
    decide=make_simple_decider(training_windows=training_windows);rows=[]
    for audit in outcome['provider_audit']:
        saved=audit.get('selection')
        if not saved:continue
        if saved.get('method')!='EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2':raise ValueError('NOT_V2_BASELINE')
        b=saved['binding'];arguments=deepcopy(b['search_arguments'])
        quotes=[dict(security_id=sid,**q) for sid,q in b['valuation_quotes'].items()]
        arguments.update(quote_as_of=b['decision_date'],price_basis=quotes[0]['price_basis'])
        simple=decide(decision_date=b['decision_date'],account_state=dict(asof=b['decision_date'],revision=b['state_revision'],
            cash=b['available_cash'],shares=b['shares'],reserved_cash='0'),valuation_quotes=quotes,
            search_arguments=arguments,source_hashes=b['source_hashes'])
        rows.append(dict(decision_date=b['decision_date'],same_state_equity=b['investable_equity'],
            v2_target=saved['target_quantities'],simple_target=simple['target_quantities'],
            targets_equal=saved['target_quantities']==simple['target_quantities'],
            v2_residual=saved['search_result']['selected']['residual_cash'],simple_residual=simple['search_result']['selected']['residual_cash']))
    return rows
