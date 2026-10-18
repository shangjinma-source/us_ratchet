"""Create isolated annual data readiness artifacts, without search or execution."""
import argparse
import gzip
import hashlib
import json
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'tmp/current_expanded_rebased_manifest_20261015_v2.json'
PRIOR = 'tmp/next12_execution_prepare_20261014_v3/prepared.json'
CALENDAR = 'data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin'


def prepare(output):
    output = (ROOT / output).resolve()
    if not output.is_relative_to(ROOT / 'tmp') or output.exists():
        raise ValueError('NEW_TMP_OUTPUT_REQUIRED')
    pins = {}

    def read(name, expected=None):
        raw = (ROOT / name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('SOURCE_DRIFT:' + name)
        pins[name] = digest
        return raw

    def bars(name, ticker, expected=None):
        raw = read(name, expected)
        doc = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw,
                         parse_float=str)['chart']['result'][0]
        if doc['meta']['symbol'] != ticker or doc['meta']['currency'] != 'USD':
            raise ValueError('SOURCE_IDENTITY:' + ticker)
        zone = ZoneInfo(doc['meta']['exchangeTimezoneName'])
        quote = doc['indicators']['quote'][0]
        result = {}
        invalid = []
        for index, timestamp in enumerate(doc['timestamp']):
            day = datetime.fromtimestamp(timestamp, zone).date().isoformat()
            if day in result:
                raise ValueError('DUPLICATE_DATE:' + ticker + day)
            values = {field: quote[field][index] for field in ('open', 'high', 'low', 'close')}
            try:
                op, hi, lo, close = [Fraction(values[k]) for k in ('open', 'high', 'low', 'close')]
                valid = 0 < lo <= min(op, close) <= max(op, close) <= hi
            except (ValueError, TypeError, ZeroDivisionError):
                valid = False
            if not valid:
                invalid.append(day)
            result[day] = values
        return result, invalid, doc.get('events', {})

    manifest = json.loads(read(MANIFEST))
    prior = json.loads(read(PRIOR))
    calendar_bars, invalid_calendar, _ = bars(CALENDAR, 'QQQ')
    if invalid_calendar:
        raise ValueError('INVALID_CALENDAR_QUOTE')
    calendar = sorted(day for day in calendar_bars if day <= '2026-10-13')
    channels = {}
    sources = []
    for row in manifest['candidates']:
        name = row['training_source']
        values, invalid, events = bars(name, row['ticker'], manifest['source_hashes'].get(name))
        channels[row['ticker']] = (values, set(invalid))
        sources.append(dict(ticker=row['ticker'], current_security_id=row['security_id'],
                            issuer_id=row['issuer_id'], path=name, sha256=pins[name],
                            first=min(values), last=max(values), invalid_ohlc_dates=invalid,
                            historical_identity_certified=False,
                            identity_source_references=row.get('identity_source_references', []),
                            coordinate_factors=row.get('price_coordinate_factors', []),
                            true_share_events=row.get('true_share_events', []),
                            provider_split_events=events.get('splits', {})))
    output.mkdir()

    def write(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    boundaries = dict(
        scope='REFERENCES_ONLY_NOT_ANNUAL_EXECUTION_ADMISSION',
        inherited_next12_distributions=prior['distribution_events'],
        inherited_next12_conversions=prior['supported_conversions'],
        current_identity_rows=sources,
        blockers=[
            'CURRENT_IDENTITIES_REQUIRE_DATED_INTERVALS_BEFORE_HISTORICAL_EXECUTION',
            'WDC_SNDK_2025_02_DISTRIBUTION_NOT_IN_NEXT12_EVENT_SET: price factor1323/1000 is not a share entitlement',
            'NON_SIMPLE_FACTOR_ADMISSIONS_CANNOT_AUTOMATICALLY_EXTEND_TO_ALL_ANNUAL_WINDOWS',
            'NEXT12_CHILD_RIGHTS_FRACTIONAL_SETTLEMENT_AND_DELIVERY_GUARDS_REMAIN_APPLICABLE'])
    write('identity_action_boundaries.json', boundaries)
    summaries = []
    for year in (2024, 2025, 2026):
        sessions = [day for day in calendar if day.startswith(str(year))]
        initial_index = calendar.index(sessions[0])
        previous_close = calendar[initial_index - 1]
        eligibility = []
        for fill_day in sessions:
            position = calendar.index(fill_day)
            signal_day = calendar[position - 1]
            training = calendar[max(0, position - 253):position]
            ready, excluded = [], []
            for ticker, (values, invalid) in channels.items():
                missing = [day for day in training if day not in values or day in invalid]
                # Availability is assessed strictly through signal_day, never using future-year coverage.
                if len(training) == 253 and not missing:
                    ready.append(ticker)
                else:
                    excluded.append(dict(ticker=ticker, reason='INSUFFICIENT_VALID_PREDECISION_253_CLOSES',
                                         missing_count=len(missing), missing_dates=missing,
                                         classification='DATA_AVAILABILITY_ONLY_NOT_IPO_ASSERTION'))
            eligibility.append(dict(signal_date=signal_day, earliest_fill_date=fill_day,
                                    training_start=training[0], training_end=training[-1],
                                    required_closes=253, price_history_ready=ready, excluded=excluded,
                                    execution_admitted=False))
        missing_execution = {ticker: [day for day in sessions if day not in values or day in invalid]
                             for ticker, (values, invalid) in channels.items()}
        # Coverage is diagnostic only and never selects the experimental universe.
        write(str(year) + '_calendar.json', dict(year=year, sessions=sessions,
              previous_close=previous_close, calendar_source=CALENDAR,
              calendar_basis='EXACT_PINNED_QQQ_OBSERVED_SESSIONS_NOT_EXCHANGE_CERTIFIED'))
        write(str(year) + '_eligibility.json', eligibility)
        write(str(year) + '_missing_execution_dates.json', missing_execution)
        year_blockers = boundaries['blockers'][:1] + boundaries['blockers'][2:3]
        if year == 2025:
            year_blockers += boundaries['blockers'][1:2]
        if year >= 2025:
            year_blockers += boundaries['blockers'][3:]
        summaries.append(dict(year=year, first=sessions[0], last=sessions[-1], sessions=len(sessions),
                              first_signal=previous_close, first_training_start=eligibility[0]['training_start'],
                              first_history_ready=len(eligibility[0]['price_history_ready']),
                              final_history_ready=len(eligibility[-1]['price_history_ready']),
                              status='DATA_PREPARED_EXECUTION_ADMISSION_BLOCKED', prepared_v4_generated=False,
                              blockers=year_blockers))
    read(Path(__file__).relative_to(ROOT).as_posix())
    write('source_manifest.json', dict(schema='CONDITIONAL_ANNUAL_CURRENT_UNIVERSE_V1',
          universe=manifest['members'], selection_basis='FIXED_CURRENT_OBSERVED_101_SURVIVOR_BIASED',
          source_hashes=pins, sources=sources, full_pit=False, economic_calls=0))
    for name, digest in list(pins.items()):
        read(name, digest)
    write('readiness.json', dict(status='PREPARATION_ONLY_NO_ECONOMIC_RUN', years=summaries,
          no_future_coverage_filter=True, no_ipo_inference=True, network_calls=0, search_calls=0,
          book_calls=0, source_pins_unchanged=True,
          next_step='Review dated identity/coordinate boundaries and WDC entitlement evidence; only then assemble v4. Do not execute partial domain silently.'))
    return summaries


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    arguments = parser.parse_args()
    print(json.dumps(prepare(arguments.output), ensure_ascii=False))
