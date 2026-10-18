"""Bounded seven-security inventory and one accession-linked dated CUSIP fact."""
import csv,gzip,hashlib,io,json
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'data/cache/research'
SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PDF=BASE/'lite_cusip_pdf_capture_20260919_v1/manifest.json';PDF_SHA='38aa736e81ffdcd3e4e918a467a8da8b97fce6b239dc1135d7822a65084edaa4'
FAIL=BASE/'current_two_cusip_capture_20260919_v1/manifest.json';FAIL_SHA='4c994257f5a9d8d54200620268aae50b953db495f53b1b2fa6e8ac5654bad6fb'
IDENTITY=BASE/'current_nine_identity_capture_20260919_v1/manifest.json';IDENTITY_SHA='adef593e19ec56acc4468ccddcc0d5177deb3b5c40d19a7db7ef3af947225c9c'
TICKERS=('TER','NBIS','LITE','RKLB','ALAB','CRWV','SPCX')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def cusip_valid(value):
    values=[int(c) if c.isdigit() else ord(c)-ord('A')+10 for c in value[:8]]
    products=[n*(1 if i%2==0 else 2) for i,n in enumerate(values)]
    return len(value)==9 and value[-1].isdigit() and (10-sum(n//10+n%10 for n in products)%10)%10==int(value[-1])
def extract(text,metadata,submissions):
    accession='0001422849-25-000008'
    if metadata.get('/Title')!=accession or metadata.get('/Subject')!='Form SC 13G filed on 2025-02-13':raise ValueError('PDF filing accession metadata differs')
    cover='Lumentum Holdings Inc. (Name of Issuer) Common Stock (Title of Class of Securities) 55024U109 (CUSIP Number) 12/31/2024 (Date of Event Which Requires Filing of this Statement)'
    if text.count(cover)!=1 or 'Date: 02/12/2025' not in text:raise ValueError('Exact contiguous dated class/CUSIP cover absent')
    if str(submissions['cik']).zfill(10)!='0001633978' or submissions['tickers']!=['LITE'] or submissions['exchanges']!=['Nasdaq']:raise ValueError('Same-position issuer/ticker/exchange differs')
    recent=submissions['filings']['recent'];matches=[i for i,a in enumerate(recent['accessionNumber']) if a==accession]
    if len(matches)!=1:raise ValueError('PDF accession absent/ambiguous in subject issuer SEC submissions')
    i=matches[0]
    if recent['form'][i]!='SCHEDULE 13G' or recent['filingDate'][i]!='2025-02-13' or recent['primaryDocument'][i]!='xslSCHEDULE_13G_X01/primary_doc.xml':raise ValueError('Bound SEC filing row differs')
    return dict(ticker='LITE',subject_issuer_cik='0001633978',accession=accession,filing_date='2025-02-13',event_date='2024-12-31',signed_date='2025-02-12',
        security_class='Common Stock',cusip='55024U109',cusip_checksum_valid=cusip_valid('55024U109'),filing_cover_start=text.index(cover),filing_cover_text=cover,
        source_kind='ISSUER_CIK_CDN_EDGAR_EXPORT_PDF_NOT_DIRECT_SEC_HTTP',pdf_export_provider=metadata.get('/Author'),
        issuer_link_method='EXACT_PDF_ACCESSION_PRESENT_IN_BOUND_SUBJECT_SEC_SUBMISSIONS_NOT_NAME_JOIN',
        dated_security_class_and_cusip_observed=True,current_20260919_cusip_certified=False,interval_identity_verified=False,
        historical_ticker_at_event_independently_verified=False,provider_price_identity_bound=False,point_in_time_verified=False,promotion_allowed=False)

def build():
    sources={str(SOURCE):LOADED}
    def read(p,h):
        p=str(Path(p).resolve());raw=Path(p).read_bytes()
        if sha(raw)!=h or p in sources and sources[p]!=h:raise ValueError('Bound source differs')
        sources[p]=h;return raw
    manifests=[json.loads(read(p,h)) for p,h in ((PDF,PDF_SHA),(FAIL,FAIL_SHA),(IDENTITY,IDENTITY_SHA))]
    for manifest in manifests:
        for p,h in manifest['source_hashes'].items():read(p,h)
    receipt,=manifests[0]['captures']
    if receipt['http_status']!=200 or receipt['final_url']!=receipt['request_url']:raise ValueError('Original successful PDF channel required')
    raw=read(receipt['raw_path'],receipt['raw_sha256']);decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    pdf=PdfReader(io.BytesIO(decoded));text=' '.join(' '.join(page.extract_text() or '' for page in pdf.pages).split())
    path=IDENTITY.parent/'0001633978.response.bin';capture,=[r for r in manifests[2]['captures'] if r['raw_path']==str(path)]
    raw=read(path,capture['raw_sha256']);sub=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)
    fact=extract(text,dict(pdf.metadata),sub)
    fact.update(raw_pdf_path=receipt['raw_path'],raw_pdf_sha256=receipt['raw_sha256'],decoded_pdf_sha256=sha(decoded),normalized_document_text_sha256=sha(text.encode()),received_at_utc=receipt['received_at_utc'])
    nport=ROOT/'data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv';raw=nport.read_bytes();read(nport,sha(raw));rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    report=dict(schema='CURRENT_SEVEN_BOUNDED_DATED_SECURITY_EVIDENCE_V1',requested_tickers=list(TICKERS),
        local_nport_exact_ticker_counts={t:sum(r['ticker']==t for r in rows) for t in TICKERS},dated_facts=[fact],
        unresolved=[dict(ticker=t,reason='NO_LOCAL_DATED_CUSIP_CLASS_RAW_LOCATED_IN_BOUNDED_SCAN',current_figi_or_issuer_not_substituted_for_cusip=True) for t in TICKERS if t!='LITE'],
        failed_requests=[dict(ticker=r['ticker'],request_url=r['request_url'],http_status=r['http_status'],raw_path=r['raw_path'],raw_sha256=r['raw_sha256']) for r in manifests[1]['captures']],
        http_retries_performed=False,all_seven_current_security_identities_closed=False,historical_interval_identity_verified=False,
        provider_price_identity_bound=False,point_in_time_verified=False,promotion_allowed=False,source_hashes=sources)
    for p,h in sources.items():read(p,h)
    return report

if __name__=='__main__':
    from scripts.ndx_base_three_cell_window_delta_research import publish
    report=build();out=BASE/'lite_cusip_pdf_capture_20260919_v1/seven_security_readback.json'
    print(json.dumps(publish(out,report)))
    for p,h in report['source_hashes'].items():
        if sha(Path(p).read_bytes())!=h:raise ValueError('Source changed after publication')
