"""Independent raw decoding and full proxy-date coverage; no fetch or training."""
from collections import defaultdict
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'data/cache/research'
INVENTORY = DIRECTORY / 'dynamic_frozen_v2/full_proxy_provider_capture_inventory_20260912.json'
INVENTORY_SHA = 'e23c0c5c61171c07eb7fa48a494b90b8c1ed8915763babf1da6f17899e9a9262'
MANIFEST = DIRECTORY / 'provider_gap_first8_capture_20260912_v1/manifest.json'
MANIFEST_SHA = 'd564b6ae13addf8c5e19e2a286526ea058f44149e9f2de4e670d584c5edf3d51'
MEMBERSHIP = DIRECTORY / 'dynamic_frozen_v2/full_membership_coverage_20260912_v2.json'
MEMBERSHIP_SHA = 'eb15d117e6b3c07a41decf1666b5dfbcfda2fd25ee00ea05b5df680d7473dd64'


def build():
    sources = {}
    def bind(path, expected):
        path = Path(path).resolve()
        raw = path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected or (str(path) in sources and sources[str(path)] != actual):
            raise ValueError('Source mismatch: ' + str(path))
        sources[str(path)] = actual
        return raw
    inventory = json.loads(bind(INVENTORY, INVENTORY_SHA))
    manifest = json.loads(bind(MANIFEST, MANIFEST_SHA))
    membership = json.loads(bind(MEMBERSHIP, MEMBERSHIP_SHA))
    for document in (inventory, manifest, membership):
        for path, expected in document['source_hashes'].items():
            bind(path, expected)
    if manifest['explicit_request_tickers'] != ['AAPL','AMGN','ASML','COST','CSCO','MSFT','MU','SPLK']:
        raise ValueError('First-eight denominator changed')
    if len(manifest['probes']) != 8 or len(inventory['candidate_rows']) != 112 or len(membership['dates']) != 15:
        raise ValueError('Bound denominator differs')
    calendars = {}
    appearances = defaultdict(list)
    for cohort in membership['dates']:
        if len(cohort['candidates']) != 101:
            raise ValueError('Proxy cohort denominator differs')
        coordinate = cohort['coordinate']['selection_date']
        context_path, = [path for path, value in membership['source_hashes'].items()
                        if value == cohort['old_context_sha256'] and Path(path).name == 'context.json']
        context = json.loads(bind(context_path, cohort['old_context_sha256']))
        days = [item['timestamp'][:10] for item in context['prepared_inputs']['returns']['payload']['mapping']['index']['items']]
        if days != sorted(set(days)):
            raise ValueError('Original training calendar not unique')
        calendars[coordinate] = days
        for candidate in cohort['candidates']:
            appearances[candidate['ticker']].append(coordinate)
    raw_captures = {}
    def decode(path, expected, ticker, cutoff, is_new):
        raw = bind(path, expected)
        decoded = gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw
        chart, = json.loads(decoded)['chart']['result']
        quote, = chart['indicators']['quote']
        if chart['meta']['symbol'] != ticker or chart['meta']['exchangeTimezoneName'] != 'America/New_York':
            raise ValueError('Channel or timezone differs')
        days = [datetime.fromtimestamp(value, ZoneInfo('America/New_York')).date().isoformat() for value in chart['timestamp']]
        if days != sorted(set(days)):
            raise ValueError('Nonunique raw date')
        valid = {}
        for field in ('open','close'):
            if len(quote[field]) != len(days):
                raise ValueError('Quote length differs')
            valid[field] = {day for day, value in zip(days, quote[field])
                            if type(value) in (int,float) and math.isfinite(value) and value > 0 and cutoff and day < cutoff}
        raw_captures[str(Path(path).resolve())] = dict(ticker=ticker, new_capture=is_new, dates=days,
            valid=valid, raw_sha256=expected, decoded_sha256=hashlib.sha256(decoded).hexdigest(),
            raw_bytes=len(raw), decoded_bytes=len(decoded), currency=chart['meta'].get('currency'),
            split_count=len(chart.get('events',{}).get('splits',{})), cutoff=cutoff)
        return raw_captures[str(Path(path).resolve())]
    for path, old in inventory['raw_captures'].items():
        ref = old['manifest_references'][0]
        receipt = ref.get('received_at_utc') or ref.get('response_saved_at_utc')
        cutoff = datetime.fromisoformat(receipt.replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date().isoformat() if receipt else None
        restored = decode(path, old['sha256'], old['provider_request_ticker'], cutoff, False)
        if restored['dates'] != old['session_dates']:
            raise ValueError('Old inventory sessions differ from original raw')
    new_facts, failures = [], []
    for probe in manifest['probes']:
        raw = bind(probe['response_path'], probe['response_sha256'])
        if len(raw) != probe['response_bytes'] or probe['request']['attempt_count'] != 1:
            raise ValueError('Capture bytes/attempts differ')
        ticker = probe['ticker']
        url = urlparse(probe['request']['url'])
        query = parse_qs(url.query, keep_blank_values=True)
        if url.hostname != 'query1.finance.yahoo.com' or url.path != '/v8/finance/chart/' + ticker:
            raise ValueError('Request channel mismatch')
        if query != dict(period1=['1640995200'], period2=[str(manifest['request_end_exclusive_utc_epoch'])], interval=['1d'], events=['div,splits']):
            raise ValueError('Request horizon changed')
        if probe['http_status'] != 200:
            failures.append(dict(ticker=ticker, http_status=probe['http_status'], path=probe['response_path'],
                                 sha256=probe['response_sha256'], provider_error=json.loads(raw)['chart']['error']))
            continue
        receipt = datetime.fromisoformat(probe['received_at_utc'])
        cutoff = receipt.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        end = datetime.fromtimestamp(manifest['request_end_exclusive_utc_epoch'], ZoneInfo('America/New_York'))
        if end.timestamp() > receipt.timestamp() or end.date().isoformat() != cutoff:
            raise ValueError('Incomplete split request horizon')
        result = decode(probe['response_path'], probe['response_sha256'], ticker, cutoff, True)
        if result['decoded_sha256'] != probe['decoded_sha256'] or result['decoded_bytes'] != probe['decoded_bytes']:
            raise ValueError('Decoded bytes mismatch')
        if len(result['dates']) != 1177 or result['dates'][0] != '2022-01-03':
            raise ValueError('New raw session denominator differs')
        new_facts.append(dict(ticker=ticker, response_path=probe['response_path'], raw_sha256=probe['response_sha256'],
            decoded_sha256=result['decoded_sha256'], raw_row_count=len(result['dates']),
            first_session=result['dates'][0], last_session=result['dates'][-1],
            complete_open_count=len(result['valid']['open']), complete_close_count=len(result['valid']['close']),
            excluded_same_receipt_date_sessions=[day for day in result['dates'] if day >= cutoff], split_count=result['split_count']))
    if {row['ticker'] for row in new_facts} != {'AAPL','AMGN','ASML','COST','CSCO','MSFT','MU'} or len(failures) != 1 or failures[0]['ticker'] != 'SPLK' or failures[0]['http_status'] != 404:
        raise ValueError('Actual success/failure cohort changed')
    references = [row for row in raw_captures.values() if row['ticker'] == 'META' and row['dates'][0] == '2022-01-03']
    reference, = references
    previous = {day: reference['dates'][index-1] for index, day in enumerate(reference['dates']) if index}
    required_by_date = {}
    for date, days in calendars.items():
        required_by_date[date] = dict(return_dates=days, previous_close_by_return_date={day:previous[day] for day in days})
    rows = []
    for ticker, dates in sorted(appearances.items()):
        variants = {path: value for path, value in raw_captures.items() if value['ticker'] == ticker}
        supports = []
        for date in dates:
            days = calendars[date]
            required = set(days) | {previous[day] for day in days}
            complete = [path for path, value in variants.items() if required <= value['valid']['close']]
            old_complete = [path for path in complete if not variants[path]['new_capture']]
            supports.append(dict(selection_date=date, original_return_count=len(days), required_close_count=len(required),
                original_complete_paths=old_complete, updated_complete_paths=complete,
                updated_complete_open_close_paths=[path for path in complete if required <= variants[path]['valid']['open']],
                new_raw_checks=[dict(path=path, missing_close_dates=sorted(required-value['valid']['close']),
                                    missing_open_dates=sorted(required-value['valid']['open']))
                                for path,value in variants.items() if value['new_capture']]))
        rows.append(dict(ticker=ticker, original_capture_present=any(not value['new_capture'] for value in variants.values()),
                         updated_capture_present=bool(variants), original_all_applicable_training_complete=all(x['original_complete_paths'] for x in supports),
                         updated_all_applicable_training_complete=all(x['updated_complete_paths'] for x in supports), periods=supports))
    counts = dict(original_captured=sum(x['original_capture_present'] for x in rows), updated_captured=sum(x['updated_capture_present'] for x in rows),
                  original_complete=sum(x['original_all_applicable_training_complete'] for x in rows), updated_complete=sum(x['updated_all_applicable_training_complete'] for x in rows))
    if counts != dict(original_captured=25, updated_captured=29, original_complete=20, updated_complete=27):
        raise ValueError('Recomputed availability differs: '+str(counts))
    attempted = {value['ticker'] for value in raw_captures.values()} | {x['ticker'] for x in failures} | {x['ticker'] for x in inventory['provider_failure_records']}
    plan = sorted({row['ticker'] for row in rows if not row['updated_capture_present']} - attempted)[:8]
    source = Path(__file__).resolve()
    sources[str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
    for path, expected in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Source drift')
    return dict(schema='FIRST8_RAW_INDEPENDENT_FULL_PROXY_COVERAGE_ADDENDUM',source_hashes=sources,
                union_security_count=112, union_issuer_count=111, date_count=15, proxy_row_count=sum(len(x['periods']) for x in rows),
                counts=counts,new_raw_facts=new_facts,failures_preserved=failures,calendar_requirements=required_by_date,candidate_rows=rows,
                next_capture_plan=dict(selection_rule='TICKER_SORT_ASC_FIRST_EIGHT_MISSING_RAW_EXCLUDING_ALL_BOUND_ATTEMPTS',tickers=plan,
                                       excluded_attempted_tickers=sorted(attempted),requests_performed=False),
                reference_calendar_independently_exchange_certified=False, raw_same_day_bars_excluded_from_completed_training=True,
                complete_date_coverage_is_not_price_basis_or_identity_admission=True, no_capture_variants_stitched=True,
                historical_provider_identity_verified=False, proxy_is_not_official_membership=True,point_in_time_verified=False,
                training_performed=False,original_inventory_modified=False,promotion_allowed=False)


if __name__ == '__main__':
    path = DIRECTORY / 'dynamic_frozen_v2/first8_provider_coverage_addendum_20260912.json'
    if path.exists():
        raise FileExistsError(path)
    result = build()
    with path.open('xb') as stream:
        stream.write((json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+'\n').encode())
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),counts=result['counts'],next=result['next_capture_plan']['tickers'])))
