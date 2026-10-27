"""Prior-date disclosure screen. Same-day timing and trading remain unresolved."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research.inventory_fundamental_pairs_v1 import build

ROOT = Path(__file__).resolve().parents[2]
inventory_path = ROOT/'tmp/historical_news_coverage_20261027/sec_event_inventory_fiscal_identity_v5.json'
queue_path = ROOT/'tmp/guidance_exposure_queue_20261027/queue.json'
inventory = json.loads(inventory_path.read_bytes())
expanded = deepcopy(inventory)
for window in expanded['windows']:
    for row in window['rows']:
        row['candidate_event_indices'] = list(range(len(
            expanded['issuers'].get(row.get('cik'), {}).get('events', []))))
pairs = build(expanded, json.loads(queue_path.read_bytes()))
output = []
for window, pair_window in zip(inventory['windows'], pairs['windows']):
    reference = window['frozen_book']
    raw = (ROOT/reference['path']).read_bytes()
    if sha256(raw).hexdigest() != reference['sha256']:
        raise ValueError('BOOK_CHANGED')
    book = json.loads(raw)
    decisions = {order['id']: order['decision_date'] for audit in book['provider_audit']
                 for order in audit.get('orders', [])}
    rows = []
    for order in book['order_log']:
        if order.get('event') != 'ASSUMED_NEXT_OPEN_FILLED' or order.get('side') != 'BUY':
            continue
        day = decisions[order['id']]
        records = [record for record in pair_window['records']
                   if record['security_id'] == order['security_id']]
        prior = [record for record in records if datetime.fromisoformat(record['acceptance'])
                 .astimezone(ZoneInfo('America/New_York')).date().isoformat() < day]
        same_day = [record for record in records if datetime.fromisoformat(record['acceptance'])
                    .astimezone(ZoneInfo('America/New_York')).date().isoformat() == day]
        # Latest complete pair is not necessarily the latest disclosure: retain this limitation.
        latest = max(prior, key=lambda record: datetime.fromisoformat(record['acceptance'])) if prior else None
        rows.append(dict(order_id=order['id'], security_id=order['security_id'], decision_date=day,
                         fill_date=order['date'], latest_prior_date_pair=latest,
                         same_day_pairs=same_day))
    negative = [row for row in rows if row['latest_prior_date_pair'] and
                row['latest_prior_date_pair']['both_absolute_changes_negative']]
    output.append(dict(window=window['window'], buys=len(rows), prior_pair_available=sum(
        row['latest_prior_date_pair'] is not None for row in rows),
        negative_prior_pair_count=len(negative), same_day_pair_buys=sum(bool(row['same_day_pairs']) for row in rows),
        negative_prior_pairs=negative, rows=rows))
result = dict(windows=output, signal=False, source_hashes={str(path.relative_to(ROOT)):
    sha256(path.read_bytes()).hexdigest() for path in (inventory_path, queue_path)}, limitations=[
    'Latest available complete pair can be stale or superseded by an unpaired report.',
    'No expiry policy assumed. Same-day events require actual session close review.',
    'Original disclosure, identity, execution calendar and full account branches remain unverified.',
    'This is a data acquisition screen, not an instruction to block any historical or live buy.'])
destination = ROOT/'tmp/fundamental_pair_inventory_20261027/prebuy.json'
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps([{key: value for key, value in window.items() if key not in ('rows', 'negative_prior_pairs')}
                  for window in output]))
for window in output:
    for row in window['negative_prior_pairs']:
        print(row['security_id'], row['decision_date'], row['latest_prior_date_pair']['acceptance'])
