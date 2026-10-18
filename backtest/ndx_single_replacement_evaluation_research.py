"""Explicit signed single replacements; exact arithmetic, no search or account path.

Preparation is fully reconstructed before any supplied plan is evaluated. Source
references remain declarations: this pure layer does not authenticate files.
"""
from copy import deepcopy
from fractions import Fraction as F
from backtest import ndx_single_replacement_domain_research as domain

SCHEMA = 'EXPLICIT_SINGLE_REPLACEMENT_EVALUATION_V1'
DOMAIN_SHA256 = '8df88963158ba8d3787c61705ca04f4a41ab481759701a291ccdbe75ae7505d7'
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
    rebuilt = domain.prepare_single_replacement_domain(rows, deepcopy(d['action_contract']))
    domain.exact(prepared, rebuilt, 'Full prepared domain must reconstruct from original rows and contract')
    return deepcopy(d)

def project_validated_task(document, ordinal):
    """Internal projection after full reconstruction; no repeated document hash."""
    require(type(ordinal) is int and 0<=ordinal<document['integer_count'],'Exact bounded global rank')
    for c in document['cases']:
        if not c['first_global_ordinal']<=ordinal<c['first_global_ordinal']+c['integer_count']:continue
        for p in c['pairs']:
            if not p['first_global_ordinal']<=ordinal<p['first_global_ordinal']+p['enumerable_quantity_count']:continue
            q=ordinal-p['first_global_ordinal']+1
            identity=dict(schema='SINGLE_REPLACEMENT_INTEGER_TASK_IDENTITY_V1',scenario_identity_sha256=c['identity_sha256'],
                rule=domain.RULE,outgoing_security_id=p['outgoing_security_id'],incoming_security_id=p['incoming_security_id'],
                sell_quantity=p['sell_quantity'],buy_quantity=q)
            original=c['identity']['original_input_row']; holdings=original['holdings']
            after={s:holdings.get(s,0) for s in sorted(set(holdings)|set(original['execution_prices']))}
            after[p['outgoing_security_id']]=0;after[p['incoming_security_id']]=q
            signed={s:0 for s in sorted(set(after)|set(holdings))}
            signed[p['outgoing_security_id']]=-p['sell_quantity'];signed[p['incoming_security_id']]=q
            return dict(task_id=domain.digest(identity),identity=identity,scenario_index=c['scenario_index'],
                pair_index=p['pair_index'],global_ordinal=ordinal,signed_trade_quantities=signed,
                proposed_holdings=after,evaluation_status='NOT_EVALUATED',**domain.FLAGS)
    raise ValueError('Prepared rank partition inconsistent')

def risk_snapshot(holdings, marks, securities, parameters):
    # Frozen 5bb risk semantics: positive stock denominator, top THREE,
    # effective N >= ratio*positive count, chain TOP ONE, exact 1e-9 slack.
    amounts = {s:marks[s]*q for s,q in sorted(holdings.items()) if q>0}
    total = sum(amounts.values(), F(0))
    require(total>0, 'Single replacement must retain positive invested stock')
    weights = {s:v/total for s,v in amounts.items()}
    ordered = sorted(weights.values(), reverse=True)
    neff = 1/sum((w*w for w in weights.values()), F(0))
    chains = {}
    for s,w in weights.items(): chains[securities[s]['risk_chain']] = chains.get(securities[s]['risk_chain'], F(0))+w
    checks = dict(zip(CHECKS,(
        ordered[0]<=parameters['max_single_weight']+TOLERANCE,
        ordered[-1]>=parameters['min_single_weight']-TOLERANCE,
        sum(ordered[:3])<=parameters['top_weight_cap']+TOLERANCE,
        neff>=parameters['minimum_effective_n_ratio']*len(weights)-TOLERANCE,
        max(chains.values())<=parameters['risk_chain_top1_cap']+TOLERANCE)))
    return dict(checks=checks,all_passed=all(checks.values()),weights={s:str(w) for s,w in weights.items()},
                effective_n=str(neff),positive_holding_count=len(weights),
                risk_chain_weights={s:str(w) for s,w in sorted(chains.items())})

def evaluate_one(row, task):
    marks = {s:domain.number(v) for s,v in row['execution_prices'].items()}
    after = task['proposed_holdings']; signed=task['signed_trade_quantities']
    sell = sum((-q*marks[s] for s,q in signed.items() if q<0), F(0))
    buy = sum((q*marks[s] for s,q in signed.items() if q>0), F(0))
    rate=domain.number(row['transaction_cost_bps'])/10000
    sell_fee,buy_fee=sell*rate,buy*rate
    cash=domain.number(row['starting_cash_usd']); flow=domain.number(row['cash_event']['amount_usd'])
    remaining=cash+flow+sell-buy-sell_fee-buy_fee
    before_stock=sum((marks[s]*q for s,q in row['holdings'].items() if q), F(0))
    stock=sum((marks[s]*q for s,q in after.items() if q), F(0))
    equity=stock+remaining; pnl=equity-cash-before_stock-flow
    require(pnl == -sell_fee-buy_fee, 'Exact self-financing bilateral fee identity')
    risk=risk_snapshot(after,marks,row['securities'],{k:domain.number(v) for k,v in row['risk_parameters'].items()})
    groups={}
    for s,q in sorted(after.items()):
        if q:groups.setdefault(row['securities'][s]['issuer_id'],[]).append(s)
    conflicts={k:v for k,v in groups.items() if len(v)>1}
    financial=dict(NONNEGATIVE_CASH=remaining>=0,CASH_BUFFER=remaining>=domain.number(row['minimum_cash_buffer_usd']))
    targets={s:domain.number(w) for s,w in row['target_weights'].items()}
    weights={s:F(w) for s,w in risk['weights'].items()}
    l1=sum((abs(weights.get(s,F(0))-targets.get(s,F(0))) for s in set(weights)|set(targets)),F(0))
    feasible=all(financial.values()) and risk['all_passed'] and not conflicts
    return dict(status='FEASIBLE' if feasible else 'INFEASIBLE', feasible=feasible,
        gross_sell_usd=str(sell),gross_buy_usd=str(buy),sell_fee_usd=str(sell_fee),buy_fee_usd=str(buy_fee),
        total_fee_usd=str(sell_fee+buy_fee),cash_after_usd=str(remaining),invested_stock_usd=str(stock),
        equity_after_usd=str(equity),cash_flow_adjusted_pnl_usd=str(pnl),financial_checks=financial,
        risk=risk,issuer_conflicts=conflicts,original_target_stock_l1=str(l1))

def evaluate_explicit_single_replacement_plans(*, prepared, registered_plans, max_evaluations):
    """Validate the entire explicit list, then evaluate its budgeted prefix.

    Each item is exactly {global_ordinal, task}, where task is domain.unrank's
    complete saved output. 'registered' is a caller assertion, never authority.
    A technical exception stops the prefix and preserves all remaining identities.
    Financial feasibility within this saved Open domain is not tradability/PIT.
    """
    d=validate_prepared(prepared)
    require(type(registered_plans) is list and len(registered_plans)<=MAX_PLANS,'Bounded explicit plans')
    require(type(max_evaluations) is int and 0<=max_evaluations<=MAX_PLANS,'Exact evaluation budget')
    supplied=deepcopy(registered_plans);seen=set()
    for p in supplied:
        require(type(p) is dict and set(p)=={'global_ordinal','task'},'Complete explicit plan envelope')
        n=p['global_ordinal']; require(type(n) is int and n not in seen,'Unique exact supplied rank')
        seen.add(n); expected=project_validated_task(d,n)
        domain.exact(p['task'],expected,'Signed plan, retained holdings and identity must match full registered domain')
    results=[];stopped=False
    for i,p in enumerate(supplied):
        if stopped or i>=max_evaluations:
            results.append(dict(supplied_index=i,plan=p,status='NOT_EVALUATED_TECHNICAL_STOP' if stopped else 'NOT_EVALUATED_BUDGET',evaluation=None));continue
        try:
            row=d['cases'][p['task']['scenario_index']]['identity']['original_input_row']
            evaluation=evaluate_one(row,p['task'])
            results.append(dict(supplied_index=i,plan=p,status=evaluation['status'],evaluation=evaluation))
        except BaseException as error:
            stopped=True
            results.append(dict(supplied_index=i,plan=p,status='EVALUATION_EXCEPTION',evaluation=None,
                                error=dict(type=type(error).__name__,message=str(error))))
    counts={s:sum(r['status']==s for r in results) for s in ('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','NOT_EVALUATED_BUDGET','NOT_EVALUATED_TECHNICAL_STOP')}
    require(sum(counts.values())==len(supplied),'Full supplied partition')
    return dict(schema=SCHEMA,prepared_content_sha256=prepared['content_sha256'],
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
        domain_source_sha256=DOMAIN_SHA256,risk_semantics_source_sha256=RISK_SEMANTICS_SHA256,
        enumeration_or_search_called=False,cross_family_winner_selected=False,
        source_code_bytes_authenticated=False,full_integer_space_infeasibility_claimed=False,**FLAGS)
