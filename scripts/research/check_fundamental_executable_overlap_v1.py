"""Map existing candidate pairs to actual baseline decision clocks, not trade signals."""
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research.build_news_session_clock_v1 import build as build_clock, event_execution
from scripts.research.inventory_fundamental_pairs_v1 import build as build_pairs


def run(root):
    references = {}
    def read(path, digest=None):
        raw = (root/path).read_bytes()
        actual = sha256(raw).hexdigest()
        if digest is not None and actual != digest:
            raise ValueError('SOURCE_CHANGED')
        references[path] = actual
        return json.loads(raw)
    inventory = read('tmp/historical_news_coverage_20261027/sec_event_inventory_fiscal_identity_v5.json')
    queue = read('tmp/guidance_exposure_queue_20261027/queue.json')
    pairs = build_pairs(inventory, queue)
    clock = build_clock(root)
    results = []
    for source, pair_window in zip(inventory['windows'], pairs['windows']):
        book = read(source['frozen_book']['path'], source['frozen_book']['sha256'])
        inputs = read(source['frozen_inputs']['path'], source['frozen_inputs']['sha256'])
        dates = inputs['assembled']['session_dates']
        audits = book['provider_audit']
        if book['status'] != 'COMPLETE' or len(audits) != len(dates)-1:
            raise ValueError('COMPLETE_DAILY_PROVIDER_HISTORY_REQUIRED')
        by_day = dict(zip(dates[:-1], audits))
        holdings = {row['date']: row['shares'] for row in book['daily_ledger']}
        holdings[dates[0]] = {}  # Both frozen accounts start entirely in cash.
        for day, audit in by_day.items():
            if any(order['decision_date'] != day for order in audit.get('orders', [])):
                raise ValueError('PROVIDER_POSITIONAL_DATE_MISMATCH')
        records = []
        for pair in pair_window['records']:
            timing = event_execution(clock['sessions'], pair['acceptance'])
            if timing is None or timing['decision_date'] not in by_day:
                records.append(dict(pair=pair, timing=timing, status='OUTSIDE_EXECUTABLE_WINDOW'))
                continue
            day, security = timing['decision_date'], pair['security_id']
            audit = by_day[day]
            current_shares = holdings.get(day, {}).get(security, 0)
            target = audit.get('target_shares', {}).get(security, 0)
            buy = any(order['security_id'] == security and order['side'] == 'BUY'
                      for order in audit.get('orders', []))
            records.append(dict(pair=pair, timing=timing, status='BASELINE_SCREEN_ONLY',
                held_at_decision_close=current_shares, effective_target=target, has_buy_order=buy,
                potentially_actionable=bool(current_shares or target or buy)))
        actionable = [row for row in records if row.get('potentially_actionable')]
        results.append(dict(window=source['window'], pairs=len(records),
            actionable_pairs=len(actionable), negative_actionable_pairs=sum(
                row['pair']['both_absolute_changes_negative'] for row in actionable), records=records))
    return dict(windows=results, source_hashes=references, calendar_sources=clock['source_hashes'],
        signal=False, limitations=[
            'SEC acceptance used as availability, not earliest news or historical API availability.',
            'End-of-day holdings are not pre-open quantities after splits or corporate actions.',
            'Potential overlap only; original review and later unpaired filings remain unresolved.',
            'Window-only candidate pairs; pre-window disclosure and ongoing ban duration are separate.',
            'No account branch simulation or performance inference.'])


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    result = run(root)
    output = root/'tmp/fundamental_pair_inventory_20261027/executable_overlap.json'
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps([{key: value for key, value in row.items() if key != 'records'} for row in result['windows']]))
