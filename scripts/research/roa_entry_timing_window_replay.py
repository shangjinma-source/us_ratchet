"""Offline execution sensitivity on adjacent sessions, not ROA signal backtest."""
import argparse
from hashlib import sha256
import json
import math
import statistics
from scripts.research.roa_entry_timing_account_probe import ARMS, simulate
from scripts.research.roa_entry_timing_event_probe import analyze
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    directory = parser.parse_args().directory
    source = directory / 'fixed_window_report.json'
    raw_report = source.read_bytes()
    report = json.loads(raw_report)
    dates = report['contract']['dates']
    tickers = report['contract']['tickers']
    capital = 35000
    contract = dict(capital=capital, slot_budget=capital / len(tickers), arms=ARMS,
                    fees=[0, 1.88, 18], dates=dates, tickers=tickers,
                    source_sha256=sha256(raw_report).hexdigest(),
                    quantity='floor((slot budget - 18)/first minute opening); missing slots stay cash',
                    design='Adjacent overlapping session pairs reset independently; never compounded; not ROA signals')
    contract_path = directory / 'window_replay_contract.json'
    serialized = json.loads(json.dumps(contract))
    if contract_path.exists() and json.loads(contract_path.read_bytes()) != serialized:
        raise ValueError('CONTRACT_CHANGED')
    contract_path.write_text(json.dumps(contract, indent=2), encoding='utf-8')
    bars = {}
    for row in report['rows']:
        if row['status'] != 'COMPLETE_PRICE_PROXY':
            continue
        raw = (directory / f"{row['ticker']}_{row['session']}.raw.json").read_bytes()
        if sha256(raw).hexdigest() != row['source_sha256']:
            raise ValueError('SOURCE_CHANGED')
        parsed, missing, symbol = analyze(raw, row['session'])
        if missing or symbol != row['ticker']:
            raise ValueError('INVALID_SOURCE')
        bars[(row['session'], symbol)] = parsed
    results = []
    for entry, exit_date in zip(dates, dates[1:]):
        eligible = [ticker for ticker in tickers if (entry, ticker) in bars and (exit_date, ticker) in bars]
        quantities = {ticker: math.floor((capital / len(tickers) - 18) / bars[(entry, ticker)][0][0])
                      for ticker in eligible}
        days = [{ticker: bars[(date, ticker)] for ticker in eligible} for date in (entry, exit_date)]
        for fee in contract['fees']:
            for touch in (False, True):
                for arm in ARMS:
                    result = simulate(days, quantities, capital, arm, fee, touch)
                    result.update(entry=entry, exit=exit_date, eligible=len(eligible),
                                  excluded=sorted(set(tickers) - set(eligible)))
                    results.append(result)
    summaries = []
    for fee in contract['fees']:
        for arm in ARMS:
            rows = [row for row in results if row['fee_per_order'] == fee and row['arm'] == arm
                    and row['fill_model'] == 'STRICT_CROSS']
            baseline = {row['entry']: row for row in results if row['fee_per_order'] == fee
                        and row['arm'] == 'OPEN_REFERENCE' and row['fill_model'] == 'STRICT_CROSS'}
            summaries.append(dict(fee=fee, arm=arm, pairs=len(rows),
                mean_pair_return_pct=statistics.mean(row['return_pct'] for row in rows),
                mean_excess_percentage_points=statistics.mean(row['return_pct']-baseline[row['entry']]['return_pct'] for row in rows),
                beat_open_pairs=sum(row['return_pct'] > baseline[row['entry']]['return_pct'] + 1e-9 for row in rows),
                buy_fills=sum(row['buy_count'] for row in rows),
                unbought=sum(len(row['unbought']) for row in rows),
                cash_rejections=sum(len(row['cash_rejected']) for row in rows),
                worst_pair_return_pct=min(row['return_pct'] for row in rows)))
    output = dict(contract=contract, summaries=summaries, results=results,
        limitations=['Current roster and incomplete-session exclusion bias.',
                     'Overlapping pairs are dependent, not an equity curve or annualized performance.',
                     'Hypothetical limit fills, no queue/spread guarantee; missing data is not a known trading signal.',
                     '1.88 fixed fee is minimum-fee sensitivity, not complete uSMART tariff; excludes other charges.',
                     'No production changes or real-account writes.'])
    (directory / 'window_replay.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps(summaries))


if __name__ == '__main__':
    main()
