"""Freeze hypothetical cash scenarios against saved coordinates, without execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
BASE = ROOT / 'data/cache/research'
OUTPUT = BASE / 'standard_cash_scenarios_20261002_v1'
PARENT = BASE / 'conditional_new_cash_inventory_20260925_v2/inventory.json'
PARENT_SHA = 'f8b88fc72c6a3906440d4ddc83b5614e2a0a009a8843603a6028b713f62cb626'
PUBLICATION = PARENT.parent / 'publication.json'
PUBLICATION_SHA = 'e18344ff2535d4cea735d57e5d1c5cd99e60da98c8990040055b2bab48aa53a7'
AMOUNTS = ('1000', '10000')
LOADED_SOURCE_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def assemble(parent, reference):
    require(parent['schema'] == 'CONDITIONAL_NEW_CASH_SIX_COORDINATE_INVENTORY_V2', 'Wrong parent schema')
    require(parent['branch_coordinate_count'] == len(parent['rows']) == 36, 'Expected 36 parent branches')
    for flag in ('cash_fork_called', 'point_in_time_verified', 'promotion_allowed'):
        require(parent[flag] is False, 'Unexpected parent authority')
    rows, seen = [], set()
    for index, row in enumerate(parent['rows']):
        coordinate = (row['lane'], row['decision_date'], row['execution_date'])
        require(coordinate not in seen, 'Duplicate branch coordinate')
        seen.add(coordinate)
        require(row['cash_event_amount_usd'] is None and row['fork_executable'] is False, 'Parent cash event already chosen')
        require(row['decision_date'] < row['execution_date'], 'Execution must follow decision')
        for amount in AMOUNTS:
            rows.append({'scenario_id': '|'.join((*coordinate, amount)), 'lane': coordinate[0],
                         'decision_date': coordinate[1], 'execution_date': coordinate[2],
                         'standardized_cash_injection_usd': amount,
                         'parent_row_reference': dict(reference, json_pointer=f'/rows/{index}'),
                         'parent_gap_count': len(row['gaps']),
                         'hypothetical_research_only': True, 'real_user_cash_claimed': False,
                         'fork_executable': False})
    return {'schema': 'STANDARD_CASH_RESEARCH_SCENARIOS_V1', 'parent_inventory_reference': reference,
            'amounts_usd': list(AMOUNTS), 'scenario_count': len(rows), 'rows': rows,
            'scope': 'HISTORICAL_CONDITIONAL_RESEARCH_SCENARIO_SELECTION_ONLY',
            'amount_selection_reason': 'Two explicit research capital levels; neither asserts user purchasing power.',
            'coordinate_selection_reason': 'Use all six saved decision/execution pairs across all six branches.',
            'selection_policy_frozen': False, 'evaluation_window_frozen': False,
            'actual_cash_event_registered': False, 'cash_fork_called': False,
            'source_gaps_resolved': False, 'point_in_time_verified': False,
            'fresh_oos_claimed': False, 'promotion_allowed': False,
            'next_required': ['source applicability and conditional assumptions',
                              'buy-only selection policy and search coverage',
                              'risk, fees and cash buffer contract',
                              'common forward window and 012922 currency treatment']}


def publish():
    require(not OUTPUT.exists(), 'Fixed namespace exists; no overwrite/retry')
    source_bytes = SOURCE.read_bytes()
    require(sha(source_bytes) == LOADED_SOURCE_SHA, 'Loaded source changed')
    raw, receipt_raw = PARENT.read_bytes(), PUBLICATION.read_bytes()
    require(sha(raw) == PARENT_SHA and sha(receipt_raw) == PUBLICATION_SHA, 'Parent bytes changed')
    require({p.name for p in PARENT.parent.iterdir()} == {'inventory.json', 'publication.json'}, 'Parent publication incomplete')
    parent, receipt = json.loads(raw), json.loads(receipt_raw)
    reference = {'path': str(PARENT), 'sha256': PARENT_SHA}
    require(receipt['inventory_reference'] == reference and receipt['source_hashes'] == parent['source_hashes']
            and receipt['status'] == 'SOURCE_LOCKED_INVENTORY_ONLY_NOT_FORK_READY'
            and receipt['fork_executed'] is False, 'Parent receipt mismatch')
    result = assemble(parent, reference)
    sources = {str(SOURCE): sha(source_bytes), str(PARENT): PARENT_SHA, str(PUBLICATION): PUBLICATION_SHA}
    result['source_hashes'] = sources
    def check():
        for path, expected in sources.items():
            require(sha(Path(path).read_bytes()) == expected, 'Source changed before publication')
    check()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    path = OUTPUT / 'scenarios.json'
    try:
        payload = encode(result)
        with path.open('xb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        check()
        require(path.read_bytes() == payload and {p.name for p in OUTPUT.iterdir()} == {'scenarios.json'}, 'Output readback differs')
        return {'path': str(path), 'sha256': sha(payload), 'scenario_count': len(result['rows'])}
    except Exception as error:
        with (OUTPUT / 'failure.json').open('xb') as stream:
            stream.write(encode({'status': 'FAILED_DO_NOT_CONSUME', 'error': str(error)}))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    if not parser.parse_args().publish:
        parser.error('Explicit --publish required')
    print(json.dumps(publish(), indent=2))
