"""Read second fixed capture batch against previously bound exact training dates."""
from copy import deepcopy
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
PRIOR = BASE / 'dynamic_frozen_v2/first8_provider_coverage_addendum_20260912.json'
PRIOR_SHA = '39e8264cda2a8f5055b94e45d34cc6d5ce1a03ff4f2ccf302446aaec3f50eccb'
MANIFEST = BASE / 'provider_gap_second8_capture_20260912_v1/manifest.json'
MANIFEST_SHA = '6a85f901ecc79d9bb82f3b5197cca24a0976d697074881079a251b390acef6b7'


def build():
    sources = {}
    def bind(path, expected):
        path = Path(path).resolve()
        raw = path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected or (str(path) in sources and sources[str(path)] != actual):
            raise ValueError('Bound source mismatch: '+str(path))
        sources[str(path)] = actual
        return raw
    prior = json.loads(bind(PRIOR, PRIOR_SHA))
    manifest = json.loads(bind(MANIFEST, MANIFEST_SHA))
    for report in (prior, manifest):
        for path, expected in report['source_hashes'].items():
            bind(path, expected)
    planned = prior['next_capture_plan']['tickers']
    if manifest['explicit_request_tickers'] != planned or [row['ticker'] for row in manifest['probes']] != planned:
        raise ValueError('Fixed second batch denominator differs')
    rows = deepcopy(prior['candidate_rows'])
    by_ticker = {row['ticker']:row for row in rows}
    facts, failures = [], []
    for probe in manifest['probes']:
        ticker = probe['ticker']
        if by_ticker[ticker]['updated_capture_present']:
            raise ValueError('Unexpected repeated successful capture')
        raw = bind(probe['response_path'], probe['response_sha256'])
        if len(raw) != probe['response_bytes'] or probe['request']['attempt_count'] != 1:
            raise ValueError('Raw bytes or attempts differ')
        decoded = gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw
        if hashlib.sha256(decoded).hexdigest() != probe['decoded_sha256'] or len(decoded) != probe['decoded_bytes']:
            raise ValueError('Decoded content differs')
        parsed = urlparse(probe['request']['url'])
        query = parse_qs(parsed.query, keep_blank_values=True)
        if parsed.hostname != 'query1.finance.yahoo.com' or parsed.path != '/v8/finance/chart/'+ticker or query != dict(period1=['1640995200'],period2=[str(manifest['request_end_exclusive_utc_epoch'])],interval=['1d'],events=['div,splits']):
            raise ValueError('Request horizon/channel differs')
        payload = json.loads(decoded)
        if probe['http_status'] != 200:
            failures.append(dict(ticker=ticker,http_status=probe['http_status'],raw_path=probe['response_path'],raw_sha256=probe['response_sha256'],provider_error=payload['chart']['error']))
            continue
        chart, = payload['chart']['result']
        quote, = chart['indicators']['quote']
        if chart['meta']['symbol'] != ticker or chart['meta']['exchangeTimezoneName'] != 'America/New_York':
            raise ValueError('Response channel/timezone differs')
        receipt = datetime.fromisoformat(probe['received_at_utc'])
        cutoff = receipt.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        end = datetime.fromtimestamp(manifest['request_end_exclusive_utc_epoch'],ZoneInfo('America/New_York'))
        if end.timestamp() > receipt.timestamp() or end.date().isoformat() != cutoff:
            raise ValueError('Capture split horizon incomplete')
        days = [datetime.fromtimestamp(value,ZoneInfo('America/New_York')).date().isoformat() for value in chart['timestamp']]
        if days != sorted(set(days)) or len(days) != 1177:
            raise ValueError('Raw session denominator differs')
        valid = {}
        for field in ('open','close'):
            if len(quote[field]) != len(days):
                raise ValueError('Quote array length differs')
            valid[field] = {day for day,value in zip(days,quote[field]) if type(value) in (int,float) and math.isfinite(value) and value>0 and day<cutoff}
        for period in by_ticker[ticker]['periods']:
            required_calendar = prior['calendar_requirements'][period['selection_date']]
            required = set(required_calendar['return_dates']) | set(required_calendar['previous_close_by_return_date'].values())
            if len(required) != period['required_close_count']:
                raise ValueError('Previously bound previous-close denominator differs')
            check = dict(path=probe['response_path'],missing_close_dates=sorted(required-valid['close']),missing_open_dates=sorted(required-valid['open']))
            period.setdefault('second_batch_raw_checks',[]).append(check)
            if not check['missing_close_dates']:
                period['updated_complete_paths'].append(probe['response_path'])
                if not check['missing_open_dates']:
                    period['updated_complete_open_close_paths'].append(probe['response_path'])
        by_ticker[ticker]['updated_capture_present'] = True
        by_ticker[ticker]['updated_all_applicable_training_complete'] = all(period['updated_complete_paths'] for period in by_ticker[ticker]['periods'])
        facts.append(dict(ticker=ticker,raw_path=probe['response_path'],raw_sha256=probe['response_sha256'],decoded_sha256=probe['decoded_sha256'],
                          observed_count=len(days),first_session=days[0],last_session=days[-1],completed_close_count=len(valid['close']),completed_open_count=len(valid['open']),
                          excluded_same_receipt_date_sessions=[day for day in days if day>=cutoff],currency=chart['meta'].get('currency'),
                          returned_split_events=chart.get('events',{}).get('splits',{}),returned_dividend_count=len(chart.get('events',{}).get('dividends',{}))))
    counts = dict(prior_captured=sum(row['updated_capture_present'] for row in prior['candidate_rows']),
                  updated_captured=sum(row['updated_capture_present'] for row in rows),
                  prior_complete=sum(row['updated_all_applicable_training_complete'] for row in prior['candidate_rows']),
                  updated_complete=sum(row['updated_all_applicable_training_complete'] for row in rows))
    if counts != dict(prior_captured=29,updated_captured=36,prior_complete=27,updated_complete=34):
        raise ValueError('Actual batch coverage differs: '+str(counts))
    if len(facts)!=7 or len(failures)!=1 or failures[0]['ticker']!='ANSS' or failures[0]['http_status']!=404:
        raise ValueError('Actual second-batch results differ')
    attempted = set(prior['next_capture_plan']['excluded_attempted_tickers'])|set(planned)
    next_tickers = sorted({row['ticker'] for row in rows if not row['updated_capture_present']}-attempted)[:8]
    source = Path(__file__).resolve()
    sources[str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
    for path,expected in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Source drift during addendum')
    return dict(schema='SECOND8_INDEPENDENT_RAW_COVERAGE_ADDENDUM',source_hashes=sources,counts=counts,candidate_rows=rows,
                calendar_requirements=prior['calendar_requirements'],union_security_count=len(rows),proxy_row_count=sum(len(row['periods']) for row in rows),
                new_raw_facts=facts,failures_preserved=prior['failures_preserved']+failures,
                next_capture_plan=dict(selection_rule='SORTED_TICKERS_MISSING_RAW_EXCLUDING_ALL_BOUND_ATTEMPTS',tickers=next_tickers,excluded_attempted_tickers=sorted(attempted),requests_performed=False),
                provider_symbol_is_not_historical_security_identity=True,complete_dates_do_not_authorize_price_basis_or_identity=True,
                observed_calendar_independently_exchange_certified=False,point_in_time_verified=False,promotion_allowed=False,
                original_cache_modified=False,training_performed=False)


if __name__=='__main__':
    path = BASE / 'dynamic_frozen_v2/second8_provider_coverage_addendum_20260912.json'
    if path.exists():
        raise FileExistsError(path)
    report=build()
    with path.open('xb') as stream:
        stream.write((json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n').encode())
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),counts=report['counts'],next=report['next_capture_plan']['tickers'])))
