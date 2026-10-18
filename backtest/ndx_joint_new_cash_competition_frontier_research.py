"""Synthetic-only lazy full whole-lot training Pareto, never a real optimizer.

No price/source IO, fits, historical path evaluation, target following or winner.
The input A object is mathematically cross-checked, not source-authenticated.
Checkpoint consistency is independently replayed; its hash is not a signature.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import re


SPECIFICATION = 'SYNTHETIC_JOINT_VARIANCE_BUY_FRONTIER_V1'
SCHEMA = 'SYNTHETIC_JOINT_COMPETITION_V1'
CHECKPOINT_SCHEMA = 'SYNTHETIC_JOINT_FRONTIER_CHECKPOINT_V1'
TOLERANCE = Fraction(1, 10**9)
RISK_KEYS = ('max_single_weight', 'min_single_weight', 'top_weight_cap',
             'minimum_effective_n_ratio', 'risk_chain_top1_cap')
CHECK_KEYS = ('MAX_SINGLE_WEIGHT', 'MIN_SINGLE_WEIGHT', 'SECURITY_TOP3_WEIGHT',
              'MINIMUM_EFFECTIVE_N', 'RISK_CHAIN_TOP1_WEIGHT')
AUTHORITY = ('source_bytes_authenticated', 'source_qualified_by_caller',
    'formal_admission_allowed', 'execution_authorized', 'promotion_allowed',
    'current_account_verified', 'current_new_money_supplied', 'winner_selected',
    'fit_called', 'continuous_global_optimality_proven', 'real_objective_registered',
    'causal_economic_frontier_proven')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode('utf-8')).hexdigest()


def _integer(value, name):
    _require(type(value) is int and value >= 0, name + ' requires nonboolean nonnegative integer')
    return value


def _rational(value, name, nonnegative=False):
    _require(type(value) in (int, str, Decimal, Fraction), name + ' requires exact rational, not float/bool')
    if type(value) is str:
        _require(len(value) <= 200 and (re.fullmatch(r'-?\d+/[1-9]\d*', value) is not None
            or re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', value) is not None),
            name + ' invalid rational literal')
    if type(value) is int:
        _require(value.bit_length() <= 540, name + ' rational resource limit')
    if type(value) is Fraction:
        _require(value.numerator.bit_length() <= 540 and value.denominator.bit_length() <= 540,
                 name + ' rational resource limit')
    if type(value) is Decimal or (type(value) is str and '/' not in value):
        decimal = Decimal(value)
        _require(decimal.is_finite(), name + ' requires finite rational')
        _require(len(decimal.as_tuple().digits) <= 160 and abs(decimal.as_tuple().exponent) <= 160,
                 name + ' rational resource limit')
    try:
        result = Fraction(value)
    except (ValueError, OverflowError, ZeroDivisionError) as error:
        raise ValueError(name + ' requires finite rational') from error
    _require(len(str(abs(result.numerator))) <= 160 and len(str(result.denominator)) <= 160,
             name + ' rational resource limit')
    if nonnegative:
        _require(result >= 0, name + ' cannot be negative')
    return result


def _instant(value):
    _require(type(value) is str, 'Aware synthetic timestamp required')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('Aware synthetic timestamp required') from error
    _require(result.tzinfo is not None and result.utcoffset() is not None, 'Aware synthetic timestamp required')
    return result


def _coefficients(issuer_weights):
    coefficients = [1]
    for issuer in sorted(issuer_weights):
        coefficients.append(0)
        for k in range(len(coefficients)-1, 0, -1):
            coefficients[k] += coefficients[k-1] * issuer_weights[issuer]
    return coefficients


def _identity_rows(rows):
    _require(type(rows) is list, 'SID metadata list required')
    result = {}
    for row in rows:
        _require(type(row) is dict and set(row) == {'security_id','issuer_id','ticker','risk_chain'}, 'Exact SID metadata')
        _require(all(type(value) is str and value and value.strip() == value for value in row.values()), 'Canonical SID metadata')
        _require(row['security_id'] not in result, 'Duplicate SID metadata')
        result[row['security_id']] = dict(row)
    return result


def _mathematical_A(problem):
    _require(type(problem) is dict and problem.get('schema') == 'VARIABLE_CARDINALITY_NEW_CASH_PROBLEM_V1', 'A schema required')
    _require(problem.get('problem_id') == _digest({key:value for key,value in problem.items() if key != 'problem_id'}), 'A problem digest drift')
    _require(problem.get('input_scope') == 'SYNTHETIC_UNBOUND'
        and problem.get('source_binding_status') == 'UNBOUND' and problem.get('status') == 'SOURCE_BLOCKED', 'Synthetic UNBOUND A only')
    _require(problem.get('domain_kind') == 'WHOLE_LOT_QUANTITIES', 'Only A WHOLE_LOT domain implemented; continuous remains UNKNOWN')
    _require(problem.get('numerical_status') == 'CONDITIONAL_CONTEXT_READY'
             and problem.get('context_blockers') == [], 'A numerical context blocked')
    _require(problem.get('qualified_inventory_or_null') is None
             and problem.get('qualified_all_k_denominators_or_null') is None, 'A cannot confer qualification')
    _require(type(problem.get('authority')) is dict and problem['authority']
             and all(value is False for value in problem['authority'].values()), 'A authority must remain False')
    _require(type(problem.get('source_checks')) is list and len(problem['source_checks']) == 10
             and all(row.get('status') == 'SOURCE_BLOCKED' for row in problem['source_checks']), 'All A source requirements remain blocked')
    inventory = _identity_rows(problem['conditional_inventory']['securities'])
    old_metadata = _identity_rows(problem['frozen_prior_book']['security_metadata'])
    for sid in set(inventory) & set(old_metadata):
        _require(inventory[sid] == old_metadata[sid], 'Old/inventory identity conflict')
    identities = dict(sorted({**inventory, **old_metadata}.items()))
    raw_q = problem['frozen_prior_book']['quantities']
    _require(type(raw_q) is dict and set(raw_q) == set(old_metadata), 'Exact positive old metadata required')
    q = {sid:_rational(value,'old quantity',True) for sid,value in raw_q.items()}
    _require(all(value > 0 for value in q.values()), 'A old quantities must be positive')
    formula, policy = problem['domain_formula'], problem['policy']
    _require(type(formula['prices']) is dict and set(formula['prices']) == set(identities), 'Complete A prices')
    prices = {sid:_rational(value,'price',True) for sid,value in formula['prices'].items()}
    _require(all(value > 0 for value in prices.values()), 'Positive prices required')
    lots = formula['lot_sizes']
    _require(type(lots) is dict and set(lots) == set(identities), 'Complete lot sizes')
    _require(all(type(value) is int and value > 0 for value in lots.values()), 'Positive integer lots required')
    excluded = problem['conditional_exclusions']
    _require(type(excluded) is dict and set(excluded) <= set(inventory), 'A exclusions outside inventory')
    buys = sorted(set(inventory)-set(excluded))
    _require(problem['conditional_buy_security_ids'] == buys, 'A full buy inventory drift')
    old_cash = _rational(problem['frozen_prior_book']['cash'],'prior cash',True)
    event = _rational(formula['cash_event_amount'],'cash event',True)
    buffer = _rational(policy['minimum_cash_buffer'],'buffer',True)
    fee_bps = _rational(policy['transaction_cost_bps'],'fee',True)
    _require(fee_bps <= 10000, 'Invalid fee')
    fee_factor, cash = 1+fee_bps/10000, old_cash+event
    budget = cash-buffer
    old_value = sum((q.get(sid,0)*prices[sid] for sid in identities), Fraction(0))
    for key, expected in (('total_cash_before_buys',cash),('cash_budget_after_buffer',budget),
            ('minimum_cash_buffer',buffer),('fee_factor',fee_factor),('old_stock_value',old_value)):
        _require(_rational(formula[key],key) == expected, 'A mathematical drift: '+key)
    _require(formula['currency'] == problem['frozen_prior_book']['currency'], 'A currency drift')
    risk = policy['risk_parameters']
    _require(type(risk) is dict and set(risk) == set(RISK_KEYS), 'Five risk parameters required')
    risk = {key:_rational(value,key,True) for key,value in risk.items()}
    _require(all(value <= 1 for value in risk.values()) and risk['max_single_weight'] > 0
        and risk['risk_chain_top1_cap'] > 0 and risk['min_single_weight'] <= risk['max_single_weight'], 'Invalid risk envelope')
    _require(_rational(policy['risk_tolerance'],'risk tolerance') == TOLERANCE, 'Risk tolerance drift')
    caps = None if budget < 0 else {sid:int(budget//(prices[sid]*lots[sid]*fee_factor)) for sid in buys}
    if caps is not None:
        _require(type(formula['coordinate_caps_or_null']) is dict
            and all(type(value) is int and value >= 0 for value in formula['coordinate_caps_or_null'].values()),
            'A quantity caps require nonboolean integers')
    _require(formula['coordinate_caps_or_null'] == caps, 'A quantity cap drift')
    box_count = None
    if caps is not None:
        box_count = 1
        for cap in caps.values():
            box_count *= cap+1
    _require(problem['bounding_box_count_or_null'] == (None if box_count is None else str(box_count)), 'A raw box count drift')
    old_issuers = {}
    for sid in q:
        old_issuers.setdefault(identities[sid]['issuer_id'],[]).append(sid)
    conflicts = {issuer:sorted(sids) for issuer,sids in old_issuers.items() if len(sids)>1}
    _require(problem['frozen_prior_book']['issuer_conflicts'] == conflicts, 'A old issuer conflict drift')
    _require(problem['frozen_prior_book']['positive_holding_count'] == len(q), 'A old support count drift')
    full_issuers = {}
    for row in identities.values():
        full_issuers[row['issuer_id']] = full_issuers.get(row['issuer_id'],0)+1
    full_coefficients = _coefficients(full_issuers)
    inventory_issuers = {}
    for row in inventory.values():
        inventory_issuers[row['issuer_id']] = inventory_issuers.get(row['issuer_id'],0)+1
    _require(problem['conditional_inventory']['security_count'] == len(inventory)
        and problem['conditional_inventory']['issuer_count'] == len(inventory_issuers), 'A inventory count drift')
    _require(problem['conditional_inventory']['all_k_denominators'] == [dict(holding_count=k,composition_count=str(value))
        for k,value in enumerate(_coefficients(inventory_issuers)) if k], 'A inventory denominator drift')
    max_k = len(full_coefficients)-1
    _require(len(problem['all_k_rows']) == max_k, 'A all-k rows drift')
    new_classes = {}
    for sid in buys:
        issuer = identities[sid]['issuer_id']
        if issuer not in old_issuers:
            new_classes[issuer] = new_classes.get(issuer,0)+1
    frozen_coefficients = _coefficients(new_classes)
    for k,row in enumerate(problem['all_k_rows'],1):
        offset = k-len(q)
        frozen_count = str(frozen_coefficients[offset]) if 0<=offset<len(frozen_coefficients) else '0'
        _require(row['holding_count'] == k and row['full_conditional_composition_count'] == str(full_coefficients[k])
            and row['frozen_old_conditional_composition_count'] == (None if conflicts else frozen_count), 'A per-k composition drift')
    wealth = old_value+cash
    _require(wealth > 0, 'Positive pretrade total wealth required; no zero-wealth turnover convention')
    # Issuer-compatible raw quantity counts, before coupled cash/risk checks.
    quantity_weights, old_factor = {}, 1
    if caps is not None and not conflicts:
        for issuer,sids in old_issuers.items():
            old_factor *= caps.get(sids[0],0)+1
        for sid in buys:
            issuer = identities[sid]['issuer_id']
            if issuer not in old_issuers:
                quantity_weights[issuer] = quantity_weights.get(issuer,0)+caps[sid]
    quantity_coefficients = _coefficients(quantity_weights)
    per_k = {}
    for k in range(1,max_k+1):
        offset = k-len(q)
        per_k[str(k)] = (old_factor*quantity_coefficients[offset]
                        if caps is not None and not conflicts and 0<=offset<len(quantity_coefficients) else 0)
    k0 = (1 if not q and caps is not None else 0)
    return dict(identities=identities, buys=buys, quantities={sid:str(value) for sid,value in sorted(q.items())},
        prices={sid:str(value) for sid,value in sorted(prices.items())}, lots=dict(lots),
        risk={key:str(value) for key,value in risk.items()}, cash=str(cash), buffer=str(buffer),
        budget=str(budget), fee_factor=str(fee_factor), old_stock_value=str(old_value), pretrade_wealth=str(wealth),
        caps=caps, raw_box_count=0 if box_count is None else box_count,
        A_raw_box_count_or_null=box_count, per_k_box_counts=per_k, k0_box_count=k0,
        old_issuer_conflicts=conflicts,
        issuer_incompatible_box_count=(0 if box_count is None else box_count-sum(per_k.values())-k0))


def _covariance(value, core, decision_timestamp):
    _require(type(value) is dict and set(value) == {'schema','security_ids','values','return_unit','available_at','timing_scope'}, 'Closed synthetic covariance schema required')
    _require(value['schema'] == 'EXPLICIT_SYNTHETIC_RATIONAL_COVARIANCE_V1'
        and value['return_unit'] == 'ONE_STEP_DECIMAL_RETURN_SQUARED'
        and value['timing_scope'] == 'SYNTHETIC_TRAINING_ONLY', 'Synthetic covariance units/timing required')
    ids = sorted(core['prices'])
    _require(value['security_ids'] == ids, 'Full ordered covariance SID inventory required')
    _require(_instant(value['available_at']) <= _instant(decision_timestamp), 'Synthetic covariance unavailable at decision')
    rows = value['values']
    _require(type(rows) is list and len(rows) == len(ids)
             and all(type(row) is list and len(row) == len(ids) for row in rows), 'Square covariance required')
    matrix = [[_rational(item,'covariance') for item in row] for row in rows]
    _require(all(matrix[i][j] == matrix[j][i] for i in range(len(ids)) for j in range(len(ids))), 'Symmetric covariance required')
    residual = [row[:] for row in matrix]
    for pivot in range(len(ids)):
        diagonal = residual[pivot][pivot]
        _require(diagonal >= 0, 'Exact covariance is not PSD')
        if diagonal == 0:
            _require(all(residual[pivot][j] == 0 for j in range(pivot+1,len(ids))), 'Exact covariance is not PSD at zero pivot')
        else:
            for i in range(pivot+1,len(ids)):
                for j in range(pivot+1,len(ids)):
                    residual[i][j] -= residual[i][pivot]*residual[pivot][j]/diagonal
    return dict(schema=value['schema'],security_ids=ids,values=[[str(item) for item in row] for row in matrix],
        return_unit=value['return_unit'],available_at=_instant(value['available_at']).isoformat(),timing_scope=value['timing_scope'],
        positive_semidefinite_check='EXACT_RATIONAL_SCHUR_COMPLEMENTS')


def prepare_synthetic_joint_competition(*, prepared_problem, synthetic_covariance):
    """Validate exact synthetic math; do not authenticate A or any source."""
    core = _mathematical_A(prepared_problem)
    covariance = _covariance(synthetic_covariance,core,prepared_problem['decision_timestamp'])
    result = dict(schema=SCHEMA,specification=SPECIFICATION,A_problem=deepcopy(prepared_problem),
        source_binding_status='SYNTHETIC_UNBOUND',core=core,synthetic_covariance=covariance,
        A_context_validation_scope='SYNTHETIC_NORMALIZED_FACTS_ONLY_RAW_AVAILABILITY_NOT_EXPORTED_OR_AUTHENTICATED',
        objective_directions=['MINIMIZE','MINIMIZE'],
        objective_units=['ONE_STEP_DECIMAL_RETURN_SQUARED','DIMENSIONLESS_PRETRADE_TOTAL_WEALTH_FRACTION'],
        real_objective_status='UNREGISTERED',real_causal_evaluation_status='NOT_IMPLEMENTED_SOURCE_BLOCKED',
        continuous=dict(status='NOT_IMPLEMENTED',weight_domain='UNCOUNTABLE',unsearched_regions='UNKNOWN',global_optimality_proven=False),
        authority=dict.fromkeys(AUTHORITY,False))
    result['competition_id'] = _digest(result)
    return deepcopy(result)


def _validate_competition(competition):
    _require(type(competition) is dict, 'Competition dict required')
    raw_covariance = {key:value for key,value in competition['synthetic_covariance'].items()
                      if key != 'positive_semidefinite_check'}
    rebuilt = prepare_synthetic_joint_competition(prepared_problem=competition['A_problem'],synthetic_covariance=raw_covariance)
    _require(_digest(competition) == _digest(rebuilt), 'Competition drift or unrecognized fields')
    return rebuilt


def _classify(competition, rank):
    core = competition['core']
    caps, buys = core['caps'],core['buys']
    digits, residue = {},rank
    for sid in reversed(buys):
        if caps is None:
            digits[sid] = 0
        else:
            residue,digits[sid] = divmod(residue,caps[sid]+1)
    q = {sid:Fraction(value) for sid,value in core['quantities'].items()}
    prices = {sid:Fraction(value) for sid,value in core['prices'].items()}
    final = {sid:q.get(sid,0)+core['lots'][sid]*digits.get(sid,0) for sid in core['identities']}
    positive = {sid:value for sid,value in final.items() if value > 0}
    gross = sum((prices[sid]*core['lots'][sid]*digits[sid] for sid in buys),Fraction(0))
    fee = gross*(Fraction(core['fee_factor'])-1)
    remaining = Fraction(core['cash'])-gross-fee
    invested = sum((prices[sid]*value for sid,value in positive.items()),Fraction(0))
    _require(invested+remaining == Fraction(core['pretrade_wealth'])-fee, 'Internal wealth conservation failure')
    weights = {sid:prices[sid]*value/invested for sid,value in positive.items()} if invested else {}
    unique = len({core['identities'][sid]['issuer_id'] for sid in positive}) == len(positive)
    risk = {key:Fraction(value) for key,value in core['risk'].items()}
    chains, checks, effective_n = {},dict.fromkeys(CHECK_KEYS,None),None
    if weights:
        for sid,weight in weights.items():
            chain = core['identities'][sid]['risk_chain']
            chains[chain] = chains.get(chain,Fraction(0))+weight
        ordered = sorted(weights.values(),reverse=True)
        effective_n = 1/sum(weight*weight for weight in weights.values())
        checks = dict(zip(CHECK_KEYS,(
            ordered[0] <= risk['max_single_weight']+TOLERANCE,
            ordered[-1] >= risk['min_single_weight']-TOLERANCE,
            sum(ordered[:3]) <= risk['top_weight_cap']+TOLERANCE,
            effective_n >= risk['minimum_effective_n_ratio']*len(weights)-TOLERANCE,
            max(chains.values()) <= risk['risk_chain_top1_cap']+TOLERANCE)))
    cash_passed = remaining >= Fraction(core['buffer'])
    category = ('ISSUER_CONFLICT' if not unique else 'CASH_REJECTED' if not cash_passed else
                'ALL_CASH_CONTROL' if not weights else 'RISK_REJECTED' if not all(checks.values()) else 'FEASIBLE')
    objectives = None
    if category == 'FEASIBLE':
        covariance = competition['synthetic_covariance']
        ids = covariance['security_ids']
        variance = sum((weights.get(sid,0)*Fraction(covariance['values'][i][j])*weights.get(other,0)
            for i,sid in enumerate(ids) for j,other in enumerate(ids)),Fraction(0))
        _require(variance >= 0, 'Internal PSD scoring failure')
        objectives = [str(variance),str(gross/Fraction(core['pretrade_wealth']))]
    return dict(rank=rank,action_id=_digest(dict(competition_id=competition['competition_id'],rank=rank)),
        buy_lots={sid:digits[sid] for sid in buys},final_quantities={sid:str(value) for sid,value in sorted(final.items())},
        positive_holding_count=len(positive),issuer_unique=unique,actual_buy_notional=str(gross),actual_fee=str(fee),
        remaining_cash=str(remaining),final_stock_value=str(invested),weights={sid:str(value) for sid,value in sorted(weights.items())},
        risk_checks=checks,effective_n=None if effective_n is None else str(effective_n),cash_passed=cash_passed,
        category=category,training_objectives=objectives,synthetic_only=True)


def iter_synthetic_quantity_candidates(*, competition, start_rank=0):
    """Lazy complete raw box; caller budget does not truncate declared domain."""
    checked = _validate_competition(competition)
    _integer(start_rank,'start_rank')
    _require(start_rank <= checked['core']['raw_box_count'], 'start_rank outside full raw box')
    for rank in range(start_rank,checked['core']['raw_box_count']):
        yield _classify(checked,rank)


def _dominates(first, second):
    left,right = [Fraction(x) for x in first['training_objectives']],[Fraction(x) for x in second['training_objectives']]
    return all(a<=b for a,b in zip(left,right)) and any(a<b for a,b in zip(left,right))


def _add_frontier(frontier, record):
    if any(_dominates(old,record) for old in frontier):
        return frontier
    return [old for old in frontier if not _dominates(record,old)]+[deepcopy(record)]


def _initial_state(competition):
    return dict(schema=CHECKPOINT_SCHEMA,competition_id=competition['competition_id'],cursor=0,
        prefix_hash=_digest(dict(competition_id=competition['competition_id'],prefix='EMPTY')),
        issuer_conflict_processed=0,all_cash_processed=0,classified_records=[],
        per_k={k:dict(processed=0,cash_rejected=0,risk_rejected=0,feasible=0,frontier=[])
               for k in competition['core']['per_k_box_counts']})


def _scan(competition, state, stop_rank, retain_records):
    records = []
    for rank in range(state['cursor'],stop_rank):
        record = _classify(competition,rank)
        if record['category'] == 'ISSUER_CONFLICT':
            state['issuer_conflict_processed'] += 1
        elif record['positive_holding_count'] == 0:
            state['all_cash_processed'] += 1
        else:
            row = state['per_k'][str(record['positive_holding_count'])]
            row['processed'] += 1
            if record['category'] == 'CASH_REJECTED':
                row['cash_rejected'] += 1
            elif record['category'] == 'RISK_REJECTED':
                row['risk_rejected'] += 1
            elif record['category'] == 'FEASIBLE':
                row['feasible'] += 1
                row['frontier'] = _add_frontier(row['frontier'],record)
            else:
                raise ValueError('Unrecognized positive-stock classification')
        state['prefix_hash'] = _digest(dict(previous=state['prefix_hash'],record=record))
        state['cursor'] = rank+1
        # Keep dominated/infeasible facts too. Training Pareto is a view, never
        # deletion of an action from a future CAGR/DD evaluation domain.
        state['classified_records'].append(deepcopy(record))
        if retain_records:
            records.append(record)
    return records


def run_synthetic_joint_frontier(*, competition, work_budget, resume_state=None, expected_resume_sha256=None):
    """Process a new prefix chunk; validate every resumed prefix independently.

    Prefix replay is intentionally visible overhead of this small synthetic
    implementation, not a scalable authenticated real-search checkpoint system.
    """
    checked = _validate_competition(competition)
    _integer(work_budget,'work_budget')
    total = checked['core']['raw_box_count']
    replayed = 0
    if resume_state is None:
        _require(expected_resume_sha256 is None, 'Resume hash without checkpoint')
        state = _initial_state(checked)
    else:
        _require(type(resume_state) is dict, 'Checkpoint dict required')
        _require(type(expected_resume_sha256) is str and re.fullmatch('[0-9a-f]{64}',expected_resume_sha256)
                 is not None and _digest(resume_state) == expected_resume_sha256, 'Resume checkpoint digest drift')
        _require(resume_state.get('competition_id') == checked['competition_id'], 'Resume competition binding mismatch')
        cursor = _integer(resume_state.get('cursor'),'resume cursor')
        _require(cursor <= total, 'Resume cursor outside full domain')
        state = _initial_state(checked)
        _scan(checked,state,cursor,False)
        _require(_digest(state) == _digest(resume_state), 'Resume prefix replay mismatch; false progress/frontier/counts')
        replayed = cursor
    old_cursor = state['cursor']
    records = _scan(checked,state,min(total,old_cursor+work_budget),True)
    complete = state['cursor'] == total
    per_k, overall = [],[]
    for k,denominator in checked['core']['per_k_box_counts'].items():
        row = state['per_k'][k]
        _require(row['processed'] <= denominator, 'Internal per-k coverage overflow')
        _require(row['processed'] == row['cash_rejected']+row['risk_rejected']+row['feasible'], 'Internal per-k coverage mismatch')
        for record in row['frontier']:
            overall = _add_frontier(overall,record)
        per_k.append(dict(holding_count=int(k),issuer_compatible_quantity_box_count=str(denominator),
            processed_quantity_count=str(row['processed']),unsearched_quantity_count=str(denominator-row['processed']),
            cash_rejected_count=str(row['cash_rejected']),risk_rejected_count=str(row['risk_rejected']),
            feasible_evaluated_count=str(row['feasible']),
            feasible_full_domain_count_or_null=str(row['feasible']) if complete else None,
            training_frontier=deepcopy(row['frontier']),frontier_scope='FULL_SYNTHETIC_INTEGER_DOMAIN' if complete else 'EVALUATED_PREFIX_ONLY',
            continuous_unsearched_regions='UNKNOWN',economic_CAGR_DD_frontier_status='NOT_EVALUATED'))
    compatible_processed = sum(row['processed'] for row in state['per_k'].values())
    _require(state['cursor'] == compatible_processed+state['issuer_conflict_processed']+state['all_cash_processed'], 'Internal raw coverage mismatch')
    zero_control = _classify(checked,0)
    return dict(schema='SYNTHETIC_JOINT_FRONTIER_RESULT_V1',specification=SPECIFICATION,
        competition_id=checked['competition_id'],status='COMPLETE_SYNTHETIC_INTEGER_DOMAIN' if complete else 'BUDGET_STOPPED',
        source_status='SYNTHETIC_UNBOUND_SOURCE_BLOCKED',authority=dict.fromkeys(AUTHORITY,False),
        continuous=deepcopy(checked['continuous']),real_objective_status='UNREGISTERED',
        real_followup_blockers=['REAL_SOURCE_ADAPTER_AND_FULL_PIT','REAL_OBJECTIVE_AND_CAUSAL_ACTION_RULE',
            'THIRTEEN_COHORT_ACTUAL_PRIOR_CASH_PATHS','DUAL_BENCHMARK_COMMON_BASIS','FOUR_LANE_ECONOMIC_FRONTIERS'],
        all_k_frontiers=per_k,overall_training_frontier=sorted(overall,key=lambda record:record['rank']),
        zero_buy_control=zero_control,all_cash_control=deepcopy(zero_control) if not checked['core']['quantities'] else None,
        processed_records=records,classified_records=deepcopy(state['classified_records']),
        coverage=dict(raw_quantity_box_count=str(total),
            A_raw_quantity_box_count_or_null=None if checked['core']['A_raw_box_count_or_null'] is None else str(checked['core']['A_raw_box_count_or_null']),
            processed_raw_quantity_count=str(state['cursor']),unsearched_raw_quantity_count=str(total-state['cursor']),
            issuer_incompatible_box_count=str(checked['core']['issuer_incompatible_box_count']),
            issuer_conflict_processed=str(state['issuer_conflict_processed']),all_cash_processed=str(state['all_cash_processed']),
            newly_classified_tuples=len(records),resume_prefix_validation_tuples=replayed,
            control_audit_classifications=1,total_classification_calls=len(records)+replayed+1,
            work_budget_scope='NEW_SEARCH_TUPLES_ONLY_EXCLUDES_REPLAY_AND_CONTROL_AUDIT',
            training_dominance_used_to_prune_economic_domain=False,economic_domain_evaluated=False,
            necessary_negative_cash_domain_empty=checked['core']['caps'] is None,
            quantity_count_semantics=('EMPTY_FEASIBLE_DOMAIN_CERTIFICATE_NOT_AN_A_RAW_BOX'
                if checked['core']['caps'] is None else 'COMPLETE_A_RAW_CARTESIAN_BOX'),
            complete_integer_classification=complete,continuous_complete=False),
        stop_certificate=dict(claim=('EMPTY_FEASIBLE_DOMAIN_NEGATIVE_CASH_BUDGET_CERTIFICATE'
                if checked['core']['caps'] is None else 'EXHAUSTIVE_SYNTHETIC_RAW_BOX_CLASSIFICATION'
                if complete else 'BUDGET_STOP_WITH_EXACT_RESIDUAL_PREFIX'),
            empty_domain_proof=(dict(left='0',comparison='>',right=checked['core']['budget'],
                reason='NONNEGATIVE_BUY_COST_EXCEEDS_NEGATIVE_AVAILABLE_BUDGET') if checked['core']['caps'] is None else None),
            domain_id=checked['competition_id'],next_rank=state['cursor'],total_ranks=str(total),
            prefix_hash=state['prefix_hash'],scope='TRAINING_VARIANCE_BUY_PARETO_ONLY_NOT_REAL_ECONOMIC_OR_ADMISSION'),
        resume_state=deepcopy(state),resume_sha256=_digest(state),current_account=None,current_new_money=None,plan_rows=[])
