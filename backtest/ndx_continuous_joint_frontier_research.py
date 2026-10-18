"""Synthetic all-support rational region search with exact replayed residuals.

Finite witness probes are proposals only. Coverage derives from region bounds,
never a grid. Degenerate/open/tangent regions may remain UNKNOWN indefinitely.
"""
from copy import deepcopy
from fractions import Fraction as F
from backtest.ndx_continuous_joint_projection_research import (
    rat, require, digest, coefficients, validate_competition, _witness, AUTHORITY)
from backtest.ndx_continuous_joint_certificates_research import (
    root_region, bound_region, cover_region, split_region, propose_witnesses, inherited_bound_relation)


def _integer(v, name):
    require(type(v) is int and v >= 0, name+' nonboolean nonnegative integer required')
    return v


def _support_counts(c, task):
    core = c['core']
    offset = len(core['quantities'])+len(task['chosen'])
    remaining = core['issuer_groups'][task['index']:]
    poly = coefficients({str(i):len(g) for i,g in enumerate(remaining)})
    return {str(k):str(poly[k-offset] if 0 <= k-offset < len(poly) else 0)
            for k in range(1,len(core['per_k'])+1)}


def _initial(c):
    core = c['core']
    branch = ('NEGATIVE_CASH_BUDGET_EMPTY' if F(core['budget']) < 0 else
        'FROZEN_ISSUER_CONFLICT_EMPTY' if core['old_issuer_conflicts'] else
        'V_ZERO_T_ZERO_ONLY_CASH' if F(core['V']) == 0 and F(core['T']) == 0 else
        'V_ZERO_T_POSITIVE_UNATTAINED_TRAINING_INFIMUM' if F(core['V']) == 0 else
        'BOUNDED_RECIPROCAL_REGION_SEARCH')
    queue = [dict(kind='SUPPORT',index=0,chosen=[])] if branch == 'BOUNDED_RECIPROCAL_REGION_SEARCH' else []
    return dict(schema='SYNTHETIC_CONTINUOUS_CHECKPOINT_V1',competition_id=c['competition_id'],
        branch=branch,events=0,search_registration=deepcopy(c['search_registration']),
        queue=queue,archived_regions=[],expanded_supports=[],witnesses=[],bound_ledger=[],partition_ledger=[],
        counters=dict(support_expansions=0,support_materializations=0,bound_checks=0,witness_proposals=0,
                      region_splits=0,region_events=0,coverage_checks=0,witness_formula_checks=0),
        event_hash=digest(dict(competition=c['competition_id'],prefix='EMPTY')))


def _event(c, state):
    task = state['queue'].pop(0)
    core = c['core']
    counter = state['counters']
    if task['kind'] == 'SUPPORT':
        i = task['index']
        groups = core['issuer_groups']
        if i < len(groups):
            counter['support_expansions'] += 1
            children = [dict(kind='SUPPORT',index=i+1,chosen=task['chosen']+extra)
                        for extra in [[]]+[[s] for s in groups[i]]]
            state['queue'].extend(children)
        else:
            support = sorted(list(core['quantities'])+task['chosen'])
            counter['support_materializations'] += 1
            if support:
                state['expanded_supports'].append(support)
                if F(core['T']) == 0 and len(support) > len(core['quantities']):
                    state['archived_regions'].append(dict(support=support,holding_count=len(support),
                        status='PROVEN_INFEASIBLE_ZERO_CAPITAL_NEW_SUPPORT',
                        domain='ENTIRE_SUPPORT',economic_domain_retained=True))
                else:
                    state['queue'].append(dict(kind='REGION',region=root_region(c,support)))
    else:
        require(task['kind'] == 'REGION', 'Unknown internal task')
        region = task['region']
        counter['region_events'] += 1
        bound = bound_region(c,region)
        counter['bound_checks'] += 1
        state['bound_ledger'].append(deepcopy(bound))
        archive = dict(support=region['support'],holding_count=region['holding_count'],
                       region=deepcopy(region),bound=bound,economic_domain_retained=True)
        if bound['infeasibility_reasons']:
            archive['status'] = 'PROVEN_INFEASIBLE_INTERVAL_CERTIFICATE'
            state['archived_regions'].append(archive)
        else:
            found,attempts,checks = propose_witnesses(c,region)
            counter['witness_proposals'] += attempts
            counter['witness_formula_checks'] += checks
            known = {w['witness_id'] for w in state['witnesses']}
            for witness in found:
                if witness['witness_id'] not in known:
                    state['witnesses'].append(witness)
                    known.add(witness['witness_id'])
            covered = False
            for witness in state['witnesses']:
                if witness['holding_count'] != region['holding_count']: continue
                counter['coverage_checks'] += 1
                # cover_region independently rechecks its bound and primal.
                counter['bound_checks'] += 1
                counter['witness_formula_checks'] += 1
                try:
                    certificate = cover_region(c,region,bound,witness)
                except ValueError:
                    continue
                archive.update(status='PER_K_EPSILON_OBJECTIVE_COVER',cover=certificate)
                state['archived_regions'].append(archive)
                covered = True
                break
            if not covered:
                children = split_region(region)
                if children is None:
                    # No valid infeasibility/cover proof: keep the unresolved
                    # singleton/face visible. Never silently discard it.
                    state['queue'].append(dict(kind='UNRESOLVED',region=region,bound=bound))
                else:
                    counter['region_splits'] += 1
                    relations = [inherited_bound_relation(c,r,bound) for r in children]
                    state['partition_ledger'].append(dict(parent_certificate_id=bound['certificate_id'],
                        parent_region_id=digest(region),children=deepcopy(list(children)),relations=relations,
                        partition='REGISTERED_MIDPOINT_LEFT_UPPER_OPEN_RIGHT_LOWER_CLOSED'))
                    state['queue'].extend(dict(kind='REGION',region=r,inherited_parent_bound=deepcopy(bound),
                        inherited_parent_relation=relation) for r,relation in zip(children,relations))
    state['events'] += 1
    state['event_hash'] = digest(dict(previous=state['event_hash'],task=task,
        counters=counter,witness_ids=[w['witness_id'] for w in state['witnesses']],
        archived_count=len(state['archived_regions'])))


def _advance(c,state, count):
    visits = 0
    while visits < count:
        # Terminal unresolved faces are retained, not repeated as work. Find
        # next refinable task without changing deterministic ownership order.
        index = next((i for i,t in enumerate(state['queue']) if t['kind'] != 'UNRESOLVED'),None)
        if index is None: break
        if index:
            state['queue'].insert(0,state['queue'].pop(index))
        _event(c,state)
        visits += 1
    return visits


def _frontier(witnesses):
    def dominates(a,b):
        av = [F(a['objectives'][key]) for key in ('variance','turnover')]
        bv = [F(b['objectives'][key]) for key in ('variance','turnover')]
        return all(x <= y for x,y in zip(av,bv)) and any(x < y for x,y in zip(av,bv))
    return [deepcopy(w) for w in witnesses if not any(dominates(p,w) for p in witnesses)]


def _result(c,state,new_events,replayed,replay_counters):
    core = c['core']
    branch = state['branch']
    regular = branch == 'BOUNDED_RECIPROCAL_REGION_SEARCH'
    unexpanded = {k:0 for k in core['per_k']}
    forest = []
    for task in state['queue']:
        if task['kind'] == 'SUPPORT':
            counts = _support_counts(c,task)
            forest.append(dict(task=deepcopy(task),per_k_composition_counts=counts))
            for k,v in counts.items(): unexpanded[k] += int(v)
    if branch.startswith('V_ZERO'):
        forest = [dict(domain='ALL_LEGAL_SUPPORTS_AND_ORIGINAL_RISK_WEIGHT_DOMAINS',
            capital_domain='EMPTY_POSITIVE_STOCK_DOMAIN' if branch == 'V_ZERO_T_ZERO_ONLY_CASH' else 't/T IN (0,1]',
            per_k_composition_counts={k:v['frozen_legal'] for k,v in core['per_k'].items()},
            weight_feasibility='UNKNOWN_NOT_SEARCHED_V0_BRANCH',stock_normalization_at_t0='UNDEFINED')]
        unexpanded = {k:int(v['frozen_legal']) for k,v in core['per_k'].items()}
    residual = [deepcopy(t) for t in state['queue'] if t['kind'] != 'SUPPORT']
    per_k = []
    for k,counts in core['per_k'].items():
        expanded = sum(len(s) == int(k) for s in state['expanded_supports'])
        require(not regular or expanded+unexpanded[k] == int(counts['frozen_legal']), 'Internal all-k support coverage drift')
        points = [w for w in state['witnesses'] if w['holding_count'] == int(k)]
        pending = [t for t in residual if t['region']['holding_count'] == int(k)]
        complete = regular and unexpanded[k] == 0 and not pending
        per_k.append(dict(holding_count=int(k),full_conditional_composition_count=counts['full_conditional'],
            frozen_legal_support_count=counts['frozen_legal'],expanded_support_count=str(expanded),
            unexpanded_support_count=str(unexpanded[k]),residual_region_count=len(pending),
            training_frontier_witnesses=_frontier(points),coverage_scope='PER_K',
            epsilon_training_objective_cover_certified=complete,exact_action_frontier_proven=False))
    V = F(core['V'])
    zero_control = None
    if V > 0:
        support = sorted(core['quantities'])
        try:
            zero_control = _witness(c,support,1/V,{s:str(F(v)/V) for s,v in core['old_amounts'].items()})
        except ValueError as error:
            zero_control = dict(status='CONTROL_FAILED_ORIGINAL_CONSTRAINTS',reason=str(error),holding_count=len(support))
    else:
        zero_control = dict(status='ALL_CASH_CONTROL',variance=None,stock_risk=None,
                            feasible_conditionally=F(core['budget']) >= 0)
    empty = branch in ('NEGATIVE_CASH_BUDGET_EMPTY','FROZEN_ISSUER_CONFLICT_EMPTY','V_ZERO_T_ZERO_ONLY_CASH')
    complete = regular and not state['queue']
    status = ('CERTIFIED_EPSILON_TRAINING_OBJECTIVE_COVER' if complete else
        'TYPED_EMPTY_OR_CASH_ONLY_DOMAIN' if empty else
        'UNATTAINED_TRAINING_PARETO_NO_POSITIVE_ACTION_ATTAINED' if branch.startswith('V_ZERO') else
        'BUDGET_STOPPED_WITH_FULL_RESIDUAL')
    return dict(schema='SYNTHETIC_CONTINUOUS_JOINT_FRONTIER_RESULT_V1',competition_id=c['competition_id'],
        status=status,branch=branch,source_status='SYNTHETIC_UNBOUND_SOURCE_BLOCKED',
        all_k_support_coverage=per_k,implicit_support_forest=forest,residual_regions=residual,
        primal_witnesses=deepcopy(state['witnesses']),global_training_frontier_witnesses=_frontier(state['witnesses']),
        global_bound_regions=deepcopy(state['bound_ledger']),
        exact_partition_ledger=deepcopy(state['partition_ledger']),
        whole_conditional_domain_objective_lower_bounds=dict(variance='0',turnover='0',
            method='PSD_NONNEGATIVE_VARIANCE_AND_NONNEGATIVE_BUY_GROSS_INCLUDES_UNEXPANDED_SUPPORTS',
            scope='STOCK_ACTIONS_ONLY_CASH_VARIANCE_UNDEFINED'),
        global_view_scope='GLOBAL_TRAINING_ONLY_NEVER_CLEARS_PER_K_RESIDUAL',
        archived_regions=deepcopy(state['archived_regions']),economic_action_domain_retained=True,
        zero_buy_control=zero_control,
        continuous_point_count='UNCOUNTABLE_DOMAIN_NOT_A_FINITE_POINT_COVER',
        work_and_replay_counters=dict(new_search_events=new_events,resume_prefix_validation_events=replayed,
            cumulative_search_components=deepcopy(state['counters']),zero_control_audits=1,
            budget_scope=c['search_registration']['budget_scope'],
            replay_component_counts=deepcopy(replay_counters)),
        search_registration=deepcopy(c['search_registration']),
        epsilon_units=dict(variance='ONE_STEP_DECIMAL_RETURN_SQUARED',turnover='PRETRADE_TOTAL_WEALTH_FRACTION'),
        exact_continuous_frontier_proven=False,analytic_optional_family='NOT_IMPLEMENTED',
        V_zero_scope='SCALING_ANY_FEASIBLE_POSITIVE_BUY_BY_HALF_IMPROVES_TURNOVER_ONLY_FOR_THIS_TRAINING_PAIR_NOT_ECONOMIC_INFEASIBILITY',
        real_followup_blockers=['REAL_SOURCE_ADAPTER_AND_FULL_PIT','THIRTEEN_CAUSAL_COHORT_PRIOR_CASH_PATHS',
            'REAL_OBJECTIVE_AND_ACTION_RULE_UNREGISTERED','DUAL_BENCHMARK_COMMON_BASIS','FOUR_LANE_ECONOMIC_FRONTIERS'],
        authority=dict.fromkeys(AUTHORITY,False),current_account=None,current_new_money=None,plan_rows=[],
        resume_state=deepcopy(state),resume_sha256=digest(state))


def search_synthetic_continuous_frontier(*, competition, work_budget, resume_state=None, expected_resume_sha256=None):
    c = validate_competition(competition)
    _integer(work_budget,'work budget')
    state = _initial(c)
    replayed = 0
    replay_counters = dict(state['counters'])
    if resume_state is None:
        require(expected_resume_sha256 is None, 'Hash without resume state')
    else:
        require(type(resume_state) is dict and type(expected_resume_sha256) is str
                and digest(resume_state) == expected_resume_sha256, 'Resume digest drift')
        replayed = _integer(resume_state.get('events'),'resume event cursor')
        require(resume_state.get('competition_id') == c['competition_id'], 'Resume competition drift')
        actual = _advance(c,state,replayed)
        require(actual == replayed and digest(state) == digest(resume_state), 'Resume exact partition/prefix replay mismatch')
        replay_counters = dict(state['counters'])
    newly = _advance(c,state,work_budget)
    return _result(c,state,newly,replayed,replay_counters)
