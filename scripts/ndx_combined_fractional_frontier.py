"""Recover saved research inputs and report economic frontiers, never train."""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_combined_fractional_frontier_research as frontier
from backtest import ndx_joint_weight_runner as encoding
from scripts import ndx_combined_fractional_date as combined
from scripts import ndx_combined_fractional_summary as summaries

SELF = Path(__file__).resolve()
LOADED = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
          for path in (SELF, Path(frontier.__file__).resolve(), Path(encoding.__file__).resolve(),
                       ROOT / 'backtest/ndx_dynamic_envelope_policy.py',
                       ROOT / 'backtest/ndx_dynamic_research_selector.py',
                       ROOT / 'backtest/ndx_fractional_research_gates.py')}


def read_bound(path, expected_sha256):
    path = Path(path).resolve()
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError('Bound input hash differs: ' + str(path))
    return json.loads(content)


def run_date(*, inventory_path, inventory_sha256, selection_date):
    combined._check_sources(LOADED)
    inventory_path = Path(inventory_path).resolve()
    inventory = read_bound(inventory_path, inventory_sha256)
    if (inventory['schema'] != 'combined_summary_inventory_20260912'
            or inventory['training_rerun'] is not False
            or inventory['execution_performed'] is not False
            or inventory['promotion_allowed'] is not False):
        raise ValueError('Research inventory required')
    rows = inventory['summaries']
    coordinates = [tuple(row['coordinate'][key] for key in combined._KEYS) for row in rows]
    if (len(set(coordinates)) != len(rows) or inventory['date_count'] != len(rows)
            or inventory['record_count'] != sum(row['record_count'] for row in rows)):
        raise ValueError('Inventory denominator differs')
    selected = [row for row in rows if row['coordinate']['selection_date'] == selection_date]
    if len(selected) != 1:
        raise ValueError('Exactly one explicit date required')
    descriptor = selected[0]
    summary_path = Path(descriptor['path']).resolve()
    saved = read_bound(summary_path, descriptor['sha256'])
    summaries._validate_summary(saved)
    if (any(saved['expected_date'][key] != value for key, value in descriptor['coordinate'].items())
            or saved['counts'] != descriptor['counts'] or saved['record_count'] != descriptor['record_count']
            or saved['economic_inputs_complete'] is not True):
        raise ValueError('Complete summary differs from inventory')
    stamp = selection_date.replace('-', '')
    equal_references = [(path, digest) for path, digest in saved['source_hashes'].items()
                        if Path(path).name == 'equal_base_' + stamp + '_20260911.json']
    context_references = [(path, digest) for path, digest in saved['source_hashes'].items()
                          if Path(path).name == 'context.json'
                          and Path(path).parent.parent.name == 'ndx_non_equal_base_fractional_v1']
    if len(equal_references) != 1 or len(context_references) != 1:
        raise ValueError('Unique saved base input bindings required')
    equal_path, equal_sha256 = equal_references[0]
    context_path, context_sha256 = context_references[0]
    date = combined.prepare_combined_date(equal_report_path=equal_path,
        equal_report_sha256=equal_sha256, non_equal_context_path=context_path,
        non_equal_context_sha256=context_sha256, **descriptor['coordinate'])
    digest = encoding._sha(encoding._normalize(date['records']))
    if (digest != saved['records_sha256'] or date['expected_date'] != saved['expected_date']
            or date['counts'] != saved['counts'] or len(date['records']) != saved['record_count']):
        raise ValueError('Rebuilt complete records differ from saved summary')
    sources = combined._merge_sources(saved['source_hashes'], date['source_hashes'], LOADED,
        {str(inventory_path): inventory_sha256, str(summary_path): descriptor['sha256']})
    combined._check_sources(sources)
    result = frontier.analyze_combined_date(date)
    combined._check_sources(sources)
    return dict(schema='ndx_combined_fractional_frontier_report_v1', analysis=result,
        source_hashes=sources, records_sha256=digest,
        summary_path=str(summary_path), summary_sha256=descriptor['sha256'],
        training_rerun=False, cutoff_refit_performed=False, execution_performed=False,
        point_in_time_verified=False, promotion_allowed=False)


def save_new(report, path):
    path = Path(path).resolve()
    research = (ROOT / 'data/cache/research').resolve()
    if research not in path.parents:
        raise ValueError('Research output directory required')
    combined._check_sources(report['source_hashes'])
    encoded = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(encoded)
    if path.read_bytes() != encoded:
        raise ValueError('Saved frontier readback differs')
    combined._check_sources(report['source_hashes'])
    return hashlib.sha256(encoded).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True)
    parser.add_argument('--inventory-sha256', required=True)
    parser.add_argument('--selection-date', required=True)
    parser.add_argument('--output', required=True)
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    report = run_date(inventory_path=arguments.inventory, inventory_sha256=arguments.inventory_sha256,
                      selection_date=arguments.selection_date)
    digest = save_new(report, arguments.output)
    logging.info('Saved %s sha256=%s counts=%s', arguments.selection_date, digest,
                 json.dumps(report['analysis']['counts'], sort_keys=True))


if __name__ == '__main__':
    main()
