"""Read and seal only 25 event facts; no quote reconstruction or HTTP."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_simple_split_exact_gap_research as core
SOURCE=Path(__file__).resolve()
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def build():
    report=core.load_registry()
    facts=report['events']
    if len(facts)!=25 or len({(r['ticker'],r['first_adjusted_trading_date']) for r in facts})!=25:
        raise ValueError('Distinct 25 event facts required')
    if {r['ticker'] for r in facts if not r['simple_split_guard_eligible']}!={'LCID','LRCX'}:
        raise ValueError('Identity transition blocks differ')
    if set(report['blocked_tickers'])!=set(core.original.BLOCKED):
        raise ValueError('Complex action blocks differ')
    expected=report['historical_expected_source_hashes']
    core.merge(expected,{str(SOURCE):LOADED})
    checked=core.partition(expected,core.drift.load_contract(),require_all=True)
    core.attach_partition(report,expected,checked)
    report.update(actual_registry_event_readback=True,quote_reconstruction_performed=False,
                  network_requests=0,training_performed=False,
                  source_partition_count=dict(expected=len(expected),verified=len(checked['verified_source_hashes']),
                                              historical_gaps=len(checked['historical_gap_observations'])))
    return report


if __name__=='__main__':
    report=build()
    folder=ROOT/'data/cache/research/standard_split_exact_gap_20260919_v1'
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/'registry_readback.json'
    raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as handle:handle.write(raw)
    checked=core.partition(report['historical_expected_source_hashes'],core.drift.load_contract(),require_all=True)
    if checked['verified_source_hashes']!=report['verified_source_hashes'] or checked['historical_gap_observations']!=report['historical_price_cache_gap_observations']:
        raise ValueError('Published source partition changed')
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),events=25,eligible=23,
                          sources=report['source_partition_count'],quote_reconstruction_performed=False)))
