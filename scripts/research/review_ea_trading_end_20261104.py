"""Classify an observed price gap against a saved exchange action notice.

No price creation, strategy execution, or assumed receipt of merger cash.
"""
from hashlib import sha256
import json
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]


def run():
    folder = ROOT / 'tmp/ea_merger_source_20261104'
    receipt = json.loads((folder / 'receipt.json').read_bytes())
    record = next(row for row in receipt if row['name'] == 'nasdaq')
    raw = (folder / 'nasdaq.html').read_bytes()
    assert record['http_status'] == 200 and sha256(raw).hexdigest() == record['sha256']
    text = ' '.join(BeautifulSoup(raw, 'html.parser').stripped_strings)
    for fact in ('Symbol: EA', 'Last Trading Date: August 4, 2026',
                 'Marketplace Effective Date for Suspension: August 5, 2026',
                 'Merger Consideration: $210 for each share held.'):
        assert fact in text, fact
    path = ROOT / 'tmp/post_july_inventory_20261104/local_gap.json'
    inventory = json.loads(path.read_bytes())
    row = next(row for row in inventory['rows'] if row['ticker'] == 'EA')
    missing = set(row['august_missing_dates'])
    if not row['has_decision_bar']:
        missing.add('2026-07-31')
    result = dict(
        ticker='EA', last_trading_date='2026-08-04', suspension_date='2026-08-05',
        merger_consideration_usd='210',
        missing_before_suspension=sorted(day for day in missing if day < '2026-08-05'),
        no_exchange_ohlc_expected=sorted(day for day in missing if day >= '2026-08-05'),
        source_url=record['url'], source_sha256=record['sha256'],
        inventory_sha256=sha256(path.read_bytes()).hexdigest(),
        scope='Modern updated exchange notice; not historical first-version certification. '
              'Cash entitlement, payment timing and strategy admission remain unmodelled. '
              'This does not certify the July index membership or missing pre-suspension prices.',
        prices_created=False, production_changed=False,
    )
    (folder / 'gap_review.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    run()
