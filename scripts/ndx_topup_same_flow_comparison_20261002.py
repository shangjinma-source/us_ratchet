"""Create-only comparison of sealed paths; never simulate or select accounts."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT / 'data/cache/research/topup_same_flow_comparison_20261002_v1'
PINS = {
    'paired_accounts': ('data/cache/research/old_holding_topup_paired_account_20261002_v1/accounts.json', '7d5df8f295657497f3919aa3458dff31f0c175a40f391eb6b37ac9e5b7512d6f'),
    'paired_publication': ('data/cache/research/old_holding_topup_paired_account_20261002_v1/publication.json', 'fb9db1ac77fffec7ec90141a7b431b3f34fb4bac0329deb07245c85b22325e7e'),
    'incumbent_accounts': ('data/cache/research/incumbent_cash_flow_paths_20261002_v1/accounts.json', 'd1ac38ebe7674756d67cdc390938a6dffbe0d4f45c25e7b10726fab5642dc36a'),
    'incumbent_publication': ('data/cache/research/incumbent_cash_flow_paths_20261002_v1/publication.json', '2abc2d2bbe9e03e6f7c84f11f6c9c9a422d81624a291c9494349c58950ede1bd'),
    'core': ('backtest/ndx_topup_same_flow_comparison_research.py', 'eb3a37e6c2951f6c6e703f71733f796b6f1acb805f01dca6a5bf5f1037066fe5'),
    'metrics': ('backtest/ndx_cash_fork_reference_window_research.py', '0d21fb1cf1580de186ad684b98f0e7704ae63ebc592bc166f1741860d7aea163'),
}
FLAGS = dict.fromkeys(('orders_executed', 'point_in_time_verified', 'promotion_allowed',
    'formal_dual_benchmark_admission', 'economic_winner_selected', 'account_simulation_called',
    'full_transitive_source_closure_reverified', 'candidate_decision_time_executability_verified'), False)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def guard(sources):
    require(sources.get(str(SOURCE)) == LOADED_SHA, 'Loaded source linkage differs')
    for path, digest in sources.items():
        require(sha(Path(path).read_bytes()) == digest, 'Source drift: ' + path)


def validate_publications(documents, refs):
    contracts = (
        ('paired', 'OLD_HOLDING_TOPUP_PAIRED_ACCOUNT_PUBLICATION_V1', 'PUBLISHED_CONDITIONAL_PRICE_ONLY_PAIRED_PATHS'),
        ('incumbent', 'INCUMBENT_CASH_FLOW_PATHS_PUBLICATION_V1', 'PUBLISHED_CONDITIONAL_SAME_FLOW_INCUMBENT_PATHS'),
    )
    for prefix, schema, status in contracts:
        role = prefix + '_accounts'
        receipt = documents[prefix + '_publication']
        require(Path(refs[prefix + '_publication']['path']).parent == Path(refs[role]['path']).parent,
                'Receipt directory differs')
        require({p.name for p in Path(refs[role]['path']).parent.iterdir()} ==
                {'started.json', 'accounts.json', 'publication.json'}, 'Parent namespace incomplete or failed')
        require(receipt['schema'] == schema and receipt['status'] == status
                and receipt['account_reference'] == refs[role]
                and receipt['source_hashes'] == documents[role]['source_hashes'], 'Parent publication differs')
        for flag in ('orders_executed', 'point_in_time_verified', 'promotion_allowed', 'full_transitive_source_closure_reverified'):
            require(receipt[flag] is False and documents[role][flag] is False, 'Parent authority changed')


def load_compare(refs):
    names = {'metrics': 'backtest.ndx_cash_fork_reference_window_research',
             'core': 'backtest.ndx_topup_same_flow_comparison_research'}
    require(all(name not in sys.modules for name in names.values()), 'Fresh CLI required; cached comparison dependency')
    module = importlib.import_module(names['core'])
    for role, name in names.items():
        require(Path(sys.modules[name].__file__).resolve() == Path(refs[role]['path']).resolve(), 'Module path differs')
    require(module.REFERENCE_METRICS_SOURCE_SHA256 == refs['metrics']['sha256'], 'Metrics dependency pin differs')
    return module.compare_same_flow_paths


def write_new(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == raw, 'Output bytes differ')
    return sha(raw)


def run():
    require(not OUTPUT.exists(), 'Fixed namespace exists; no retry')
    require(all(type(digest) is str and len(digest) == 64 for _, digest in PINS.values()), 'Pending source pins')
    sources = {str(SOURCE): LOADED_SHA}
    guard(sources)
    refs, documents = {}, {}
    for role, (relative, digest) in PINS.items():
        path = ROOT / relative
        raw = path.read_bytes()
        require(sha(raw) == digest, 'Source mismatch: ' + role)
        sources[str(path)] = digest
        refs[role] = {'path': str(path), 'sha256': digest}
        if role not in ('core', 'metrics'):
            documents[role] = json.loads(raw)
    validate_publications(documents, refs)
    compare = load_compare(refs)
    guard(sources)
    OUTPUT.mkdir(parents=True, exist_ok=False)
    try:
        write_new(OUTPUT / 'started.json', {'schema': 'TOPUP_SAME_FLOW_COMPARISON_STARTED_V1',
            'started_at_utc': datetime.now(timezone.utc).isoformat(), 'source_hashes': sources,
            'planned_scenario_count': 40, 'retry_allowed': False, **FLAGS})
        result = compare(paired_accounts=documents['paired_accounts'], incumbent_accounts=documents['incumbent_accounts'],
                         paired_reference=refs['paired_accounts'], incumbent_reference=refs['incumbent_accounts'])
        require(result['schema'] == 'TOPUP_SAME_FLOW_INCUMBENT_EXACT_COMPARISON_V1'
                and len(result['rows']) == 40, 'Comparison result scope differs')
        for flag in FLAGS:
            require(result[flag] is False, 'Comparison authority changed: ' + flag)
        result.update(source_hashes=sources, input_references=refs)
        guard(sources)
        digest = write_new(OUTPUT / 'comparison.json', result)
        guard(sources)
        pubsha = write_new(OUTPUT / 'publication.json', {'schema': 'TOPUP_SAME_FLOW_COMPARISON_PUBLICATION_V1',
            'status': 'PUBLISHED_CONDITIONAL_DIAGNOSTIC_COMPARISON',
            'comparison_reference': {'path': str(OUTPUT / 'comparison.json'), 'sha256': digest},
            'source_hashes': sources, **FLAGS})
        guard(sources)
        require(sha((OUTPUT / 'comparison.json').read_bytes()) == digest
                and sha((OUTPUT / 'publication.json').read_bytes()) == pubsha
                and {p.name for p in OUTPUT.iterdir()} == {'started.json', 'comparison.json', 'publication.json'},
                'Final publication differs')
        return {'path': str(OUTPUT / 'comparison.json'), 'sha256': digest, 'publication_sha256': pubsha}
    except Exception as error:
        write_new(OUTPUT / 'failure.json', {'status': 'FAILED_DO_NOT_CONSUME', 'error': str(error), 'retry_allowed': False})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    if not parser.parse_args().execute:
        parser.error('Explicit --execute required')
    print(json.dumps(run(), indent=2))
