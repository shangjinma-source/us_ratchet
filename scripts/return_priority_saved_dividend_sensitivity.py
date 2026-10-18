"""Derive dividend sensitivity from sealed books, never rerun portfolio trades."""
from datetime import datetime
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from backtest.return_priority_dividend_accrual_diagnostic import diagnose_dividend_accrual, PRICE_BASIS

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tmp/joint_family_experiment_20261014_v1'
OUTPUT = ROOT / 'tmp/saved_dividend_sensitivity_20261014_v1'


def main():
    sources = {}

    def read(path, expected=None):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None:
            assert digest == expected, str(path)
        sources[str(path.relative_to(ROOT))] = digest
        return raw

    result = json.loads(read(SOURCE / 'result.json', 'd59604d82d4398d9165373f70d6010c87150a387358b04695b4bd2f4a9a872ea'))
    snapshots = json.loads(read(SOURCE / 'frozen_candidate_snapshots.json', result['frozen_candidates_sha256']))
    blocks = []
    for index in range(4):
        receipt = json.loads(read(SOURCE / f'block_{index}_receipt.json'))
        blocks.append(json.loads(read(SOURCE / f'block_{index}.json', receipt['sha256'])))
    metadata = {}
    for snapshot in snapshots:
        for candidate in snapshot['records']:
            for security, row in candidate.get('metadata', {}).items():
                if security in metadata:
                    assert metadata[security] == row['ticker']
                metadata[security] = row['ticker']
    rules = [row['rule'] for row in result['rankings']]
    assert len(rules) == 46
    held = {security for block in blocks for rule in rules if 'book' in block[rule]
            for row in block[rule]['book']['daily_rows'] for security in row['shares']}
    events, splits, raw_audit = [], [], []
    panel = json.loads(read(ROOT / 'tmp/current_ohlc_actual_projection_20261013_v1/panel.json',
                           '92361a7321765594a5544ab3cb9128410c8296799d99b3d23090e24a37df9822'))
    panel_rows = {row['ticker']: row for row in panel['stocks']}
    for security in sorted(held):
        ticker = metadata[security]
        raw = read(ROOT / f'data/cache/research/current_raw_capture_20261013_v1/{ticker}.response.bin')
        data = json.loads(gzip.decompress(raw))['chart']['result'][0]
        assert data['meta']['symbol'] == ticker and data['meta']['currency'] == 'USD'
        timezone = ZoneInfo(data['meta']['exchangeTimezoneName'])
        def day(timestamp):
            return datetime.fromtimestamp(timestamp, timezone).date().isoformat()
        closes = {day(timestamp): close for timestamp, close in
                  zip(data['timestamp'], data['indicators']['quote'][0]['close'])}
        for session, values in zip(panel['calendar'], panel_rows[ticker]['values']):
            assert closes.get(session) == values[3], (ticker, session)
        returned = data.get('events', {})
        for key, event in returned.get('dividends', {}).items():
            events.append(dict(id=f'{security}:{key}', security_id=security,
                               event_date=day(event['date']), amount_per_share=str(event['amount'])))
        for event in returned.get('splits', {}).values():
            splits.append(dict(security_id=security, ticker=ticker, event_date=day(event['date']),
                               ratio=event['splitRatio']))
        raw_audit.append(dict(ticker=ticker, security_id=security,
                              returned_dividend_count=len(returned.get('dividends', {})),
                              quote_close_panel_matched=True, payment_dates_available=False))
    read(ROOT / 'backtest/return_priority_dividend_accrual_diagnostic.py',
         '1b9cd616b88c302cf2eacbb372d375fd5d92dcf4946ad34a8a64b10e09c385df')
    read(Path(__file__))
    OUTPUT.mkdir(exist_ok=False)
    def save(name, value):
        with (OUTPUT / name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2)
    save('registration.json', dict(sources=sources, rules=rules, initial_equity='20000',
                                  initial_shares={}, scope='FIXED_TRADES_GROSS_ACCRUAL_SENSITIVITY',
                                  unit_basis='ASSUMED_NOT_AUTHENTICATED', historical_fee_bps=10,
                                  changes_current_zero_commission=False, strategy_runs=0, book_calls=0))
    derived, summaries = {}, []
    for rank, original in enumerate(result['rankings'], 1):
        rule = original['rule']
        outcomes = []
        derived[rule] = []
        for index, block in enumerate(blocks):
            value = block[rule]
            if value['status'] == 'COMPLETE_ALL_CASH_REFERENCE':
                outcomes.append(dict(net_return=0., gross_accrual='0', drawdown=0., returned_split_exposure=[]))
                derived[rule].append(dict(status='UNCHANGED_ALL_CASH_REFERENCE'))
                continue
            book = value['book']
            rows = book['daily_rows']
            assert rows[0]['shares'] == {} and Fraction(rows[0]['cash']) == 20000
            assert Fraction(rows[0]['close_equity']) == 20000
            owned = {security for row in rows for security in row['shares']}
            selected_events = [event for event in events if event['security_id'] in owned]
            diagnostic = diagnose_dividend_accrual(book=book, events=selected_events, initial_shares={},
                                                  initial_equity=20000, price_basis=PRICE_BASIS,
                                                  same_share_unit_basis=True)
            exposure = [split for split in splits if split['security_id'] in owned
                        and rows[0]['session'] <= split['event_date'] <= rows[-1]['session']]
            diagnostic['returned_split_exposure'] = exposure
            diagnostic['block_index'] = index
            derived[rule].append(diagnostic)
            outcomes.append(dict(net_return=float(Fraction(diagnostic['derived_net_return'])),
                                 gross_accrual=diagnostic['cumulative_gross_entitlement'],
                                 drawdown=-float(Fraction(diagnostic['derived_max_drawdown'])),
                                 returned_split_exposure=exposure))
        mean = sum(math.log1p(row['net_return']) for row in outcomes) / 4
        summaries.append(dict(rule=rule, original_rank=rank, original_mean_log_return=original['mean_net_log_return'],
                              diagnostic_mean_log_return=mean, blocks=outcomes,
                              mean_log_change=mean-original['mean_net_log_return'],
                              has_returned_split_exposure=any(row['returned_split_exposure'] for row in outcomes)))
    summaries.sort(key=lambda row: (-row['diagnostic_mean_log_return'], row['rule']))
    for rank, row in enumerate(summaries, 1):
        row['diagnostic_rank'] = rank
    clean = [row for row in summaries if not row['has_returned_split_exposure']]
    old_clean = sorted(clean, key=lambda row: row['original_rank'])
    for path, expected in sources.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    save('derived_books.json', derived)
    save('source_events.json', dict(events=events, splits=splits, raw_audit=raw_audit))
    save('result.json', dict(status='COMPLETE_CONDITIONAL_SENSITIVITY_NOT_RERANKED_STRATEGY',
                            summaries=summaries, original_top=rules[0], diagnostic_top=summaries[0]['rule'],
                            changed_rank_count=sum(row['original_rank'] != row['diagnostic_rank'] for row in summaries),
                            no_returned_split_rule_count=len(clean),
                            no_returned_split_relative_order_changed=[row['rule'] for row in clean] != [row['rule'] for row in old_clean],
                            derived_book_count=180, unchanged_cash_references=4, book_calls=0, strategy_runs=0,
                            ranking_changes_applied=False, original_sources_unchanged=True,
                            conditional_same_unit_assumption=True, complete_dividend_coverage_verified=False,
                            total_return_certified=False, payment_dates_verified=False,
                            taxes_included=False, reinvestment_performed=False, independent_oos=False,
                            source_refs=sources))
    print(json.dumps(dict(top=summaries[0]['rule'], changed_ranks=sum(row['original_rank'] != row['diagnostic_rank'] for row in summaries),
                          no_split_rules=len(clean), derived_books=180)))


if __name__ == '__main__':
    main()
