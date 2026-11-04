"""Same-window EMA comparisons; arithmetic output is not an independent audit."""
import argparse
import json
import sys
from datetime import date
from fractions import Fraction
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.summarize_cross_month_held_peak_20261105 import metrics, verify


def read(path):
    return json.loads(path.read_bytes())


def experience(rows, start):
    high = Fraction(20000)
    peak_date = start
    longest = 0
    underwater = False
    months = {}
    for row in rows:
        value = Fraction(row['equity'])
        day = row['date']
        if value < high:
            underwater = True
            longest = max(longest, (date.fromisoformat(day) - date.fromisoformat(peak_date)).days)
        else:
            if underwater:
                longest = max(longest, (date.fromisoformat(day) - date.fromisoformat(peak_date)).days)
            underwater = False
            high, peak_date = value, day
        months[day[:7]] = value
    previous = Fraction(20000)
    losses = 0
    for value in months.values():
        losses += value < previous
        previous = value
    return {'longest_peak_to_recovery_or_last_underwater_days': longest,
            'negative_calendar_months': losses, 'observed_calendar_months': len(months),
            'last_month_may_be_partial': True}


def summarize(window, mode):
    folder = ROOT / 'tmp/ema20_economic_20261105' / mode / window
    contract = read(folder / 'contract.json')
    verify(contract['source_hashes'])
    assert contract['mode'] == mode and contract['window'] == window
    name = ('recent_continuous_baseline_20261026_v7' if window == '2021_2023'
            else 'old_continuous_baseline_20261026_v9')
    baseline = ROOT / 'tmp' / name
    dates = read(baseline / 'execution_inputs.json')['assembled']['session_dates']
    book = read(folder / 'book.json')
    original = read(baseline / 'book.json')
    qqq_folder = ROOT / 'tmp/qqq_fair_hold_20261105'
    verify(read(qqq_folder / 'summary.json')['source_hashes'])
    qqq = read(qqq_folder / (name + '.json'))
    assert book['status'] == original['status'] == 'COMPLETE'
    summary = read(folder / 'summary.json')
    assert summary['searches']['new'] <= contract['maximum_new_searches']
    series = {'candidate': book['daily_ledger'], 'v27': original['daily_ledger'], 'qqq': qqq['ledger']}
    output = {'window': window, 'mode': mode,
              'status': 'ARITHMETIC_VERIFIED_REQUIRES_SEPARATE_INDEPENDENT_AUDIT',
              'source_hashes': {}}
    for label, rows in series.items():
        assert [r['date'] for r in rows] == dates[1:], label
        orders = book['order_log'] if label == 'candidate' else original['order_log'] if label == 'v27' else []
        fills = sum(r.get('event') == 'ASSUMED_NEXT_OPEN_FILLED' for r in orders) if label != 'qqq' else 1
        output[label] = metrics(rows, dates[0], fills)
        output[label]['experience'] = experience(rows, dates[0])
        if window == '2024_2026':
            prefix = [r for r in rows if r['date'] <= '2025-12-31']
            output[label]['through_2025'] = metrics(prefix, dates[0], None)
    assert abs(output['candidate']['drawdown_pct'] - float(Fraction(book['drawdown']['maximum_close_drawdown'])) * 100) < 1e-9
    assert abs(output['candidate']['terminal'] / 20000 - 1 - float(Fraction(book['total_return']))) < 1e-9
    output['beats_qqq_both'] = (output['candidate']['cagr_pct'] > output['qqq']['cagr_pct']
                              and output['candidate']['drawdown_pct'] < output['qqq']['drawdown_pct'])
    audit_path = folder / 'independent_review.json'
    if audit_path.exists():
        audit = read(audit_path)
        verify(audit['source_hashes'])
        assert audit['status'] == 'INDEPENDENT_EMA20_ORIGINAL_EXIT_FINANCE_PASS'
        assert audit['mode'] == mode and audit['sessions_checked'] == len(dates) - 1
        assert audit['source_hashes'][(folder / 'book.json').relative_to(ROOT).as_posix()] == sha256((folder / 'book.json').read_bytes()).hexdigest()
        output['status'] = 'COMPLETE_INDEPENDENTLY_REVIEWED_COMPARISON'
        output['source_hashes'][audit_path.relative_to(ROOT).as_posix()] = sha256(audit_path.read_bytes()).hexdigest()
    for path in [folder / 'book.json', folder / 'contract.json', baseline / 'book.json',
                 qqq_folder / (name + '.json'), Path(__file__),
                 ROOT / 'scripts/research/summarize_cross_month_held_peak_20261105.py']:
        output['source_hashes'][path.relative_to(ROOT).as_posix()] = sha256(path.read_bytes()).hexdigest()
    (folder / 'comparison.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--window', choices=['2021_2023', '2024_2026'], required=True)
    parser.add_argument('--mode', choices=['daily', 'monthly_reentry'], required=True)
    args = parser.parse_args()
    summarize(args.window, args.mode)
