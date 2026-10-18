"""Two bounded public mapping requests for seven unresolved security coordinates."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_current_22_price_capture_20260919 import save

OUTPUT = ROOT/'data/cache/research/current_seven_figi_capture_20260919_v1'
FACT = ROOT/'data/cache/research/current_92_sec_submissions_capture_20260919_v1/current101_issuer_facts.json'
FACT_SHA = '4fdd72c4f8887d59ad802ef37ac1641415888fb9c604b8a91601cb219a023d9d'
TICKERS = ('TER', 'NBIS', 'LITE', 'RKLB', 'ALAB', 'CRWV', 'SPCX')
URL = 'https://api.openfigi.com/v3/mapping'


if __name__ == '__main__':
    source = Path(__file__).resolve()
    sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
               (source, FACT, ROOT/'scripts/ndx_current_22_price_capture_20260919.py')}
    if sources[str(FACT)] != FACT_SHA:
        raise ValueError('Hard current SEC observation changed')
    facts = json.loads(FACT.read_bytes())
    if not set(TICKERS) <= {r['ticker'] for r in facts['rows']}:
        raise ValueError('Requested ticker outside current observed scope')
    OUTPUT.mkdir(parents=True, exist_ok=False)
    captures = []
    for offset in (0, 4):
        tickers = TICKERS[offset:offset+4]
        jobs = [dict(idType='TICKER', idValue=t, exchCode='US', marketSecDes='Equity') for t in tickers]
        payload = json.dumps(jobs, separators=(',', ':')).encode()
        name = 'batch_'+str(offset//4+1)
        request_path = OUTPUT/(name+'.request.json')
        with request_path.open('xb') as stream:
            stream.write(payload)
        row = dict(name=name, request_method='POST', request_url=URL, json_payload=jobs,
                   request_body_path=str(request_path), request_body_sha256=hashlib.sha256(payload).hexdigest(),
                   started_at_utc=datetime.now(timezone.utc).isoformat(), attempt_count=1, credentials_sent=False)
        headers = {'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json', 'Accept-Encoding': 'identity'}
        try:
            response = urlopen(Request(URL, data=payload, headers=headers, method='POST'), timeout=35)
        except HTTPError as error:
            response = error
        except Exception as error:
            row.update(http_status=None, error_type=type(error).__name__)
            response = None
        if response is not None:
            with response:
                raw = response.read()
                row.update(http_status=response.status, final_url=response.url,
                           response_headers={k: response.headers.get(k) for k in
                                             ('Date', 'Content-Type', 'Content-Encoding', 'Content-Length')})
            path = OUTPUT/(name+'.response.bin')
            with path.open('xb') as stream:
                stream.write(raw)
            decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
            row.update(raw_path=str(path), raw_sha256=hashlib.sha256(raw).hexdigest(),
                       raw_bytes=len(raw), decoded_sha256=hashlib.sha256(decoded).hexdigest())
        row['received_at_utc'] = datetime.now(timezone.utc).isoformat()
        save(OUTPUT/(name+'.receipt.json'), row)
        captures.append(row)
    for path, expected in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Source changed')
    path = OUTPUT/'manifest.json'
    sha = save(path, dict(schema='CURRENT_SEVEN_FIGI_MAPPING_RAW_CAPTURE_V1', captures=captures,
                         requested_tickers=list(TICKERS), source_hashes=sources,
                         historical_identity_verified=False, provider_price_identity_bound=False,
                         current_figi_mapping_adjudicated=False, point_in_time_verified=False,
                         promotion_allowed=False, no_retry_performed=True))
    print(json.dumps(dict(path=str(path), sha256=sha, statuses=[r.get('http_status') for r in captures])))
