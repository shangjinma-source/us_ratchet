"""Independent raw-only readback; never joins historical aliases or generates returns."""
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research'
FOLDER = BASE / 'current_22_price_capture_20260919_v1'
LOADED = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
INDEXES = [('08', '5a5a8bcf9c4f30d798e8b86b5c29ea935711b2105006617ec22e58e3d6ac203e'),
           ('16', '47f24af6dbec3e9b2cea75d4b8a2f9457c979b655d3d580296bc6c95b2ee7745'),
           ('22', '7a41e3f47ecb4ea9fc6757a9e0393993be99ffeaceab8d2b21ea38c83797890d')]
PLAN_SHA = '099f4a363917e43a1b5a625e097365f1b093254ca0829cc36919b2593bb99334'
NY = ZoneInfo('America/New_York')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect_chart(chart, cutoff):
    stamps = chart['timestamp']
    if any(type(t) is not int for t in stamps) or stamps != sorted(set(stamps)):
        raise ValueError('Duplicate/unordered timestamp denominator')
    dates = [datetime.fromtimestamp(t, NY).date().isoformat() for t in stamps]
    if dates != sorted(set(dates)):
        raise ValueError('Multiple timestamps for observed New York session')
    quote, = chart['indicators']['quote']
    if any(len(quote[field]) != len(stamps) for field in ('open', 'close')):
        raise ValueError('Quote array denominator differs')
    finite = lambda v: type(v) in (int, float) and math.isfinite(v) and v > 0
    valid = {field: [date for date, value in zip(dates, quote[field]) if finite(value)] for field in ('open', 'close')}
    completed = {field: {date for date in days if date < cutoff} for field, days in valid.items()}
    joint = sorted(completed['open'] & completed['close'])
    events = []
    for kind, mapping in chart.get('events', {}).items():
        for event_id, event in mapping.items():
            events.append(dict(kind=kind, provider_event_id=event_id, raw_event=event,
                               observed_new_york_date=datetime.fromtimestamp(event['date'], NY).date().isoformat()))
    return dict(timestamp_count=len(stamps), timestamp_first=dates[0] if dates else None,
                timestamp_last=dates[-1] if dates else None,
                finite_positive_counts={field: len(days) for field, days in valid.items()},
                finite_positive_first_last={field: [days[0], days[-1]] if days else [None, None] for field, days in valid.items()},
                null_or_nonpositive_dates={field: [date for date in dates if date not in valid[field]] for field in valid},
                receipt_date_or_later_excluded=[date for date in dates if date >= cutoff],
                completed_joint_open_close_count=len(joint), completed_joint_first_last=[joint[0], joint[-1]] if joint else [None, None],
                events=events), completed


def build():
    sources = {}
    def bound(path, expected):
        path = Path(path)
        raw = path.read_bytes()
        if sha(raw) != expected or (str(path) in sources and sources[str(path)] != expected):
            raise ValueError('Source SHA differs: ' + str(path))
        sources[str(path)] = expected
        return raw
    def load(path, expected):
        return json.loads(bound(path, expected))
    plan = load(FOLDER/'plan.json', PLAN_SHA)
    for path, expected in plan['source_hashes'].items():
        bound(path, expected)
    observation = load(BASE/'ndx_current_quote_list_capture_20260919_v1/observation.json', '50cbca76647e14d99f4990deff0c6adc7226f31109393df2fa0298b062fc5c77')
    old = load(BASE/'provider_gap_batch12_capture_20260912_v1/completed_queue_sha_event_index.json', '5d9d2b55d88441045c3b3c98cfb0c33687a707da030266ff028e151b35357117')
    if plan['tickers'] != sorted(set(observation['observed_symbols'])-set(old['provider_channels'])) or len(plan['tickers']) != 22:
        raise ValueError('Hard actual channel difference differs')
    calendar = load(BASE/'provider_gap_batch12_capture_20260912_v1/coverage_addendum.json', '6fc0d5ee29cecb12ae70433fece84cd43e64ae90030aa92fe00f95880a3b1b22')['calendar_requirements']
    previous = []
    for i, (count, digest) in enumerate(INDEXES):
        path = FOLDER/('completion_index_'+count+'.json')
        index = load(path, digest)
        if index['plan_sha256'] != PLAN_SHA or index['output_directory'] != str(FOLDER) or len(index['entries']) != int(count) or index['entries'][:len(previous)] != previous:
            raise ValueError('Cumulative batch chain differs')
        if i:
            old_count, old_sha = INDEXES[i-1]
            if Path(index['previous_index_path']).resolve() != FOLDER/('completion_index_'+old_count+'.json') or index['previous_index_sha256'] != old_sha:
                raise ValueError('External previous index binding differs')
        elif index['previous_index_path'] is not None or index['previous_index_sha256'] is not None:
            raise ValueError('Unexpected first index parent')
        previous = index['entries']
    if [entry['ticker'] for entry in previous] != plan['tickers']:
        raise ValueError('Full planned ticker denominator differs')
    rows = []
    for entry in previous:
        ticker = entry['ticker']
        if entry['receipt_path'] != str(FOLDER/(ticker+'.receipt.json')) or entry['decoded_path'] != str(FOLDER/(ticker+'.decoded.json')):
            raise ValueError('Capture coordinate differs')
        receipt = load(entry['receipt_path'], entry['receipt_sha256'])
        started = load(FOLDER/(ticker+'.started.json'), receipt['started_sha256'])
        if any(receipt[k] != value for k, value in started.items()) or started['ticker'] != ticker or started['plan_sha256'] != PLAN_SHA or started['attempt_count'] != 1:
            raise ValueError('Attempt/receipt binding differs')
        url = urlparse(started['request_url'])
        query = parse_qs(url.query, keep_blank_values=True)
        start = datetime.fromisoformat(started['started_at_utc'])
        received = datetime.fromisoformat(receipt['received_at_utc'])
        if url.hostname != 'query1.finance.yahoo.com' or url.path != '/v8/finance/chart/'+ticker or query != dict(period1=['1640995200'], period2=[str(int(start.timestamp()))], interval=['1d'], events=['div,splits']) or start > received:
            raise ValueError('Actual request horizon differs')
        cutoff = received.astimezone(NY).date().isoformat()
        if receipt['completed_training_excludes_dates_on_or_after'] != cutoff:
            raise ValueError('Completed-bar boundary differs')
        parsed = load(entry['decoded_path'], entry['decoded_sha256'])
        if parsed['receipt_sha256'] != entry['receipt_sha256'] or parsed['ticker'] != ticker:
            raise ValueError('Decode record differs')
        row = dict(ticker=ticker, http_status=receipt.get('http_status'), request_url=started['request_url'],
                   received_at_utc=receipt['received_at_utc'], exclude_dates_on_or_after=cutoff,
                   historical_identity_verified=False, quote_basis_verified=False,
                   provider_event_completeness_verified=False, same_ticker_alias_join_allowed=False)
        if receipt.get('raw_path'):
            if receipt['raw_path'] != str(FOLDER/(ticker+'.response.bin')):
                raise ValueError('Raw coordinate differs')
            raw = bound(receipt['raw_path'], receipt['raw_sha256'])
            if len(raw) != receipt['raw_bytes']:
                raise ValueError('Body byte count differs')
            decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
            if sha(decoded) != parsed['decoded_sha256']:
                raise ValueError('Decoded bytes differ')
            body = json.loads(decoded)
            row['provider_error'] = body.get('chart', {}).get('error')
            if receipt.get('http_status') == 200 and not row['provider_error']:
                chart, = body['chart']['result']
                if chart['meta']['symbol'] != ticker or chart['meta']['exchangeTimezoneName'] != 'America/New_York':
                    raise ValueError('Provider channel metadata differs')
                facts, completed = inspect_chart(chart, cutoff)
                row.update(facts, provider_meta=chart['meta'], raw_path=receipt['raw_path'], raw_sha256=receipt['raw_sha256'])
                checks = []
                for date, required in calendar.items():
                    dates = set(required['return_dates']) | set(required['previous_close_by_return_date'].values())
                    checks.append(dict(selection_date=date, required_count=len(dates),
                                       missing_open_dates=sorted(dates-completed['open']), missing_close_dates=sorted(dates-completed['close'])))
                row['old_15_calendar_coverage_only_not_membership_admission'] = checks
                row['all_old_training_dates_have_open_close'] = all(not c['missing_open_dates'] and not c['missing_close_dates'] for c in checks)
        rows.append(row)
    bound(Path(__file__).resolve(), LOADED)
    for path, expected in list(sources.items()):
        bound(path, expected)
    return dict(schema='CURRENT22_ORIGINAL_PRICE_CHANNEL_READBACK_V1', rows=rows, channel_count=len(rows),
                successful_http_count=sum(row['http_status']==200 for row in rows),
                all_old_training_dates_have_open_close_count=sum(row.get('all_old_training_dates_have_open_close', False) for row in rows),
                observed_101_original_channel_union_count=len(set(old['provider_channels'])|set(plan['tickers'])),
                old_107_modified=False, historical_membership_verified=False, current_identity_verified=False,
                point_in_time_verified=False, promotion_allowed=False, training_performed=False,
                price_reconstruction_performed=False, source_hashes=dict(sorted(sources.items())))


if __name__ == '__main__':
    report = build()
    path = FOLDER/'coverage_readback.json'
    raw = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()
    with path.open('xb') as handle:
        handle.write(raw)
    print(json.dumps(dict(path=str(path), sha256=sha(raw), channels=report['channel_count'],
                          old_calendar_complete=report['all_old_training_dates_have_open_close_count'], sources=len(report['source_hashes']))))
