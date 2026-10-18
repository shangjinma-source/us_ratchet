"""Numerical coverage of sealed provider observations; no raw decoding or price repair."""
import argparse
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path

SOURCE = Path(__file__).resolve()
BASE = SOURCE.parents[1] / 'data/cache/research'
OUTPUT = BASE / 'new_cutoff_completeness_20260923_v1/manifest.json'
BOUND = {
    'readback': ('new_cutoff_raw_readback_20260923_v1/completed102.json', '7c03247919319c8e1a1a12be2fd8ccdba59aec20e0d9ee6634e69cc85fd0d53b'),
    'observation': ('current_quote_list_observation_20260923_v1/observation.json', 'a6d8899fb2bc22f755ecd721271ed173f24a0b959b6ff8da9c96985f940fa990'),
    'plan': ('new_cutoff_raw_capture_20260923_v1/plan.json', '96696abaaa7a8d9dc2765ce436ec2b312af74f4490243a963732bcf26bfedf71'),
}
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
FIELDS = ('open', 'high', 'low', 'close', 'volume', 'adjclose')
OHLC = FIELDS[:4]
OHLCV = FIELDS[:5]
FLAGS = ('http_performed', 'fit_performed', 'raw_decoding_reperformed', 'returns_computed',
         'prices_reconstructed', 'missing_values_filled', 'volume_unit_verified', 'liquidity_admitted',
         'complete_corporate_actions_verified', 'historical_identity_verified',
         'point_in_time_membership_verified', 'exchange_calendar_certified',
         'legal_training_input_admitted', 'promotion_allowed', 'transitive_raw_sources_reverified')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def guard(sources):
    require(sha(SOURCE) == LOADED_SHA, 'Loaded source changed')
    for path, digest in sources.items():
        require(sha(path) == digest, 'Bound source changed: ' + path)


def valid(value, field):
    return type(value) in (int, float) and math.isfinite(value) and (value >= 0 if field == 'volume' else value > 0)


def channel_rows(channel):
    require(channel['readback_status'] == 'RAW_CHANNEL_READBACK_ONLY' and channel['http_status'] == 200,
            'Successful sealed observation required')
    observation = channel['observation']
    require(observation['ticker'] == channel['ticker'], 'Channel ticker mismatch')
    for key in ('prices_reconstructed', 'volume_unit_verified', 'complete_corporate_actions_verified',
                'historical_identity_verified', 'point_in_time_verified', 'legal_training_input_admitted', 'promotion_allowed'):
        require(observation.get(key) is False, 'Observation scope upgraded')
    result = {}
    all_days = []
    for row in observation['rows']:
        day = row['new_york_date']
        require(type(day) is str and date.fromisoformat(day).isoformat() == day and day not in all_days, 'Unique canonical dates required')
        all_days.append(day)
        require(type(row['excluded_receipt_day_or_later']) is bool, 'Exact exclusion boolean required')
        require(row['excluded_receipt_day_or_later'] == (day >= channel['receipt_new_york_day']), 'Receipt exclusion differs')
        values = row['raw_provider_fields']
        require(set(values) == set(FIELDS), 'Exact provider fields required')
        require(sorted(row['missing_fields']) == sorted(key for key, value in values.items() if value is None), 'Missing field declaration differs')
        require(all(value is None or valid(value, key) for key, value in values.items()), 'Invalid numerical provider value')
        if not row['excluded_receipt_day_or_later']:
            result[day] = values
    require(all_days == sorted(all_days), 'Dates must increase')
    require(result, 'No retained observations')
    return result


def coverage(rows, calendar, fields):
    missing_days = [day for day in calendar if day not in rows]
    missing_fields = {day: [field for field in fields if not valid(rows[day][field], field)]
                      for day in calendar if day in rows and any(not valid(rows[day][field], field) for field in fields)}
    complete = len(calendar) - len(missing_days) - len(missing_fields)
    return dict(expected_day_count=len(calendar), complete_day_count=complete, missing_dates=missing_days,
                missing_fields_by_date=missing_fields, numerical_coverage_complete=complete == len(calendar))


def assemble(readback, observation, plan):
    require(readback['schema'] == 'NEW_CUTOFF_INDEPENDENT_RAW_READBACK_V1', 'Wrong raw readback schema')
    require(plan['schema'] == 'NEW_CUTOFF_RAW_CHANNEL_CAPTURE_PREPARATION_V1', 'Wrong capture plan schema')
    members = observation['observed_symbols']
    require(len(members) == len(set(members)) == 101 and not set(members) & {'TSM', 'QQQ', 'SPY'}, 'Exact observed denominator required')
    queue = plan['queue']
    require([row['ticker'] for row in queue] == members + ['TSM', 'QQQ', 'SPY'], 'Exact 104 channel queue required')
    require(type(readback['queue_count']) is int and readback['queue_count'] == 104 and
            type(readback['attempted_prefix_count']) is int and readback['attempted_prefix_count'] == 102, 'Exact attempted denominator required')
    require([row['ticker'] for row in readback['rows']] == members + ['TSM'], 'Exact 102 attempted prefix required')
    require(readback.get('prices_reconstructed') is False and readback.get('promotion_allowed') is False and
            observation.get('point_in_time_membership_verified') is False and observation.get('promotion_allowed') is False,
            'Source scope upgraded')
    channels = {row['ticker']: channel_rows(row) for row in readback['rows']}
    complete_dates = {ticker: [day for day, values in rows.items() if all(valid(values[f], f) for f in OHLCV)]
                      for ticker, rows in channels.items()}
    require(all(days for days in complete_dates.values()), 'Every attempted channel needs a complete numerical day')
    common = sorted(set.intersection(*(set(days) for days in complete_dates.values())))
    require(common and common[-1] == '2026-09-21', 'Sealed observation common latest complete date differs')
    cutoff = common[-1]
    # Select dates before testing numerical completeness: never compress missing bars.
    calendar = [day for day in channels['AAPL'] if day <= cutoff][-127:]
    require(len(calendar) == 127 and coverage(channels['AAPL'], calendar, OHLCV)['numerical_coverage_complete'],
            'AAPL raw date sequence must itself cover 127 complete OHLCV days')
    volume_calendar = calendar[-63:]
    rows = []
    for item in queue:
        ticker = item['ticker']
        role = 'OBSERVED_MEMBER_PROVIDER_CHANNEL' if ticker in members else 'ORIGINAL_INCUMBENT_ONLY' if ticker == 'TSM' else 'OBSERVED_SESSION_REFERENCE_ONLY'
        require(item['role'] == role, 'Channel role differs')
        if ticker not in channels:
            rows.append(dict(ticker=ticker, role=role, status='NOT_ATTEMPTED', reason='OUTSIDE_SEALED_102_ATTEMPT_PREFIX',
                             numerical_coverage_assessed=False))
            continue
        values = channels[ticker]
        later = values.get('2026-09-22')
        require(later is not None and later['close'] is None and later['adjclose'] is None,
                'Sealed September 22 close/adjclose missing condition differs')
        price = coverage(values, calendar, OHLC)
        volume = coverage(values, volume_calendar, ('volume',))
        adjacent = sum(all(day in values and all(valid(values[day][f], f) for f in OHLC) for day in pair)
                       for pair in zip(calendar, calendar[1:]))
        rows.append(dict(ticker=ticker, role=role, status='OBSERVATION_NUMERICAL_COVERAGE_ONLY', numerical_coverage_assessed=True,
                         latest_present_date=max(values), latest_complete_ohlcv_date=complete_dates[ticker][-1],
                         september22=dict(date_present=True, raw_provider_fields=later, complete_ohlcv=False,
                                          missing_fields=[f for f in FIELDS if later[f] is None]),
                         ohlc_127=price, volume_63=volume,
                         return_126_use=dict(expected_adjacent_pairs=126, numerically_available_ohlc_pairs=adjacent,
                                            missing_pair_count=126-adjacent, returns_computed=False,
                                            legal_training_input_admitted=False),
                         volume_unit='UNKNOWN_PROVIDER_UNIT_NO_SPLIT_ADJUSTMENT_ASSUMED'))
    return dict(schema='NEW_CUTOFF_NUMERICAL_COMPLETENESS_MANIFEST_V1', queue_count=104, observed_member_count=101,
                attempted_count=102, incumbent_only_count=1, not_attempted_tickers=['QQQ', 'SPY'],
                candidate_cutoff=cutoff, cutoff_basis='LATEST_COMMON_NUMERICALLY_COMPLETE_OBSERVED_DAY_NOT_EXCHANGE_CERTIFIED',
                reference_calendar_ticker='AAPL', reference_calendar_policy='LAST_127_RAW_OBSERVED_DATES_THEN_VALIDATE_WITHOUT_COMPRESSION',
                observed_reference_calendar_127=calendar, observed_volume_calendar_63=volume_calendar,
                common_complete_dates_diagnostic_only=common, rows=rows,
                summary=dict(ohlc_127_complete_channels=sum(row.get('ohlc_127', {}).get('numerical_coverage_complete', False) for row in rows),
                             volume_63_complete_channels=sum(row.get('volume_63', {}).get('numerical_coverage_complete', False) for row in rows)),
                interpretation='DATE_PRESENCE_IS_NOT_NUMERICAL_COMPLETENESS_AND_NUMERICAL_COVERAGE_IS_NOT_TRAINING_ADMISSION',
                **dict.fromkeys(FLAGS, False))


def build():
    sources = {str(SOURCE): LOADED_SHA}
    docs = {}
    for role, (relative, digest) in BOUND.items():
        path = BASE / relative
        sources[str(path)] = digest
    guard(sources)
    for role, (relative, digest) in BOUND.items():
        raw = (BASE / relative).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == digest, 'Consumed input bytes differ')
        docs[role] = json.loads(raw)
    result = assemble(**docs)
    result['source_hashes'] = sources
    result['input_references'] = {role: dict(path=str(BASE / relative), sha256=digest) for role, (relative, digest) in BOUND.items()}
    guard(sources)
    return result


def publish(value, output):
    require(Path(output).resolve() == OUTPUT.resolve() and not OUTPUT.parent.exists(), 'Fresh fixed namespace required')
    guard(value['source_hashes'])
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    OUTPUT.parent.mkdir(parents=True, exist_ok=False)
    with OUTPUT.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    guard(value['source_hashes'])
    require(OUTPUT.read_bytes() == raw, 'Published bytes differ')
    return dict(path=str(OUTPUT), sha256=sha(OUTPUT))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(publish(build(), args.output)))
