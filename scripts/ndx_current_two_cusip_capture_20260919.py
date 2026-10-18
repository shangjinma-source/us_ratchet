"""Two explicitly bounded SEC Schedule13G requests, no retries or old overwrites."""
from datetime import datetime,timezone
import gzip,hashlib,json,os
from pathlib import Path
import urllib.request,urllib.error

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research/current_two_cusip_capture_20260919_v1'
SOURCE=Path(__file__).resolve()
REQUESTS=(('TER','0000097210','0002012383-26-003160','https://www.sec.gov/Archives/edgar/data/97210/000201238326003160/primary_doc.xml'),
          ('LITE','0001633978','0000315066-26-001454','https://www.sec.gov/Archives/edgar/data/1633978/000031506626001454/primary_doc.xml'))
def now():return datetime.now(timezone.utc).isoformat()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(path,raw):
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
def main():
    BASE.mkdir(exist_ok=False);rows=[];sources={str(SOURCE):sha(SOURCE.read_bytes())}
    original=ROOT/'data/cache/research/current_nine_identity_capture_20260919_v1/manifest.json'
    if sha(original.read_bytes())!='adef593e19ec56acc4468ccddcc0d5177deb3b5c40d19a7db7ef3af947225c9c':raise ValueError('Bound issuer submissions manifest changed')
    sources[str(original)]=sha(original.read_bytes());manifest=json.loads(original.read_bytes())
    for ticker,cik,accession,url in REQUESTS:
        source=original.parent/(cik+'.response.bin');raw=source.read_bytes();sources[str(source)]=sha(raw)
        captures=[c for c in manifest['captures'] if c['raw_path']==str(source)]
        if len(captures)!=1 or captures[0]['raw_sha256']!=sha(raw):raise ValueError('Bound submissions raw changed')
        body=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)
        recent=body['filings']['recent'];i=recent['accessionNumber'].index(accession)
        if recent['form'][i]!='SCHEDULE 13G/A' or recent['primaryDocument'][i].split('/')[-1]!='primary_doc.xml':raise ValueError('Original accession/document differs')
        started=dict(ticker=ticker,subject_cik=cik,accession=accession,filing_date=recent['filingDate'][i],request_url=url,started_at_utc=now(),attempt=1)
        p=BASE/(ticker+'.started.json');save(p,json.dumps(started,sort_keys=True).encode());sources[str(p)]=sha(p.read_bytes())
        request=urllib.request.Request(url,headers={'User-Agent':'ResearchIdentityReadback/1.0','Accept-Encoding':'gzip'})
        try:
            response=urllib.request.urlopen(request,timeout=35);status=response.status
        except urllib.error.HTTPError as error:response=error;status=error.code
        except Exception as error:
            row=dict(started,received_at_utc=now(),http_status=None,error_type=type(error).__name__,error=str(error),raw_path=None)
            rows.append(row);save(BASE/(ticker+'.receipt.json'),json.dumps(row,sort_keys=True).encode());continue
        with response:raw=response.read();headers=dict(response.headers);final_url=response.geturl()
        path=BASE/(ticker+'.response.bin');save(path,raw);sources[str(path)]=sha(raw)
        row=dict(started,received_at_utc=now(),http_status=status,response_headers=headers,final_url=final_url,raw_path=str(path),raw_sha256=sha(raw),bytes=len(raw),credentials_sent=False)
        receipt=BASE/(ticker+'.receipt.json');save(receipt,json.dumps(row,sort_keys=True).encode());sources[str(receipt)]=sha(receipt.read_bytes());rows.append(row)
        print(json.dumps(dict(ticker=ticker,status=status,sha256=sha(raw))),flush=True)
    report=dict(schema='BOUNDED_TWO_SEC_CUSIP_CAPTURE_V1',captures=rows,source_hashes=sources,no_retries=True,point_in_time_verified=False)
    path=BASE/'manifest.json';save(path,(json.dumps(report,sort_keys=True,indent=2)+'\n').encode());print(json.dumps(dict(path=str(path),sha256=sha(path.read_bytes()))))
if __name__=='__main__':main()
