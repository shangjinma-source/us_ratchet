"""Exact rank lower bound for four-stock empty-holding cash scenarios; no search."""
from fractions import Fraction
from math import prod
from pathlib import Path
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BASE = ROOT / 'data/cache/research'
OUTPUT = BASE / 'cash_prefix_coverage_precheck_20261002_v1'
INPUTS = {
    'inventory': ('conditional_new_cash_inventory_20260925_v2/inventory.json', 'f8b88fc72c6a3906440d4ddc83b5614e2a0a009a8843603a6028b713f62cb626'),
    'scenarios': ('standard_cash_scenarios_20261002_v1/scenarios.json', '5100a90a6b862492fadd2bd38f6596195cb6aba9dc08c37cb25552728469c5bf')}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def first_all_positive_rank(caps):
    require(len(caps) == 4 and all(type(x) is int and x >= 1 for x in caps), 'Four positive integer caps required')
    return sum(prod(cap + 1 for cap in caps[index + 1:]) for index in range(4))


def publish():
    require(not OUTPUT.exists(), 'Fixed namespace exists; no overwrite')
    require(sha(SOURCE.read_bytes()) == LOADED_SHA, 'Loaded code changed')
    sources = {str(SOURCE): LOADED_SHA}
    documents = {}
    for role, (relative, expected) in INPUTS.items():
        path = BASE / relative
        raw = path.read_bytes()
        require(sha(raw) == expected, 'Source bytes changed')
        sources[str(path)] = expected
        documents[role] = json.loads(raw)
    rows = []
    for scenario in documents['scenarios']['rows']:
        if scenario['decision_date'] != '2023-03-31' or scenario['lane'].endswith('_CONTROL'):
            continue
        pointer = scenario['parent_row_reference']['json_pointer']
        require(scenario['parent_row_reference']['path'] == str(BASE / INPUTS['inventory'][0])
                and scenario['parent_row_reference']['sha256'] == INPUTS['inventory'][1], 'Parent reference changed')
        original = documents['inventory']['rows'][int(pointer.split('/')[-1])]
        require(original['baseline']['shares'] == {} and len(original['lane_target']['targets']) == 4, 'Expected empty baseline / four targets')
        require(all(original[key] == scenario[key] for key in ('lane', 'decision_date', 'execution_date')), 'Coordinate differs')
        prices = {}
        for security in original['securities']:
            marks = {Fraction(item['decimal_literal']) for item in security['execution_open_observations'] if item['currency'] == 'USD'}
            require(len(marks) == 1 and next(iter(marks)) > 0, 'Missing/conflicting positive USD mark')
            prices[security['security_id']] = next(iter(marks))
        require(set(prices) == set(original['lane_target']['targets']) and len(original['securities']) == 4, 'Target/price union changed')
        available = Fraction(str(original['baseline']['cash_usd'])) + Fraction(scenario['standardized_cash_injection_usd']) - 100
        caps = {sid: available // (price * Fraction(10010, 10000)) for sid, price in sorted(prices.items())}
        rank = first_all_positive_rank(list(caps.values()))
        rows.append({'scenario_id': scenario['scenario_id'], 'parent_row_pointer': pointer,
                     'independent_affordability_caps': caps, 'cartesian_count': prod(cap + 1 for cap in caps.values()),
                     'first_all_positive_rank_zero_based': rank, 'minimum_prefix_evaluations_to_visit': rank + 1,
                     'prefix_budget_example': 10000, 'prefix_can_reach_four_positive': rank < 10000,
                     'all_positive_is_sufficient_for_feasibility': False})
    require(len(rows) == 8, 'Expected eight first-period main-lane scenarios')
    require({row['scenario_id'] for row in rows} == {
        '|'.join((lane, '2023-03-31', '2023-04-03', amount))
        for lane in ('RETURN', 'BAD_TAIL', 'DRAWDOWN', 'LEGACY_TARGET_DISTANCE') for amount in ('1000', '10000')}, 'Exact eight scenario identities required')
    result = {'schema': 'CASH_PREFIX_COVERAGE_LOWER_BOUND_V1', 'source_hashes': sources, 'rows': rows,
              'assumed_fee_bps': '10', 'assumed_buffer_usd': '100',
              'domain_semantics': 'Zero-to-independent-affordability caps; sorted SID mixed radix, last SID fastest.',
              'proof': 'With positive stock equity and top-three weight cap 0.8+1e-9, fewer than four positive holdings cannot pass. Empty starting holdings and exactly four candidate SIDs therefore require all four buys positive.',
              'full_domain_searched': False, 'portfolio_infeasibility_claimed': False,
              'cash_fork_called': False, 'orders_executed': False, 'promotion_allowed': False}
    for path, expected in sources.items():
        require(sha(Path(path).read_bytes()) == expected, 'Source drift')
    OUTPUT.mkdir(parents=True, exist_ok=False)
    payload = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    path = OUTPUT / 'precheck.json'
    try:
        with path.open('xb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        for source, expected in sources.items():
            require(sha(Path(source).read_bytes()) == expected, 'Post-write source drift')
        require(path.read_bytes() == payload and {p.name for p in OUTPUT.iterdir()} == {'precheck.json'}, 'Readback failed')
    except Exception as error:
        with (OUTPUT / 'failure.json').open('xb') as stream:
            stream.write(json.dumps({'status': 'FAILED_DO_NOT_CONSUME', 'error': str(error)}).encode())
        raise
    return {'path': str(path), 'sha256': sha(payload), 'rank_bounds': [row['first_all_positive_rank_zero_based'] for row in rows]}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    if not parser.parse_args().publish:
        parser.error('Explicit --publish required')
    print(json.dumps(publish(), indent=2))
