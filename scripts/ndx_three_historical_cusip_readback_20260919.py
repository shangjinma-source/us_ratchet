"""Actual dated SEC accession/10K readback; refused CUSIP raw remains unresolved."""
import argparse,gzip,hashlib,json,re,sys
from pathlib import Path
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.ndx_base_three_cell_window_delta_research import publish
BASE=ROOT/'data/cache/research'
MANIFESTS={
 'three_historical_cusip_capture_20260919_v1/manifest.json':'a284757f9cc856a52353b19fbd9c9733688280cd485c89ced8266586a8cfd689',
 'three_cusip_proxy_capture_20260919_v1/manifest.json':'31085bdb196c9bc955fa52d0313580a0502e00b13a3cc18babb0cbd2f158ac22',
 'three_cusip_mirror_capture_20260919_v1/manifest.json':'721f652ba1eb6cac7b83f9c9e8f030d95c2d71363ca0580c7a9ad2217cdd9f80',
 'three_cusip_primary_document_capture_20260919_v1/manifest.json':'3183e57a1f4b9d505920005ba9885b40ca615fd2fd535d4dc9063c84a0f93dc0'}
SECROOT=ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec'
FACTS={
 'ADI':dict(cik='0000006281',cusip='032654105',name='ANALOG DEVICES INC',security_class='Common Stock',file='issuer_0000006281/000000628121000294/adi-20211030.htm',sha='255342488f21389d46960ed589b984d58cd60e0e1618909272a972e3a015a6ea'),
 'BKR':dict(cik='0001701605',cusip='05722G100',name='BAKER HUGHES CO',security_class='Class A Common Stock',file='issuer_0001701605/000170160523000044/bkr-20221231.htm',sha='8458f2d9338cdbaa8f0660727f1989a2b96907d98e45539692a2265f1b5d1132'),
 'ENPH':dict(cik='0001463101',cusip='29355A107',name='ENPHASE ENERGY INC',security_class='Common Stock',file='issuer_0001463101/000146310123000025/enph-20221231.htm',sha='f47eb4e10c93db78039c7d70d89a8c2eb9098de30ed0a7784b8b3cc72ddf22ab')}
SOURCE=Path(__file__).resolve();LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,Path(publish.__code__.co_filename).resolve())}

def decode(raw):return gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
def checksum(cusip):
    total=0
    for i,c in enumerate(cusip[:8]):
        n=int(c) if c.isdigit() else ord(c)-55;n*=1 if i%2==0 else 2;total+=n//10+n%10
    return len(cusip)==9 and cusip[-1]==str((10-total%10)%10)

def parse_primary(raw,ticker,selection):
    fact=FACTS[ticker]
    if selection['cik']!=fact['cik'] or selection['ticker']!=ticker or selection['form'] not in ('SC 13G','SC 13G/A'):raise ValueError('Original accession subject differs')
    text=' '.join(BeautifulSoup(decode(raw).decode('utf-8'),'html.parser').get_text(' ',strip=True).split())
    cover=text.split('Check the appropriate box',1)[0]
    if selection['primary_document'] not in text[:1000] or 'SCHEDULE 13G' not in cover:raise ValueError('Exact original primary document required')
    separators=r'\s*(?:-+\s*)?'
    pattern=re.escape(fact['name'])+separators+r'\(Name of Issuer\)\s*'+re.escape(fact['security_class'])+separators+r'\(Title of Class of Securities\)\s*'+fact['cusip']+separators+r'\(CUSIP Number\)\s*December 31, 2022'
    if re.search(pattern,cover,re.I) is None or not checksum(fact['cusip']):raise ValueError('Contiguous dated security cover differs')
    return dict(cusip=fact['cusip'],security_class=fact['security_class'],event_date='2022-12-31',filing_date=selection['filing_date'],accession=selection['accession'])

def parse_cover(raw,ticker):
    soup=BeautifulSoup(raw.decode('utf-8'),'html.parser');fact=FACTS[ticker]
    def field(name):
        values={n.get_text(' ',strip=True) for n in soup.find_all() if n.get('name','').lower()=='dei:'+name.lower()}
        if len(values)!=1:raise ValueError('Unique cover field required')
        return values.pop()
    cik=field('EntityCentralIndexKey');symbol=field('TradingSymbol');title=field('Security12bTitle')
    if cik!=fact['cik'] or symbol!=ticker or not title.startswith(fact['security_class']):raise ValueError('Original cover identity differs')
    return dict(cik=cik,ticker=symbol,security_class_title=title,period_end_original_text=field('DocumentPeriodEndDate'),cusip_present_in_filing_text=fact['cusip'] in soup.get_text())

def verify(sources):
    for p,h in sources.items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise ValueError('Source changed')

def build():
    sources=dict(LOADED)
    def add(path,h):
        path=str(Path(path).resolve())
        if path in sources and sources[path]!=h:raise ValueError('Source collision')
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=h:raise ValueError('Hard source differs')
        sources[path]=h;return Path(path).read_bytes()
    manifests=[]
    for relative,h in MANIFESTS.items():
        value=json.loads(add(BASE/relative,h));manifests.append(value)
        for p,sha in value['source_hashes'].items():add(p,sha)
    rows=[];selections=manifests[0]['selections']
    if {r['ticker'] for r in selections}!=set(FACTS) or len(selections)!=3:raise ValueError('Complete three-subject denominator required')
    for selection in selections:
        ticker=selection['ticker'];fact=FACTS[ticker]
        submission=json.loads(decode(add(selection['submissions_path'],selection['submissions_sha256'])))
        if str(submission['cik']).zfill(10)!=fact['cik']:raise ValueError('Subject CIK differs from actual SEC submissions')
        recent=submission['filings']['recent'];i=recent['accessionNumber'].index(selection['accession'])
        if any(selection[k]!=recent[field][i] for k,field in (('form','form'),('filing_date','filingDate'),('primary_document','primaryDocument'))):raise ValueError('Actual dated accession row differs')
        cover=parse_cover(add(SECROOT/fact['file'],fact['sha']),ticker)
        outcomes=[{k:r.get(k) for k in ('name','request_url','http_status','raw_path','raw_sha256','received_at_utc')} for manifest in manifests for r in manifest['captures'] if r['name'].startswith(ticker+'_') and 'submissions' not in r['name']]
        if any(r['http_status']==200 for r in outcomes):raise ValueError('New successful raw requires explicit independent readback, not automatic promotion')
        rows.append(dict(ticker=ticker,requested_local_cusip=fact['cusip'],cusip_checksum_valid=checksum(fact['cusip']),actual_sec_accession=selection,
            original_10k_cover=cover,capture_outcomes=outcomes,cusip_raw_primary_verified=False,
            status='DATED_ACCESSION_AND_CIK_TICKER_CLASS_LOCATED_CUSIP_RAW_UNAVAILABLE',provider_binding_verified=False,historical_identity_interval_verified=False))
    verify(sources)
    return dict(schema='THREE_HISTORICAL_CUSIP_SOURCE_GAP_READBACK_V1',rows=rows,security_count=3,raw_cusip_verified_count=0,
        all_failed_responses_preserved=True,web_search_snippets_used_as_raw_evidence=False,source_hashes=sources,
        same_failed_endpoint_retried=False,point_in_time_verified=False,promotion_allowed=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    value=build();saved=publish(args.output,value);verify(value['source_hashes']);print(json.dumps(saved))
