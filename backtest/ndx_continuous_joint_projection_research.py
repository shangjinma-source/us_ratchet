"""Pure synthetic continuous buy-only projection; no source IO or real fit.

Rational, covariance and identity utilities are fixed pure helpers from the
locked integer research kernel. A continuous domain is independently rebuilt;
no conversion to a whole-lot problem, source authentication or caller authority.
"""
from copy import deepcopy
from fractions import Fraction as F
from backtest.ndx_joint_new_cash_competition_frontier_research import (
    _rational as rat, _require as require, _digest as digest,
    _identity_rows as identities, _coefficients as coefficients,
    _covariance as covariance_check, RISK_KEYS, AUTHORITY)

TAU = F(1, 10**9)
SCHEMA = 'SYNTHETIC_CONTINUOUS_JOINT_COMPETITION_V1'
SEARCH_REGISTRATION = dict(schema='RATIONAL_CONTINUOUS_REGION_SEARCH_RULE_V1',
    budget_scope='NEW_EVENTS_ONLY_EXCLUDES_REPLAY_CONTROL_AND_INPUT_VALIDATION_NOT_TOTAL_OPERATIONS_OR_TIME',
    event='ONE_SUPPORT_EXPANSION_OR_ONE_REGION_BOUND_AT_MOST_THREE_PRIMAL_PROPOSALS_THEN_COVER_OR_SPLIT',
    split='WIDEST_RAW_AXIS_RATIONAL_MIDPOINT_LEFT_UPPER_OPEN_RIGHT_LOWER_CLOSED',
    coverage='PER_K_SAME_K_FEASIBLE_WITNESS_ONLY',resume='EXACT_DETERMINISTIC_PREFIX_REPLAY')


def _core(p):
    require(type(p) is dict and p.get('schema') == 'VARIABLE_CARDINALITY_NEW_CASH_PROBLEM_V1', 'A schema required')
    require(p.get('problem_id') == digest({k:v for k,v in p.items() if k != 'problem_id'}), 'A digest drift')
    require(p.get('domain_kind') == 'CONTINUOUS_INCREMENTAL_DOLLARS', 'A continuous domain required')
    require(p.get('input_scope') == 'SYNTHETIC_UNBOUND' and p.get('source_binding_status') == 'UNBOUND'
            and p.get('status') == 'SOURCE_BLOCKED', 'Synthetic UNBOUND only')
    require(p.get('numerical_status') == 'CONDITIONAL_CONTEXT_READY' and p.get('context_blockers') == [], 'Numerical context blocked')
    require(p.get('qualified_inventory_or_null') is None and p.get('qualified_all_k_denominators_or_null') is None, 'No qualification')
    require(type(p.get('authority')) is dict and p['authority'] and all(v is False for v in p['authority'].values()), 'All authority False')
    require(type(p.get('source_checks')) is list and len(p['source_checks']) == 10
            and all(r.get('status') == 'SOURCE_BLOCKED' for r in p['source_checks']), 'Ten blocked sources required')
    inv = identities(p['conditional_inventory']['securities'])
    old = p['frozen_prior_book']
    oldmeta = identities(old['security_metadata'])
    require(all(inv[s] == oldmeta[s] for s in set(inv)&set(oldmeta)), 'Old identity conflict')
    meta = dict(sorted({**inv, **oldmeta}.items()))
    require(type(old['quantities']) is dict and set(old['quantities']) == set(oldmeta), 'Old quantities/metadata exact')
    q = {s:rat(v, 'frozen quantity', True) for s,v in old['quantities'].items()}
    require(all(v > 0 for v in q.values()), 'Positive old quantities')
    f, policy = p['domain_formula'], p['policy']
    require(type(f['prices']) is dict and set(f['prices']) == set(meta), 'Full prices required')
    prices = {s:rat(v,'price',True) for s,v in f['prices'].items()}
    require(all(v > 0 for v in prices.values()), 'Positive prices')
    require(type(f['lot_sizes']) is dict and set(f['lot_sizes']) == set(meta)
            and all(type(v) is int and v > 0 for v in f['lot_sizes'].values()), 'Integer lot metadata required')
    exclusions = p['conditional_exclusions']
    require(type(exclusions) is dict and set(exclusions) <= set(inv), 'Invalid exclusions')
    buys = sorted(set(inv)-set(exclusions))
    require(p['conditional_buy_security_ids'] == buys, 'Full buy inventory drift')
    cash = rat(old['cash'],'prior cash',True)+rat(f['cash_event_amount'],'event cash',True)
    buffer = rat(policy['minimum_cash_buffer'],'buffer',True)
    fee = rat(policy['transaction_cost_bps'],'fee',True)
    require(fee <= 10000, 'Fee above supported range')
    factor, budget = 1+fee/10000, cash-buffer
    amounts = {s:q[s]*prices[s] for s in q}
    V = sum(amounts.values(), F(0))
    W = V+cash
    require(W > 0, 'Positive pretrade wealth required')
    for key,value in dict(total_cash_before_buys=cash, minimum_cash_buffer=buffer,
                          cash_budget_after_buffer=budget, fee_factor=factor, old_stock_value=V).items():
        require(rat(f[key],key) == value, 'A mathematical drift: '+key)
    require(f['currency'] == old['currency'], 'Currency drift')
    T = budget/factor if budget >= 0 else None
    require(f['maximum_incremental_gross_or_null'] == (None if T is None else str(T)), 'A gross bound drift')
    require(f['coordinate_caps_or_null'] is None and p['bounding_box_count_or_null'] is None, 'Continuous domain cannot carry integer caps')
    risk = policy['risk_parameters']
    require(type(risk) is dict and set(risk) == set(RISK_KEYS), 'Five risk parameters')
    risk = {k:rat(v,k,True) for k,v in risk.items()}
    require(all(v <= 1 for v in risk.values()) and risk['max_single_weight'] > 0
            and risk['risk_chain_top1_cap'] > 0 and risk['min_single_weight'] <= risk['max_single_weight'], 'Invalid risk policy')
    require(rat(policy['risk_tolerance'],'tau') == TAU, 'Original tolerance required')
    occupied = {}
    for sid in q:
        occupied.setdefault(meta[sid]['issuer_id'], []).append(sid)
    conflicts = {i:sorted(s) for i,s in occupied.items() if len(s)>1}
    require(old['issuer_conflicts'] == conflicts and old['positive_holding_count'] == len(q), 'Old issuer/count drift')
    groups = {}
    for s in buys:
        issuer = meta[s]['issuer_id']
        if issuer not in occupied:
            groups.setdefault(issuer, []).append(s)
    groups = [sorted(groups[i]) for i in sorted(groups)]
    eligible = coefficients({str(i):len(g) for i,g in enumerate(groups)})
    full = {}
    for row in meta.values():
        full[row['issuer_id']] = full.get(row['issuer_id'],0)+1
    full = coefficients(full)
    invgroups = {}
    for row in inv.values():
        invgroups[row['issuer_id']] = invgroups.get(row['issuer_id'],0)+1
    require(p['conditional_inventory']['security_count'] == len(inv)
            and p['conditional_inventory']['issuer_count'] == len(invgroups), 'Inventory count drift')
    require(p['conditional_inventory']['all_k_denominators'] == [dict(holding_count=k,composition_count=str(v))
            for k,v in enumerate(coefficients(invgroups)) if k], 'Inventory denominator drift')
    require(len(p['all_k_rows']) == len(full)-1, 'All k required')
    per_k = {}
    for k,row in enumerate(p['all_k_rows'],1):
        n = k-len(q)
        count = eligible[n] if 0 <= n < len(eligible) else 0
        require(row['holding_count'] == k and row['full_conditional_composition_count'] == str(full[k])
                and row['frozen_old_conditional_composition_count'] == (None if conflicts else str(count)), 'Per-k domain drift')
        per_k[str(k)] = dict(full_conditional=str(full[k]),frozen_legal=str(0 if conflicts else count))
    return dict(metadata=meta,quantities={s:str(v) for s,v in q.items()},prices={s:str(v) for s,v in prices.items()},
                buy_security_ids=buys,old_amounts={s:str(v) for s,v in amounts.items()},
                cash=str(cash),buffer=str(buffer),fee_factor=str(factor),budget=str(budget),V=str(V),W0=str(W),
                T=None if T is None else str(T),risk={k:str(v) for k,v in risk.items()},
                issuer_groups=groups,old_issuer_conflicts=conflicts,per_k=per_k)


def prepare_synthetic_continuous_competition(*, prepared_problem_A, synthetic_covariance,
        epsilon_variance='0', epsilon_turnover='0'):
    core = _core(prepared_problem_A)
    cov = covariance_check(synthetic_covariance,core,prepared_problem_A['decision_timestamp'])
    result = dict(schema=SCHEMA,A_problem=deepcopy(prepared_problem_A),core=core,synthetic_covariance=cov,
        search_registration=deepcopy(SEARCH_REGISTRATION),
        epsilon_variance=str(rat(epsilon_variance,'variance epsilon',True)),
        epsilon_turnover=str(rat(epsilon_turnover,'turnover epsilon',True)),
        source_status='SYNTHETIC_UNBOUND_SOURCE_BLOCKED',real_objective_status='UNREGISTERED',
        context_scope='NORMALIZED_SYNTHETIC_FACTS_ONLY_RAW_AVAILABLE_AT_NOT_EXPORTED_OR_AUTHENTICATED',
        authority=dict.fromkeys(AUTHORITY,False),analytic_optional_family='NOT_IMPLEMENTED')
    result['competition_id'] = digest(result)
    return deepcopy(result)


def validate_competition(c):
    require(type(c) is dict, 'Competition dict required')
    cov = {k:v for k,v in c['synthetic_covariance'].items() if k != 'positive_semidefinite_check'}
    rebuilt = prepare_synthetic_continuous_competition(prepared_problem_A=c['A_problem'],synthetic_covariance=cov,
        epsilon_variance=c['epsilon_variance'],epsilon_turnover=c['epsilon_turnover'])
    require(digest(c) == digest(rebuilt), 'Competition drift')
    return rebuilt


def check_support(core, support):
    require(type(support) is list and all(type(s) is str for s in support)
            and support == sorted(set(support)) and bool(support), 'Canonical nonempty support')
    require(not core['old_issuer_conflicts'], 'Frozen issuer conflict')
    require(set(core['quantities']) <= set(support)
            and set(support) <= set(core['quantities'])|set(core['buy_security_ids']), 'Full old support/eligible new support required')
    require(len({core['metadata'][s]['issuer_id'] for s in support}) == len(support), 'Issuer class conflict')


def project_frozen_support(*, competition, support_security_ids, total_buy_notional=None, reciprocal_total_stock=None):
    c = validate_competition(competition)
    core, support = c['core'], support_security_ids
    check_support(core,support)
    V, T = F(core['V']), None if core['T'] is None else F(core['T'])
    require((total_buy_notional is None) != (reciprocal_total_stock is None), 'Exactly one t or y required')
    require(T is not None, 'Negative budget empty domain')
    if total_buy_notional is not None:
        t = rat(total_buy_notional,'t',True)
        require(V+t > 0, 'Zero-stock normalization undefined')
        y = 1/(V+t)
    else:
        y = rat(reciprocal_total_stock,'y',True)
        require(y > 0, 'Positive y required')
        t = 1/y-V
    require(0 <= t <= T, 'Funding interval exceeded')
    rows = {s:dict(kind='LOWER_BOUND' if s in core['buy_security_ids'] else 'EXACT_EQUALITY',
                  frozen_weight=str(F(core['old_amounts'].get(s,'0'))*y)) for s in support}
    return dict(support=deepcopy(support),holding_count=len(support),t=str(t),y=str(y),
        weights=rows,strict_support=True,budget=str(T),source_status=c['source_status'])


def _witness(c, support, y, weights):
    core = c['core']
    check_support(core,support)
    require(type(weights) is dict and set(weights) == set(support), 'Exact witness support fields')
    w = {s:rat(weights[s],'weight',True) for s in support}
    require(all(v > 0 for v in w.values()) and sum(w.values(),F(0)) == 1, 'Strict positive normalized weights')
    y = rat(y,'y',True)
    require(y > 0, 'Positive y')
    V, W = F(core['V']), F(core['W0'])
    t = 1/y-V
    require(core['T'] is not None and 0 <= t <= F(core['T']), 'Cash budget violation')
    x = {s:w[s]/y-F(core['old_amounts'].get(s,'0')) for s in support}
    require(all(v >= 0 for v in x.values()), 'Cannot sell frozen quantities')
    require(all(x[s] == 0 for s in support if s not in core['buy_security_ids']), 'Nonbuyable old requires exact equality')
    require(sum(x.values(),F(0)) == t, 'Gross conservation')
    fee = t*(F(core['fee_factor'])-1)
    remaining = F(core['cash'])-t-fee
    require(remaining >= F(core['buffer']) and 1/y+remaining == W-fee, 'Wealth/fee conservation')
    r = {k:F(v) for k,v in core['risk'].items()}
    ordered = sorted(w.values(),reverse=True)
    chains = {}
    for s,v in w.items():
        chain = core['metadata'][s]['risk_chain']
        chains[chain] = chains.get(chain,F(0))+v
    checks = dict(max_single=max(ordered)<=r['max_single_weight']+TAU,
        min_single=min(ordered)>=r['min_single_weight']-TAU,
        top3=sum(ordered[:3])<=r['top_weight_cap']+TAU,
        effective_n=1/sum(v*v for v in w.values())>=r['minimum_effective_n_ratio']*len(support)-TAU,
        chain=max(chains.values())<=r['risk_chain_top1_cap']+TAU)
    require(all(checks.values()), 'Original tolerance-aware risk failed')
    cov = c['synthetic_covariance']
    ids, matrix = cov['security_ids'], cov['values']
    variance = sum((w.get(a,0)*w.get(b,0)*F(matrix[i][j]) for i,a in enumerate(ids)
                    for j,b in enumerate(ids)),F(0))
    result = dict(schema='SYNTHETIC_CONTINUOUS_FEASIBLE_WITNESS_V1',competition_id=c['competition_id'],
        support=list(support),holding_count=len(support),y=str(y),t=str(t),
        weights={s:str(v) for s,v in w.items()},increments={s:str(v) for s,v in x.items()},
        final_quantities={s:str(F(core['quantities'].get(s,'0'))+x[s]/F(core['prices'][s])) for s in support},
        fee=str(fee),cash_after=str(remaining),risk_checks=checks,
        objectives=dict(variance=str(variance),turnover=str(t/W)),
        authority=dict.fromkeys(AUTHORITY,False))
    result['witness_id'] = digest(result)
    return result


def verify_continuous_witness(*, competition, support_security_ids, reciprocal_total_stock, weights):
    return _witness(validate_competition(competition),support_security_ids,reciprocal_total_stock,weights)
