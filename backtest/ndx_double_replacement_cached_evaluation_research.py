"""Explicit signed double replacements; exact arithmetic, no search or account path.

Preparation is fully reconstructed before any supplied plan is evaluated.
Fixed-pair invariants use immutable tuples/Fractions. No point skipping or
cross-flow result reuse. The naive oracle is a declared test reference only;
this module never imports or calls it.
The five-risk and bilateral-fee formulas preserve the frozen single-replacement
arithmetic (4303ead0), but tasks and denominator use the double domain only. Source
references remain declarations: this pure layer does not authenticate files.
"""
from copy import deepcopy
from fractions import Fraction as F
from typing import NamedTuple
from backtest import ndx_double_replacement_domain_research as domain

SCHEMA = 'EXPLICIT_DOUBLE_REPLACEMENT_CACHED_EVALUATION_V1'
ORACLE_SOURCE_SHA256 = '42640b41f3b54ba827e47d90c4c200c31b03ac13c6d867e928dc9a5956f4d5a2'
DOMAIN_SHA256 = '334af655e4d30a928af9d965b1c63bfe664c5c9a633dca3591bfac7f8130d4b6'
RISK_SEMANTICS_SHA256 = '5bb17d621b42707cfe312676279d59b565c3e97900bf3bdd6f9335df65aa0c5f'
MAX_PLANS = 10000
TOLERANCE = F(1, 10**9)
CHECKS = ('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT',
          'MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')
FLAGS = {k:False for k in domain.FLAGS if k not in ('risk_evaluated','financial_feasibility_evaluated')}

def require(ok, message):
    if not ok: raise ValueError(message)

def validate_prepared(prepared):
    d = domain.checked(prepared)
    rows = [dict(input_row=deepcopy(c['identity']['original_input_row']),
                 input_reference=deepcopy(c['identity']['input_reference'])) for c in d['cases']]
    rebuilt = domain.prepare_double_replacement_domain(rows, deepcopy(d['action_contract']))
    domain.exact(prepared, rebuilt, 'Full prepared domain must reconstruct from original rows and contract')
    return deepcopy(d)

def project_validated_task(document, ordinal):
    """Project an exact two-out/two-in task after full domain reconstruction.

    The frozen domain projection does not hash/rebuild the document again.
    Its budget helper maps each quantity pair to the original global rank.
    """
    return domain._task(document, ordinal)


def error_text(error):
    try:
        return str(error)
    except BaseException as failure:
        return 'ERROR_STRING_FAILED: ' + type(failure).__name__


class PairCache(NamedTuple):
    scenario_index: int
    pair_index: int
    outgoing: tuple
    incoming: tuple
    incoming_prices: tuple
    incoming_chains: tuple
    retained_amounts: tuple
    retained_sum: F
    retained_squares: F
    retained_top3: tuple
    retained_min: object
    chain_amounts: tuple
    unaffected_chain_max: F
    targets: tuple
    parameters: tuple
    gross_sell: F
    sell_fee: F
    rate: F
    cash: F
    flow: F
    buffer: F
    before_stock: F
    budget: F


def _prepare_pair_cache(case, pair):
    """Internal only: arguments are from the isolated fully rebuilt domain.

    Every leaf is immutable; no original mappings, caller aliases or previously
    returned result dictionaries are retained in the cache.
    """
    require(pair['enumerable_integer_count']>0,'Only enumerable pair')
    row=case['identity']['original_input_row'];outgoing=tuple(pair['outgoing_security_ids']);incoming=tuple(pair['incoming_security_ids'])
    prices={s:domain.number(v)for s,v in row['execution_prices'].items()}
    retained=tuple((s,prices[s]*q)for s,q in sorted(row['holdings'].items())if q>0 and s not in outgoing)
    amounts=tuple(a for _,a in retained);R=sum(amounts,F());Q=sum((a*a for a in amounts),F())
    incoming_chains=tuple(row['securities'][s]['risk_chain']for s in incoming);chains={}
    for s,a in retained:
        chain=row['securities'][s]['risk_chain'];chains[chain]=chains.get(chain,F())+a
    unaffected=max((a for chain,a in chains.items()if chain not in incoming_chains),default=F())
    sale=sum((prices[s]*row['holdings'][s]for s in outgoing),F());rate=domain.number(row['transaction_cost_bps'])/10000
    cash=domain.number(row['starting_cash_usd']);flow=domain.number(row['cash_event']['amount_usd']);buffer=domain.number(row['minimum_cash_buffer_usd'])
    before=sum((prices[s]*q for s,q in row['holdings'].items()if q),F())
    return PairCache(case['scenario_index'],pair['pair_index'],outgoing,incoming,tuple(prices[s]for s in incoming),incoming_chains,retained,R,Q,tuple(sorted(amounts,reverse=True)[:3]),min(amounts)if amounts else None,tuple(sorted(chains.items())),unaffected,tuple(sorted((s,domain.number(v))for s,v in row['target_weights'].items())),tuple(sorted((s,domain.number(v))for s,v in row['risk_parameters'].items())),sale,sale*rate,rate,cash,flow,buffer,before,cash+flow+sale*(1-rate)-buffer)


def evaluate_cached_point(cache, task):
    """Point arithmetic for an internally validated task/cache pair.

    Public source authorization is never conferred by this helper. The batch
    entry below validates the *entire* supplied task list before invoking it.
    """
    require(type(cache)is PairCache,'Immutable cache type')
    require(task['scenario_index']==cache.scenario_index and task['pair_index']==cache.pair_index,'Cache coordinate')
    identity=task['identity'];require(tuple(identity['incoming_security_ids'])==cache.incoming and tuple(identity['outgoing_security_ids'])==cache.outgoing,'Cache SID order')
    q=identity['buy_quantities'];require(type(q)is list and len(q)==2 and all(type(v)is int and v>=1 for v in q),'Exact quantities in incoming order')
    x,y=(p*v for p,v in zip(cache.incoming_prices,q));buy=x+y
    require(buy*(1+cache.rate)<=cache.budget,'Exact joint financial domain')
    stock=cache.retained_sum+buy;require(stock>0,'Positive stock denominator')
    amounts=dict(cache.retained_amounts);amounts.update(zip(cache.incoming,(x,y)))
    weights={s:a/stock for s,a in sorted(amounts.items())}
    top=sorted((*cache.retained_top3,x,y),reverse=True)
    minimum=min(x,y)if cache.retained_min is None else min(cache.retained_min,x,y)
    neff=stock*stock/(cache.retained_squares+x*x+y*y)
    chains=dict(cache.chain_amounts)
    for chain,amount in zip(cache.incoming_chains,(x,y)):chains[chain]=chains.get(chain,F())+amount
    chain_top=max(cache.unaffected_chain_max,*(chains[chain]for chain in cache.incoming_chains))
    parameters=dict(cache.parameters)
    checks=dict(zip(CHECKS,(top[0]/stock<=parameters['max_single_weight']+TOLERANCE,minimum/stock>=parameters['min_single_weight']-TOLERANCE,sum(top[:3],F())/stock<=parameters['top_weight_cap']+TOLERANCE,neff>=parameters['minimum_effective_n_ratio']*len(weights)-TOLERANCE,chain_top/stock<=parameters['risk_chain_top1_cap']+TOLERANCE)))
    risk=dict(checks=checks,all_passed=all(checks.values()),weights={s:str(v)for s,v in weights.items()},effective_n=str(neff),positive_holding_count=len(weights),risk_chain_weights={s:str(v/stock)for s,v in sorted(chains.items())})
    buy_fee=buy*cache.rate;fees=cache.sell_fee+buy_fee
    remaining=cache.cash+cache.flow+cache.gross_sell-buy-fees;equity=stock+remaining
    pnl=equity-cache.cash-cache.before_stock-cache.flow;require(pnl==-fees,'Exact self financing')
    financial=dict(NONNEGATIVE_CASH=remaining>=0,CASH_BUFFER=remaining>=cache.buffer)
    targets=dict(cache.targets);l1=sum((abs(weights.get(s,F())-targets.get(s,F()))for s in set(weights)|set(targets)),F())
    feasible=all(financial.values())and risk['all_passed']
    # Issuer uniqueness is pair-invariant and fully reconstructed before cache
    # creation. Structural-conflict pairs have no enumerable task at all.
    return dict(status='FEASIBLE'if feasible else 'INFEASIBLE',feasible=feasible,gross_sell_usd=str(cache.gross_sell),gross_buy_usd=str(buy),sell_fee_usd=str(cache.sell_fee),buy_fee_usd=str(buy_fee),total_fee_usd=str(fees),cash_after_usd=str(remaining),invested_stock_usd=str(stock),equity_after_usd=str(equity),cash_flow_adjusted_pnl_usd=str(pnl),financial_checks=financial,risk=risk,issuer_conflicts={},original_target_stock_l1=str(l1))

def evaluate_explicit_double_replacement_plans_cached(*, prepared, registered_plans, max_evaluations):
    """Validate the entire explicit list, then evaluate its budgeted prefix.

    Each item is exactly {global_ordinal, task}, where task is domain.unrank's
    complete saved output. 'registered' is a caller assertion, never authority.
    A technical exception stops the prefix and preserves all remaining identities.
    Financial feasibility within this saved Open domain is not tradability/PIT.
    """
    d=validate_prepared(prepared)
    validated_content_sha256=domain.digest(d)
    require(type(registered_plans) is list and len(registered_plans)<=MAX_PLANS,'Bounded explicit plans')
    require(type(max_evaluations) is int and 0<=max_evaluations<=MAX_PLANS,'Exact evaluation budget')
    supplied=deepcopy(registered_plans);seen=set()
    for p in supplied:
        require(type(p) is dict and set(p)=={'global_ordinal','task'},'Complete explicit plan envelope')
        n=p['global_ordinal']; require(type(n) is int and n not in seen,'Unique exact supplied rank')
        seen.add(n); expected=project_validated_task(d,n)
        domain.exact(p['task'],expected,'Signed plan, retained holdings and identity must match full registered domain')
    results=[];stopped=False;caches={};cache_hits=0
    for i,p in enumerate(supplied):
        if stopped or i>=max_evaluations:
            results.append(dict(supplied_index=i,plan=p,status='NOT_EVALUATED_TECHNICAL_STOP' if stopped else 'NOT_EVALUATED_BUDGET',evaluation=None));continue
        try:
            key=(p['task']['scenario_index'],p['task']['pair_index'])
            if key not in caches:
                case=d['cases'][key[0]];caches[key]=_prepare_pair_cache(case,case['pairs'][key[1]])
            else:cache_hits+=1
            evaluation=evaluate_cached_point(caches[key],p['task'])
            results.append(dict(supplied_index=i,plan=p,status=evaluation['status'],evaluation=evaluation))
        except BaseException as error:
            stopped=True
            results.append(dict(supplied_index=i,plan=p,status='EVALUATION_EXCEPTION',evaluation=None,
                                error=dict(type=type(error).__name__,message=error_text(error))))
    counts={s:sum(r['status']==s for r in results) for s in ('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','NOT_EVALUATED_BUDGET','NOT_EVALUATED_TECHNICAL_STOP')}
    require(sum(counts.values())==len(supplied),'Full supplied partition')
    return dict(schema=SCHEMA,pair_cache_count=len(caches),pair_cache_hit_count=cache_hits,cache_scope='WITHIN_VALIDATED_SCENARIO_AND_PAIR_ONLY',risk_result_reused_across_points=False,intervals_skipped=False,naive_oracle_called=False,naive_oracle_source_sha256=ORACLE_SOURCE_SHA256,prepared_content_sha256=validated_content_sha256,
        prepared_identity_scope='RECONSTRUCTED_INTERNAL_CONSISTENCY_NOT_ORIGINAL_BYTE_AUTHENTICATION',
        action_contract=deepcopy(d['action_contract']),source_hash_claims=deepcopy(d['source_hash_claims']),
        full_scenario_count=d['scenario_count'],full_pair_count=d['pair_count'],full_integer_count=d['integer_count'],
        financial_integer_count_before_issuer=d['financial_integer_count_before_issuer'],
        structurally_excluded_integer_count=d['structurally_excluded_integer_count'],
        supplied_plan_count=len(supplied),unsupplied_integer_count=d['integer_count']-len(supplied),
        max_evaluations=max_evaluations,counts=counts,results=results,
        status='TECHNICAL_STOP' if stopped else 'ALL_SUPPLIED_EVALUATED' if len(supplied)<=max_evaluations else 'BUDGET_LIMITED',
        risk_tolerance='1e-9',financial_tolerance='0',arithmetic='EXACT_FRACTION_FROM_SAVED_DECIMAL_LITERALS',
        monetary_value_encoding='EXACT_RATIONAL_STRING_IN_USD_UNITS_NOT_DECIMAL_RENDERING',
        completed_evaluation_count=counts['FEASIBLE']+counts['INFEASIBLE'],
        supplied_plan_registration_authenticated=False,prepared_domain_bytes_authenticated=False,
        domain_source_sha256=DOMAIN_SHA256,budget_math_source_sha256=domain.BUDGET_MATH_SHA256,
        risk_semantics_source_sha256=RISK_SEMANTICS_SHA256,
        enumeration_or_search_called=False,cross_family_winner_selected=False,
        source_code_bytes_authenticated=False,full_integer_space_infeasibility_claimed=False,**FLAGS)
