"""Single-attempt public mirror capture; not SEC-origin HTTP evidence."""
from datetime import datetime,timezone
import gzip,hashlib,json,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/cache/research/adobe_historical_peer_mirror_20260919_v1'
PRIOR=ROOT/'data/cache/research/adobe_historical_peer_capture_20260919_v1/manifest.json'
PRIOR_SHA='d1d7ac4beb0dd4b85b68033129eb852b34e2da0bb193577d321f63f03dc90947'
URLS={2023:'https://cdn.yahoofinance.com/prod/sec-filings/0000796343/000079634323000011/adbe8-kex10212623.htm',2024:'https://cdn.yahoofinance.com/prod/sec-filings/0000796343/000079634324000024/adbeex10212624.htm'}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(path,raw):
    with path.open('xb') as stream:stream.write(raw)
def now():return datetime.now(timezone.utc).isoformat()
def run():
    if sha(PRIOR.read_bytes())!=PRIOR_SHA:raise ValueError('Bound original failed capture changed')
    OUT.mkdir(exist_ok=False);rows=[]
    for year,url in URLS.items():
        started=now();request=dict(year=year,request_url=url,started_at_utc=started,request_method='GET',credentials_sent=False,attempt_count=1)
        save(OUT/f'{year}.started.json',json.dumps(request,sort_keys=True).encode())
        row=dict(request)
        try:
            try:response=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept-Encoding':'identity'}),timeout=50)
            except urllib.error.HTTPError as error:response=error
            raw=response.read();row.update(http_status=response.status,final_url=response.geturl(),response_headers={k:response.headers.get(k) for k in ('Content-Type','Content-Encoding','Content-Length','Date','Last-Modified','ETag')})
            row['received_at_utc']=now();path=OUT/f'{year}.response.bin';save(path,raw)
            row.update(raw_path=str(path),raw_sha256=sha(raw),raw_bytes=len(raw))
            decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
            row['decoded_sha256']=sha(decoded)
        except Exception as error:row.update(error_type=type(error).__name__,received_at_utc=now())
        save(OUT/f'{year}.receipt.json',json.dumps(row,sort_keys=True,indent=2).encode());rows.append(row)
    report=dict(schema='ADOBE_PUBLIC_MIRROR_RAW_CAPTURE_V1',captures=rows,source_hashes={str(PRIOR):PRIOR_SHA,str(Path(__file__).resolve()):sha(Path(__file__).read_bytes())},sec_origin_http_obtained=False,mirror_chain_is_original_sec_authentication=False,point_in_time_verified=False,exact_ndx_security_baseline_verified=False)
    path=OUT/'manifest.json';save(path,json.dumps(report,sort_keys=True,indent=2).encode());print(json.dumps(dict(path=str(path),sha256=sha(path.read_bytes()),statuses=[r.get('http_status') for r in rows])))
if __name__=='__main__':run()
