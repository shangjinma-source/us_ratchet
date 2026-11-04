"""Saved E1 ledger attribution only; no selection, strategy or counterfactual."""
import json
from collections import defaultdict
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    folder = ROOT/'tmp/ema20_economic_20261105/daily/2021_2023'
    inputs = ROOT/'tmp/recent_continuous_baseline_20261026_v7/execution_inputs.json'
    book = json.loads((folder/'book.json').read_bytes())
    document = json.loads(inputs.read_bytes())
    market = json.loads((folder/'market_audit.json').read_bytes())
    review = json.loads((folder/'independent_review.json').read_bytes())
    assert review['status'] == 'INDEPENDENT_EMA20_ORIGINAL_EXIT_FINANCE_PASS'
    for name, digest in review['source_hashes'].items():
        assert sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
    assert len(book['daily_ledger']) == len(market) == review['sessions_checked'] == 753
    assert book['status'] == 'COMPLETE' and not document['assembled']['actions']
    bars = document['ohlc']
    trades = defaultdict(list)
    for order in book['order_log']:
        if order['event'] == 'ASSUMED_NEXT_OPEN_FILLED':
            trades[order['date']].append(order)
    dividends = defaultdict(lambda: defaultdict(F))
    for item in book['dividend_ledger']['events'].values():
        event = item['event']
        dividends[event['ex_date']][event['security_id']] += F(item['net'])
    contributions = defaultdict(lambda: defaultdict(F))
    facts = defaultdict(lambda: dict(days=0, off_days=0, cash_weights=[], off_cash_weights=[],
                                    stock_weights=[], market_on_transitions=0, reentries=0, on_transition_reentries=0))
    previous_shares = {}
    previous_date = document['assembled']['session_dates'][0]
    previous_equity = F(20000)
    previous_on = market[0]['market_on']
    ever_held = set()
    yearly_start = {}
    yearly_end = {}
    daily = []
    for row, gate in zip(book['daily_ledger'], market):
        day = row['date']; year = day[:4]; equity = F(row['equity'])
        yearly_start.setdefault(year, previous_equity); yearly_end[year] = equity
        values = {}
        for sid in set(previous_shares) | set(row['shares']) | set(dividends[day]):
            value = (row['shares'].get(sid, 0)*F(bars[sid][day]['close']) if row['shares'].get(sid, 0) else F(0))
            value -= previous_shares.get(sid, 0)*F(bars[sid][previous_date]['close']) if previous_shares.get(sid, 0) else F(0)
            value += dividends[day].get(sid, F(0))
            values[sid] = value
        transition = not previous_on and gate['market_on']
        f = facts[year]; f['days'] += 1; f['market_on_transitions'] += transition
        for order in trades[day]:
            sid = order['security_id']; quantity = order['quantity']
            amount = quantity*F(order['price'])
            values[sid] = values.get(sid, F(0)) + (amount if order['side'] == 'SELL' else -amount)-F(order['fee'])
            if order['side'] == 'BUY' and quantity > 0 and previous_shares.get(sid, 0) == 0 and sid in ever_held:
                f['reentries'] += 1
                f['on_transition_reentries'] += transition
        assert sum(values.values(), F(0)) == equity-previous_equity, day
        for sid, value in values.items():
            contributions[year][sid] += value
        f['cash_weights'].append(F(row['cash'])/equity)
        f['stock_weights'].append(F(row['stock_value'])/equity)
        if not gate['market_on']:
            f['off_days'] += 1; f['off_cash_weights'].append(F(row['cash'])/equity)
        daily.append(dict(date=day, equity=str(equity), contributions={s:str(v) for s,v in values.items()}))
        ever_held.update(s for s,q in row['shares'].items() if q)
        previous_date, previous_shares, previous_equity, previous_on = day, row['shares'], equity, gate['market_on']
    result = {}
    for year, f in facts.items():
        assert sum(contributions[year].values(), F(0)) == yearly_end[year]-yearly_start[year]
        result[year] = dict(start_equity=float(yearly_start[year]), end_equity=float(yearly_end[year]),
            return_percent=100*float(yearly_end[year]/yearly_start[year]-1),
            contributions_usd={s:float(v) for s,v in sorted(contributions[year].items(), key=lambda pair:pair[1])},
            **{k:v for k,v in f.items() if not isinstance(v,list)},
            **{k+'_mean_percent':100*float(sum(v,F(0))/len(v)) if v else None for k,v in f.items() if isinstance(v,list)})
    trough = book['drawdown']['trough_date']
    eligible = [r for r in daily if r['date'] <= trough]
    peak = max(eligible, key=lambda row:F(row['equity']))
    interval = defaultdict(F)
    for row in daily:
        if peak['date'] < row['date'] <= trough:
            for sid, value in row['contributions'].items(): interval[sid] += F(value)
    target = ROOT/'tmp/ema20_early_saved_diagnostic_20261105';target.mkdir(exist_ok=True)
    report = dict(years=result, drawdown=dict(peak_date=peak['date'],peak_equity=float(F(peak['equity'])),trough_date=trough,
        contributions_usd={s:float(v) for s,v in sorted(interval.items(),key=lambda pair:pair[1])}),
        definitions=dict(contribution='End stock value minus prior stock value plus actual sell proceeds minus buy costs/fees plus ex-date net dividend accrual. Daily sum equals account equity change exactly.',
        reentry='Positive actual BUY from zero prior-close shares after previously having positive close shares; counts security-execution events, including new months.',
        on_transition_reentry='Subset of reentries executed first session after OFF-to-ON signal transition.',cash='Arithmetic mean of close cash/equity, not causal lost return.',
        limits='Saved realized-path attribution only; cannot isolate causal selection, sizing, market gate or foregone returns. No new backtest.'),
        source_hashes={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in [folder/'book.json',folder/'market_audit.json',folder/'independent_review.json',inputs,Path(__file__)]})
    (target/'result.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__': main()
