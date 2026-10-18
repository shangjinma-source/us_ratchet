"""Bounded one-shot historical ADI/BKR/ENPH submissions and 13G capture."""
from datetime import datetime,timezone
import gzip,hashlib,json,os
from pathlib import Path
import urllib.request,urllib.error

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research/three_historical_cusip_capture_20260919_v1'
SOURCE=Path(__file__).resolve()
PARENT=ROOT/'data/cache/research/current_92_sec_submissions_capture_20260919_v1/manifest.json'
PARENT_SHA='dd7e767031ad6902944d6a540c63e901319d7bca4cc20cfb34f6d2e2b46bf743'

def now():return datetime.now(timezone.utc).isoformat()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(path,raw):
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())

def capture(name,url,sources):
    started=dict(name=name,request_url=url,started_at_utc=now(),attempt=1,credentials_sent=False)
    p=BASE/(name+'.started.json');save(p,json.dumps(started,sort_keys=True).encode());sources[str(p)]=sha(p.read_bytes())
    request=urllib.request.Request(url,headers={'User-Agent':'ResearchIdentityReadback/1.0','Accept-Encoding':'gzip'})
    try:
        response=urllib.request.urlopen(request,timeout=35);status=response.status
    except urllib.error.HTTPError as error:response=error;status=error.code
    except Exception as error:
        row=dict(started,http_status=None,received_at_utc=now(),error_type=type(error).__name__,error=str(error),raw_path=None)
    else_error=False
    if 'response' in locals():
        with response:raw=response.read();headers=dict(response.headers);final=response.geturl()
        p=BASE/(name+'.response.bin');save(p,raw);sources[str(p)]=sha(raw)
        row=dict(started,http_status=status,received_at_utc=now(),response_headers=headers,final_url=final,raw_path=str(p),raw_sha256=sha(raw),bytes=len(raw))
    p=BASE/(name+'.receipt.json');save(p,json.dumps(row,sort_keys=True).encode());sources[str(p)]=sha(p.read_bytes())
    print(json.dumps(dict(name=name,status=row['http_status'],sha256=row.get('raw_sha256'))),flush=True)
    return row

def decode(raw):return json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)

def main():
    if sha(PARENT.read_bytes())!=PARENT_SHA:raise ValueError('Original submissions parent changed')
    BASE.mkdir(exist_ok=False);sources={str(SOURCE):sha(SOURCE.read_bytes()),str(PARENT):PARENT_SHA}
    parent=json.loads(PARENT.read_bytes());captures=[];selections=[]
    for ticker,cik,accession in [('ADI','0000006281','0001306550-23-008254'),('BKR','0001701605','0001306550-23-007056'),('ENPH','0001463101',None)]:
        if ticker!='ENPH':
            p=PARENT.parent/(cik+'.response.bin');raw=p.read_bytes()
            entry,=[r for r in parent['captures'] if r['raw_path']==str(p)]
            if sha(raw)!=entry['raw_sha256']:raise ValueError('Original issuer submissions changed')
            sources[str(p)]=sha(raw);body=decode(raw)
        else:
            response=capture('ENPH_submissions','https://data.sec.gov/submissions/CIK0001463101.json',sources);captures.append(response)
            if response['http_status']!=200:continue
            p=Path(response['raw_path']);body=decode(p.read_bytes())
        if int(body['cik'])!=int(cik):raise ValueError('Target CIK differs')
        recent=body['filings']['recent']
        if accession is None:
            eligible=[i for i,f in enumerate(recent['form']) if f in ('SC 13G','SC 13G/A') and '2023-01-01'<=recent['filingDate'][i]<='2023-03-31']
            if not eligible:raise ValueError('No actual contemporaneous ENPH filing located')
            i=min(eligible,key=lambda i:(recent['filingDate'][i],recent['accessionNumber'][i]));accession=recent['accessionNumber'][i]
        i=recent['accessionNumber'].index(accession)
        if recent['form'][i] not in ('SC 13G','SC 13G/A') or not '2023-01-01'<=recent['filingDate'][i]<='2023-03-31':raise ValueError('Exact dated 13G required')
        selection=dict(ticker=ticker,cik=cik,accession=accession,form=recent['form'][i],filing_date=recent['filingDate'][i],primary_document=recent['primaryDocument'][i],submissions_path=str(p),submissions_sha256=sha(p.read_bytes()))
        selections.append(selection)
        url=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/{accession}.txt'
        captures.append(capture(ticker+'_13G',url,sources))
    for p,h in sources.items():
        if sha(Path(p).read_bytes())!=h:raise ValueError('Source changed')
    report=dict(schema='THREE_DATED_CUSIP_BOUNDED_CAPTURE_V1',selections=selections,captures=captures,source_hashes=sources,no_retries=True,point_in_time_verified=False,promotion_allowed=False)
    p=BASE/'manifest.json';save(p,(json.dumps(report,sort_keys=True,indent=2)+'\n').encode());print(json.dumps(dict(path=str(p),sha256=sha(p.read_bytes()))))

if __name__=='__main__':main()
