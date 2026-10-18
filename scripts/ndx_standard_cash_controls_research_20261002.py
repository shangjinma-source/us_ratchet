"""Source-bound cash-retention and add-only migration controls; no return path."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT / 'data/cache/research/standard_cash_controls_research_20261002_v1'
SCHEMA = 'STANDARD_CASH_CONTROLS_RESEARCH_V1'
PINS = {
    'inputs': ('data/cache/research/remaining_standard_cash_inputs_20261002_v1/inputs.json', '1143482cc4d610c6bd3976f846730b98ef1f11148e3b1f5eb008135a5faea1e5'),
    'publication': ('data/cache/research/remaining_standard_cash_inputs_20261002_v1/publication.json', '54d6f6d2771dc4caf85c07b2b8a28e33e1a50a3aace1df99308c012ae1ad5dc1'),
    'generator': ('backtest/ndx_target_cash_neighbors_research.py', '77819f44ae8e7b73aa9683a544ff96a16d27b2194ca3d7fac4376e81dc0e4c68'),
    'evaluator': ('backtest/ndx_explicit_cash_plan_evaluation_research.py', 'bc98beb6afdf04110c61857aef4b573a3840811076d729d4efc022d9b6523191'),
    'kernel': ('backtest/ndx_conditional_new_cash_fork_research.py', '5bb17d621b42707cfe312676279d59b565c3e97900bf3bdd6f9335df65aa0c5f')}
CLOCKS = (('2023-03-31','2023-04-03'), ('2023-04-28','2023-05-01'),
          ('2023-05-31','2023-06-01'), ('2023-06-30','2023-07-03'),
          ('2023-07-31','2023-08-01'), ('2023-08-31','2023-09-01'))
ROLES = {'CASH_RETENTION_CONTROL': 'CASH_RETENTION_CONTROL', 'INCUMBENT_ADD_ONLY_CONTROL': 'MIGRATION_CONTROL'}
BUDGET = 1024  # Engineering budget, not a portfolio cardinality or eligible-pool rule.
FLAGS = dict.fromkeys(('time_series_return_evaluated','economic_winner_selected','global_optimality_claimed',
    'orders_executed','point_in_time_verified','promotion_allowed','account_path_replayed','repair_called',
    'evidence_gaps_resolved','real_benchmark_return_claimed','full_transitive_source_closure_reverified'), False)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def ratio(value):
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def research_row(row, generate, evaluate):
    role = ROLES.get(row['lane'])
    require(role is not None and row['branch_role'] == role, 'Explicit control role required')
    cash_only = role == 'CASH_RETENTION_CONTROL'
    require(row['zero_buy_only'] is cash_only and row['target_l1_applicable'] is (not cash_only), 'Control scope mismatch')
    require(row['allowed_buy_security_ids'] == sorted(row['target_weights']), 'Allowed buy SID/target mismatch')
    require(not row['target_weights'] if cash_only else 1 <= len(row['target_weights']) <= 8, 'Control target domain')
    inputs = {key: deepcopy(row[key]) for key in ('cash_event','starting_cash_usd','holdings','execution_prices',
        'risk_parameters','transaction_cost_bps','minimum_cash_buffer_usd')}
    inputs['securities'] = {sid: {key: item[key] for key in ('issuer_id','risk_chain')} for sid,item in row['securities'].items()}
    generated = None
    if cash_only:
        limits, plans = {}, [{}]
    else:
        cash, injection, buffer, fee = (Fraction(value) for value in (row['starting_cash_usd'],
            row['cash_event']['amount_usd'], row['minimum_cash_buffer_usd'], row['transaction_cost_bps']))
        gross = max(Fraction(0), cash + injection - buffer) / (1 + fee / 10000)
        limits = {sid: gross // Fraction(row['execution_prices'][sid]) for sid in sorted(row['target_weights'])}
        generated = generate(holdings=row['holdings'], starting_cash_usd=row['starting_cash_usd'],
            injection_usd=row['cash_event']['amount_usd'], execution_prices=row['execution_prices'],
            target_weights=row['target_weights'], buy_limits=limits, transaction_cost_bps=row['transaction_cost_bps'],
            minimum_cash_buffer_usd=row['minimum_cash_buffer_usd'], max_generated_plans=BUDGET)
        require(type(generated['ungenerated_count']) is int and generated['ungenerated_count'] == 0
                and 1 <= len(generated['plans']) <= 257, 'Complete bounded eight-target neighborhood required')
        plans = generated['plans']
    inputs.update(branches=[{'branch_id': row['scenario_id'], 'buy_limits': limits}], max_evaluations=BUDGET)
    evaluation = evaluate(evaluation_inputs=inputs, plans_by_branch={row['scenario_id']: plans})
    require(evaluation['schema'] == 'EXPLICIT_BUY_ONLY_CASH_PLAN_EVALUATION_V1'
            and type(evaluation['unevaluated_supplied_plan_count']) is int
            and evaluation['unevaluated_supplied_plan_count'] == 0
            and evaluation['evaluated_count'] == len(plans), 'Explicit evaluation incomplete')
    require(len(evaluation['branches']) == 1 and evaluation['branches'][0]['branch_id'] == row['scenario_id'], 'Evaluation branch mismatch')
    for key in ('orders_executed','point_in_time_verified','promotion_allowed','global_optimality_claimed'):
        require(evaluation[key] is False, 'Evaluation authority')
    scores = []
    if not cash_only:
        total_target = sum((Fraction(value) for value in row['target_weights'].values()), Fraction(0))
        require(total_target > 0, 'Positive target total required')
        normalized = {sid: Fraction(value) / total_target for sid,value in row['target_weights'].items()}
        for plan in evaluation['branches'][0]['evaluated_plans']:
            require(type(plan['feasible']) is bool, 'Exact feasibility boolean required')
            if not plan['feasible']:
                continue
            notionals = {sid: count * Fraction(row['execution_prices'][sid]) for sid,count in plan['proposed_holdings'].items()}
            total = sum(notionals.values(), Fraction(0))
            require(total > 0, 'Feasible equity must be positive')
            distance = sum((abs(notionals.get(sid, 0)/total - normalized.get(sid, 0))
                            for sid in set(notionals) | set(normalized)), Fraction(0))
            scores.append((distance, Fraction(plan['fees_usd']), plan['supplied_plan_index']))
    winner = min(scores) if scores else None
    return {'scenario_id': row['scenario_id'], 'branch_role': role, 'input_row': deepcopy(row),
        'buy_limits': limits, 'generator': generated, 'evaluation': evaluation,
        'feasible_scores': [{'target_l1_distance': ratio(distance), 'fee_usd': ratio(fee), 'supplied_plan_index': index}
                            for distance,fee,index in scores],
        'selected_supplied_plan_index': None if winner is None else winner[2],
        'cash_control_plan_index': 0 if cash_only else None,
        'selection_status': ('ZERO_BUY_CONTROL_RETAINED_WITH_ORIGINAL_RISK_RESULT' if cash_only else
            'NO_FEASIBLE_SUPPLIED_PLAN' if winner is None else 'BEST_TARGET_DISTANCE_AMONG_SUPPLIED_FEASIBLE_PLANS'),
        'scope': 'ZERO_BUY_CONTROL' if cash_only else 'ADD_ONLY_MIGRATION_ROUNDING_NEIGHBORHOOD_NOT_FULL_INTEGER_SPACE',
        'historical_instant_plan_research_executed': True, **FLAGS}


def control_rows(document):
    require(document['schema'] == 'REMAINING_STANDARD_CASH_INPUTS_V1' and type(document['scenario_count']) is int
            and document['scenario_count'] == 64 and len(document['rows']) == 64, 'Expected frozen remaining64 inputs')
    for flag in ('cash_fork_called','search_called','account_rerun','point_in_time_verified','promotion_allowed','orders_executed'):
        require(document[flag] is False, 'Input authority')
    selected = [(index,row) for index,row in enumerate(document['rows']) if row['lane'] in ROLES]
    expected = {(lane,decision,execution,amount) for lane in ROLES for decision,execution in CLOCKS for amount in ('1000','10000')}
    actual = [(row['lane'],row['cash_event']['decision_date'],row['cash_event']['execution_date'],row['cash_event']['amount_usd']) for _,row in selected]
    require(len(selected) == 24 and len(set(actual)) == 24 and set(actual) == expected, 'Exact six-clock two-amount 24 controls required')
    require(len({row['scenario_id'] for row in document['rows']}) == 64, 'Duplicate scenario ID')
    require(sum(row['branch_role'] == 'MAIN_LANE' for row in document['rows']) == 40, 'Main-lane denominator changed')
    return selected


def write_new(path, value):
    raw = encode(value)
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    require(path.read_bytes() == raw, 'Output bytes changed')
    return sha(raw)


def load_modules(refs):
    names = {'generator': 'backtest.ndx_target_cash_neighbors_research',
             'evaluator': 'backtest.ndx_explicit_cash_plan_evaluation_research',
             'kernel': 'backtest.ndx_conditional_new_cash_fork_research'}
    require(all(name not in sys.modules for name in names.values()), 'Fresh CLI required; cached research module present')
    modules = {role: importlib.import_module(name) for role,name in names.items()}
    require(all(Path(module.__file__).resolve() == Path(refs[role]['path']).resolve() for role,module in modules.items()), 'Imported module path differs')
    return modules['generator'].generate_target_neighbors, modules['evaluator'].evaluate_explicit_plans


def run():
    require(not OUTPUT.exists(), 'Fixed namespace exists; no retry/overwrite')
    require(sha(SOURCE.read_bytes()) == LOADED_SHA, 'Loaded source changed')
    require(all(type(pin) is str and len(pin) == 64 for _,pin in PINS.values()), 'Pending source anchors')
    sources = {str(SOURCE): LOADED_SHA}; refs = {}; raw = {}
    for role,(relative,expected) in PINS.items():
        path = ROOT / relative; raw[role] = path.read_bytes()
        require(sha(raw[role]) == expected, 'Source mismatch: '+role)
        sources[str(path)] = expected; refs[role] = {'path': str(path), 'sha256': expected}
    parent = Path(refs['inputs']['path']).parent
    require({p.name for p in parent.iterdir()} == {'inputs.json','publication.json'}, 'Input namespace incomplete')
    document, receipt = json.loads(raw['inputs']), json.loads(raw['publication'])
    require(receipt['schema'] == 'REMAINING_STANDARD_CASH_INPUTS_PUBLICATION_V1'
            and receipt['input_reference'] == refs['inputs'] and receipt['source_hashes'] == document['source_hashes']
            and receipt['status'] == 'INPUTS_ONLY_NOT_EXECUTED', 'Input publication mismatch')
    selected = control_rows(document)
    generate, evaluate = load_modules(refs)
    def guard():
        for path,digest in sources.items():
            require(sha(Path(path).read_bytes()) == digest, 'Source drift')
    guard(); OUTPUT.mkdir(parents=True, exist_ok=False)
    try:
        write_new(OUTPUT/'started.json', {'schema': 'STANDARD_CASH_CONTROLS_STARTED_V1',
            'started_at_utc': datetime.now(timezone.utc).isoformat(), 'source_hashes': sources,
            'planned_control_count': 24, 'retry_allowed': False})
        rows = []
        for index,row in selected:
            result = research_row(row, generate, evaluate)
            result['input_reference'] = dict(refs['inputs'], json_pointer=f'/rows/{index}')
            rows.append(result)
        guard()
        result = {'schema': SCHEMA, 'source_hashes': sources, 'input_references': refs,
            'parent_source_hashes_preserved_not_reaudited': document['source_hashes'],
            'parent_execution_contract': document['original_execution_contract'],
            'parent_execution_contract_reference': document['execution_contract_reference'],
            'rows': rows, 'control_count': 24, 'cash_retention_count': 12, 'migration_control_count': 12,
            'parent_scenario_count': 64, 'main_lane_count_not_evaluated': 40,
            'selection_order': ['LOWEST_EXACT_STOCK_WEIGHT_L1','LOWEST_EXACT_FEES','LOWEST_SUPPLIED_PLAN_INDEX'],
            'generator_budget_per_migration': BUDGET, 'evaluation_budget_per_scenario': BUDGET,
            'historical_instant_plan_research_executed': True, **FLAGS}
        digest = write_new(OUTPUT/'results.json', result); guard()
        publication = {'schema': 'STANDARD_CASH_CONTROLS_PUBLICATION_V1', 'status': 'PUBLISHED_CONDITIONAL_INSTANT_CONTROLS_ONLY',
            'result_reference': {'path': str(OUTPUT/'results.json'), 'sha256': digest}, 'source_hashes': sources, **FLAGS}
        publication_sha = write_new(OUTPUT/'publication.json', publication); guard()
        require(sha((OUTPUT/'results.json').read_bytes()) == digest
                and sha((OUTPUT/'publication.json').read_bytes()) == publication_sha
                and {p.name for p in OUTPUT.iterdir()} == {'started.json','results.json','publication.json'}, 'Final publication differs')
        return {'path': str(OUTPUT/'results.json'), 'sha256': digest, 'publication_sha256': publication_sha, 'control_count': 24}
    except Exception as error:
        write_new(OUTPUT/'failure.json', {'status': 'FAILED_DO_NOT_CONSUME', 'error': str(error), 'retry_allowed': False})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--execute', action='store_true')
    if not parser.parse_args().execute:
        parser.error('Explicit --execute required')
    print(json.dumps(run(), indent=2))
