"""Reconcile five old identity exclusions with later saved evidence; no admission."""
import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def main():
    pins = {}

    def read(name):
        path = ROOT / name
        raw = path.read_bytes()
        pins[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    acceptance = read('tmp/current_quantity_domain_acceptance_20261014_v2.json')
    admission = read('tmp/next12_identity_admission_20261014_v1/identity_admission.json')
    for name, expected in admission['source_hashes'].items():
        path = ROOT / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('Changed identity source: '+name)
        pins[str(path)] = actual
    panel = read('tmp/current_ohlc_actual_projection_20261014_v1/panel.json')
    days = panel['calendar'][-253:]
    assert len(days) == 253 and days[-1] == acceptance['decision_date'] == '2026-10-13'
    stocks = {row['ticker']: row for row in panel['stocks']}
    rows = []
    for ticker in ['TER', 'RKLB', 'ALAB', 'SNDK', 'CRWV']:
        records = [row for row in admission['rows'] if row['ticker'] == ticker]
        identities = {(row['security_id'], row['issuer_id']) for row in records}
        assert len(identities) == 1 and all(row['identity_reviewed'] and not row['unresolved'] for row in records)
        identity = max(records, key=lambda row: row['decision_date'])
        sid, issuer = next(iter(identities))
        cik = issuer.split(':')[1]
        subject = read(f'data/cache/research/current_nine_identity_capture_20260919_v1/{cik}.response.bin')
        assert str(subject['cik']).zfill(10) == cik and ticker in subject['tickers']
        assert sid == 'security:'+cik+':'+identity['cusip']
        path = ROOT/f'data/cache/research/current_raw_capture_20261014_v1/{ticker}.response.bin'
        raw = path.read_bytes(); pins[str(path)] = hashlib.sha256(raw).hexdigest()
        quote = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)['chart']['result'][0]
        meta = quote['meta']
        assert meta['symbol'] == ticker and meta['currency'] == 'USD' and meta['instrumentType'] == 'EQUITY'
        timezone = ZoneInfo(meta['exchangeTimezoneName'])
        dates = [datetime.fromtimestamp(value, timezone).date().isoformat() for value in quote['timestamp']]
        assert len(dates) == len(set(dates))
        closes = dict(zip(dates, quote['indicators']['quote'][0]['close']))
        values = [row[3] for row in stocks[ticker]['values'][-253:]]
        assert values == [closes[day] for day in days] and all(type(value) in (int, float) and value > 0 for value in values)
        events = {kind: list(entries.values()) for kind, entries in quote.get('events', {}).items()}
        rows.append(dict(ticker=ticker, security_id=sid, issuer_id=issuer,
                         old_exclusion=acceptance['excluded_reasons'][ticker],
                         identity_evidence_cutoff=identity['decision_date'],
                         dated_security_evidence=identity['dated_security_evidence'],
                         security_class=identity['security_class'], issuer_name=subject['name'],
                         matched_raw_closes=253, provider_returned_events=events,
                         status='EXISTING_IDENTITY_JOIN_FOUND_CURRENT_ADMISSION_PENDING',
                         remaining=['Review identity continuity from prior cutoff to2026-10-13.',
                                    'Review provider price coordinate over the full training window.',
                                    'Empty returned events do not certify absence of corporate actions.'],
                         point_in_time_certified=False, automatically_admitted=False))
    report = dict(status='FIVE_STALE_EXCLUSION_REASONS_RECONCILED_NOT_POOL_ADMISSION',
                  decision_date=days[-1], training_start=days[0], rows=rows,
                  prior_accepted_securities=94, potential_identity_plus_close_securities=99,
                  full_denominator=101, remaining_short_history=['SPCX', 'HONA'],
                  source_hashes=pins, search_calls=0, book_calls=0, network_calls=0,
                  accepted_domain_modified=False)
    output = ROOT/'tmp/current_five_identity_reconciliation_20261015_v1.json'
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(dict(output=str(output), source_pins=len(pins),
                          matched_raw_closes=sum(row['matched_raw_closes'] for row in rows))))


if __name__ == '__main__':
    main()
