"""Apply audited same-date gross returns to the CURRENT branch account target."""
from copy import deepcopy
from fractions import Fraction
from docs.candidates.qqq_risk_budget_exact import scale_targets_to_qqq_risk


def apply_risk_budget_selection(*, selected, arguments, risk_input):
    day=arguments['decision_date']
    if risk_input.get('status')!='CONDITIONAL_INPUT_READY' or risk_input.get('decision_date')!=day:
        raise ValueError('CURRENT_REVIEWED_RISK_INPUT_REQUIRED')
    saved=risk_input['arguments'];target=selected['target_quantities']
    if any(type(q) is not int or q<0 for q in target.values()):
        raise ValueError('NONNEGATIVE_INTEGER_TARGET_REQUIRED')
    positive={s:q for s,q in target.items() if q>0}
    if saved['decision_date']!=day or not set(positive)<=set(saved['stock_gross_returns']):
        raise ValueError('BLOCKED_DYNAMIC_TARGET_RISK_COVERAGE_REQUIRED')
    quotes={}
    for row in arguments['valuation_quotes']:
        sid=row['security_id']
        if sid in quotes:raise ValueError('DUPLICATE_DECISION_QUOTE')
        quotes[sid]=row['price']
    account=arguments['account_state']
    equity=Fraction(account['cash'])+sum((q*Fraction(quotes[s]) for s,q in account['shares'].items() if q),Fraction(0))
    if equity!=Fraction(selected['investable_equity']):
        raise ValueError('BRANCH_TRADABLE_EQUITY_MISMATCH')
    budget=scale_targets_to_qqq_risk(decision_date=day,target_quantities=positive,
        decision_prices={s:quotes[s] for s in positive},tradable_equity=str(equity),
        stock_gross_returns={s:saved['stock_gross_returns'][s] for s in positive},
        qqq_gross_returns=saved['qqq_gross_returns'])
    budget['zero_target_securities_excluded_from_covariance']=sorted(set(target)-set(positive))
    budget['original_target_quantities']=dict(target)
    budget['target_quantities']={s:budget['target_quantities'].get(s,0) for s in target}
    result=deepcopy(selected)
    result['risk_budget_original_selection']=deepcopy(selected)
    result['risk_budget']=budget
    result['risk_budget_source_binding']=deepcopy(risk_input['source_binding'])
    result['target_quantities']=budget['target_quantities']
    return result
