"""One sealed new buy-vector evaluation; never search, fit or execute an account."""
import argparse
import builtins
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import types

SOURCE = Path(__file__).resolve()
ROOT = SOURCE.parents[1]
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT / 'data/cache/research/cash_topup_neighbor_evaluation_20261003_v1'
PREP_ROOT = ROOT / 'data/cache/research/cash_topup_neighbor_preparation_20261003_v1'
BOUND = {
    'preparation': (str(PREP_ROOT / 'preparation.json'), '04cf54101f56303cc656e60079f1434661845da6e13c6c7d23305f3e9f1dde2b'),
    'publication': (str(PREP_ROOT / 'publication.json'), 'dbe1e731c02293dab4a5cca4f0fa7fbf84367cd201dbf90b9e703cab1fd86b53'),
    'audit': (str(ROOT / 'data/cache/research/cash_topup_neighbor_preparation_independent_readback_20261003_v1/independent_readback.json'), 'c29c98c5c48d61e2533c7a587291932eda3b5776d81a9d0288a75a6b7d891ce8'),
}
PINS = {
    'evaluator': ('backtest/ndx_explicit_cash_plan_evaluation_research.py', 'bc98beb6afdf04110c61857aef4b573a3840811076d729d4efc022d9b6523191'),
    'kernel': ('backtest/ndx_conditional_new_cash_fork_research.py', '5bb17d621b42707cfe312676279d59b565c3e97900bf3bdd6f9335df65aa0c5f'),
    'preparation_reader': ('scripts/ndx_cash_topup_neighbor_preparation_independent_readback_20261003.py', '483a11cbb1037ec9c30ff01ded864e883c2570110b0fe03660d209b3d2fe2f76'),
    'original_score_semantics': ('scripts/ndx_old_holding_topup_research_20261002.py', '3898ab695053108742acc8e13d3fce7c81231f72d81d12c37156e07211c8723c'),
}
RULE = 'ALL_SAVED_FEASIBLE_SEEDS_SINGLE_PM1_AND_PAIR_PM1_NONNEGATIVE_SAVED_CAPS_V1'
FLAGS = dict.fromkeys(('old_search_reexecuted', 'old_audit_reexecuted', 'fit_performed', 'account_executed',
    'orders_executed', 'point_in_time_verified', 'promotion_allowed', 'full_transitive_source_closure_reverified',
    'full_integer_domain_exhausted', 'economic_winner_selected', 'target_weights_changed', 'holdings_sold',
    'issuer_eligibility_verified', 'new_dated_77_pool_used', 'retry_allowed'), False)
PREP_FLAGS = ('risk_evaluated', 'financial_feasibility_evaluated', 'fit_performed', 'account_executed',
    'orders_executed', 'point_in_time_verified', 'promotion_allowed')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def enc(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def digest(value):
    return sha(enc(value))


def exact(left, right, message):
    require(enc(left) == enc(right), message)


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, 'Exact nonnegative integer required')
    return value


def hash_string(value):
    require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'Explicit SHA256 required')
    return value


def decode(blob):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'Duplicate JSON key')
            out[key] = value
        return out
    def invalid(value):
        raise ValueError('Nonfinite JSON')
    return json.loads(blob, object_pairs_hook=pairs, parse_constant=invalid)


def reference(path, expected):
    return {'path': str(path), 'sha256': hash_string(expected)}


def load_reference(ref):
    require(set(ref) == {'path', 'sha256'}, 'Exact file reference')
    blob = Path(ref['path']).read_bytes()
    require(sha(blob) == hash_string(ref['sha256']), 'Consumed source hash mismatch')
    return blob


def source_map():
    return {str(SOURCE): LOADED, **{str(ROOT / path): h for path, h in PINS.values()}}


def guard(sources):
    fixed = source_map()
    require(all(path not in sources or sources[path] == h for path, h in fixed.items()), 'Source conflict')
    for path, h in {**sources, **fixed}.items():
        require(sha(Path(path).read_bytes()) == hash_string(h), 'Source drift')


def fresh_evaluator():
    """Private module objects; no sys.modules replacement or old producer import."""
    modules = {}
    for role in ('kernel', 'evaluator'):
        path, h = PINS[role]
        path = ROOT / path
        blob = path.read_bytes()
        require(sha(blob) == h, 'Fresh numerical module hash')
        module = types.ModuleType('_isolated_cash_' + role)
        module.__file__ = str(path)
        if role == 'evaluator':
            importer = builtins.__import__
            def isolated_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name == 'backtest' and fromlist == ('ndx_conditional_new_cash_fork_research',) and level == 0:
                    return types.SimpleNamespace(ndx_conditional_new_cash_fork_research=modules['kernel'])
                return importer(name, globals, locals, fromlist, level)
            module.__dict__['__builtins__'] = dict(vars(builtins), __import__=isolated_import)
        exec(compile(blob, str(path), 'exec'), module.__dict__)
        modules[role] = module
    return modules['evaluator'].evaluate_explicit_plans


def load_common():
    # All pending pins reject before reading any input or loading numerical code.
    refs = {key: reference(path, h) for key, (path, h) in BOUND.items()}
    sources = source_map()
    docs = {}
    for key, ref in refs.items():
        docs[key] = decode(load_reference(ref))
        sources[ref['path']] = ref['sha256']
    p, pub, audit = (docs[key] for key in ('preparation', 'publication', 'audit'))
    require(p['schema'] == 'CASH_TOPUP_NEIGHBOR_PREPARATION_V1' and len(p['rows']) == 40, 'Preparation scope')
    require(integer(p['scenario_count']) == 40 and integer(p['task_evaluation_count']) == 0 and p['declared_local_neighborhood_complete'] is True, 'Unevaluated complete preparation')
    require(pub['schema'] == 'CASH_TOPUP_NEIGHBOR_PREPARATION_PUBLICATION_V1' and pub['status'] == 'PUBLISHED_UNEVALUATED_CANDIDATES_ONLY', 'Publication status')
    exact(pub['preparation_reference'], refs['preparation'], 'Preparation publication link')
    exact(pub['source_hashes'], p['source_hashes'], 'Preparation source map retained')
    require(audit['schema'] == 'CASH_TOPUP_NEIGHBOR_PREPARATION_INDEPENDENT_READBACK_V1' and audit['status'] == 'PASS', 'Preparation independent readback')
    exact(audit['preparation_reference'], refs['preparation'], 'Audit preparation link')
    exact(audit['publication_reference'], refs['publication'], 'Audit publication link')
    require(audit['reader_sha256'] == PINS['preparation_reader'][1], 'Independent reader source')
    for doc in (p, pub):
        require(all(doc[k] is False for k in PREP_FLAGS), 'Parent authority')
    require(not (PREP_ROOT / 'failure.json').exists(), 'Failed preparation')
    seen = set()
    for i, row in enumerate(p['rows']):
        require(row['scenario_id'] not in seen, 'Duplicate scenario')
        seen.add(row['scenario_id'])
        require(Path(row['contract_reference']['path']) == PREP_ROOT / f'scenario-{i:02d}' / 'contract.json', 'Fixed contract path')
        next_start = 0
        for j, shard in enumerate(row['shards']):
            require(Path(shard['path']) == PREP_ROOT / f'scenario-{i:02d}' / f'tasks-{j:05d}.jsonl', 'Fixed shard path')
            require(integer(shard['start']) == next_start and 1 <= integer(shard['stop']) - next_start <= 1000, 'Contiguous stable shard ranges')
            next_start = shard['stop']
        require(next_start == integer(row['statistics']['new_candidate_count']), 'Full shard denominator')
    require(sum(r['statistics']['new_candidate_count'] for r in p['rows']) == integer(p['statistics']['new_candidate_count']), 'Total new denominator')
    guard(sources)
    common = dict(references=refs, preparation=p, source_hashes=sources)
    common['metadata_sha256'] = digest({k: common[k] for k in ('references', 'preparation', 'source_hashes')})
    return common


def validate_task(prepared, task, expected_task_id):
    c = prepared['contract']
    require(digest(c) == prepared['contract_sha256'], 'Full contract digest')
    require(c['schema'] == 'CONDITIONAL_TOPUP_NEIGHBOR_SCENARIO_CONTRACT_V1' and c['rule'] == RULE, 'Declared neighborhood contract')
    require(task['task_id'] == hash_string(expected_task_id) == digest(task['identity']), 'Full new task identity')
    buy = task['identity']['buy_shares']
    exact(task['identity'], dict(schema='CONDITIONAL_TOPUP_NEIGHBOR_TASK_IDENTITY_V1', rule=RULE,
        scenario_contract_sha256=prepared['contract_sha256'], buy_shares=buy), 'Complete identity fields')
    require(task['scenario_id'] == c['scenario_id'] and task['evaluation_status'] == 'NOT_EVALUATED', 'Only new same-scenario task')
    integer(task['scenario_candidate_ordinal'])
    for obj in (c, task):
        require(all(obj[k] is False for k in PREP_FLAGS), 'Task authority')
    row = c['original_input_row']
    require(row['scenario_id'] == c['scenario_id'] and row['branch_role'] == 'MAIN_LANE' and row['target_l1_applicable'] is True and row['zero_buy_only'] is False, 'Original main-lane contract')
    require(all(row[k] is False for k in ('point_in_time_verified', 'promotion_allowed', 'orders_executed', 'fork_executable')), 'Original conditional authority')
    ids, caps = c['conditional_research_buy_ids'], c['saved_buy_limits']
    require(ids == sorted(set(ids)) and set(buy) == set(caps) == set(ids), 'Whole buy vector including zeros')
    require(set(ids) == set(row['target_weights']) | {sid for sid, q in row['holdings'].items() if integer(q) > 0}, 'All old positive holdings and original targets')
    for sid in ids:
        require(integer(buy[sid]) <= integer(caps[sid]), 'Saved cap cannot widen')
    points = c['old_evaluated_points']
    require(all(buy != p['buy_shares'] for p in points), 'Old evaluated point must never be repeated')
    origin = task['first_origin']
    index = integer(origin['seed_candidate_index'])
    require(index < len(points) and points[index]['candidate_index'] == index and points[index]['saved_feasible'] is True, 'Saved feasible seed required')
    require(index in c['all_feasible_seed_indexes'], 'Seed membership')
    exact(origin['seed_reference'], points[index]['reference'], 'Exact seed evidence pointer')
    moves = origin['moves']
    require(type(moves) is list and len(moves) in (1, 2) and [m['security_id'] for m in moves] == sorted({m['security_id'] for m in moves}), 'One or two distinct sorted coordinates')
    reconstructed = deepcopy(points[index]['buy_shares'])
    for move in moves:
        require(set(move) == {'security_id', 'delta'} and move['security_id'] in ids and type(move['delta']) is int and move['delta'] in (-1, 1), 'Signed unit move only')
        reconstructed[move['security_id']] += move['delta']
    exact(reconstructed, buy, 'Task is stated seed neighborhood')
    return row


def load_task(common, scenario_index, shard_index, task_index, expected_task_id):
    hardrefs = {key: reference(path, h) for key, (path, h) in BOUND.items()}
    exact(common['references'], hardrefs, 'Cached references must equal fixed external anchors')
    exact(common['source_hashes'], {**source_map(), **{r['path']: r['sha256'] for r in hardrefs.values()}}, 'Independent cached source base')
    require(digest(common['preparation']) == hardrefs['preparation']['sha256'], 'Cached canonical preparation must equal hard sealed bytes')
    require(common['metadata_sha256'] == digest({k: common[k] for k in ('references', 'preparation', 'source_hashes')}), 'Cached metadata mutation')
    guard(common['source_hashes'])
    rows = common['preparation']['rows']
    require(integer(scenario_index) < len(rows), 'Scenario index')
    row = rows[scenario_index]
    require(integer(shard_index) < len(row['shards']), 'Shard index')
    shard = row['shards'][shard_index]
    prepared = decode(load_reference(row['contract_reference']))
    shardref = reference(shard['path'], shard['sha256'])
    tasks = [decode(line) for line in load_reference(shardref).splitlines()]
    require(len(tasks) == shard['stop'] - shard['start'] and integer(task_index) < len(tasks), 'Complete shard and local index')
    require([integer(t['scenario_candidate_ordinal']) for t in tasks] == list(range(shard['start'], shard['stop'])), 'Shard ordinal sequence')
    require(len({t['task_id'] for t in tasks}) == len(tasks), 'Unique shard tasks')
    task = tasks[task_index]
    require(prepared['contract_sha256'] == row['contract_sha256'] and task['scenario_id'] == row['scenario_id'], 'Selected preparation row')
    validate_task(prepared, task, expected_task_id)
    sources = dict(common['source_hashes'])
    for ref in (row['contract_reference'], shardref):
        require(ref['path'] not in sources or sources[ref['path']] == ref['sha256'], 'Task source conflict')
        sources[ref['path']] = ref['sha256']
    return dict(prepared=prepared, task=task, contract_reference=row['contract_reference'],
        task_reference=dict(shardref, jsonl_line_index=task_index, scenario_candidate_ordinal=task['scenario_candidate_ordinal']), source_hashes=sources)


def evaluation_arguments(prepared, task):
    row = validate_task(prepared, task, task['task_id'])
    c = prepared['contract']
    inputs = {key: deepcopy(row[key]) for key in ('cash_event', 'starting_cash_usd', 'holdings', 'execution_prices',
        'risk_parameters', 'transaction_cost_bps', 'minimum_cash_buffer_usd')}
    inputs['securities'] = {sid: {k: v[k] for k in ('issuer_id', 'risk_chain')} for sid, v in row['securities'].items()}
    inputs.update(branches=[dict(branch_id=row['scenario_id'], buy_limits=deepcopy(c['saved_buy_limits']))], max_evaluations=1)
    return dict(evaluation_inputs=inputs, plans_by_branch={row['scenario_id']: [deepcopy(task['identity']['buy_shares'])]})


def inspect_return(prepared, task, result):
    require(result['schema'] == 'EXPLICIT_BUY_ONLY_CASH_PLAN_EVALUATION_V1', 'Explicit evaluator schema')
    for key, value in (('evaluated_count', 1), ('unevaluated_supplied_plan_count', 0), ('kernel_validation_call_count', 1), ('kernel_cartesian_search_evaluation_count', 0)):
        require(integer(result[key]) == value, 'Single explicit call counts')
    require(all(result[k] is False for k in ('orders_executed', 'point_in_time_verified', 'promotion_allowed', 'global_optimality_claimed')), 'Numerical result authority')
    branches = result['branches']
    require(len(branches) == 1 and branches[0]['branch_id'] == task['scenario_id'] and len(branches[0]['evaluated_plans']) == 1, 'Exactly one returned plan')
    plan = branches[0]['evaluated_plans'][0]
    exact(plan['buy_shares'], task['identity']['buy_shares'], 'Returned buy vector unchanged')
    require(type(plan['feasible']) is bool, 'Exact feasibility flag')
    row = prepared['contract']['original_input_row']
    score = None
    if plan['feasible']:
        total_weight = sum((Fraction(v) for v in row['target_weights'].values()), Fraction(0))
        require(total_weight > 0, 'Positive original target sum')
        target = {s: Fraction(v) / total_weight for s, v in row['target_weights'].items()}
        values = {s: q * Fraction(row['execution_prices'][s]) for s, q in plan['proposed_holdings'].items()}
        total = sum(values.values(), Fraction(0))
        require(total > 0, 'Feasible stock denominator')
        distance = sum((abs(values.get(s, 0) / total - target.get(s, 0)) for s in set(values) | set(target)), Fraction(0))
        def ratio(v):
            return {'numerator': v.numerator, 'denominator': v.denominator}
        score = {'distance': ratio(distance), 'fees_usd': ratio(Fraction(plan['fees_usd']))}
    return {'outcome': 'FEASIBLE' if plan['feasible'] else 'INFEASIBLE', 'original_target_stock_weight_l1': score,
        'score_absence_reason': None if score is not None else 'ORIGINAL_POLICY_SCORES_ONLY_FEASIBLE_PLANS'}


def save(path, value):
    blob = enc(value)
    with path.open('xb') as stream:
        stream.write(blob); stream.flush(); os.fsync(stream.fileno())
    require(path.read_bytes() == blob, 'Durable output bytes')
    return reference(path, sha(blob))


def run(scenario_index, shard_index, task_index, *, expected_task_id, common=None, execute=False):
    require(execute is True, 'Explicit single evaluation opt-in required')
    directory = OUTPUT / hash_string(expected_task_id)
    require(not directory.exists(), 'Existing attempt: do not retry')
    common = load_common() if common is None else common
    state = load_task(common, scenario_index, shard_index, task_index, expected_task_id)
    arguments = evaluation_arguments(state['prepared'], state['task'])
    sources = state['source_hashes']; guard(sources)
    evaluate = fresh_evaluator()  # Never accept a caller-supplied/cached callable.
    identity = dict(schema='CASH_TOPUP_SINGLE_EVALUATION_IDENTITY_V1', prepared_task=state['task']['identity'],
        task_reference=state['task_reference'], contract_reference=state['contract_reference'],
        preparation_references=common['references'], numerical_sources={k: reference(ROOT / p, h) for k, (p, h) in PINS.items() if k in ('kernel', 'evaluator', 'original_score_semantics')})
    directory.mkdir(parents=True, exist_ok=False)
    try:
        started = save(directory / 'started.json', dict(schema='CASH_TOPUP_SINGLE_EVALUATION_STARTED_V1', task_id=expected_task_id,
            evaluation_identity=identity, evaluation_identity_sha256=digest(identity), original_contract=state['prepared'], task=state['task'],
            evaluation_arguments=arguments, source_hashes=sources, **FLAGS))
        result, error = None, None
        try:
            result = evaluate(**arguments)
        except Exception as failure:
            error = dict(type=type(failure).__name__, message=str(failure))
        raw = save(directory / 'raw.json', dict(schema='CASH_TOPUP_SINGLE_EVALUATION_RAW_V1', task_id=expected_task_id,
            started_reference=started, explicit_evaluator_call_attempt_count=1, returned_evaluation_count=int(error is None),
            result=result, error=error, source_hashes=sources, **FLAGS))
        validation_error = None
        detail = dict(outcome='EVALUATION_EXCEPTION', original_target_stock_weight_l1=None, score_absence_reason='NO_RETURNED_EVALUATION')
        try:
            guard(sources)
            if error is None:
                detail = inspect_return(state['prepared'], state['task'], result)
        except Exception as failure:
            validation_error = dict(type=type(failure).__name__, message=str(failure))
            detail = dict(outcome='VALIDATION_FAILURE', original_target_stock_weight_l1=None, score_absence_reason='UNACCEPTED_RETURNED_EVALUATION')
        out = save(directory / 'postcheck.json', dict(schema='CASH_TOPUP_SINGLE_EVALUATION_POSTCHECK_V1', task_id=expected_task_id,
            started_reference=started, raw_reference=raw, **detail, evaluation_error=error, validation_error=validation_error,
            status='ACCEPTED_SINGLE_PLAN_DIAGNOSTIC' if detail['outcome'] in ('FEASIBLE', 'INFEASIBLE') else 'TECHNICAL_FAILURE_NOT_INFEASIBILITY',
            source_hashes=sources, **FLAGS))
        guard(sources)
        for ref in (started, raw, out):
            load_reference(ref)
        require({p.name for p in directory.iterdir()} == {'started.json', 'raw.json', 'postcheck.json'}, 'Exact final attempt directory')
        return out
    except Exception as failure:
        if not (directory / 'failure.json').exists():
            save(directory / 'failure.json', dict(status='FAILED_ATTEMPT_DO_NOT_RETRY', error_type=type(failure).__name__, error=str(failure), **FLAGS))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for key in ('scenario-index', 'shard-index', 'task-index'):
        parser.add_argument('--' + key, type=int, required=True)
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.scenario_index, args.shard_index, args.task_index, expected_task_id=args.task_id, execute=args.execute)))
