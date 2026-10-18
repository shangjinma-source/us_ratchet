"""Financially feasible integer incumbent control, with observational risk only.

Targets are never projected. This fixed-control research allocator cannot admit
candidate portfolios. A finite-domain optimum is not a global portfolio answer.
"""
import itertools
import math
from collections.abc import Mapping

RISK_FIELDS=frozenset({'max_single_weight','min_single_weight','top_weight_cap',
    'minimum_effective_n_ratio','risk_chain_top1_cap'})
TOLERANCE=1e-9


def _require(condition,message):
    if not condition:
        raise ValueError(message)


def _number(value,label,*,positive=False):
    _require(type(value) in (int,float) and math.isfinite(value)
        and (value>0 if positive else value>=0),'Invalid '+label)
    return float(value)


def search_incumbent_integer_control_domain(*,prices,target_weights,current_shares,current_cash,
        transaction_cost_bps,minimum_cash_buffer_usd,risk_chain_by_ticker,
        constraints,share_domains,max_evaluations):
    """Enumerate a deterministic prefix of the full explicit Cartesian domain.

    E_after = initial marked equity - fees. Securities target
    target_weights * (E_after-buffer)/E_after; cash target buffer/E_after.
    All security concentration constraints use invested equity, not total equity.
    The Pareto objectives are (cash-inclusive squared tracking error, fees USD).
    Missing budgeted vectors are unexamined, never classified as infeasible.
    """
    mappings=(prices,target_weights,current_shares,risk_chain_by_ticker,share_domains)
    _require(all(isinstance(v,Mapping) and v for v in mappings),'Explicit nonempty mappings required')
    _require(all(isinstance(t,str) and t and t==t.strip() for t in prices),'Invalid ticker')
    names=sorted(prices)
    _require(all(set(v)==set(names) for v in mappings),'Ticker coverage differs')
    _require(isinstance(constraints,Mapping) and set(constraints)==RISK_FIELDS,'Complete risk contract required')
    risk={key:_number(value,key,positive=True) for key,value in constraints.items()}
    _require(all(v<=1 for v in risk.values()) and risk['min_single_weight']<=risk['max_single_weight'],
             'Invalid risk bounds')
    marks={t:_number(prices[t],'price',positive=True) for t in names}
    target={t:_number(target_weights[t],'target weight',positive=True) for t in names}
    _require(abs(sum(target.values())-1)<=1e-10,'Target weights must sum to one')
    _require(all(type(current_shares[t]) is int and current_shares[t]>=0 for t in names),'Invalid current shares')
    _require(all(isinstance(risk_chain_by_ticker[t],str) and risk_chain_by_ticker[t]
        and risk_chain_by_ticker[t]==risk_chain_by_ticker[t].strip() for t in names),'Invalid risk chain')
    domains={}
    for ticker in names:
        domain=share_domains[ticker]
        _require(isinstance(domain,(list,tuple)) and domain
            and all(type(v) is int and v>=0 for v in domain)
            and len(domain)==len(set(domain)),'Invalid/duplicate integer domain')
        domains[ticker]=sorted(domain)
    _require(type(max_evaluations) is int and max_evaluations>0,'Positive explicit search budget required')
    cash=_number(current_cash,'current cash')
    buffer=_number(minimum_cash_buffer_usd,'cash buffer')
    fees_rate=_number(transaction_cost_bps,'transaction cost bps')/10000.
    initial_equity=cash+sum(current_shares[t]*marks[t] for t in names)
    _require(math.isfinite(initial_equity) and initial_equity>0,'Invalid pretrade equity')
    denominator=math.prod(len(v) for v in domains.values())
    evaluated=feasible=0;failure_counts={};risk_failure_counts={};pareto=[]
    for vector in itertools.islice(itertools.product(*(domains[t] for t in names)),max_evaluations):
        evaluated+=1
        shares=dict(zip(names,vector))
        purchases=sum(max(0,shares[t]-current_shares[t])*marks[t] for t in names)
        sales=sum(max(0,current_shares[t]-shares[t])*marks[t] for t in names)
        fees=(purchases+sales)*fees_rate
        after_cash=cash+sales-purchases-fees
        notionals={t:shares[t]*marks[t] for t in names}
        invested=sum(notionals.values());equity=initial_equity-fees
        _require(all(math.isfinite(v) for v in (fees,after_cash,invested,equity)), 'Allocation arithmetic overflow')
        failures=[]
        if after_cash<buffer-TOLERANCE:failures.append('CASH_BUFFER')
        if after_cash<0:failures.append('NEGATIVE_CASH')
        if equity<=0:failures.append('NONPOSITIVE_EQUITY')
        if failures:
            for reason in failures:failure_counts[reason]=failure_counts.get(reason,0)+1
            continue
        failures=[]
        if min(vector)<1:failures.append('MINIMUM_ONE_SHARE')
        if invested<=0:failures.append('NO_INVESTED_EQUITY')
        weights={t:notionals[t]/invested if invested>0 else 0. for t in names}
        ordered=sorted(weights.values(),reverse=True)
        effective=1/sum(w*w for w in weights.values()) if invested>0 else 0.
        groups={}
        for t,w in weights.items():
            group=risk_chain_by_ticker[t];groups[group]=groups.get(group,0.)+w
        if min(weights.values())<risk['min_single_weight']-TOLERANCE:failures.append('WEIGHT_FLOOR')
        if max(weights.values())>risk['max_single_weight']+TOLERANCE:failures.append('TOP1')
        if sum(ordered[:3])>risk['top_weight_cap']+TOLERANCE:failures.append('TOP3')
        if effective<risk['minimum_effective_n_ratio']*len(names)-TOLERANCE:failures.append('EFFECTIVE_N')
        if max(groups.values())>risk['risk_chain_top1_cap']+TOLERANCE:failures.append('RISK_CHAIN_TOP1')
        for reason in failures:risk_failure_counts[reason]=risk_failure_counts.get(reason,0)+1
        feasible+=1
        security_error=sum((weights[t]-target[t])**2 for t in names)
        cash_error=((after_cash-buffer)/equity)**2
        tracking=sum((notionals[t]/equity-target[t]*(equity-buffer)/equity)**2 for t in names)+cash_error
        candidate=dict(shares=shares,risk_constraints_passed=not failures,risk_failure_reasons=list(failures),
            fees_usd=fees,posttrade_cash_usd=after_cash,posttrade_equity_usd=equity,
            purchases_usd=purchases,sales_usd=sales,security_weights=weights,effective_n=effective,
            risk_chain_weights=groups,security_only_tracking_error=security_error,
            cash_tracking_error=cash_error,total_tracking_error_including_cash=tracking)
        def dominates(a,b):
            x=(a['total_tracking_error_including_cash'],a['fees_usd'])
            y=(b['total_tracking_error_including_cash'],b['fees_usd'])
            return all(left<=right for left,right in zip(x,y)) and any(left<right for left,right in zip(x,y))
        if not any(dominates(p,candidate) for p in pareto):
            pareto=[p for p in pareto if not dominates(candidate,p)]
            pareto.append(candidate)
    complete=evaluated==denominator
    selected = min(pareto, key=lambda row:(row['total_tracking_error_including_cash'],row['fees_usd'],
        tuple(row['shares'][ticker] for ticker in names))) if pareto else None
    return dict(schema='ndx_incumbent_integer_control_research_v1',
        role='INCUMBENT_CONTROL',candidate_eligibility=False,
        target_weights=dict(target),target_weights_projected=False,risk_contract=dict(risk),
        risk_chain_by_ticker=dict(risk_chain_by_ticker),risk_constraints_enforced=False,
        risk_failure_counts=risk_failure_counts,selected_tracking_first=selected,
        selection_policy='TRACKING_FIRST_THEN_FEES_THEN_LEXICOGRAPHIC_SHARES',
        portfolio_scope='FIXED_EXPLICIT_TICKER_SET_FINITE_INTEGER_DOMAIN',
        share_domains=domains,finite_domain_size=denominator,evaluated=evaluated,unexamined=denominator-evaluated,
        feasible_evaluated=feasible,infeasible_evaluated=evaluated-feasible,failure_counts=failure_counts,
        pareto=pareto,pareto_complete_within_explicit_domain=complete,
        status='FINITE_DOMAIN_EXHAUSTED' if complete else 'BUDGET_LIMITED_PARTIAL_DOMAIN',
        global_share_space_exhausted=False,global_optimality_claim_allowed=False,
        cash_tracking_target='MINIMUM_CASH_BUFFER',
        constraint_tolerance=TOLERANCE,pretrade_equity_usd=initial_equity,
        promotion_allowed=False,order_generation_allowed=False)


