"""One new issuer-CDN Schedule13G PDF request, never retries SEC failures."""
from datetime import datetime,timezone
import hashlib,json,os,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research/lite_cusip_pdf_capture_20260919_v1'
URL='https://d18rn0p25nwr6d.cloudfront.net/CIK-0001633978/b4fbf679-6549-49f6-8e06-6671a8a13e28.pdf'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(path,raw):
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
def main():
    BASE.mkdir(exist_ok=False)
    start=dict(request_url=URL,attempt=1,credentials_sent=False,started_at_utc=datetime.now(timezone.utc).isoformat())
    save(BASE/'started.json',json.dumps(start,sort_keys=True).encode())
    try:response=urllib.request.urlopen(urllib.request.Request(URL,headers={'User-Agent':'ResearchIdentityReadback/1.0','Accept-Encoding':'gzip'}),timeout=35)
    except urllib.error.HTTPError as error:response=error
    with response:raw=response.read();status=response.status;headers=dict(response.headers);final=response.geturl()
    path=BASE/'response.bin';save(path,raw)
    receipt=dict(start,received_at_utc=datetime.now(timezone.utc).isoformat(),http_status=status,response_headers=headers,final_url=final,raw_path=str(path),raw_sha256=sha(raw),bytes=len(raw))
    save(BASE/'receipt.json',json.dumps(receipt,sort_keys=True).encode())
    sources={str(p):sha(p.read_bytes()) for p in [Path(__file__).resolve(),BASE/'started.json',BASE/'receipt.json',path]}
    report=dict(schema='SINGLE_ISSUER_CDN_PDF_CAPTURE_V1',captures=[receipt],source_hashes=sources,sec_origin_http=False,no_retries=True)
    out=BASE/'manifest.json';save(out,(json.dumps(report,sort_keys=True,indent=2)+'\n').encode());print(json.dumps(dict(path=str(out),sha256=sha(out.read_bytes()),status=status)))
if __name__=='__main__':main()
