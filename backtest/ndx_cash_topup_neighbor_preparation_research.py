"""Enumerate a declared local buy-quantity neighborhood, without evaluating it."""
from copy import deepcopy
import hashlib,itertools,json

RULE='ALL_SAVED_FEASIBLE_SEEDS_SINGLE_PM1_AND_PAIR_PM1_NONNEGATIVE_SAVED_CAPS_V1'
FLAGS=dict.fromkeys(('risk_evaluated','financial_feasibility_evaluated','issuer_eligibility_verified','old_evaluations_repeated','fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed','global_optimality_claimed','full_integer_domain_exhausted','target_weights_changed','holdings_sold','new_candidates_selected'),False)
def require(ok,message):
    if not ok:raise ValueError(message)
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(encode(v)).hexdigest()
def exact(a,b,message):require(encode(a)==encode(b),message)
def reference(r):require(type(r) is dict and set(r)=={'path','sha256','json_pointer'} and type(r['path']) is str and r['path'] and type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']) and type(r['json_pointer']) is str and r['json_pointer'].startswith('/rows/'),'Explicit source row pointer')

def prepare_scenario(*,input_row,previous_row,input_reference,previous_reference):
    reference(input_reference);reference(previous_reference);exact(previous_row['input_reference'],input_reference,'Same original input anchor');exact(previous_row['input_row'],input_row,'Entire source input unchanged')
    require(input_row['branch_role']=='MAIN_LANE' and previous_row['scenario_id']==input_row['scenario_id'],'Only explicit main scenario')
    for obj in (input_row,previous_row):
        for k in ('point_in_time_verified','promotion_allowed','fork_executable','orders_executed'):require(obj[k] is False,'Original authority')
    require(previous_row['target_weights_changed'] is False and previous_row['cash_must_be_fully_invested'] is False and previous_row['new_buy_domain_is_research_assumption'] is True,'Saved domain assumption')
    domain=previous_row['domain'];ids=domain['conditional_research_buy_ids'];require(type(ids) is list and ids==sorted(set(ids)) and ids,'Canonical full buy coordinates')
    union=set(input_row['target_weights'])|{s for s,q in input_row['holdings'].items() if q>0};require(set(ids)==union,'Original targets plus all positive old holdings')
    for s,q in input_row['holdings'].items():require(type(q) is int and q>=0,'Whole old shares')
    require(set(ids)<=set(input_row['securities']) and set(ids)<=set(input_row['execution_prices']),'Complete original metadata and prices')
    exact(previous_row['original_allowed_buy_security_ids'],input_row['allowed_buy_security_ids'],'Original permission list unchanged')
    caps=domain['buy_limits'];require(set(caps)==set(ids) and all(type(caps[s]) is int and caps[s]>=0 for s in ids),'Saved exact caps')
    branches=previous_row['evaluation']['branches'];require(type(branches) is list and len(branches)==1 and branches[0]['branch_id']==input_row['scenario_id'],'Single original evaluation branch')
    plans=branches[0]['evaluated_plans'];require(type(plans) is list,'Saved evaluated plans')
    require(type(branches[0]['evaluated_count']) is int and branches[0]['evaluated_count']==len(plans),'All evaluated points available')
    seeds=[];old=[];seen=set()
    for i,p in enumerate(plans):
        buy=p['buy_shares'];require(set(buy)==set(ids) and all(type(buy[s]) is int and 0<=buy[s]<=caps[s] for s in ids),'Complete original buy vector')
        require(type(p['feasible']) is bool,'Saved feasibility type');vector=tuple(buy[s] for s in ids);require(vector not in seen,'Unique original evaluated points');seen.add(vector)
        pointer=previous_reference['json_pointer']+'/evaluation/branches/0/evaluated_plans/'+str(i)
        item=dict(candidate_index=i,buy_shares=deepcopy(buy),saved_feasible=p['feasible'],reference=dict(previous_reference,json_pointer=pointer))
        old.append(item)
        if p['feasible']:seeds.append(item)
    expected=[i for i,p in enumerate(plans) if p['feasible']]
    require([s['candidate_index'] for s in seeds]==expected,'Every feasible seed, not only selected')
    identity=dict(schema='CONDITIONAL_TOPUP_NEIGHBOR_SCENARIO_CONTRACT_V1',rule=RULE,scenario_id=input_row['scenario_id'],input_reference=deepcopy(input_reference),previous_result_reference=deepcopy(previous_reference),original_input_row=deepcopy(input_row),conditional_research_buy_ids=deepcopy(ids),saved_buy_limits=deepcopy(caps),saved_domain_assumption=previous_row['assumption'],original_selected_candidate_index=previous_row['selected_candidate_index'],old_evaluated_points=old,all_feasible_seed_indexes=expected,move_order='SEED_ORIGINAL_INDEX;SINGLE_SORTED_SID_MINUS_PLUS;PAIR_LEXICOGRAPHIC_MINUS_PLUS_CARTESIAN',boundary_policy='REJECT_NEGATIVE_NEW_BUY_OR_ABOVE_SAVED_CAP_NO_REBUDGET',duplicate_policy='FIRST_SEED_AND_MOVE_RETAINED;COUNTS_PRESERVE_ALL_ATTEMPTS',raw_move_attempt_count=len(seeds)*2*len(ids)**2,whole_existing_holdings_preserved=True,economic_evaluation_identity_not_created=True,**FLAGS)
    return dict(contract=identity,contract_sha256=digest(identity))

def iter_neighbors(prepared,statistics):
    """One scenario's tuple set only; callers stream records into bounded shards."""
    c=prepared['contract'];require(digest(c)==prepared['contract_sha256'],'Contract changed');ids=c['conditional_research_buy_ids'];caps=c['saved_buy_limits'];points=c['old_evaluated_points'];old={tuple(p['buy_shares'][s] for s in ids) for p in points};seen=set()
    statistics.update(raw_move_attempt_count=c['raw_move_attempt_count'],processed_move_count=0,boundary_rejected_count=0,old_point_excluded_count=0,duplicate_new_point_count=0,new_candidate_count=0,unprocessed_move_count=c['raw_move_attempt_count'])
    for index in c['all_feasible_seed_indexes']:
        seed=points[index];require(seed['candidate_index']==index and seed['saved_feasible'] is True,'Original feasible seed index')
        for width in (1,2):
            for coordinates in itertools.combinations(range(len(ids)),width):
                for signs in itertools.product((-1,1),repeat=width):
                    statistics['processed_move_count']+=1;statistics['unprocessed_move_count']-=1;vector=[seed['buy_shares'][s] for s in ids]
                    for j,delta in zip(coordinates,signs):vector[j]+=delta
                    if any(v<0 or v>caps[s] for s,v in zip(ids,vector)):statistics['boundary_rejected_count']+=1;continue
                    key=tuple(vector)
                    if key in old:statistics['old_point_excluded_count']+=1;continue
                    if key in seen:statistics['duplicate_new_point_count']+=1;continue
                    seen.add(key);ordinal=statistics['new_candidate_count'];statistics['new_candidate_count']+=1;buy=dict(zip(ids,vector))
                    identity=dict(schema='CONDITIONAL_TOPUP_NEIGHBOR_TASK_IDENTITY_V1',rule=RULE,scenario_contract_sha256=prepared['contract_sha256'],buy_shares=buy)
                    yield dict(task_id=digest(identity),identity=identity,scenario_id=c['scenario_id'],scenario_candidate_ordinal=ordinal,first_origin=dict(seed_candidate_index=index,seed_reference=seed['reference'],moves=[dict(security_id=ids[j],delta=delta) for j,delta in zip(coordinates,signs)]),evaluation_status='NOT_EVALUATED',**FLAGS)
    require(statistics['processed_move_count']==c['raw_move_attempt_count'] and statistics['unprocessed_move_count']==0,'Declared neighborhood complete')
    require(sum(statistics[k] for k in ('boundary_rejected_count','old_point_excluded_count','duplicate_new_point_count','new_candidate_count'))==statistics['processed_move_count'],'Complete attempt partition')
