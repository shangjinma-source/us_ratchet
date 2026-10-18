"""Create-only conditional coordinate artifact; no economics or network."""
import gzip
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.annual_simple_split_coordinates import build_coordinates, training_close

PLAN = 'tmp/annual_simple_split_coordinate_plan_20261016_v1/coordinate_plan.json'
SUPPLEMENT = 'tmp/annual_training_split_tri_primary_evidence_20261016_v1/evidence.json'


def prepare(output):
    directory = (ROOT / output).resolve()
    if not directory.is_relative_to(ROOT / 'tmp') or directory.exists():
        raise ValueError('NEW_TMP_DIRECTORY_REQUIRED')
    pins = {}

    def read(path, expected=None):
        raw = (ROOT / path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('SOURCE_DRIFT:' + path)
        pins[path] = digest
        return raw

    plan = json.loads(read(PLAN))
    for path, digest in plan['input_hashes'].items():
        read(path, digest)
    supplement = json.loads(read(SUPPLEMENT))
    for source in supplement['sources']:
        if source.get('raw_path'):
            read(source['raw_path'], source['raw_sha256'])
    additions = {event['ticker']: event for event in supplement['events']
                 if event['kind'] == 'SIMPLE_STOCK_DIVIDEND'}
    rows = []
    for row in plan['rows']:
        ticker = row['ticker']
        events = [dict(event) for event in row['events']]
        if ticker in additions:
            fact = additions[ticker]
            matching = [event for event in events if event['date'] == fact['first_adjusted_session']
                        and event['ratio'] == fact['ratio']]
            if len(matching) != 1:
                raise ValueError('SUPPLEMENT_PROVIDER_MISMATCH:' + ticker)
            matching[0].update(share_event_candidate=True, source_status='SUPPLEMENT_OFFICIAL_WEB_OBSERVATION',
                               source_reference=SUPPLEMENT, official_source_ids=fact['sources'])
        for event in events:
            event['event_id'] = ticker + '_SIMPLE_' + event['date']
        raw = read(row['raw_source'], row['raw_sha256'])
        quote = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw,
                           parse_float=str)['chart']['result'][0]
        if quote['meta']['symbol'] != ticker or quote['meta']['currency'] != 'USD':
            raise ValueError('WRONG_RAW_IDENTITY')
        zone = ZoneInfo(quote['meta']['exchangeTimezoneName'])
        values = quote['indicators']['quote'][0]
        bars = {}
        for index, timestamp in enumerate(quote['timestamp']):
            day = datetime.fromtimestamp(timestamp, zone).date().isoformat()
            if day in bars:
                raise ValueError('DUPLICATE_RAW_DAY')
            bars[day] = {field: values[field][index] for field in ('open', 'high', 'low', 'close')}
        selected = {day: values for day, values in bars.items() if plan['training_start'] <= day <= plan['capture_coordinate_end']}
        result = build_coordinates(ticker=ticker, bars=selected, events=events,
                                   capture_end=plan['capture_coordinate_end'])
        result.update(raw_source=row['raw_source'], current_security_id=row['current_security_id'])
        if result['nominal_ohlc'] is not None:
            # This full series is expressed in final capture units. Each earlier
            # decision must call training_close with its own cutoff instead.
            result['capture_unit_split_neutral_close'] = {
                day: training_close(day=day, decision_date=plan['capture_coordinate_end'],
                                    nominal_close=values['ohlc']['close'], events=events)
                for day, values in result['nominal_ohlc'].items()}
        rows.append(result)
    for path in ('backtest/annual_simple_split_coordinates.py',
                 'scripts/prepare_annual_simple_split_coordinates_20261016.py'):
        read(path)
    for path, digest in list(pins.items()):
        read(path, digest)
    directory.mkdir()
    artifact = dict(schema='ANNUAL_SIMPLE_SPLIT_COORDINATE_COMPONENT_V1',
                    rows=rows, source_hashes=pins, domain_count=len(rows),
                    blocked_tickers=[row['ticker'] for row in rows if row['nominal_ohlc'] is None],
                    complex_tickers_not_in_supplied_domain=['AZN'] if not any(row['ticker'] == 'AZN' for row in rows) else [],
                    economic_calls=0, execution_admitted=False, total_return=False,
                    conditional_provider_adjustment_assumption=True,
                    identity_admission_inherited=False, independent_review_pending=True)
    (directory / 'coordinates.json').write_text(json.dumps(artifact, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in artifact.items() if key not in ('rows', 'source_hashes')}))


if __name__ == '__main__':
    prepare(sys.argv[1])
