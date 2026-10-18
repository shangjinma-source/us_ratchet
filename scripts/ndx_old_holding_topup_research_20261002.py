"""Source-bound conditional old-holding topups; original targets stay unchanged."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib
from itertools import product
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT / 'data/cache/research/old_holding_topup_research_20261002_v1'
PINS = {
    'inputs': ('data/cache/research/remaining_standard_cash_inputs_20261002_v1/inputs.json', '1143482cc4d610c6bd3976f846730b98ef1f11148e3b1f5eb008135a5faea1e5'),
    'publication': ('data/cache/research/remaining_standard_cash_inputs_20261002_v1/publication.json', '54d6f6d2771dc4caf85c07b2b8a28e33e1a50a3aace1df99308c012ae1ad5dc1'),
    'closure': ('backtest/ndx_min_weight_topup_closure_research.py', '53439e46d78ab51dbabb69a9b394a60960c794297711acbf6e171cf03b012858'),
    'evaluator': ('backtest/ndx_explicit_cash_plan_evaluation_research.py', 'bc98beb6afdf04110c61857aef4b573a3840811076d729d4efc022d9b6523191'),
    'kernel': ('backtest/ndx_conditional_new_cash_fork_research.py', '5bb17d621b42707cfe312676279d59b565c3e97900bf3bdd6f9335df65aa0c5f')}
MAX_SEEDS = 10000
MAX_ITERATIONS = 100
FRACTIONS = (Fraction(1,4), Fraction(1,2), Fraction(3,4), Fraction(1))
FLAGS = dict.fromkeys(('orders_executed', 'point_in_time_verified', 'promotion_allowed',
    'formal_eligibility_verified', 'fork_executable', 'global_optimality_claimed',
    'economic_winner_selected', 'time_series_return_evaluated', 'identity_gaps_resolved',
    'old_experiments_reexecuted', 'full_transitive_source_closure_reverified'), False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def ratio(value):
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def number(value):
    require(type(value) is str and 0 < len(value) <= 80, 'Saved decimal literal required')
    return Fraction(value)


def seed_domain(row):
    """Full bounded seed family, without evaluating any old or new plan."""
    prices = {sid: number(value) for sid,value in row['execution_prices'].items()}
    holdings = row['holdings']; targets = row['target_weights']; securities = row['securities']
    require(all(type(q) is int and q >= 0 for q in holdings.values()), 'Whole old shares required')
    old = {sid for sid,q in holdings.items() if q > 0}
    union = old | set(targets)
    require(set(prices) == set(securities) == union and all(value > 0 for value in prices.values()), 'Exact positive price and metadata union')
    require(1 <= len(targets) <= 8 and len(union) <= 256, 'Engineering input bound')
    require(row['allowed_buy_security_ids'] == sorted(targets), 'Original target permission differs')
    require(all(number(value) > 0 for value in targets.values()), 'Positive targets required')
    target_sum = sum(map(number, targets.values()), Fraction(0))
    normalized = {sid: number(value)/target_sum for sid,value in targets.items()}
    cash, injection, buffer, fees = [number(value) for value in (row['starting_cash_usd'], row['cash_event']['amount_usd'], row['minimum_cash_buffer_usd'], row['transaction_cost_bps'])]
    require(min(cash,injection,buffer,fees) >= 0, 'Nonnegative money required')
    gross_budget = max(Fraction(0), cash + injection - buffer)/(1+fees/10000)
    limits = {sid: gross_budget // prices[sid] for sid in sorted(union)}
    old_notionals = {sid: holdings.get(sid,0)*prices[sid] for sid in union}
    old_total = sum(old_notionals.values(), Fraction(0))
    new = sorted(set(targets)-old); supports = []; seeds = []
    for mask in range(2**len(new)):
        support = sorted(old | {sid for index,sid in enumerate(new) if mask & (1 << index)})
        issuers = {}
        for sid in support:
            issuers.setdefault(securities[sid]['issuer_id'], []).append(sid)
        conflicts = {issuer: ids for issuer,ids in issuers.items() if len(ids) > 1}
        record = {'support_index': mask, 'support_security_ids': support, 'issuer_conflicts': conflicts,
                  'structurally_excluded': bool(conflicts), 'seed_count': 0}
        supports.append(record)
        if conflicts:
            continue
        seen = set()
        def append(seed, origin):
            key = tuple(seed[sid] for sid in sorted(union))
            if key not in seen:
                seen.add(key); record['seed_count'] += 1
                seeds.append({'support_index': mask, 'support_security_ids': support,
                              'seed_buy_shares': seed, 'origin': origin})
        minimum = {sid: int(sid in support and sid not in old) for sid in sorted(union)}
        append(minimum, {'kind': 'MINIMUM_POSITIVE_SUPPORT'})
        active_targets = sorted(set(targets) & set(support))
        for fraction in FRACTIONS:
            directional_budget = fraction * gross_budget
            deficits = {sid: max(Fraction(0), normalized[sid]*(old_total+directional_budget)-old_notionals[sid]) for sid in active_targets}
            total_deficit = sum(deficits.values(), Fraction(0))
            scale = min(Fraction(1), directional_budget/total_deficit) if total_deficit else Fraction(0)
            choices = []
            for sid in active_targets:
                ideal = deficits[sid]*scale/prices[sid]
                floor = ideal.numerator // ideal.denominator
                ceiling = -(-ideal.numerator // ideal.denominator)
                choices.append(sorted({max(minimum[sid],floor), max(minimum[sid],ceiling)}))
            for amounts in product(*choices):
                seed = dict(minimum); seed.update(zip(active_targets,amounts))
                append(seed, {'kind':'ORIGINAL_TARGET_DIRECTION_FLOOR_CEIL', 'gross_budget_fraction':ratio(fraction)})
    return {'supports': supports, 'seeds': seeds, 'buy_limits': limits,
            'gross_budget_usd': ratio(gross_budget), 'conditional_research_buy_ids': sorted(union),
            'old_positive_ids': sorted(old), 'new_target_ids': new,
            'original_target_sum': ratio(target_sum), 'normalized_original_targets': {sid:ratio(value) for sid,value in normalized.items()}}


def research_row(row, close, evaluate):
    require(row['branch_role'] == 'MAIN_LANE' and row['zero_buy_only'] is False and row['target_l1_applicable'] is True, 'Explicit main-lane contract required')
    domain = seed_domain(row); records = []; plans = []; seen = {}
    for seed_index,seed in enumerate(domain['seeds'][:MAX_SEEDS]):
        result = close(holdings={sid:row['holdings'].get(sid,0) for sid in domain['conditional_research_buy_ids']},
            execution_prices=row['execution_prices'], support_security_ids=seed['support_security_ids'],
            seed_buy_shares=seed['seed_buy_shares'], buy_limits=domain['buy_limits'],
            min_single_weight=row['risk_parameters']['min_single_weight'],
            starting_cash_usd=row['starting_cash_usd'], cash_injection_usd=row['cash_event']['amount_usd'],
            transaction_cost_bps=row['transaction_cost_bps'], minimum_cash_buffer_usd=row['minimum_cash_buffer_usd'],
            max_iterations=MAX_ITERATIONS)
        record = {'seed_index': seed_index, 'closure': result, 'candidate_index': None}
        require(result['status'] in ('FIXED_POINT','PROVEN_INFEASIBLE_UPWARD_DOMAIN','UNKNOWN_ITERATION_BUDGET','UNSUPPORTED_EMPTY_SUPPORT'), 'Unknown closure status')
        if result['status'] == 'FIXED_POINT':
            plan = result['buy_shares']
            key = tuple(plan[sid] for sid in domain['conditional_research_buy_ids'])
            if key not in seen:
                seen[key] = len(plans); plans.append(plan)
            record['candidate_index'] = seen[key]
        records.append(record)
    evaluation_inputs = {key:deepcopy(row[key]) for key in ('cash_event','starting_cash_usd','holdings','execution_prices','risk_parameters','transaction_cost_bps','minimum_cash_buffer_usd')}
    evaluation_inputs['securities'] = {sid:{key:value[key] for key in ('issuer_id','risk_chain')} for sid,value in row['securities'].items()}
    evaluation_inputs.update(branches=[{'branch_id':row['scenario_id'],'buy_limits':domain['buy_limits']}], max_evaluations=MAX_SEEDS)
    evaluation = evaluate(evaluation_inputs=evaluation_inputs, plans_by_branch={row['scenario_id']:plans})
    require(evaluation['evaluated_count'] == len(plans) and evaluation['unevaluated_supplied_plan_count'] == 0, 'Candidate evaluation truncated')
    require(len(evaluation['branches']) == 1 and evaluation['branches'][0]['branch_id'] == row['scenario_id'], 'Evaluation branch mismatch')
    for flag in ('orders_executed','point_in_time_verified','promotion_allowed','global_optimality_claimed'):
        require(evaluation[flag] is False, 'Evaluation authority changed')
    target_sum = sum(map(number,row['target_weights'].values()),Fraction(0))
    normalized = {sid:number(value)/target_sum for sid,value in row['target_weights'].items()}
    scores = []
    for plan in evaluation['branches'][0]['evaluated_plans']:
        if plan['feasible']:
            values = {sid:q*number(row['execution_prices'][sid]) for sid,q in plan['proposed_holdings'].items()}
            total = sum(values.values(), Fraction(0))
            distance = sum((abs(values.get(sid,0)/total-normalized.get(sid,0)) for sid in set(values)|set(normalized)),Fraction(0))
            scores.append((distance,number(plan['fees_usd']),plan['supplied_plan_index']))
    winner = min(scores) if scores else None
    return {'scenario_id': row['scenario_id'], 'input_row':deepcopy(row), 'domain':domain,
        'closure_records':records, 'unprocessed_seed_count':max(0,len(domain['seeds'])-MAX_SEEDS),
        'evaluation':evaluation, 'feasible_scores':[{'distance':ratio(d),'fees_usd':ratio(f),'candidate_index':i} for d,f,i in scores],
        'selected_candidate_index':None if winner is None else winner[2],
        'original_allowed_buy_security_ids':deepcopy(row['allowed_buy_security_ids']),
        'new_buy_domain_is_research_assumption':True,
        'assumption':'ALLOW_ORIGINAL_TARGET_AND_ALL_POSITIVE_OLD_SIDS_FOR_ISOLATED_CONDITIONAL_RESEARCH_ONLY',
        'target_weights_changed':False, 'cash_must_be_fully_invested':False, **FLAGS}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(path, value):
    raw = (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    require(path.read_bytes() == raw, 'Output readback differs')
    return sha(raw)


def run():
    require(not OUTPUT.exists(), 'Fixed namespace exists; no retry')
    require(sha(SOURCE.read_bytes()) == LOADED_SHA, 'Loaded source changed')
    documents = {}; refs = {}; sources = {str(SOURCE):LOADED_SHA}
    for role,(relative,digest) in PINS.items():
        require(len(digest) == 64, 'Pending source pin')
        path = ROOT/relative; raw = path.read_bytes(); require(sha(raw) == digest, 'Source mismatch: '+role)
        refs[role] = {'path':str(path),'sha256':digest}; sources[str(path)] = digest
        if role in ('inputs','publication'):
            documents[role] = json.loads(raw)
    inputs = documents['inputs']; receipt = documents['publication']
    require({p.name for p in Path(refs['inputs']['path']).parent.iterdir()} == {'inputs.json','publication.json'}, 'Input namespace incomplete')
    require(inputs['schema'] == 'REMAINING_STANDARD_CASH_INPUTS_V1' and len(inputs['rows']) == 64, 'Remaining64 required')
    require(receipt['schema'] == 'REMAINING_STANDARD_CASH_INPUTS_PUBLICATION_V1' and receipt['input_reference'] == refs['inputs']
            and receipt['source_hashes'] == inputs['source_hashes'] and receipt['status'] == 'INPUTS_ONLY_NOT_EXECUTED', 'Input receipt differs')
    selected = [(i,row) for i,row in enumerate(inputs['rows']) if row['branch_role'] == 'MAIN_LANE']
    require(len(selected) == 40 and len({row['scenario_id'] for _,row in selected}) == 40, 'Exact40 required')
    clocks = (('2023-04-28','2023-05-01'),('2023-05-31','2023-06-01'),('2023-06-30','2023-07-03'),('2023-07-31','2023-08-01'),('2023-08-31','2023-09-01'))
    expected = {(lane,decision,execution,amount) for lane in ('RETURN','BAD_TAIL','DRAWDOWN','LEGACY_TARGET_DISTANCE') for decision,execution in clocks for amount in ('1000','10000')}
    require({(row['lane'],row['cash_event']['decision_date'],row['cash_event']['execution_date'],row['cash_event']['amount_usd']) for _,row in selected} == expected, 'Main scenario coordinates differ')
    for flag in ('cash_fork_called','point_in_time_verified','orders_executed','promotion_allowed'):
        require(inputs[flag] is False, 'Input authority changed')
    names = {'closure':'backtest.ndx_min_weight_topup_closure_research','evaluator':'backtest.ndx_explicit_cash_plan_evaluation_research','kernel':'backtest.ndx_conditional_new_cash_fork_research'}
    require(all(name not in sys.modules for name in names.values()), 'Fresh CLI required')
    modules = {role:importlib.import_module(name) for role,name in names.items()}
    require(all(Path(module.__file__).resolve() == Path(refs[role]['path']).resolve() for role,module in modules.items()), 'Imported path differs')
    def guard():
        require(all(sha(Path(path).read_bytes()) == digest for path,digest in sources.items()), 'Source drift')
    guard(); OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        write_new(OUTPUT/'started.json', {'source_hashes':sources,'started_at_utc':datetime.now(timezone.utc).isoformat(),'retry_allowed':False})
        rows = []
        for index,row in selected:
            result = research_row(row,modules['closure'].close_min_weight_topups,modules['evaluator'].evaluate_explicit_plans)
            result['input_reference'] = dict(refs['inputs'],json_pointer=f'/rows/{index}'); rows.append(result)
        result = {'schema':'OLD_HOLDING_TOPUP_CONDITIONAL_RESEARCH_V1','rows':rows,'source_hashes':sources,
            'input_references':refs,'parent_source_hashes_preserved_not_reaudited':inputs['source_hashes'],
            'seed_budget_per_scenario':MAX_SEEDS,'closure_iteration_budget':MAX_ITERATIONS,
            'scenario_count':40,'controls_evaluated':False,'historical_instant_plan_research_executed':True,
            'selection_order':['ORIGINAL_TARGET_STOCK_WEIGHT_L1','FEES','CANDIDATE_INDEX'],**FLAGS}
        guard(); digest = write_new(OUTPUT/'results.json',result); guard()
        publication = {'schema':'OLD_HOLDING_TOPUP_PUBLICATION_V1','result_reference':{'path':str(OUTPUT/'results.json'),'sha256':digest},
            'source_hashes':sources,'status':'PUBLISHED_CONDITIONAL_TOPUPS_ONLY',**FLAGS}
        receipt_sha = write_new(OUTPUT/'publication.json',publication); guard()
        require(sha((OUTPUT/'results.json').read_bytes()) == digest and sha((OUTPUT/'publication.json').read_bytes()) == receipt_sha
                and {p.name for p in OUTPUT.iterdir()} == {'started.json','results.json','publication.json'}, 'Final publication differs')
        return {'path':str(OUTPUT/'results.json'),'sha256':digest,'publication_sha256':receipt_sha}
    except Exception as error:
        write_new(OUTPUT/'failure.json',{'status':'FAILED_DO_NOT_CONSUME','error':str(error),'retry_allowed':False})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--execute',action='store_true')
    if not parser.parse_args().execute:
        parser.error('Explicit --execute required')
    print(json.dumps(run(),indent=2))
