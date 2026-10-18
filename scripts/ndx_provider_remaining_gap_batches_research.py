"""Authorized fixed-order, at-most-eight raw-only batches; never retries a ticker."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_provider_gap_first8_capture_research as transport

BASE=ROOT/'data/cache/research'
INITIAL=BASE/'dynamic_frozen_v2/second8_provider_coverage_addendum_20260912.json'
INITIAL_SHA='cb9976eeba0fcf92a0ccb71bcc5e0844d350da5ce83036d446f0f191a438bd4a'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,document):
    with path.open('xb') as stream:
        stream.write((json.dumps(document,sort_keys=True,indent=2,allow_nan=False)+'\n').encode())
    return sha(path)


def load_bound(path,expected):
    if sha(path)!=expected:
        raise ValueError('Bound prior report differs')
    document=json.loads(path.read_bytes())
    for source,digest in document['source_hashes'].items():
        if sha(source)!=digest:
            raise ValueError('Source closure differs: '+source)
    return document


def addendum(prior,prior_path,prior_sha,manifest,manifest_path,manifest_sha):
    sources=dict(prior['source_hashes'])
    sources[str(prior_path)]=prior_sha
    sources[str(manifest_path)]=manifest_sha
    for path,digest in manifest['source_hashes'].items():
        if path in sources and sources[path]!=digest:
            raise ValueError('Source hash conflict')
        sources[path]=digest
    rows=deepcopy(prior['candidate_rows']);by_ticker={row['ticker']:row for row in rows}
    if len(by_ticker)!=112 or sum(len(row['periods']) for row in rows)!=1515:
        raise ValueError('Full proxy denominator differs')
    planned=prior['next_capture_plan']['tickers']
    attempted=set(prior['next_capture_plan']['excluded_attempted_tickers'])
    expected_plan=sorted({row['ticker'] for row in rows if not row['updated_capture_present']}-attempted)[:8]
    if not planned or planned!=expected_plan or manifest['explicit_request_tickers']!=planned or [p['ticker'] for p in manifest['probes']]!=planned:
        raise ValueError('Fixed order or request denominator differs')
    facts=[];failures=[]
    for probe in manifest['probes']:
        ticker=probe['ticker']
        if ticker in attempted or by_ticker[ticker]['updated_capture_present'] or probe['request']['attempt_count']!=1:
            raise ValueError('Repeated request')
        path=probe.get('response_path')
        if path is None:
            failures.append(dict(ticker=ticker,http_status=probe.get('http_status'),error_type=probe.get('error_type'),raw_path=None))
            continue
        if sha(path)!=probe['response_sha256']:
            raise ValueError('Raw body SHA differs')
        sources[path]=probe['response_sha256']
        raw=Path(path).read_bytes()
        if len(raw)!=probe['response_bytes']:
            raise ValueError('Raw bytes differ')
        parsed=urlparse(probe['request']['url']);query=parse_qs(parsed.query,keep_blank_values=True)
        if parsed.hostname!='query1.finance.yahoo.com' or parsed.path!='/v8/finance/chart/'+ticker or query!=dict(period1=['1640995200'],period2=[str(manifest['request_end_exclusive_utc_epoch'])],interval=['1d'],events=['div,splits']):
            raise ValueError('Unexpected quote channel or horizon')
        decoded=gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw
        if probe.get('decoded_sha256') and hashlib.sha256(decoded).hexdigest()!=probe['decoded_sha256']:
            raise ValueError('Decoded SHA differs')
        try:
            payload=json.loads(decoded)
        except (ValueError,UnicodeError):
            failures.append(dict(ticker=ticker,http_status=probe.get('http_status'),raw_path=path,raw_sha256=probe['response_sha256'],reason='NON_JSON_BODY_PRESERVED'))
            continue
        if probe.get('http_status')!=200 or probe.get('parse_status')!='RAW_QUOTE_CHANNEL_PARSED_NOT_IDENTITY_ADJUDICATION':
            failures.append(dict(ticker=ticker,http_status=probe.get('http_status'),raw_path=path,raw_sha256=probe['response_sha256'],provider_error=payload.get('chart',{}).get('error'),parse_status=probe.get('parse_status')))
            continue
        chart,=payload['chart']['result'];quote,=chart['indicators']['quote']
        if chart['meta']['symbol']!=ticker or chart['meta']['exchangeTimezoneName']!='America/New_York':
            raise ValueError('Response channel differs')
        receipt=datetime.fromisoformat(probe['received_at_utc']);cutoff=receipt.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        end=datetime.fromtimestamp(manifest['request_end_exclusive_utc_epoch'],ZoneInfo('America/New_York'))
        if end.timestamp()>receipt.timestamp() or end.date().isoformat()!=cutoff:
            raise ValueError('Insufficient split event horizon')
        days=[datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat() for t in chart['timestamp']]
        if not days or days!=sorted(set(days)):
            raise ValueError('Duplicate/unordered sessions')
        valid={}
        for field in ('open','close'):
            if len(quote[field])!=len(days):
                raise ValueError('Quote array denominator differs')
            valid[field]={day for day,value in zip(days,quote[field]) if type(value) in (int,float) and math.isfinite(value) and value>0 and day<cutoff}
        check_count=0;missing=0
        for period in by_ticker[ticker]['periods']:
            calendar=prior['calendar_requirements'][period['selection_date']]
            required=set(calendar['return_dates'])|set(calendar['previous_close_by_return_date'].values())
            if len(required)!=period['required_close_count']:
                raise ValueError('Required previous-close denominator differs')
            check=dict(path=path,missing_close_dates=sorted(required-valid['close']),missing_open_dates=sorted(required-valid['open']),batch_ordinal=manifest['batch_ordinal'])
            period.setdefault('remaining_batch_raw_checks',[]).append(check)
            check_count+=1;missing+=len(check['missing_close_dates'])+len(check['missing_open_dates'])
            if not check['missing_close_dates']:
                period['updated_complete_paths'].append(path)
                if not check['missing_open_dates']:
                    period['updated_complete_open_close_paths'].append(path)
        by_ticker[ticker]['updated_capture_present']=True
        by_ticker[ticker]['updated_all_applicable_training_complete']=all(p['updated_complete_paths'] for p in by_ticker[ticker]['periods'])
        facts.append(dict(ticker=ticker,raw_path=path,raw_sha256=probe['response_sha256'],decoded_sha256=hashlib.sha256(decoded).hexdigest(),
                          observed_count=len(days),first_session=days[0],last_session=days[-1],completed_open_count=len(valid['open']),completed_close_count=len(valid['close']),
                          excluded_same_receipt_date_sessions=[day for day in days if day>=cutoff],currency=chart['meta'].get('currency'),
                          returned_split_events=chart.get('events',{}).get('splits',{}),returned_dividend_count=len(chart.get('events',{}).get('dividends',{})),
                          applicable_training_checks=check_count,total_missing_open_close_date_occurrences=missing,
                          provider_current_long_name=chart['meta'].get('longName'),historical_identity_adjudicated=False))
    attempted.update(planned)
    next_tickers=sorted({row['ticker'] for row in rows if not row['updated_capture_present']}-attempted)[:8]
    counts=dict(prior_captured=sum(row['updated_capture_present'] for row in prior['candidate_rows']),updated_captured=sum(row['updated_capture_present'] for row in rows),
                prior_complete=sum(row['updated_all_applicable_training_complete'] for row in prior['candidate_rows']),updated_complete=sum(row['updated_all_applicable_training_complete'] for row in rows))
    for path,digest in sources.items():
        if sha(path)!=digest:
            raise ValueError('Source drift before save')
    return dict(schema='SEQUENTIAL_FIXED_RAW_BATCH_COVERAGE_ADDENDUM',source_hashes=sources,batch_ordinal=manifest['batch_ordinal'],counts=counts,
                candidate_rows=rows,calendar_requirements=prior['calendar_requirements'],union_security_count=112,proxy_row_count=1515,
                new_raw_facts=facts,failures_preserved=prior['failures_preserved']+failures,
                next_capture_plan=dict(selection_rule='SORTED_TICKERS_MISSING_RAW_EXCLUDING_ALL_BOUND_ATTEMPTS',tickers=next_tickers,excluded_attempted_tickers=sorted(attempted),requests_performed=False),
                unknown_identity_events_are_not_resolved_by_request_ticker=True,observed_calendar_independently_exchange_certified=False,
                point_in_time_verified=False,promotion_allowed=False,training_performed=False,original_cache_modified=False)


def main():
    prior_path=INITIAL;prior_sha=INITIAL_SHA;ordinal=3
    while True:
        prior=load_bound(prior_path,prior_sha)
        tickers=prior['next_capture_plan']['tickers']
        if not tickers:
            print(json.dumps(dict(status='ALL_PREVIOUSLY_MISSING_CHANNELS_ATTEMPTED_ONCE',final_coverage_path=str(prior_path),final_coverage_sha256=prior_sha)),flush=True)
            return
        if len(tickers)>8 or tickers!=sorted(set(tickers)):
            raise ValueError('Invalid sorted batch')
        directory=BASE/('provider_gap_batch%02d_capture_20260912_v1'%ordinal)
        directory.mkdir(parents=True,exist_ok=False)
        transport.OUTPUT=directory
        period2=int(datetime.now(timezone.utc).timestamp())
        with ThreadPoolExecutor(max_workers=2) as executor:
            probes=list(executor.map(lambda ticker:transport.capture(ticker,period2),tickers))
        sources={str(prior_path):prior_sha,str(Path(__file__).resolve()):sha(__file__),str(Path(transport.__file__).resolve()):sha(transport.__file__)}
        helper=str(Path(transport.__file__).resolve())
        if sources[helper]!=prior['source_hashes'][helper]:
            raise ValueError('Frozen capture helper differs')
        manifest=dict(schema='FIXED_AT_MOST_EIGHT_REMAINING_PROVIDER_RAW_CAPTURE',source_hashes=sources,batch_ordinal=ordinal,
                      explicit_request_tickers=tickers,request_count=len(tickers),maximum_attempts_per_ticker=1,
                      request_end_exclusive_utc_epoch=period2,requested_start='2022-01-01',probes=probes,
                      no_historical_alias_stitching=True,no_old_cache_writes=True,no_training=True,point_in_time_verified=False,promotion_allowed=False)
        manifest_path=directory/'manifest.json';manifest_sha=save(manifest_path,manifest)
        report=addendum(prior,prior_path,prior_sha,manifest,manifest_path,manifest_sha)
        coverage_path=directory/'coverage_addendum.json';coverage_sha=save(coverage_path,report)
        print(json.dumps(dict(batch=ordinal,tickers=tickers,manifest_path=str(manifest_path),manifest_sha256=manifest_sha,
                              coverage_path=str(coverage_path),coverage_sha256=coverage_sha,counts=report['counts'],
                              actual=[dict(ticker=p['ticker'],http_status=p.get('http_status'),rows=p.get('observed_session_count')) for p in probes])),flush=True)
        prior_path=coverage_path;prior_sha=coverage_sha;ordinal+=1


if __name__=='__main__':
    main()
