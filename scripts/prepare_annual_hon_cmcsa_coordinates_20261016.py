"""Map two complex parents without extending sealed event admission."""
import gzip
import hashlib
import json
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PRIOR = 'tmp/next12_execution_prepare_20261014_v3/prepared.json'
TRAINING = 'tmp/next12_training_prepare_20261014_v1/prepared.json'
ADMISSION = 'tmp/next12_nonsimple_final_admission_20261014_v1.json'
ANNUAL = 'tmp/conditional_calendar_year_inputs_20261016_v2/source_manifest.json'


def prepare(output):
    directory = (ROOT / output).resolve()
    if not directory.is_relative_to(ROOT / 'tmp') or directory.exists():
        raise ValueError('NEW_TMP_OUTPUT_REQUIRED')
    pins = {}

    def read(path, expected=None):
        raw = (ROOT / path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('SOURCE_DRIFT:' + path)
        if path in pins and pins[path] != digest:
            raise ValueError('PIN_CONFLICT')
        pins[path] = digest
        return raw

    prior = json.loads(read(PRIOR))
    for path, digest in prior['source_hashes'].items():
        read(path, digest)
    training = json.loads(read(TRAINING))
    admission = json.loads(read(ADMISSION))
    annual = json.loads(read(ANNUAL))
    annual_sources = {row['ticker']: row for row in annual['sources']}
    output_rows = []
    checked_nominal = checked_training = 0
    for ticker in ('HON', 'CMCSA'):
        coordinate = admission['tickers'][ticker]
        source = annual_sources[ticker]
        if source['path'] != coordinate['source_path']:
            raise ValueError('ANNUAL_WHOLE_SOURCE_DIFFERS')
        raw = read(source['path'], source['sha256'])
        parsed = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw,
                            parse_float=str)['chart']['result'][0]
        if parsed['meta']['symbol'] != ticker:
            raise ValueError('WRONG_TICKER')
        zone = ZoneInfo(parsed['meta']['exchangeTimezoneName'])
        quote = parsed['indicators']['quote'][0]
        rows = {}
        for index, timestamp in enumerate(parsed['timestamp']):
            day = datetime.fromtimestamp(timestamp, zone).date().isoformat()
            if not '2022-12-28' <= day <= '2026-10-13':
                continue
            factor = Fraction(1)
            divisor = Fraction(1)
            for event in coordinate['price_coordinate_factors']:
                if day < event['date']:
                    factor *= Fraction(event['factor'])
            for event in coordinate['true_share_events']:
                if day < event['date']:
                    divisor *= Fraction(event['ratio'])
            nominal = {field: Fraction(quote[field][index]) * factor
                       for field in ('open', 'high', 'low', 'close')}
            if not 0 < nominal['low'] <= min(nominal['open'], nominal['close']) <= max(nominal['open'], nominal['close']) <= nominal['high']:
                raise ValueError('INVALID_NOMINAL_OHLC')
            matches = []
            for sid, metadata in prior['metadata'].items():
                if metadata['ticker'] == ticker and day in prior['ohlc'][sid]:
                    if any(nominal[field] != Fraction(prior['ohlc'][sid][day][field]) for field in nominal):
                        raise ValueError('PRIOR_OHLC_MISMATCH')
                    matches.append(sid)
                    checked_nominal += 1
            rows[day] = dict(nominal_ohlc={field: str(value) for field, value in nominal.items()},
                             training_capture_unit_close=str(nominal['close'] / divisor),
                             coordinate_factor=str(factor), true_share_divisor=str(divisor),
                             prior_execution_identity_matches=matches,
                             scope='EXACT_PRIOR_EXECUTION_MAPPING' if matches else 'PENDING_ANNUAL_EXTENSION_ADMISSION')
        training_matches = []
        for window in training['windows']:
            candidate = next(row for row in window['candidates'] if row['ticker'] == ticker)
            for day, expected in zip(window['training_dates'], candidate['training_close']):
                if Fraction(rows[day]['training_capture_unit_close']) != Fraction(expected):
                    raise ValueError('PRIOR_TRAINING_MISMATCH')
                checked_training += 1
            training_matches.append(dict(decision=window['decision_cutoff'],
                                         first=window['training_dates'][0], last=window['training_dates'][-1]))
        events = [event for event in prior['distribution_events']
                  if prior['metadata'][event['parent_sid']]['ticker'] == ticker]
        child_ids = {event['child_sid'] for event in events}
        children = {name: value for name, value in prior['child_instruments'].items()
                    if value['security_id'] in child_ids}
        output_rows.append(dict(ticker=ticker, status='ANNUAL_MAPPING_CANDIDATE_NOT_EXECUTION_ADMISSION',
             raw_source=source['path'], source_equal_to_next12=True, rows=rows,
             price_coordinate_factors=coordinate['price_coordinate_factors'],
             true_share_events=coordinate['true_share_events'], prior_training_matches=training_matches,
             prior_event_candidates=events, child_instruments=children,
             fractional_cash_values=prior['distribution_fractional_cash_values'],
             blocked_extension_intervals=[dict(start='2022-12-28', end='2025-07-30',
                    reason='COMPUTED_COORDINATES_ONLY_PRIOR_EXECUTION_ADMISSION_NOT_EXTENDED'),
                 dict(start='2026-07-31', end='2026-10-13',
                    reason='POST_NEXT12_COORDINATES_IDENTITY_ACTION_ABSENCE_NOT_CERTIFIED')],
             constraints=['PRICE_FACTORS_NEVER_CHANGE_QUANTITY', 'CHILD_RIGHTS_NOT_AVAILABLE_CASH',
                'FRACTIONAL_NET_CASH_UNKNOWN_MUST_GUARD', 'CHILD_DELIVERY_UNKNOWN_NONTRADABLE',
                'HON_ODD_PARENT_REVERSE_FRACTION_REQUIRES_SETTLEMENT' if ticker == 'HON' else
                'CMCSA_JAN2_AFTER_CLOSE_RIGHTS_AND_JAN5_PRICE_COORDINATE_ARE_DISTINCT'],
             total_return=False, ordinary_dividends_included=False))
    read(Path(__file__).relative_to(ROOT).as_posix())
    for path, digest in list(pins.items()):
        read(path, digest)
    directory.mkdir()
    result = dict(schema='ANNUAL_HON_CMCSA_MAPPING_CANDIDATE_V1', rows=output_rows,
                  source_hashes=pins, checked_prior_nominal_rows=checked_nominal,
                  checked_prior_training_values=checked_training, economic_calls=0,
                  independent_review_pending=True, execution_admitted=False)
    (directory / 'mapping_candidate.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(pins=len(pins), nominal_checks=checked_nominal,
                         training_checks=checked_training, execution_admitted=False)))


if __name__ == '__main__':
    prepare(sys.argv[1])
