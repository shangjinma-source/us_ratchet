"""Bounded official-current evidence capture; does not certify historical membership."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/cache/research/ndx_current_component_evidence_20260912_v1'
BASE = ROOT / 'data/cache/research/ndx_current_quote_list_capture_20260912_v1'
BOUND = {'manifest.json': 'e7927e7c0987ddbb92df1a6b92b6ab248c5d1e68388c9a66578638d02bd3a110',
         'observation.json': '950a76544cc63d11ed492b8feb37f2d7eebe4212f42b1761e9ac9a65938a5e38',
         'nasdaq100_quote_list.response.bin': '127c761b125aa9408af9f04623b70fa138ff9349b4efcfbc484296a2d8e3f513'}
URLS = {
    'official_overview': 'https://indexes.nasdaq.com/Index/Overview/NDX',
    'current_methodology': 'https://indexes.nasdaq.com/docs/Methodology_NDX.pdf',
    'spcx_addition': 'https://ir.nasdaq.com/news-releases/news-release-details/space-exploration-technologies-corporation-join-nasdaq-100',
    'hona_completed_spinoff': 'https://www.nasdaq.com/press-release/honeywell-technologies-launches-independent-pure-play-automation-company-following',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def capture(item):
    name, url = item
    row = dict(name=name, request_url=url, request_method='GET', attempt_count=1,
               started_at_utc=datetime.now(timezone.utc).isoformat(), credentials_sent=False)
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'identity'}
    row['request_headers'] = headers
    raw = None
    try:
        response = urlopen(Request(url, headers=headers), timeout=35)
    except HTTPError as error:
        response = error
    except Exception as error:
        row.update(http_status=None, error_type=type(error).__name__)
        response = None
    if response is not None:
        with response:
            raw = response.read()
            row.update(http_status=response.status, final_url=response.url,
                       response_headers={key: response.headers.get(key) for key in
                                         ('Date', 'Content-Type', 'Content-Encoding', 'Content-Length', 'ETag', 'Last-Modified')})
    row['received_at_utc'] = datetime.now(timezone.utc).isoformat()
    row['response_header_policy'] = 'LISTED_CONTENT_DATE_VALIDATOR_FIELDS_ONLY_NO_COOKIES'
    if raw is not None:
        path = OUTPUT / (name + '.response.bin')
        with path.open('xb') as stream:
            stream.write(raw)
        assert path.read_bytes() == raw
        decoded = gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw
        row.update(raw_path=str(path), raw_sha256=sha(raw), raw_bytes=len(raw), decoded_sha256=sha(decoded))
    return row


def main():
    sources = {str(Path(__file__).resolve()): sha(Path(__file__).read_bytes())}
    for name, expected in BOUND.items():
        path = BASE / name
        if sha(path.read_bytes()) != expected:
            raise ValueError('Bound source changed: ' + name)
        sources[str(path)] = expected
    raw = json.loads((BASE / 'nasdaq100_quote_list.response.bin').read_bytes())
    data = raw['data']
    rows = data['data']['rows']
    symbols = [row['symbol'] for row in rows]
    observation = json.loads((BASE / 'observation.json').read_bytes())
    if not (raw['status']['rCode'] == 200 and len(rows) == len(set(symbols)) == data['totalrecords'] == data['limit'] == 102
            and data['offset'] == 0 and observation['rows'] == rows and observation['observed_symbols'] == symbols):
        raise ValueError('Endpoint denominator, distinctness or bound observation differs')
    OUTPUT.mkdir(parents=True, exist_ok=False)
    with ThreadPoolExecutor(max_workers=2) as executor:
        captures = list(executor.map(capture, URLS.items()))
    report = dict(schema='ndx_current_component_official_evidence_capture_v1', captures=captures,
                  source_hashes=sources, verified_quote_row_count=102, unique_quote_symbols=102,
                  pagination=dict(totalrecords=102, limit=102, offset=0, entire_returned_endpoint_denominator=True),
                  provider_date=data['date'], provider_asof=data['data']['asOf'],
                  source_date_semantics='QUOTE_DISPLAY_DATE_NOT_MEMBERSHIP_EFFECTIVE_DATE',
                  historical_membership_backfill_allowed=False, complete_pit_membership_verified=False,
                  listing_identity_adjudicated=False, securities_count_is_not_issuer_count=True,
                  same_ticker_history_join_allowed=False, promotion_allowed=False)
    for path, expected in sources.items():
        if sha(Path(path).read_bytes()) != expected:
            raise ValueError('Source drift during capture')
    path = OUTPUT / 'manifest.json'
    with path.open('xb') as stream:
        stream.write((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps(dict(path=str(path), sha256=sha(path.read_bytes()), statuses=[(x['name'], x['http_status']) for x in captures])))


if __name__ == '__main__':
    main()
