"""Pure current-byte observation planning with explicit TZif and baseline bytes."""
import csv
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import io
import json
from zoneinfo import ZoneInfo

MAX_BYTES = 8_000_000
FIELDS = ('Date', 'Open', 'High', 'Low', 'Close', 'Volume')
FALSE = {key: False for key in ('candidate_seal_allowed', 'cohort_registration_allowed',
    'decision_eligible', 'canonical_calendar_append_allowed', 'source_price_execution_verified',
    'exchange_holidays_verified', 'early_closes_verified', 'authentic_clock_verified',
    'point_in_time_verified', 'promotion_allowed', 'live_mutation_allowed',
    'oos_recovery_completed', 'historical_first_observation_claimed', 'fresh_observation')}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def decimal_text(value):
    if value == 0:
        return '0'
    text = format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def session(value):
    require(type(value) is str, 'Date string required')
    parsed = date.fromisoformat(value)
    require(parsed.isoformat() == value and parsed.weekday() < 5, 'Canonical weekday required')
    return parsed


def parse(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, 'Bounded nonempty CSV bytes required')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
    require(reader.fieldnames == list(FIELDS), 'Exact OHLCV header required')
    rows = {}; previous = ''
    for row in reader:
        require(set(row) == set(FIELDS) and all(type(v) is str and v.strip() == v and v for v in row.values()), 'Complete canonical CSV row required')
        session(row['Date']); require(row['Date'] > previous, 'Unique ascending dates required')
        previous = row['Date']; values = {}
        for field in FIELDS[1:]:
            require(len(row[field]) <= 100, 'Numeric text bound')
            value = Decimal(row[field])
            require(value.is_finite() and len(value.as_tuple().digits) <= 50 and
                    -50 <= value.as_tuple().exponent <= 50, 'Finite bounded decimal required')
            require(value >= 0 if field == 'Volume' else value > 0, 'Invalid price or volume')
            values[field] = value
        require(values['Low'] <= min(values['Open'], values['Close']) and
                values['High'] >= max(values['Open'], values['Close']) and
                values['Low'] <= values['High'], 'OHLC bounds violated')
        normalized = {'Date': row['Date'], **{key: decimal_text(values[key]) for key in FIELDS[1:]}}
        rows[row['Date']] = {'normalized_ohlcv': normalized,
            'normalized_row_sha256': sha(canonical(normalized)), 'raw_csv_row': dict(row)}
    require(rows and len(rows) <= 20000, 'Bounded source rows required')
    return rows


def plan_forward_source_capture(*, frontier, source_csv_bytes, baseline_csv_bytes,
                                tzif_bytes, capture_started_at_utc, observed_at_utc):
    require(type(frontier) is dict and frontier.get('schema') == 'OBSERVATION_GAP_FRONTIER_RESEARCH_V1', 'Frontier schema')
    for key in ('fresh_observation', 'decision_eligible', 'candidate_seal_allowed',
                'cohort_registration_allowed', 'point_in_time_verified', 'oos_recovery_completed'):
        require(frontier.get(key) is False, 'Frontier permissions changed')
    require(frontier.get('month_first_semantics') == 'UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE', 'Monthly boundary changed')
    known = frontier['known_accounted_rows']
    require(type(known) is list and known, 'Accounted prefix required')
    accounted = [row['session'] for row in known]
    require(accounted == sorted(set(accounted)), 'Unique ordered accounted prefix')
    for value in accounted: session(value)
    require(frontier['last_accounted_session'] == accounted[-1], 'Accounted tail changed')
    observed_rows = [row['session'] for row in known if row['kind'] == 'SEALED_PARENT_OBSERVED_SESSION']
    gaps = [row for row in known if row['kind'] == 'MISSED_OBSERVATION']
    require(observed_rows and len(observed_rows)+len(gaps) == len(known) and
            accounted == observed_rows+[row['session'] for row in gaps] and
            frontier['last_observed_session'] == observed_rows[-1], 'Observed/gap roles changed')
    require(all(row.get('counts_as_observed_session') is False and row.get('decision_eligible') is False for row in gaps), 'Gap privilege changed')
    for field, count in (('parent_observed_session_count',len(observed_rows)),('accounted_gap_count',len(gaps))):
        require(type(frontier[field]) is int and frontier[field] == count, 'Frontier count changed')
    require(type(tzif_bytes) is bytes and 0 < len(tzif_bytes) <= MAX_BYTES, 'TZif bytes required')
    zone = ZoneInfo.from_file(io.BytesIO(tzif_bytes))
    require(type(observed_at_utc) is str, 'Explicit UTC clock required')
    observed = datetime.fromisoformat(observed_at_utc)
    require(observed.tzinfo is not None and observed.utcoffset() == timedelta(0), 'UTC required')
    require(type(capture_started_at_utc) is str, 'Explicit capture start required')
    started = datetime.fromisoformat(capture_started_at_utc)
    require(started.tzinfo is not None and started.utcoffset() == timedelta(0)
            and started <= observed, 'Ordered UTC capture interval required')
    def timing(day):
        close = datetime.combine(day, time(16), zone).astimezone(timezone.utc)
        following = day+timedelta(days=1)
        while following.weekday() >= 5: following += timedelta(days=1)
        return close, datetime.combine(following,time(9,30),zone).astimezone(timezone.utc)
    require(started >= timing(session(accounted[-1]))[0], 'Clock precedes accounted close')
    for mapping in (source_csv_bytes, baseline_csv_bytes):
        require(type(mapping) is dict and set(mapping) == {'QQQ','SPY'}, 'Exact source pair required')
    sources = {ticker: parse(raw) for ticker, raw in source_csv_bytes.items()}
    baseline = {ticker: parse(raw) for ticker, raw in baseline_csv_bytes.items()}
    for role, mapping in (('Current', sources), ('Baseline', baseline)):
        for ticker, rows in mapping.items():
            prefix = [day for day in rows if day >= accounted[0]][:len(accounted)]
            require(prefix == accounted, role+' ticker lost exact accounted prefix: '+ticker)
    unmatched = {ticker: sorted(day for day in sources[ticker]
        if day > accounted[-1] and day not in sources[other])
        for ticker, other in (('QQQ','SPY'),('SPY','QQQ'))}
    source_suffix_asymmetric = any(unmatched.values())
    common = sorted(set(sources['QQQ']) & set(sources['SPY']))
    aligned = [day for day in common if day >= accounted[0]]
    require(aligned[:len(accounted)] == accounted, 'Current common dates lost accounted prefix')
    revisions = []
    for ticker in ('QQQ','SPY'):
        for day in accounted:
            require(day in baseline[ticker], 'Baseline missing accounted row')
            old = baseline[ticker][day]; new = sources[ticker][day]
            if old['normalized_row_sha256'] != new['normalized_row_sha256']:
                revisions.append({'ticker':ticker,'session':day,'baseline_evidence':old,
                    'current_evidence':new,'role':'DIAGNOSTIC_ONLY_NEVER_REWRITE_ACCOUNTED_EVIDENCE'})
    new_dates = aligned[len(accounted):]
    completed = [day for day in new_dates if timing(session(day))[0] <= started]
    excluded = [day for day in new_dates if day not in completed]
    classifications = []; candidate = None
    for index, day in enumerate(completed):
        close, deadline = timing(session(day))
        status = ('MISSED_EARLIER_COMPLETED_SOURCE_SESSION' if index < len(completed)-1 else
                  'SOURCE_SUFFIX_ASYMMETRY_REQUIRES_REVIEW' if source_suffix_asymmetric else
                  'TIMELINESS_REVIEW_CANDIDATE_ONLY' if observed < deadline else 'MISSED_SEAL_DEADLINE')
        row = {'session':day, 'classification':status,'conservative_close_utc':close.isoformat(),
            'conservative_next_weekday_open_utc':deadline.isoformat(),
            'capture_started_at_utc':capture_started_at_utc, 'observed_at_utc':observed_at_utc, **FALSE}
        classifications.append(row)
        if status == 'TIMELINESS_REVIEW_CANDIDATE_ONLY': candidate = dict(row)
    return {'schema':'FORWARD_SOURCE_CAPTURE_PLANNING_V1',
        'status':('SOURCE_SUFFIX_ASYMMETRY_REQUIRES_REVIEW' if source_suffix_asymmetric else
                  'NO_NEW_SOURCE_SESSION' if not new_dates else 'NEW_SOURCE_DATES_REQUIRE_REVIEW'),
        'capture_started_at_utc':capture_started_at_utc,
        'observed_at_utc':observed_at_utc,'tzif_sha256':sha(tzif_bytes),
        'timezone_semantics':'CALLER_BOUND_TZIF_NOT_INDEPENDENTLY_CERTIFIED_NEW_YORK',
        'source_sha256':{key:sha(value) for key,value in source_csv_bytes.items()},
        'baseline_sha256':{key:sha(value) for key,value in baseline_csv_bytes.items()},
        'source_rows':sources,'accounted_prefix_dates':accounted,
        'last_observed_session_unchanged':frontier['last_observed_session'],
        'last_accounted_session_unchanged':frontier['last_accounted_session'],
        'new_source_dates':new_dates,'excluded_unfinished_source_dates':excluded,
        'unmatched_new_source_dates_by_ticker': unmatched,
        'source_suffix_asymmetry_blocks_timeliness_candidate': source_suffix_asymmetric,
        'classifications':classifications,'timeliness_candidate':candidate,'revisions':revisions,
        'month_first_semantics':frontier['month_first_semantics'],
        'scope':'CURRENT_BYTE_CAPTURE_PLANNING_NOT_SEAL_OR_RECOVERY', **FALSE}
