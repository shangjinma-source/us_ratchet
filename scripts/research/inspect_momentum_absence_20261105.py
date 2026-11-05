"""Inspect five existing captures; does not admit events or execute a strategy."""
import gzip
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]


def run():
    inventory_path = ROOT / 'tmp/momentum_action_inventory_20261105/inventory.json'
    inventory = json.loads(inventory_path.read_bytes())
    document_path = ROOT / 'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json'
    document = json.loads(document_path.read_bytes())
    pins = inventory['source_hashes']
    records = []
    source_hashes = {}
    for item in inventory['unique_remaining']:
        if item['window'] != '2024_2026' or item['category'] != 'missing_action_streams':
            continue
        event = item['event']; ticker = event['ticker']; source = event['source']
        raw = (ROOT / source).read_bytes()
        assert sha256(raw).hexdigest() == pins[source]
        receipt_path = source.replace('.response.bin', '.receipt.json')
        started_path = source.replace('.response.bin', '.started.json')
        receipt = json.loads((ROOT / receipt_path).read_bytes())
        started = json.loads((ROOT / started_path).read_bytes())
        assert sha256(raw).hexdigest() == receipt['raw_sha256'] and len(raw) == receipt['raw_bytes']
        assert receipt['http_status'] == 200 and receipt['credentials_sent'] is False
        assert receipt['request_url'] == receipt['final_url'] == started['request_url']
        assert receipt['started_at_utc'] == started['started_at_utc']
        assert not receipt.get('body_truncated', False)
        url = urlparse(receipt['request_url']); query = parse_qs(url.query)
        assert url.scheme == 'https' and url.hostname == 'query1.finance.yahoo.com'
        assert url.path == '/v8/finance/chart/' + ticker
        assert query['events'] == ['div,splits'] and query['interval'] == ['1d']
        decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
        if 'decoded_sha256' in receipt:
            assert sha256(decoded).hexdigest() == receipt['decoded_sha256']
        chart = json.loads(decoded)['chart']; assert chart['error'] is None and len(chart['result']) == 1
        result = chart['result'][0]; assert result['meta']['symbol'] == ticker
        assert result['meta']['instrumentType'] == 'EQUITY'
        assert not result.get('events')
        if 'returned_events' in receipt:
            assert not receipt['returned_events']
        days = [datetime.fromtimestamp(t, ZoneInfo('America/New_York')).date().isoformat() for t in result['timestamp']]
        assert days == sorted(set(days))
        if 'rows' in receipt:
            assert len(days) == receipt['rows']
        periods = [r for r in inventory['rows'] if r['window'] == '2024_2026' and r['decision_date'] in item['decision_dates']]
        begin = min(r['decision_date'] for r in periods)
        end = max(r['reviewed_inventory']['exposure_end_by_security'][event['security_id']] for r in periods)
        required = [d for d in document['assembled']['session_dates'] if begin <= d <= end]
        start_epoch, end_epoch = int(query['period1'][0]), int(query['period2'][0])
        assert datetime.fromtimestamp(start_epoch, ZoneInfo('America/New_York')).date().isoformat() <= begin
        assert datetime.fromtimestamp(end_epoch, ZoneInfo('America/New_York')).date().isoformat() > end
        lookup = {day: index for index, day in enumerate(days)}
        assert set(required) <= set(lookup)
        for field in ('open', 'high', 'low', 'close'):
            values = result['indicators']['quote'][0][field]
            assert len(values) == len(days) and all(values[lookup[d]] is not None and values[lookup[d]] > 0 for d in required)
        records.append(dict(ticker=ticker, security_id=event['security_id'], source=source,
                            start=begin, end=end, sessions_checked=len(required),
                            legacy_receipt='body_truncated' not in receipt,
                            receipt_event_summary_present='returned_events' in receipt,
                            receipt_row_count_present='rows' in receipt,
                            gzip_crc_checked=raw[:2] == b'\x1f\x8b', events_omitted='events' not in result))
        for name in (source, receipt_path, started_path):
            source_hashes[name] = sha256((ROOT / name).read_bytes()).hexdigest()
    assert len(records) == 5
    for path in (inventory_path, document_path, Path(__file__)):
        source_hashes[path.relative_to(ROOT).as_posix()] = sha256(path.read_bytes()).hexdigest()
    output = ROOT / 'tmp/momentum_absence_inspection_20261105'
    output.mkdir(exist_ok=False)
    report = dict(status='CAPTURES_INSPECTED_NOT_ADMITTED', records=records, source_hashes=source_hashes,
                  limitation='Conditional provider div/split absence only. No official exhaustive action proof, identity certification, new events, or account execution. Legacy normalization and independent admission review remain required.')
    (output / 'inspection.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(dict(status=report['status'], records=records)))


if __name__ == '__main__':
    run()
