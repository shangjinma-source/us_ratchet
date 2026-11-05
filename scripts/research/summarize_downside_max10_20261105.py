"""Read-only, audit-gated late-window comparison; never runs selection or accounts."""
import argparse
import gzip
import json
import sys
from datetime import datetime
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backtest.research_exact_fraction_json import loads, ENCODING
from scripts.research.summarize_cross_month_held_peak_20261105 import metrics, verify
from scripts.research.summarize_ema20_market_20261105 import experience


READ_HASHES = {}

def read(path):
    raw = path.read_bytes()
    READ_HASHES[path.resolve()] = sha256(raw).hexdigest()
    text = raw.decode('utf8')
    value = json.loads(text)
    return loads(text) if isinstance(value, dict) and value.get('encoding') == ENCODING else value


def require(value, reason):
    if not value:
        raise ValueError(reason)


def pinned_book(report, path):
    pins = report['source_hashes']
    verify(pins)
    normalized = {str((ROOT / name).resolve()): digest for name, digest in pins.items()}
    require(normalized.get(str(path.resolve())) == sha256(path.read_bytes()).hexdigest(), 'CURRENT_BOOK_NOT_AUDIT_BOUND')


def verify_qqq(saved, manifest, audit, dates):
    """Reconcile current QQQ output against pinned raw sources; old audit lacks book hash."""
    verify(manifest['source_hashes'])
    prices, dividends = {}, {}
    sources = [name for name in manifest['source_hashes'] if name.endswith('QQQ.response.bin')]
    require(len(sources) == 2, 'QQQ_TWO_RAW_SOURCES')
    for name in sources:
        raw = (ROOT / name).read_bytes()
        body = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw, parse_float=str)['chart']['result'][0]
        require(body['meta']['symbol'] == 'QQQ' and not body.get('events', {}).get('splits'), 'QQQ_IDENTITY')
        quote = body['indicators']['quote'][0]
        for i, timestamp in enumerate(body['timestamp']):
            if quote['open'][i] is None or quote['close'][i] is None:
                continue
            day = datetime.fromtimestamp(timestamp, ZoneInfo('America/New_York')).date().isoformat()
            value = F(quote['open'][i]), F(quote['close'][i])
            require(day not in prices or prices[day] == value, 'QQQ_OVERLAP')
            prices[day] = value
        for event in body.get('events', {}).get('dividends', {}).values():
            day = datetime.fromtimestamp(event['date'], ZoneInfo('America/New_York')).date().isoformat()
            amount = F(event['amount'])
            require(day not in dividends or dividends[day] == amount, 'QQQ_DIVIDEND_OVERLAP')
            dividends[day] = amount
    quantity = int(F(20000) / (prices[dates[1]][0] * F(10005, 10000)))
    cash = F(20000) - quantity * prices[dates[1]][0] * F(10005, 10000)
    require(saved['order']['quantity'] == quantity and saved['order']['date'] == dates[1], 'QQQ_ORDER')
    receivable = F(0)
    require(audit['daily_accounting_exact'] is True and audit['dd_exact'] is True, 'QQQ_AUDIT_FAILED')
    for row in saved['ledger']:
        if row['date'] > dates[1]:
            receivable += quantity * dividends.get(row['date'], F(0))
        require(row['shares'] == quantity and F(row['cash']) == cash and F(row['dividend_receivable']) == receivable
                and F(row['equity']) == cash + quantity * prices[row['date']][1] + receivable, 'QQQ_DAILY_ACCOUNT')
    previous = F(20000)
    for year, item in audit['annual'].items():
        last = [r for r in saved['ledger'] if r['date'].startswith(year)][-1]
        require(F(item['start']) == previous and F(item['end']) == F(last['equity']) and item['end_date'] == last['date'], 'QQQ_AUDIT_ENDPOINT')
        previous = F(last['equity'])


def summarize(output):
    folder = (ROOT / output).resolve()
    contract, summary, book, audit = [read(folder / n) for n in ('contract.json', 'summary.json', 'book.json', 'independent_review.json')]
    require(contract['window'] == '2024_2026', 'LATE_WINDOW_ONLY')
    require(summary['status'] == book['status'] == 'COMPLETE', 'COMPLETE_REQUIRED')
    require(summary['completed_sessions'] == summary['required_sessions'] == len(book['daily_ledger']) == 646, 'FULL_646_SESSIONS_REQUIRED')
    require(audit['status'] == 'INDEPENDENT_DOWNSIDE_MAX10_CHAIN_FINANCE_PASS' and audit['months_checked'] == 31, 'INDEPENDENT_PASS_REQUIRED')
    require(audit['finance']['risk_sessions_checked'] == 646, 'AUDIT_646_SESSIONS')
    verify(contract['source_hashes'])
    pinned_book(audit, folder / 'book.json')
    require('asml_timing_limitation' in audit and 'asml_decision_dependency_review' in audit, 'ASML_LIMITATION_AUDIT_REQUIRED')
    name = 'old_continuous_baseline_20261026_v9'
    baseline = ROOT / 'tmp' / name
    original = read(baseline / 'book.json')
    old_audit = read(baseline / 'independent_prefix_review.json')
    require(old_audit['status'] == 'COMPLETE_DECLARED_INTERVAL_REVIEW_PASS' and old_audit['executed_sessions'] == 646, 'BASELINE_FULL_AUDIT')
    require(not old_audit['pending_decision_dates'] and not old_audit['unexecuted_selection_dates'], 'BASELINE_PENDING')
    pinned_book(old_audit, baseline / 'book.json')
    dates = read(baseline / 'execution_inputs.json')['assembled']['session_dates']
    require(len(dates) == 647 and dates[0] == '2023-12-29' and dates[-1] == '2026-07-30', 'FIXED_DATES')
    qdir = ROOT / 'tmp/qqq_fair_hold_20261105'
    qqq, manifest, qaudits = read(qdir / (name + '.json')), read(qdir / 'summary.json'), read(qdir / 'independent_audit.json')
    qaudit = next(a for a in qaudits if a['window'] == name)
    verify_qqq(qqq, manifest, qaudit, dates)
    result = dict(status='COMPLETE_AUDITED_LATE_WINDOW_COMPARISON', window='2024_2026', initial_cash=20000,
                  commission_bps=0, slippage_bps=5, end='2026-07-30', start=dates[0], source_hashes={},
                  asml_timing_limitation=audit['asml_timing_limitation'], asml_decision_dependency_review=audit['asml_decision_dependency_review'],
                  limitations=['Early window remains blocked; this is not a complete bull/bear success.',
                               'Gross dividends; issuer payment conventions are not verified HSBC cash arrival.',
                               'QQQ unpaid gross dividends remain receivable and are not reinvested.',
                               '2026 is partial through July 30; no forced terminal liquidation.'])
    for label, current, rows in [('candidate', book, book['daily_ledger']), ('v27', original, original['daily_ledger']), ('qqq', qqq, qqq['ledger'])]:
        require([r['date'] for r in rows] == dates[1:], label + '_DATES')
        orders = [] if label == 'qqq' else current['order_log']
        if label != 'qqq':
            require(current['status'] == 'COMPLETE' and F(current['fee_bps']) == 0 and F(current['slippage_bps']) == 5, label + '_COSTS')
        fills = [r for r in orders if r.get('event') == 'ASSUMED_NEXT_OPEN_FILLED']
        counts = [sum(F(q) > 0 for q in r['shares'].values()) if isinstance(r['shares'], dict) else int(r['shares'] > 0) for r in rows]
        result[label] = metrics(rows, dates[0], 1 if label == 'qqq' else len(fills))
        result[label]['experience'] = experience(rows, dates[0])
        prior_equity, prior_day = F(20000), dates[0]
        result[label]['calendar_periods'] = {}
        for year in ('2024', '2025', '2026'):
            annual_rows = [r for r in rows if r['date'].startswith(year)]
            normalized = [dict(date=r['date'], equity=F(r['equity']) * 20000 / prior_equity) for r in annual_rows]
            annual_fills = int(year == '2024') if label == 'qqq' else sum(r['date'].startswith(year) for r in fills)
            period = metrics(normalized, prior_day, annual_fills)
            period.update(start_equity=float(prior_equity), end_equity=float(F(annual_rows[-1]['equity'])),
                          return_pct=float(F(annual_rows[-1]['equity']) / prior_equity - 1) * 100,
                          partial=year == '2026', normalized_terminal_base=20000)
            period['experience'] = experience(normalized, prior_day)
            result[label]['calendar_periods'][year] = period
            prior_equity, prior_day = F(annual_rows[-1]['equity']), annual_rows[-1]['date']
        result[label]['actual_holdings'] = dict(minimum=min(counts), maximum=max(counts), median=median(counts), cash_only_sessions=counts.count(0))
        prefix = [r for r in rows if r['date'] <= '2025-12-31']
        result[label]['excluding_2026'] = metrics(prefix, dates[0], 1 if label == 'qqq' else sum(r['date'] <= '2025-12-31' for r in fills))
        result[label]['excluding_2026']['experience'] = experience(prefix, dates[0])
        result[label]['return_pct'] = (result[label]['terminal'] / 20000 - 1) * 100
        result[label]['excluding_2026']['return_pct'] = (result[label]['excluding_2026']['terminal'] / 20000 - 1) * 100
    monthly = {}
    for row in book['provider_audit']:
        day, target = row.get('target_decision_date'), row.get('monthly_ceiling')
        if day and isinstance(target, dict):
            require(day not in monthly or monthly[day] == target, 'MONTHLY_CEILING_CHANGED')
            monthly[day] = target
    require(len(monthly) == 31, '31_MONTHLY_TARGETS_REQUIRED')
    counts = {day: sum(F(q) > 0 for q in target.values()) for day, target in monthly.items()}
    require(max(counts.values()) <= 10, 'MONTHLY_MAX10')
    result['candidate']['monthly_target_holdings'] = dict(counts=counts, maximum=max(counts.values()), scope='Positive monthly ceiling quantities; distinct from daily actual holdings.')
    paths = [folder / n for n in ('contract.json', 'summary.json', 'book.json', 'independent_review.json')]
    paths += [baseline / n for n in ('book.json', 'execution_inputs.json', 'independent_prefix_review.json')]
    paths += [qdir / n for n in (name + '.json', 'summary.json', 'independent_audit.json')]
    paths += [Path(__file__), ROOT/'scripts/research/summarize_cross_month_held_peak_20261105.py', ROOT/'scripts/research/summarize_ema20_market_20261105.py', ROOT/'backtest/research_exact_fraction_json.py']
    result['source_hashes'] = {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in paths}
    for pins in (contract['source_hashes'], audit['source_hashes'], old_audit['source_hashes'], manifest['source_hashes']):
        verify(pins)
    for path, digest in READ_HASHES.items():
        require(sha256(path.read_bytes()).hexdigest() == digest, 'INPUT_CHANGED_DURING_SUMMARY')
    (folder / 'comparison.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    answer = summarize(args.output)
    print(json.dumps({'status': answer['status'], 'output': args.output}, ensure_ascii=False))
