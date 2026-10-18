"""One request per explicit missing provider channel; create-only raw capture."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import zlib
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
INVENTORY=ROOT/'data/cache/research/dynamic_frozen_v2/full_proxy_provider_capture_inventory_20260912.json'
INVENTORY_SHA='e23c0c5c61171c07eb7fa48a494b90b8c1ed8915763babf1da6f17899e9a9262'
TICKERS=('AAPL','AMGN','ASML','COST','CSCO','MSFT','MU','SPLK')
OUTPUT=ROOT/'data/cache/research/provider_gap_first8_capture_20260912_v1'
HEADER_FIELDS=('Date','Content-Type','Content-Encoding','Content-Length','Last-Modified','ETag','Cache-Control')


def preflight():
    raw=INVENTORY.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=INVENTORY_SHA:raise ValueError('Missing-source inventory differs')
    inventory=json.loads(raw);rows={row['ticker']:row for row in inventory['candidate_rows']}
    expected_missing={'AAPL','AMGN','COST','CSCO','SPLK'}
    expected_short={'ASML','MSFT','MU'}
    for ticker in TICKERS:
        row=rows[ticker]
        if ticker in expected_missing:
            if row['provider_capture_paths']:raise ValueError('Already captured missing target: '+ticker)
        elif ticker in expected_short:
            if row['raw_capture_status']!='CAPTURE_PRESENT_BUT_SOME_ORIGINAL_TRAINING_DATES_MISSING':
                raise ValueError('Already sufficient source or changed short-history classification')
        else:raise ValueError('Undeclared request target')
    return inventory


def capture(ticker,period2):
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+ticker+'?'+urlencode(
        dict(period1=1640995200,period2=period2,interval='1d',events='div,splits'))
    request_headers={'User-Agent':'Mozilla/5.0','Accept':'application/json','Accept-Encoding':'gzip, deflate'}
    metadata=dict(ticker=ticker,request=dict(method='GET',url=url,headers=request_headers,
        credentials_sent=False,attempt_count=1),started_at_utc=datetime.now(timezone.utc).isoformat())
    raw=None
    try:
        with urlopen(Request(url,headers=request_headers),timeout=25) as response:
            raw=response.read();metadata.update(http_status=response.status,final_url=response.url,
                response_headers={key:response.headers.get(key) for key in HEADER_FIELDS},transport_success=True)
    except HTTPError as error:
        raw=error.read();metadata.update(http_status=error.code,final_url=error.url,
            response_headers={key:error.headers.get(key) for key in HEADER_FIELDS},transport_success=False,error_type='HTTPError')
    except Exception as error:
        metadata.update(http_status=None,transport_success=False,error_type=type(error).__name__)
    metadata['received_at_utc']=datetime.now(timezone.utc).isoformat()
    metadata['response_headers_policy']='EXACT_VALUES_FOR_LISTED_CONTENT_DATE_VALIDATOR_FIELDS_NO_COOKIE_OR_SESSION_HEADERS'
    if raw is None:
        metadata.update(response_path=None,response_sha256=None,response_bytes=0,parse_status='NO_RESPONSE_BODY')
        return metadata
    path=OUTPUT/(ticker+'.response.bin')
    with path.open('xb') as stream:stream.write(raw)
    if path.read_bytes()!=raw:raise ValueError('Raw HTTP body readback differs')
    metadata.update(response_path=str(path),response_sha256=hashlib.sha256(raw).hexdigest(),response_bytes=len(raw),
        response_saved_at_utc=datetime.now(timezone.utc).isoformat())
    try:
        encoding=metadata.get('response_headers',{}).get('Content-Encoding','') or ''
        if raw.startswith(b'\x1f\x8b') or encoding.lower()=='gzip':decoded=gzip.decompress(raw)
        elif encoding.lower()=='deflate':decoded=zlib.decompress(raw)
        elif encoding.lower() in ('','identity'):decoded=raw
        else:raise ValueError('Unrecognized response compression')
        payload=json.loads(decoded)
        metadata.update(decoded_sha256=hashlib.sha256(decoded).hexdigest(),decoded_bytes=len(decoded))
        if metadata['http_status']!=200:
            metadata.update(parse_status='HTTP_FAILURE_BODY_PRESERVED',provider_error=payload.get('chart',{}).get('error'));return metadata
        chart,=payload['chart']['result'];quotes,=chart['indicators']['quote']
        if chart['meta']['symbol']!=ticker or chart['meta'].get('exchangeTimezoneName')!='America/New_York':
            raise ValueError('Provider channel/timezone differs')
        days=[datetime.fromtimestamp(stamp,ZoneInfo('America/New_York')).date().isoformat() for stamp in chart['timestamp']]
        if days!=sorted(set(days)):raise ValueError('Nonunique provider session calendar')
        if any(len(quotes[key])!=len(days) for key in ('open','close')):raise ValueError('Quote array denominator differs')
        received_date=datetime.fromisoformat(metadata['received_at_utc']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        metadata.update(parse_status='RAW_QUOTE_CHANNEL_PARSED_NOT_IDENTITY_ADJUDICATION',currency=chart['meta'].get('currency'),
            response_symbol=chart['meta']['symbol'],provider_long_name=chart['meta'].get('longName'),
            observed_session_count=len(days),first_observed_session=days[0],last_observed_session=days[-1],
            unfinalized_or_same_receipt_date_sessions=[day for day in days if day>=received_date],
            completed_sessions_strictly_before_receipt_date=sum(day<received_date for day in days),
            missing_open_count=sum(value is None for value in quotes['open']),missing_close_count=sum(value is None for value in quotes['close']),
            returned_split_events=chart.get('events',{}).get('splits',{}),
            returned_dividend_count=len(chart.get('events',{}).get('dividends',{})),
            raw_quote_and_adjclose_separate=True,price_basis_adjudicated=False)
    except Exception as error:
        metadata.update(parse_status='RESPONSE_BODY_PRESERVED_PARSE_REJECTED',parse_error_type=type(error).__name__)
    return metadata


def main():
    inventory=preflight()
    OUTPUT.mkdir(parents=True,exist_ok=False)
    period2=int(datetime.now(timezone.utc).timestamp())
    with ThreadPoolExecutor(max_workers=2) as executor:
        rows=list(executor.map(lambda ticker:capture(ticker,period2),TICKERS))
    if [row['ticker'] for row in rows]!=list(TICKERS):raise ValueError('Exact bounded target denominator differs')
    source=Path(__file__).resolve()
    sources={str(source):hashlib.sha256(source.read_bytes()).hexdigest(),str(INVENTORY):INVENTORY_SHA}
    for row in rows:
        if row['response_path']:sources[row['response_path']]=row['response_sha256']
    report=dict(schema='ndx_provider_gap_first8_capture_v1',probes=rows,source_hashes=sources,
        explicit_request_tickers=list(TICKERS),request_count=8,maximum_attempts_per_ticker=1,
        request_end_exclusive_utc_epoch=period2,requested_start='2022-01-01',
        scope='MISSING_CHANNEL_OR_SHORT_HISTORY_RAW_EVIDENCE_ONLY',
        provider_request_ticker_is_not_historical_security_identity=True,delisted_security_missing_history_filled=False,
        historical_ticker_aliases_stitched=False,old_price_cache_modified=False,
        price_basis_and_corporate_action_completeness_adjudicated=False,
        provider_to_security_identity_verified=False,point_in_time_verified=False,promotion_allowed=False)
    for path,sha in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Capture closure changed')
    path=OUTPUT/'manifest.json';raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as stream:stream.write(raw)
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),outcomes=[
        {key:row.get(key) for key in ('ticker','http_status','response_bytes','parse_status','observed_session_count')} for row in rows])),flush=True)


if __name__=='__main__':main()
