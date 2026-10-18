"""Explicit original-weight control replay under the frozen dynamic clock."""
import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_dynamic_frozen_control_input import prepare_control
from scripts.ndx_dynamic_frozen_input_probe import _check_sources
from scripts.ndx_dynamic_frozen_replay_probe import save_new
from backtest.ndx_dynamic_frozen_incumbent_control import simulate_dynamic_frozen_incumbent_control


def run(lane_key):
    prepared = prepare_control(lane_key)
    result = simulate_dynamic_frozen_incumbent_control(
        closes=prepared['closes'], opens=prepared['opens'], schedule=prepared['schedule'],
        risk_chains_by_decision=prepared['risk_chains'], corporate_actions=[],
        initial_cash_usd=prepared['capital_usd'],
        minimum_cash_buffer_usd=prepared['minimum_cash_buffer_usd'],
        valuation_end_date=prepared['date_end'], transaction_cost_bps=prepared['transaction_cost_bps'])
    source = Path(__file__).resolve()
    sources = {**prepared['source_hashes'], **result['source_hashes'],
               str(source): hashlib.sha256(source.read_bytes()).hexdigest()}
    _check_sources(sources)
    return dict(schema='ndx_dynamic_frozen_control_probe_v1', lane_key=lane_key,
                original_weights=prepared['original_weights'], execution=result,
                source_hashes=sources, identity_scope=prepared['identity_scope'],
                risk_provenance=prepared['risk_provenance'], promotion_allowed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lane-key', required=True)
    parser.add_argument('--output-path', required=True)
    args = parser.parse_args()
    if Path(args.output_path).exists():
        raise ValueError('Output exists; do not rerun')
    report = run(args.lane_key)
    print(save_new(report, args.output_path))
    print(report['execution']['summary'])
