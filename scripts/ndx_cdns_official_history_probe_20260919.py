"""One request per new CDNS public URL; no retries or old 403 endpoints."""
import hashlib,json,urllib.request,urllib.error
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/cache/research/cdns_history_source_probe_20260919_v1'
URLS={'current_ir_annual':'https://investor.cadence.com/financials/annual-reports/default.aspx','q4_hosted_history':'https://cadencenextgen.q4web.com/Stock-Historical/default.aspx'}


def save(path,value):
    with path.open('xb') as f:f.write(json.dumps(value,sort_keys=True,indent=2).encode())


def main():
    OUT.mkdir(exist_ok=False);rows=[]
    for name,url in URLS.items():
        start=datetime.now(timezone.utc).isoformat();record=dict(name=name,url=url,request_method='GET',credentials_sent=False,attempt_count=1,started_at_utc=start)
        save(OUT/(name+'.started.json'),record)
        try:
            try:response=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept-Encoding':'identity'}),timeout=45)
            except urllib.error.HTTPError as error:response=error
            with response:
                body=response.read();record.update(http_status=response.code,final_url=response.geturl(),response_headers={k:v for k,v in response.headers.items() if k.lower() not in ('set-cookie','cookie','authorization')})
            path=OUT/(name+'.response.bin')
            with path.open('xb') as f:f.write(body)
            record.update(response_path=str(path),response_sha256=hashlib.sha256(body).hexdigest(),response_bytes=len(body))
        except Exception as error:record.update(error_type=type(error).__name__)
        record['received_at_utc']=datetime.now(timezone.utc).isoformat();save(OUT/(name+'.receipt.json'),record);rows.append(record)
    value=dict(schema='CDNS_NEW_HISTORY_SOURCE_CAPTURE_V1',probes=rows,source_hashes={str(Path(__file__).resolve()):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},official_q4_host_delegation_independently_verified=False,point_in_time_verified=False)
    path=OUT/'manifest.json';save(path,value);print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),statuses=[r.get('http_status') for r in rows])))


if __name__=='__main__':main()
