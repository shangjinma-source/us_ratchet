"""Explicit V2 wrapper plus all-k DFS/FIFO fair synthetic region scheduling.

The unchanged V1 mathematical competition is validated as a separate embedded
object. V2 has its own identity, registration and checkpoint; no V1 state cast.
Only fixed pure projection/certificate helpers operate on the validated math.
No source IO, real fit, winner, trade or economic admission.
"""
from copy import deepcopy
from fractions import Fraction as F
from backtest import ndx_continuous_joint_projection_research as P
from backtest import ndx_continuous_joint_certificates_research as C
from backtest.ndx_continuous_joint_frontier_research import _frontier

require, digest = P.require,P.digest
_coefficient_polynomial = P.coefficients
REGISTRATION = dict(
    schema='RATIONAL_CONTINUOUS_REGION_SEARCH_RULE_V2',
    scheduler='ONE_FINITE_MAX_LEGAL_K_DFS_WARMUP_THEN_TWO_LANE_ALTERNATION_WITH_PER_K_DFS_ROUND_ROBIN_AND_REGION_FIFO',
    budget_scope='NEW_EVENTS_ONLY_EXCLUDES_REPLAY_CONTROL_INPUT_VALIDATION_AND_INITIAL_COEFFICIENT_SETUP_NOT_TOTAL_OPERATIONS_OR_TIME',
    support_group_order='ASCENDING_ISSUER_ID_FIXED_FROM_COMPLETE_CONDITIONAL_BUY_INVENTORY_EXCLUDING_OCCUPIED_ISSUERS',
    support_logical_child_order='ASCENDING_SID_TAKE_CHOICES_THEN_SKIP',
    support_stack_push_order='REVERSE_LOGICAL_CHILD_ORDER_THEN_POP_LAST',
    support_cardinality_partition='DISJOINT_TARGET_K_FORESTS_FOR_EVERY_NONZERO_LEGAL_K_COEFFICIENT_NO_ECONOMIC_PRESELECTION',
    warmup='MAX_NONZERO_LEGAL_K_FIRST_LEAF_AT_MOST_N_PLUS_ONE_SUPPORT_EVENTS_THEN_IRREVOCABLY_DISABLE_WARMUP',
    support_fairness='AFTER_WARMUP_ASCENDING_K_CYCLIC_ROUND_ROBIN_ONE_DFS_PREFIX_OR_LEAF_EVENT_PER_NONEMPTY_STACK',
    lane_rule='START_SUPPORT_AFTER_ACTUAL_SUPPORT_EVENT_PREFER_REGION_AFTER_ACTUAL_REGION_EVENT_PREFER_SUPPORT_EMPTY_LANE_FALLBACK_CONSUMES_NO_EXTRA_EVENT',
    region_order='FIFO_ENQUEUE_SERIAL_WITH_CHILDREN_LEFT_THEN_RIGHT_AT_TAIL',
    terminal_unresolved='RETAIN_SEPARATE_FROM_REFINABLE_REGION_FIFO_DO_NOT_BLOCK_OR_REPEAT',
    split='WIDEST_RAW_AXIS_RATIONAL_MIDPOINT_LEFT_UPPER_OPEN_RIGHT_LOWER_CLOSED',
    coverage='PER_K_SAME_K_FEASIBLE_WITNESS_ONLY_GLOBAL_VIEW_CANNOT_CLEAR_PER_K_RESIDUAL',
    resume='V2_SCHEMA_FIXED_REGISTRATION_EXACT_FULL_PREFIX_REPLAY_REJECT_ALL_V1_CHECKPOINTS_NO_AUTOMATIC_MIGRATION')
SCHEMA = 'SYNTHETIC_CONTINUOUS_FAIR_COMPETITION_V2'
CHECKPOINT = 'SYNTHETIC_CONTINUOUS_FAIR_CHECKPOINT_V2'


def prepare_synthetic_fair_continuous_competition(*, mathematical_competition):
    base = P.validate_competition(mathematical_competition)
    result = dict(schema=SCHEMA,mathematical_competition=base,
        mathematical_competition_id=base['competition_id'],search_registration=deepcopy(REGISTRATION),
        core=deepcopy(base['core']),synthetic_covariance=deepcopy(base['synthetic_covariance']),
        epsilon_variance=base['epsilon_variance'],epsilon_turnover=base['epsilon_turnover'],
        source_status=base['source_status'],authority=deepcopy(base['authority']),
        real_objective_status='UNREGISTERED',wrapper_scope='NEW_EXPLICIT_SCHEDULER_IDENTITY_OVER_VALIDATED_UNCHANGED_V1_MATH')
    result['competition_id'] = digest(result)
    return deepcopy(result)


def validate_fair_competition(c):
    require(type(c) is dict and c.get('schema') == SCHEMA, 'Explicit V2 competition required')
    rebuilt = prepare_synthetic_fair_continuous_competition(mathematical_competition=c['mathematical_competition'])
    require(digest(c) == digest(rebuilt), 'V2 competition/registration drift')
    return rebuilt


def verify_fair_witness(*, competition, support_security_ids, reciprocal_total_stock, weights):
    return P._witness(validate_fair_competition(competition),support_security_ids,reciprocal_total_stock,weights)


def verify_fair_region_certificate(*, competition, region, certificate):
    c = validate_fair_competition(competition)
    plane = certificate.get('supporting_plane')
    rebuilt = C.bound_region(c,region,None if plane is None else plane['point'])
    require(digest(certificate) == digest(rebuilt), 'V2 region certificate drift')
    return rebuilt


def verify_fair_cover_certificate(*, competition, region, bound, certificate):
    c = validate_fair_competition(competition)
    require(certificate.get('scope') == 'PER_K', 'PER_K certificate required')
    rebuilt = C.cover_region(c,region,bound,certificate['witness'])
    require(digest(certificate) == digest(rebuilt), 'V2 cover drift')
    return rebuilt


def verify_fair_inherited_bound(*, competition, child_region, parent_certificate):
    c = validate_fair_competition(competition)
    plane = parent_certificate.get('supporting_plane')
    rebuilt = C.bound_region(c,parent_certificate['region'],None if plane is None else plane['point'])
    require(digest(parent_certificate) == digest(rebuilt), 'V2 parent bound drift')
    return C.inherited_bound_relation(c,child_region,rebuilt)


def _integer(value,name):
    require(type(value) is int and value >= 0, name+' nonboolean nonnegative integer required')
    return value


def _count(c, target_k, index, chosen, counters):
    remaining = c['core']['issuer_groups'][index:]
    counters['coefficient_calls'] += 1
    counters['coefficient_factor_visits'] += len(remaining)
    poly = _coefficient_polynomial({str(i):len(g) for i,g in enumerate(remaining)})
    r = target_k-len(c['core']['quantities'])-len(chosen)
    return poly[r] if 0 <= r < len(poly) else 0


def _initial(c):
    core = c['core']
    branch = ('NEGATIVE_CASH_BUDGET_EMPTY' if F(core['budget']) < 0 else
        'FROZEN_ISSUER_CONFLICT_EMPTY' if core['old_issuer_conflicts'] else
        'V_ZERO_T_ZERO_ONLY_CASH' if F(core['V']) == 0 and F(core['T']) == 0 else
        'V_ZERO_T_POSITIVE_UNATTAINED_TRAINING_INFIMUM' if F(core['V']) == 0 else 'BOUNDED_RECIPROCAL_REGION_SEARCH')
    setup = dict(coefficient_calls=0,coefficient_factor_visits=0,root_rows_visited=0,positive_roots_created=0)
    stacks,root_zeros = {},[]
    for k,row in core['per_k'].items():
        setup['root_rows_visited'] += 1
        stacks[k] = []
        if branch == 'BOUNDED_RECIPROCAL_REGION_SEARCH':
            count = _count(c,int(k),0,[],setup)
            require(str(count) == row['frozen_legal'], 'V2 root coefficient drift')
            if count:
                stacks[k] = [dict(target_k=int(k),index=0,chosen=[],composition_count=str(count))]
                setup['positive_roots_created'] += 1
            else:
                root_zeros.append(dict(target_k=int(k),composition_count='0',
                    claim='EXACT_ZERO_ROOT_CARDINALITY_COEFFICIENT_NOT_ECONOMIC_PRUNING',
                    reason='BELOW_FROZEN_POSITIVE_HOLDING_COUNT' if int(k)<len(core['quantities']) else 'ABOVE_ELIGIBLE_NEW_ISSUER_SUPPORT'))
    active = [int(k) for k,v in stacks.items() if v]
    observations = {k:dict(support_services=0,last_support_event=None,first_leaf_event=None,
                          first_bound_event=None,first_search_witness_event=None) for k in core['per_k']}
    return dict(schema=CHECKPOINT,competition_id=c['competition_id'],search_registration=deepcopy(REGISTRATION),
        branch=branch,events=0,warmup_target_k=max(active) if active else None,warmup_complete=not active,
        preferred_lane='SUPPORT',support_k_cursor=min(active) if active else 1,support_stacks_by_k=stacks,
        region_fifo=[],next_region_enqueue_serial=0,region_turn=0,terminal_unresolved_regions=[],
        expanded_supports=[],witnesses=[],bound_ledger=[],partition_ledger=[],archived_regions=[],zero_coefficient_proofs=[],
        root_zero_coefficient_proofs=root_zeros,
        per_k_service_observations=observations,first_leaf_event=None,first_bound_event=None,first_search_witness_event=None,
        setup_components=setup,event_trace=[],counters=dict(support_expansions=0,support_materializations=0,
        region_events=0,bound_checks=0,witness_proposals=0,witness_formula_checks=0,coverage_checks=0,
        region_splits=0,region_split_attempts=0,coefficient_calls=0,coefficient_factor_visits=0),event_hash=digest(dict(competition=c['competition_id'],prefix='EMPTY')))


def _enqueue(state, region, **extra):
    state['region_fifo'].append(dict(region=deepcopy(region),enqueue_serial=state['next_region_enqueue_serial'],
        enqueued_after_region_turn=state['region_turn'],older_refinable_tasks_at_enqueue=len(state['region_fifo']),**deepcopy(extra)))
    state['next_region_enqueue_serial'] += 1


def _support_event(c,state,event):
    active = sorted(int(k) for k,v in state['support_stacks_by_k'].items() if v)
    if not state['warmup_complete']:
        k = state['warmup_target_k']
    else:
        k = next((k for k in active if k >= state['support_k_cursor']),active[0])
    state['support_k_cursor'] = k+1
    task = state['support_stacks_by_k'][str(k)].pop()
    obs = state['per_k_service_observations'][str(k)]
    obs['support_services'] += 1
    obs['last_support_event'] = event
    groups = c['core']['issuer_groups']
    i = task['index']
    counters = state['counters']
    if i < len(groups):
        counters['support_expansions'] += 1
        children = []
        for extra in [[s] for s in groups[i]]+[[]]:
            chosen = task['chosen']+extra
            count = _count(c,k,i+1,chosen,counters)
            child = dict(target_k=k,index=i+1,chosen=chosen,composition_count=str(count))
            if count:
                children.append(child)
            else:
                state['zero_coefficient_proofs'].append(dict(parent=deepcopy(task),empty_child=child,
                    claim='EXACT_ZERO_REMAINING_CARDINALITY_COEFFICIENT_NOT_ECONOMIC_PRUNING'))
        require(sum(int(t['composition_count']) for t in children) == int(task['composition_count']), 'Child coefficient conservation')
        state['support_stacks_by_k'][str(k)].extend(reversed(children))
    else:
        counters['support_materializations'] += 1
        support = sorted(list(c['core']['quantities'])+task['chosen'])
        require(len(support) == k and task['composition_count'] == '1', 'Leaf cardinality/count mismatch')
        state['expanded_supports'].append(support)
        if obs['first_leaf_event'] is None: obs['first_leaf_event'] = event
        if state['first_leaf_event'] is None: state['first_leaf_event'] = event
        state['warmup_complete'] = True
        if F(c['core']['T']) == 0 and k > len(c['core']['quantities']):
            state['archived_regions'].append(dict(support=support,holding_count=k,
                status='PROVEN_INFEASIBLE_ZERO_CAPITAL_NEW_SUPPORT',economic_domain_retained=True))
        else:
            _enqueue(state,C.root_region(c,support))
    return dict(lane='SUPPORT',target_k=k,task=task)


def _region_event(c,state,event):
    task = state['region_fifo'].pop(0)
    region = task['region']
    k = region['holding_count']
    obs = state['per_k_service_observations'][str(k)]
    counter = state['counters']
    if obs['first_bound_event'] is None: obs['first_bound_event'] = event
    if state['first_bound_event'] is None: state['first_bound_event'] = event
    wait = state['region_turn']-task['enqueued_after_region_turn']
    state['region_turn'] += 1
    counter['region_events'] += 1
    bound = C.bound_region(c,region)
    counter['bound_checks'] += 1
    state['bound_ledger'].append(deepcopy(bound))
    archive = dict(region=deepcopy(region),support=region['support'],holding_count=k,bound=bound,economic_domain_retained=True)
    if bound['infeasibility_reasons']:
        archive['status'] = 'PROVEN_INFEASIBLE_INTERVAL_CERTIFICATE'
        state['archived_regions'].append(archive)
    else:
        found,attempts,checks = C.propose_witnesses(c,region)
        counter['witness_proposals'] += attempts
        counter['witness_formula_checks'] += checks
        known = {w['witness_id'] for w in state['witnesses']}
        for w in found:
            if w['witness_id'] not in known:
                state['witnesses'].append(w)
                known.add(w['witness_id'])
                if obs['first_search_witness_event'] is None: obs['first_search_witness_event'] = event
                if state['first_search_witness_event'] is None: state['first_search_witness_event'] = event
        covered = False
        for w in state['witnesses']:
            if w['holding_count'] != k: continue
            counter['coverage_checks'] += 1
            counter['bound_checks'] += 1
            counter['witness_formula_checks'] += 1
            try: cover = C.cover_region(c,region,bound,w)
            except ValueError: continue
            archive.update(status='PER_K_EPSILON_OBJECTIVE_COVER',cover=cover)
            state['archived_regions'].append(archive)
            covered = True
            break
        if not covered:
            counter['region_split_attempts'] += 1
            children = C.split_region(region)
            if children is None:
                state['terminal_unresolved_regions'].append(dict(region=region,bound=bound,status='UNRESOLVED_NOT_REFINEABLE'))
            else:
                counter['region_splits'] += 1
                relations = [C.inherited_bound_relation(c,r,bound) for r in children]
                state['partition_ledger'].append(dict(parent_certificate_id=bound['certificate_id'],parent_region_id=digest(region),
                    children=deepcopy(list(children)),relations=relations,partition='REGISTERED_HALFOPEN_MIDPOINT'))
                for r,rel in zip(children,relations):
                    _enqueue(state,r,inherited_parent_bound=bound,inherited_parent_relation=rel)
    return dict(lane='REGION',target_k=k,enqueue_serial=task['enqueue_serial'],region_wait_turns=wait,task=task)


def _advance(c,state,count):
    visits = 0
    while visits < count:
        support = any(state['support_stacks_by_k'].values())
        region = bool(state['region_fifo'])
        if not support and not region: break
        lane = state['preferred_lane']
        if lane == 'SUPPORT' and not support: lane = 'REGION'
        if lane == 'REGION' and not region: lane = 'SUPPORT'
        event = state['events']+1
        warmup_before = state['warmup_complete']
        trace = _support_event(c,state,event) if lane == 'SUPPORT' else _region_event(c,state,event)
        state['preferred_lane'] = 'REGION' if lane == 'SUPPORT' else 'SUPPORT'
        state['events'] = event
        trace.update(event=event,warmup_complete_before=warmup_before,warmup_complete_after=state['warmup_complete'])
        state['event_trace'].append(trace)
        state['event_hash'] = digest(dict(previous=state['event_hash'],trace=trace,counters=state['counters']))
        visits += 1
    return visits


def _result(c,state,new,replayed,replay_counts):
    core = c['core']
    regular = state['branch'] == 'BOUNDED_RECIPROCAL_REGION_SEARCH'
    forest,rows = [],[]
    residual = deepcopy(state['region_fifo'])
    for task in residual: task['current_age_region_turns'] = state['region_turn']-task['enqueued_after_region_turn']
    unresolved = deepcopy(state['terminal_unresolved_regions'])
    for k,denominator in core['per_k'].items():
        stack = state['support_stacks_by_k'][k]
        pending = sum(int(t['composition_count']) for t in stack)
        expanded = sum(len(s) == int(k) for s in state['expanded_supports'])
        if regular: require(pending+expanded == int(denominator['frozen_legal']), 'All-k residual conservation')
        for t in stack: forest.append(dict(target_k=int(k),prefix=deepcopy(t),composition_count=t['composition_count']))
        waiting = sum(t['region']['holding_count'] == int(k) for t in residual+unresolved)
        rows.append(dict(holding_count=int(k),full_conditional_composition_count=denominator['full_conditional'],
            frozen_legal_support_count=denominator['frozen_legal'],expanded_support_count=str(expanded),
            unexpanded_support_count=str(pending) if regular else denominator['frozen_legal'],
            residual_region_count=waiting,service=deepcopy(state['per_k_service_observations'][k]),
            training_frontier_witnesses=_frontier([w for w in state['witnesses'] if w['holding_count'] == int(k)]),
            epsilon_training_objective_cover_certified=regular and pending == 0 and waiting == 0,
            coverage_scope='PER_K',exact_action_frontier_proven=False))
        rows[-1]['structural_zero_domain_certificate'] = next((deepcopy(p) for p in state['root_zero_coefficient_proofs'] if p['target_k']==int(k)),None)
    if state['branch'].startswith('V_ZERO'):
        forest = [dict(domain='ALL_LEGAL_SUPPORTS_AND_ORIGINAL_RISK_WEIGHT_DOMAINS_UNSEARCHED',
            per_k_composition_counts={k:r['frozen_legal'] for k,r in core['per_k'].items()},capital_domain='t/T IN (0,1] IF T>0',
            no_attained_pareto_scope='SCALING_POSITIVE_BUY_BY_HALF_THIS_TRAINING_PAIR_ONLY_NOT_ECONOMIC_INFEASIBILITY')]
    if F(core['V']) > 0:
        try:
            control = P._witness(c,sorted(core['quantities']),1/F(core['V']),
                {s:str(F(v)/F(core['V'])) for s,v in core['old_amounts'].items()})
        except ValueError as error: control = dict(status='CONTROL_FAILED_ORIGINAL_CONSTRAINTS',reason=str(error))
    else: control = dict(status='ALL_CASH_CONTROL',variance=None,stock_risk=None,feasible_conditionally=F(core['budget'])>=0)
    complete = regular and not forest and not residual and not unresolved
    return dict(schema='SYNTHETIC_CONTINUOUS_FAIR_RESULT_V2',competition_id=c['competition_id'],branch=state['branch'],
        status='CERTIFIED_EPSILON_TRAINING_OBJECTIVE_COVER' if complete else 'RESIDUAL_OR_TYPED_BRANCH_NOT_EXACT_FRONTIER',
        all_k_support_coverage=rows,implicit_support_forest=forest,residual_regions=residual,terminal_unresolved_regions=unresolved,
        zero_coefficient_proofs=deepcopy(state['zero_coefficient_proofs']),primal_witnesses=deepcopy(state['witnesses']),
        root_zero_coefficient_proofs=deepcopy(state['root_zero_coefficient_proofs']),
        global_training_frontier_witnesses=_frontier(state['witnesses']),global_view_never_clears_per_k_residual=True,
        global_bound_regions=deepcopy(state['bound_ledger']),exact_partition_ledger=deepcopy(state['partition_ledger']),
        archived_regions=deepcopy(state['archived_regions']),economic_action_domain_retained=True,
        whole_domain_stock_objective_lower_bounds=dict(variance='0',turnover='0',method='PSD_AND_NONNEGATIVE_BUYS'),
        observations={key:deepcopy(state[key]) for key in ['first_leaf_event','first_bound_event','first_search_witness_event',
            'warmup_complete','warmup_target_k','preferred_lane','support_k_cursor','region_turn','next_region_enqueue_serial']},
        zero_buy_control=control,work=dict(new_search_events=new,resume_prefix_validation_events=replayed,
            setup_components=deepcopy(state['setup_components']),replay_component_counts=deepcopy(replay_counts),
            cumulative_search_components=deepcopy(state['counters']),zero_control_audits=1,
            budget_scope=REGISTRATION['budget_scope']),search_registration=deepcopy(REGISTRATION),
        source_status='SYNTHETIC_UNBOUND_SOURCE_BLOCKED',real_objective_status='UNREGISTERED',
        real_followup_blockers=['FULL_SOURCE_PIT','THIRTEEN_CAUSAL_PRIOR_CASH_PATHS','DUAL_BENCHMARK_COMMON_BASIS','FOUR_LANE_ECONOMIC_FRONTIERS'],
        analytic_optional_family='NOT_IMPLEMENTED',V_zero_weight_search='NOT_IMPLEMENTED_FULL_DOMAIN_RETAINED',
        exact_continuous_frontier_proven=False,continuous_point_count='UNCOUNTABLE',authority=deepcopy(c['authority']),
        current_account=None,current_new_money=None,plan_rows=[],resume_state=deepcopy(state),resume_sha256=digest(state))


def search_synthetic_fair_continuous_frontier(*, competition, work_budget, resume_state=None, expected_resume_sha256=None):
    c = validate_fair_competition(competition)
    _integer(work_budget,'work budget')
    if resume_state is not None:
        require(type(resume_state) is dict and resume_state.get('schema') == CHECKPOINT, 'V2 checkpoint only; V1 migration forbidden')
        require(resume_state.get('search_registration') == REGISTRATION, 'V2 fixed resume registration required')
        require(type(expected_resume_sha256) is str and digest(resume_state) == expected_resume_sha256, 'Resume digest drift')
    else: require(expected_resume_sha256 is None, 'Hash without resume')
    state = _initial(c)
    replayed,replay_counts = 0,{key:0 for key in state['counters']}
    if resume_state is not None:
        require(resume_state.get('competition_id') == c['competition_id'], 'Resume competition mismatch')
        replayed = _integer(resume_state.get('events'),'resume events')
        require(_advance(c,state,replayed) == replayed and digest(state) == digest(resume_state), 'Exact V2 prefix/partition replay mismatch')
        replay_counts = deepcopy(state['counters'])
    new = _advance(c,state,work_budget)
    return _result(c,state,new,replayed,replay_counts)
