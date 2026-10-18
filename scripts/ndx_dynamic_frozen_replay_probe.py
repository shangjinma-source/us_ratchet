"""Explicit sealed-lane execution diagnostic, not portfolio admission."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_dynamic_frozen_input_probe import prepare_lane, _check_sources
from backtest.ndx_dynamic_frozen_execution_research import simulate_dynamic_frozen_execution_research


def run(lane_key):
    prepared = prepare_lane(lane_key)
    metadata = prepared['summary']
    source = Path(__file__).resolve()
    sources = {**metadata['source_hashes'], str(source): hashlib.sha256(source.read_bytes()).hexdigest()}
    result = simulate_dynamic_frozen_execution_research(
        closes=prepared['closes'], opens=prepared['opens'],
        schedule=prepared['schedule'], risk_chains_by_decision=prepared['risk_chains'],
        corporate_actions=[], identity_events=[], initial_cash_usd=metadata['capital_usd'],
        minimum_cash_buffer_usd=metadata['minimum_cash_buffer_usd'],
        transaction_cost_bps=metadata['transaction_cost_bps'],
        valuation_end_date=metadata['date_end'])
    sources.update(result['source_hashes'])
    _check_sources(sources)
    return dict(schema='ndx_dynamic_frozen_replay_probe_v1', input=metadata,
                execution=result, source_hashes=sources,
                dual_benchmark_completed=False, promotion_allowed=False)


def save_new(report, destination):
    path = Path(destination)
    raw = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
    if path.read_bytes() != raw:
        raise ValueError('Persisted report differs')
    return hashlib.sha256(raw).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lane-key', required=True)
    parser.add_argument('--output-path', required=True)
    args = parser.parse_args()
    if Path(args.output_path).exists():
        raise ValueError('Output exists; inspect it rather than rerunning')
    report = run(args.lane_key)
    digest = save_new(report, args.output_path)
    print(json.dumps(dict(path=args.output_path, sha256=digest,
                          summary=report['execution']['summary'], promotion_allowed=False)))
