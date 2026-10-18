"""Three dated split facts from sealed primary documents; no registry mutation."""
import hashlib,json,io
from pathlib import Path
import sys
from bs4 import BeautifulSoup
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.ndx_current_22_price_capture_20260919 import save
BASE=ROOT/'data/cache/research'
BINDINGS={str(BASE/'current_three_split_official_20260919_v1/manifest.json'):'d15123ee810a9b105aeb6b21991271aaf49b174e1740aa855fc2e451acb8d75b',str(BASE/'current_mstr_pdf_split_20260919_v1/manifest.json'):'971e8ffe8b540cf949be248f01b0e46fc3570607d98c3abb4256ca7452aac105'}
SPEC=[('MSTR','mstr_pdf',10,'2024-08-01','2024-08-07','2024-08-08',['10-for-1 stock split','class A common stock and class B common stock','August 1, 2024','August 7, 2024','open on August 8, 2024']),('SHOP','shop_split',10,'2022-06-22','2022-06-28','2022-06-29',['10-for-1 split','Class A and Class B shares','June 22, 2022','June 28, 2022','split-adjusted basis will commence on June 29, 2022']),('WMT','wmt_split',3,'2024-02-22','2024-02-23','2024-02-26',['3-for-1','two additional shares of common stock for each share held','Feb. 22, 2024','Feb. 23, 2024','market open on Monday, Feb. 26, 2024'])]

def build():
    sources=dict(BINDINGS);captures={}
    for path,sha in BINDINGS.items():
        raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Manifest SHA differs')
        m=json.loads(raw);sources.update(m['source_hashes']);captures.update({r['name']:r for r in m['captures']})
    rows=[]
    for ticker,name,ratio,record,distribution,trade,markers in SPEC:
        c=captures[name];raw=Path(c['raw_path']).read_bytes()
        if c['http_status']!=200 or hashlib.sha256(raw).hexdigest()!=c['raw_sha256']:raise ValueError('Successful primary bytes required')
        sources[c['raw_path']]=c['raw_sha256']
        text=' '.join((' '.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(raw)).pages) if name=='mstr_pdf' else BeautifulSoup(raw.decode('utf-8'),'html.parser').get_text(' ',strip=True)).split())
        if not all(marker in text for marker in markers):raise ValueError('Actual primary text lacks fact marker: '+ticker)
        rows.append(dict(ticker=ticker,new_shares=ratio,old_shares=1,record_date=record,distribution_date=distribution,first_adjusted_trading_date=trade,specific_simple_share_split_event_supported=True,announcement_is_execution_completion_certificate=False,primary_url=c['request_url'],primary_raw_path=c['raw_path'],primary_raw_sha256=c['raw_sha256'],actual_received_at_utc=c['received_at_utc'],normalized_text_sha256=hashlib.sha256(text.encode()).hexdigest(),fact_marker_offsets=[text.index(marker) for marker in markers],price_identity_verified=False,quote_basis_authenticated=False))
    sources[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for path,sha in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Source closure differs')
    return dict(schema='THREE_CURRENT_STANDARD_SPLIT_PRIMARY_FACTS_V1',events=rows,event_count=3,source_hashes=sources,old_registry_modified=False,provider_price_reconstruction_performed=False,point_in_time_verified=False,promotion_allowed=False)

if __name__=='__main__':
    report=build();path=BASE/'current_mstr_pdf_split_20260919_v1/three_split_facts.json';sha=save(path,report)
    print(json.dumps(dict(path=str(path),sha256=sha,events=3)))
