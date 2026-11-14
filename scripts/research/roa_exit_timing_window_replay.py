"""Fixed exit-time sensitivity; buys held identical, no production changes."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import statistics
from scripts.research.roa_entry_timing_account_probe import simulate
from scripts.research.roa_entry_timing_event_probe import analyze


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--reprice-unfilled', action='store_true')
    args = parser.parse_args()
    directory = args.directory
    prefix = 'exit_reprice' if args.reprice_unfilled else 'exit_window'
    policies = [(1,False),(1,True)] if args.reprice_unfilled else [(1,False),(60,False),(150,False)]
    raw_report = (directory / 'fixed_window_report.json').read_bytes()
    report = json.loads(raw_report)
    dates, tickers = report['contract']['dates'], report['contract']['tickers']
    contract = dict(source_sha256=sha256(raw_report).hexdigest(), capital=35000,
                    buy_arms=['OPEN_REFERENCE', 'BUY_1200'], sell_policies=[list(p) for p in policies],
                    fees=[0, 1.88, 18], dates=dates, tickers=tickers,
                    design='Same fixed quantities and buys across exits; overlapping pairs reset, not ROA signals')
    if not args.reprice_unfilled:
        del contract['sell_policies']
        contract['sell_minutes']=[1,60,150]
    path = directory / (prefix+'_contract.json')
    if path.exists() and json.loads(path.read_bytes()) != contract:
        raise ValueError('CONTRACT_CHANGED')
    path.write_text(json.dumps(contract, indent=2), encoding='utf-8')
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
        quantities = {ticker: math.floor((3500 - 18) / bars[(entry, ticker)][0][0]) for ticker in eligible}
        days = [{ticker: bars[(date, ticker)] for ticker in eligible} for date in (entry, exit_date)]
        for arm in contract['buy_arms']:
            for fee in contract['fees']:
                for sell_start,reprice in policies:
                    result = simulate(days, quantities, 35000, arm, fee, sell_start=sell_start,reprice_unfilled=reprice)
                    result.update(entry=entry, exit=exit_date)
                    results.append(result)
    summaries = []
    for arm in contract['buy_arms']:
        for fee in contract['fees']:
            baseline = {r['entry']: r for r in results if r['arm'] == arm and r['fee_per_order'] == fee and r['sell_start'] == 1 and not r['reprice_unfilled']}
            for minute,reprice in policies:
                rows = [r for r in results if r['arm'] == arm and r['fee_per_order'] == fee and r['sell_start'] == minute and r['reprice_unfilled']==reprice]
                summaries.append(dict(buy_arm=arm, fee=fee, sell_minute=minute,reprice_unfilled=reprice,
                    mean_return_pct=statistics.mean(r['return_pct'] for r in rows),
                    beat_open_sell_pairs=sum(r['return_pct'] > baseline[r['entry']]['return_pct'] + 1e-9 for r in rows),
                    worst_return_pct=min(r['return_pct'] for r in rows),
                    worst_sampled_drawdown_pct=max(r['sampled_minute_close_drawdown_pct'] for r in rows),
                    unsold_positions=sum(len(r['remaining_holdings']) for r in rows),
                    repriced_positions=sum(len(r['repricings']) for r in rows)))
    output = dict(contract=contract, summaries=summaries, results=results,
                  limitations=['Independent overlapping two-day experiments, no annualization or compounding.',
                               'Current roster and complete-data selection bias; not historical risk exit signals.',
                               'Unfilled sells remain marked at close; no guarantee of execution or risk elimination.',
                               'Reprice assumes instantaneous cancel acknowledgement before replacement; no partial-fill or cancellation-race simulation; no cancel fee.'])
    (directory / (prefix+'_replay.json')).write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps([r for r in summaries if r['fee'] == 18]))


if __name__ == '__main__':
    main()
