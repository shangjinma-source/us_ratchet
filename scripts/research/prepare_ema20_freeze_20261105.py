"""Freeze existing market-state artifact; does not run economic research."""
import gzip
import json
from pathlib import Path
from hashlib import sha256
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2]

def main():
    directory=ROOT/'research_contracts/ema20_20261105'
    directory.mkdir(parents=True,exist_ok=False)
    source=ROOT/'tmp/ema20_market_states_20261105/result.json'
    result=json.loads(source.read_bytes())
    old=json.loads((ROOT/'research_contracts/research_archive_20261026/trend_fixed_candidate_v1_manifest.json').read_bytes())['base_file_dependencies']
    dates=set()
    for name,digest in result['source_hashes'].items():
        raw=(ROOT/name).read_bytes()
        assert sha256(raw).hexdigest()==digest==old[name]
        record=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)['chart']['result'][0]
        dates.update(datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat() for t in record['timestamp'])
    monthends={}
    for day in sorted(dates):monthends[day[:7]]=day
    # Exclude the source's truncated final month; never call the last bar a month end.
    del monthends[max(dates)[:7]]
    assert monthends['2026-07']=='2026-07-31' and '2026-07-30' not in monthends.values()
    artifact=directory/'signals.json'
    artifact.write_text(json.dumps(dict(signals=result['signals'],month_ends=sorted(monthends.values()),
        calendar_basis='EXISTING_CONDITIONAL_QQQ_FULL_SOURCE_MONTHS',source_hashes=result['source_hashes'],
        first_253_ready=result['first_253_ready'],seed_first_day=result['seed_first_day'],seed_sma20_end=result['seed_sma20_end'],
        precision=result['precision'],causal_prefix_checks=result['causal_prefix_checks']),indent=2),encoding='utf-8')
    files=[source,artifact,Path(__file__)]+[ROOT/name for name in [
        'scripts/research/run_ema20_market_20261105.py','scripts/research/ema20_market_states_20261105.py',
        'docs/candidates/ema20_market_adapter.py','docs/candidates/ema20_execution_contract_20261105.md',
        'core/monthly_peak_exit.py','backtest/monthly_exit_core_research_adapter.py',
        'backtest/historical_dividend_frontier_research.py','backtest/frontier_capped_next_open_research.py',
        'backtest/historical_dividend_next_open_book_research.py','backtest/current_quantity_v2_next_open_book.py',
        'backtest/capped_frontier_rerank_research.py','backtest/continuous_guided_account_decision.py',
        'backtest/continuous_guided_cost_monthly_provider.py','scripts/run_recent_continuous_probe.py',
        'scripts/assemble_old_continuous_inputs_v1.py','scripts/run_old_continuous_probe_v4.py',
        'scripts/run_old_continuous_probe_v1.py']]
    pins={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in files}
    pins.update(result['source_hashes'])
    (directory/'freeze.json').write_text(json.dumps(dict(status='PREPARED_NOT_RUN',
        signal_artifact=artifact.relative_to(ROOT).as_posix(),source_hashes=pins,
        modes=['daily','monthly_reentry'],windows={'2021_2023':36,'2024_2026':31},
        seconds_per_mode_window=1800,initial_cash='20000',fee_bps='0',slippage_bps='5'),indent=2),encoding='utf-8')
    print(str(directory/'freeze.json'))

if __name__=='__main__':main()
