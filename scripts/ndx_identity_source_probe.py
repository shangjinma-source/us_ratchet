"""Small create-only public source probe; no identity binding or execution."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data.ndx_history import _sec_headers, _sec_user_agent


def requests_to_probe():
    mappings = [{'idType': 'ID_CUSIP', 'idValue': value, 'exchCode': 'US'}
                for value in ('038222105', '11135F101', '127387108', '02079K107')]
    return [
        dict(name='openfigi_cusip_mapping', method='POST', url='https://api.openfigi.com/v3/mapping',
             json_payload=mappings, direct=False),
        dict(name='eastmoney_amat_nominal_two_sessions', method='GET', direct=True,
             url='https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=105.AMAT&klt=101&fqt=0'
                 '&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56&beg=20230331&end=20230403'),
        dict(name='yahoo_amat_two_sessions', method='GET', direct=False,
             url='https://query1.finance.yahoo.com/v8/finance/chart/AMAT?period1=1680220800&period2=1680566400&interval=1d'),
        dict(name='nasdaq_amat_historical_access', method='GET', direct=False,
             url='https://api.nasdaq.com/api/quote/AMAT/historical?assetclass=stocks&fromdate=2023-03-31&todate=2023-04-03&limit=10'),
        dict(name='nasdaq_meta_20220603_rename_notice', method='GET', direct=False,
             url='https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2022-125'),
        dict(name='occ_fiserv_20230605_rename_notice', method='GET', direct=False,
             url='https://infomemo.theocc.com/infomemos?number=52538'),
        dict(name='sec_qqq_nport_20230228', method='GET', direct=False,
             url='https://www.sec.gov/Archives/edgar/data/1067839/000175272423047901/primary_doc.xml'),
    ]


def capture(request):
    started = datetime.now(timezone.utc).isoformat()
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': '*/*'}
    if request['name'].startswith('sec_'):
        headers.update(_sec_headers(_sec_user_agent()))
    if 'nasdaq' in request['name']:
        headers['Referer'] = 'https://www.nasdaq.com/'
    payload = request.get('json_payload')
    body = json.dumps(payload, separators=(',', ':')).encode() if payload is not None else None
    if body is not None:
        headers['Content-Type'] = 'application/json'
    metadata = dict(name=request['name'], request=dict(method=request['method'], url=request['url'],
        json_payload=payload, direct_connection=request['direct'], credentials_sent=False), started_at_utc=started)
    try:
        opener = build_opener(ProxyHandler({})) if request['direct'] else build_opener()
        with opener.open(Request(request['url'], data=body, headers=headers, method=request['method']), timeout=20) as response:
            raw = response.read()
            metadata.update(http_status=response.status, final_url=response.url,
                            content_type=response.headers.get('Content-Type'), transport_success=True)
    except HTTPError as error:
        raw = error.read()
        metadata.update(http_status=error.code, final_url=request['url'],
                        content_type=error.headers.get('Content-Type'), transport_success=False,
                        error_type=type(error).__name__)
    except Exception as error:
        raw = None
        metadata.update(http_status=None, transport_success=False, error_type=type(error).__name__)
    metadata['received_at_utc'] = datetime.now(timezone.utc).isoformat()
    return metadata, raw


def run(output_directory):
    directory = Path(output_directory).resolve()
    if (ROOT / 'data/cache/research').resolve() not in directory.parents:
        raise ValueError('Separate research directory required')
    directory.mkdir(parents=True, exist_ok=False)
    items = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        for metadata, raw in executor.map(capture, requests_to_probe()):
            if raw is not None:
                path = directory / (metadata['name'] + '.response.bin')
                with path.open('xb') as stream:
                    stream.write(raw)
                metadata.update(response_path=str(path), response_sha256=hashlib.sha256(raw).hexdigest(),
                                response_bytes=len(raw))
                if path.read_bytes() != raw:
                    raise ValueError('Raw response readback differs')
            else:
                metadata.update(response_path=None, response_sha256=None, response_bytes=0)
            items.append(metadata)
    local = ROOT / 'data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv'
    manifest = dict(schema='ndx_identity_public_source_probe_v1', probes=items,
        observed_at_utc=datetime.now(timezone.utc).isoformat(),
        source_hashes={str(Path(__file__).resolve()): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      str(local): hashlib.sha256(local.read_bytes()).hexdigest()},
        purpose='ACTUAL_ACCESS_AND_RETROSPECTIVE_IDENTITY_EVIDENCE_PROBE_NOT_BRIDGE_INPUT',
        securities_are_probe_examples_not_fixed_portfolio=True,
        candidate_scope='ALL_POINT_IN_TIME_NDX_ISSUERS_NO_INDUSTRY_FILTER',
        provider_to_historical_security_binding_verified=False,
        historic_information_availability_verified=False, source_authenticity_adjudicated=False,
        point_in_time_verified=False, execution_performed=False, promotion_allowed=False,
        price_cache_modified=False, official_and_provider_claims_require_separate_review=True)
    path = directory / 'manifest.json'
    raw = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw)
    print(json.dumps(dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
        outcomes=[dict(name=row['name'], status=row['http_status'], bytes=row['response_bytes']) for row in items]), indent=2))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', required=True)
    run(parser.parse_args().output_directory)
