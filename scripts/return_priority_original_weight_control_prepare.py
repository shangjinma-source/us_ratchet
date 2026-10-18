"""Read saved sources and bind a conditional fixed-weight control; never run a book."""
import gzip
import hashlib
import json
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo


def prepare():
    pins = {}

    def read(path, expected=None):
        raw = Path(path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('Source hash mismatch: ' + str(path))
        pins[str(path)] = digest
        return raw

    proposal_path = 'tmp/next12_original_weight_control_inputs_proposal_20261015_v1.json'
    proposal = json.loads(read(proposal_path))
    for path, digest in proposal['source_hashes'].items():
        read(path, digest)
    prepared = json.loads(read('tmp/next12_execution_prepare_20261014_v3/prepared.json'))
    dates = proposal['session_dates']
    if dates != prepared['session_dates']:
        raise ValueError('Same calendar required')
    rows = []
    for sid, metadata in proposal['metadata'].items():
        provenance = prepared['source_provenance'].get(sid)
        path = provenance['whole_source'] if provenance else (
            'data/cache/research/new_cutoff_raw_capture_20260923_v1/TSM.response.bin')
        expected = prepared['source_hashes'].get(path)
        if expected is None:
            expected = next((v for k,v in proposal['source_hashes'].items()
                             if Path(k) == Path(path)), None)
        if expected is None:
            raise ValueError('Raw source pin missing: ' + path)
        raw = read(path, expected)
        payload = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw,
                             parse_float=str)['chart']['result'][0]
        if payload['meta']['symbol'] != metadata['ticker'] or payload['meta']['currency'] != 'USD':
            raise ValueError('Raw identity/currency mismatch')
        if provenance and provenance['coordinate_factors']:
            raise ValueError('Nonidentity coordinate requires separate review')
        bars = payload['indicators']['quote'][0]
        index = {}
        for i, timestamp in enumerate(payload['timestamp']):
            day = datetime.fromtimestamp(timestamp, ZoneInfo('America/New_York')).date().isoformat()
            if day in index:
                raise ValueError('Duplicate source day')
            index[day] = i
        for day in dates:
            for field in ('open', 'high', 'low', 'close'):
                if Fraction(str(bars[field][index[day]])) != Fraction(proposal['ohlc'][sid][day][field]):
                    raise ValueError('Raw OHLC mismatch: ' + metadata['ticker'] + ' ' + day)
        events = []
        for kind, items in payload.get('events', {}).items():
            for event in items.values():
                day = datetime.fromtimestamp(event['date'], ZoneInfo('America/New_York')).date().isoformat()
                if dates[0] <= day <= dates[-1]:
                    events.append(dict(kind=kind, date=day, payload=event))
        rows.append(dict(security_id=sid, ticker=metadata['ticker'], raw_source=path,
                         checked_ohlc_values=len(dates)*4, returned_events=events))

    fields = ('split_events_reference_only', 'identity_migrations', 'cash_stock_merger_events',
              'distribution_events', 'supported_conversions', 'required_exposure_guards')
    applicable = []
    identities = set(proposal['metadata'])
    for field in fields:
        for event in prepared.get(field, []):
            if any(event.get(key) in identities for key in
                   ('security_id', 'parent_sid', 'post_parent_sid', 'new_security_id', 'child_sid')):
                applicable.append(dict(source_field=field, event=event))
    unexpected = [e for row in rows for e in row['returned_events'] if e['kind'] != 'dividends']
    if applicable or unexpected:
        raise ValueError('Exposed event requires explicit execution binding')
    monthly = []
    for day in proposal['proposed_account']['monthly_decision_dates']:
        monthly.append(dict(decision_date=day, valuation_quotes=[
            dict(security_id=sid, price=proposal['ohlc'][sid][day]['close'])
            for sid in proposal['metadata']], search_arguments=dict(fee_bps='0', minimum_cash_buffer='0'),
            source_hashes=dict(pins)))
    return dict(status='CONDITIONAL_FIXED_WEIGHT_PAYLOAD_NOT_ADMITTED', source_hashes=pins,
        source_audit=rows, applicable_known_events=applicable,
        provider_arguments=dict(weights=proposal['target_weights'], session_dates=dates,
            monthly_inputs=monthly, close_prices={sid:{d:v['close'] for d,v in series.items()}
                for sid,series in proposal['ohlc'].items()}, actions=[]),
        execution_authorized=False, independent_review=False, book_calls=0,
        limitations=['Empty returned actions do not prove complete corporate-action history.',
            'Conditional price-only comparison; returned dividends excluded, not total return.',
            'TSM overlay identity retained; lifecycle completeness not certified.',
            'Research historical closes are not current executable buy advice.'])


if __name__ == '__main__':
    result = prepare()
    destination = Path('tmp/next12_original_weight_control_binding_20261015_v1.json')
    if destination.exists():
        raise SystemExit('Refusing to replace existing evidence')
    destination.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(path=str(destination), securities=len(result['source_audit']),
        monthly_payloads=len(result['provider_arguments']['monthly_inputs']),
        source_pins=len(result['source_hashes']))))
