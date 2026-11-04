"""Inventory existing research decisions; no new backtest or live-account access."""
import json
from hashlib import sha256
from pathlib import Path


def inventory(root):
    windows = []
    for window in ('2021_2023', '2024_2026'):
        path = root / f'tmp/reentry_repair_20261029/candidate_{window}/book.json'
        raw = path.read_bytes()
        book = json.loads(raw)
        intervals = {}
        mixed_buy_filter_decisions = []
        for decision in book['reentry_audit']:
            original_buys = [order for order in decision.get('original', {}).get('orders', []) if order['side'] == 'BUY']
            adjusted_buys = [order for order in decision.get('adjusted', {}).get('orders', []) if order['side'] == 'BUY']
            removed = [order for order in original_buys if order not in adjusted_buys]
            if removed and adjusted_buys:
                mixed_buy_filter_decisions.append(dict(
                    decision_session=decision['decision_date'],
                    removed_buys=removed, retained_buys=adjusted_buys))
            for review in decision.get('interval_reviews', []):
                lock, proof = review['lock'], review['proof']
                key = (lock['security_id'], lock['exit_date'], lock['epoch'])
                item = intervals.setdefault(key, dict(
                    security_id=key[0], exit_session=key[1], epoch=key[2],
                    reference_price=lock['reference_price'],
                    first_review=decision['decision_date'], last_review=None,
                    recovered_session=None, recovery_observed_on=None,
                    source_hashes={}, coverage_scopes=[], conversions=[]))
                item['last_review'] = decision['decision_date']
                for name, digest in proof.get('source_hashes', {}).items():
                    previous = item['source_hashes'].setdefault(name, digest)
                    if previous != digest:
                        raise ValueError(f'Changed source within interval: {name}')
                for coverage in proof.get('coverage', []):
                    scope = coverage.get('evidence_scope')
                    if scope and scope not in item['coverage_scopes']:
                        item['coverage_scopes'].append(scope)
                for row in proof.get('completed_rows', []):
                    if row.get('conversion'):
                        conversion = dict(session=row['date'], value=row['conversion'])
                        if conversion not in item['conversions']:
                            item['conversions'].append(conversion)
                if review.get('recovered_at'):
                    item['recovered_session'] = review['recovered_at']
                    item['recovery_observed_on'] = decision['decision_date']
        unreviewed = []
        for lock in book['reentry_locks'].values():
            key = (lock['security_id'], lock['exit_date'], lock['epoch'])
            if key not in intervals:
                unreviewed.append(dict(security_id=key[0], exit_session=key[1], epoch=key[2],
                                       reason='NO_INTERVAL_REVIEW_IN_SAVED_AUDIT'))
        items = sorted(intervals.values(), key=lambda item: (item['exit_session'], item['security_id']))
        windows.append(dict(window=window, book_path=path.relative_to(root).as_posix(),
                            book_sha256=sha256(raw).hexdigest(), intervals=items,
                            recovered_intervals=sum(item['recovered_session'] is not None for item in items),
                            remaining_locks=len(book['reentry_locks']),
                            remaining_unreviewed_locks=unreviewed,
                            mixed_buy_filter_decisions=mixed_buy_filter_decisions))
    return dict(schema='REENTRY_RESEARCH_INTERVAL_INVENTORY_V1', windows=windows,
                production_authorization=False, source_completeness_certified=False,
                new_backtests=0, account_mutated=False)


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    result = inventory(root)
    output = root / 'tmp/strategy_fit_20261104/reentry_interval_inventory.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    for window in result['windows']:
        print(window['window'], 'reviewed intervals:', len(window['intervals']),
              'recovered:', window['recovered_intervals'], 'remaining:', window['remaining_locks'])
        for item in window['intervals']:
            if item['recovered_session']:
                print(item['security_id'], item['exit_session'], item['recovered_session'],
                      'observed:', item['recovery_observed_on'], 'conversions:', len(item['conversions']))
