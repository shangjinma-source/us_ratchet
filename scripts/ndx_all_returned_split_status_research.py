"""Bound eleven additional event facts and reconcile the complete returned 32-event denominator."""
from collections import Counter
from fractions import Fraction
import gzip,hashlib,json,re
from io import BytesIO
from pathlib import Path
import sys
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_standard_split_fact_readback_research as prior
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(prior.__file__).resolve())}
DIRECTORY=ROOT/'data/cache/research/remaining_standard_split_evidence_20260912_v1'
MANIFESTS={'manifest.json':'1665428a092c597598882e1d7fdf249ccde4a699b943fa07ee48930651a13996',
 'supplement_manifest.json':'86b0687f5771450cb5b9fe894f90e94138444e8df66818193bb501f92b4c417b',
 'crwd_mirror_manifest.json':'44d0402887220abb34b597bfe23bacfd03393bcba178ff384df4c5083efbdac4'}
FORWARD=(('BKNG','2026-04-06',25,'09857L108','bkng'),('MNST','2026-08-11',2,'61174X109','mnst'),
 ('FAST','2025-05-22',2,'311900104','fast_miax'),('PANW','2024-12-16',2,'697435105','panw_miax'),
 ('CRWD','2026-07-02',4,'22788C105','crwd_miax'),('NFLX','2025-11-17',10,'64110L106','nflx_miax'))

def require(text,fragments):
    for fragment in fragments:
        if fragment not in text:raise ValueError('Exact event clause missing: '+fragment)

def forward(text,*,ticker,session,new_shares,cusip):
    text=' '.join(text.split())
    if ticker=='NFLX':
        clause="(NFLX) has announced a 10 for 1 stock split, subject to the filing of an amendment to the Company's Amended and Restated Certificate of Incorporation."
        if text.count(clause)!=1:raise ValueError('Netflix conditional declaration differs')
        text=text.replace(clause,'(NFLX) has announced a 10 for 1 stock split.')
    result=prior.parse_occ(text,ticker=ticker,session=session,new_shares=new_shares,old_shares=1,cusip=cusip)
    result['conditional_charter_filing_clause_present']=ticker=='NFLX'
    result['security_class']='CLASS_A_COMMON' if ticker=='CRWD' else 'COMMON'
    if ticker=='CRWD':require(text,['(CRWD) Class A Common Shares'])
    return result

def reverse_lcid(text):
    text=' '.join(text.split())
    require(text,['(LCID) has announced a 1-for-10 reverse stock split.',
      'each LCID Common Share will be converted into the right to receive 0.1 (New) Lucid Group, Inc. Common Shares.',
      'effective before the market open on September 2, 2025.','Effective Date:September 2, 2025',
      'CUSIP: LCID (New): 549498202'])
    if len(re.findall(r'has announced a .*? reverse stock split\.',text))!=1:raise ValueError('Ambiguous reverse split')
    if prior.only(r'CUSIP: LCID \(New\):\s*([A-Z0-9]{9})',text)!='549498202':raise ValueError('CUSIP differs')
    return dict(ticker='LCID',first_adjusted_trading_date='2025-09-02',new_shares=1,old_shares=10,
      cusip='549498202',cusip_role='NEW_POST_ACTION_CUSIP',old_cusip_in_event_document=None,
      publication_date='2025-08-28',security_class='COMMON',identity_transition_requires_explicit_mapping=True,
      document_role='CLEARING_MEMO_HOSTED_BY_EXCHANGE',clearing_memo_calls_itself_unofficial_summary=True,
      option_symbols_not_equity_ticker_changes=True)

def build():
    from pypdf import PdfReader
    sources={};captures={}
    def bind(path,expected=None):
        path=Path(path).resolve();raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if expected is not None and digest!=expected:raise ValueError('Source differs: '+str(path))
        if str(path) in sources and sources[str(path)]!=digest:raise ValueError('Conflicting source')
        sources[str(path)]=digest;return raw
    def load(path,expected):
        report=json.loads(bind(path,expected))
        for p,h in report.get('source_hashes',{}).items():bind(p,h)
        return report
    for path,digest in LOADED.items():bind(path,digest)
    for name,digest in MANIFESTS.items():
        manifest=load(DIRECTORY/name,digest)
        for capture in manifest['captures']:
            if capture['name'] in captures:raise ValueError('Duplicate capture')
            captures[capture['name']]=capture
            if capture.get('raw_path'):bind(capture['raw_path'],capture['raw_sha256'])
    def text(name):
        capture=captures[name]
        if capture.get('http_status')!=200:raise ValueError('Required evidence failed')
        raw=bind(capture['raw_path'],capture['raw_sha256'])
        raw=gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw
        if hashlib.sha256(raw).hexdigest()!=capture['decoded_sha256']:raise ValueError('Decoded source differs')
        if name=='panw_miax':
            boundary=b'--ewq7Bq2HrlMj-57HCsr4tSbI9v6f-hvgeEf'
            prefix=boundary+b'\r\nContent-Disposition: form-data; name="file"; filename="PANW_Split_55607.pdf"\r\nContent-Type: application/octet-stream\r\nContent-Transfer-Encoding: binary\r\n\r\n'
            suffix=b'\r\n'+boundary+b'--\r\n'
            if not raw.startswith(prefix) or not raw.endswith(suffix) or raw.count(boundary)!=2:raise ValueError('Bound PANW multipart envelope differs')
            raw=raw[len(prefix):-len(suffix)]
            capture['payload_note']='ORIGINAL_HTTP_BODY_IS_SINGLE_MULTIPART_FILE_DESPITE_APPLICATION_PDF_HEADER'
            capture['embedded_pdf_sha256']=hashlib.sha256(raw).hexdigest()
        value=' '.join(p.extract_text() for p in PdfReader(BytesIO(raw)).pages) if raw.startswith(b'%PDF') else BeautifulSoup(raw,'html.parser').get_text(' ',strip=True)
        return ' '.join(value.split())
    def reference(fact,name):
        c=captures[name]
        fact.update(raw_path=c['raw_path'],raw_sha256=c['raw_sha256'],received_at_utc=c['received_at_utc'],source_url=c['request_url'])
        return fact
    facts=[reference(forward(text(name),ticker=ticker,session=session,new_shares=ratio,cusip=cusip),name) for ticker,session,ratio,cusip,name in FORWARD]
    facts.append(reference(reverse_lcid(text('lcid')),'lcid'))
    require(text('lrcx'),['(Nasdaq: LRCX)','shares of common stock at a ratio of 10:1.',"common stock will begin trading on a post-split basis at the market open on Thursday, October 3, 2024"])
    require(text('lrcx_8937'),['10-for-1 forward stock split 512807306 LRCX','every one (1) share', 'automatically divided into 10 (ten) shares of common stock.','The forward stock split was a mandatory exchange.'])
    facts.append(reference(dict(ticker='LRCX',first_adjusted_trading_date='2024-10-03',new_shares=10,old_shares=1,
      publication_date='2024-05-21',legal_effective_date='2024-10-02',cusip='512807306',cusip_role='POST_ACTION_FORM_8937',
      security_class='COMMON',identity_transition_requires_explicit_mapping=True,old_cusip_in_event_document=None,
      identity_evidence=reference({},'lrcx_8937'),document_role='ISSUER_ANNOUNCEMENT_AND_ISSUER_FORM_8937'),'lrcx'))
    require(text('klac'),['KLA Corporation (NASDAQ: KLAC)','Ten-for-One forward stock split','nine additional shares for each share held',
      'Shares will begin trading on a split adjusted basis at market open on Friday, June 12, 2026.'])
    facts.append(reference(dict(ticker='KLAC',first_adjusted_trading_date='2026-06-12',new_shares=10,old_shares=1,
      publication_date='2026-05-07',cusip=None,security_class='COMMON',document_role='ISSUER_HOSTED_SEC_EXHIBIT'),'klac'))
    require(text('orly'),['15-for-1 stock split means for each one share of stock, the stock will split and become 15 shares',
      'stock market opens on June 10, 2025, the ORLY stock will begin trading at its new split- adjusted price.'])
    facts.append(reference(dict(ticker='ORLY',first_adjusted_trading_date='2025-06-10',new_shares=15,old_shares=1,
      publication_date=None,cusip=None,security_class='COMMON',document_role='ISSUER_STOCK_SPLIT_FAQ'),'orly'))
    local=ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/raw_sec/issuer_0000723254/000072325425000017/ctas-20250531.htm'
    digest='78495a5265b6b3e93c5ceb5f11f5e699db5e5f873b6db40aa400dc2f394fdf27'
    local_text=' '.join(BeautifulSoup(bind(local,digest),'html.parser').get_text(' ',strip=True).split())
    require(local_text,['announced a four-for-one split of its common stock','received three additional common stock shares for each common stock share held',
      "common stock shares began trading on a post Stock Split basis after the market opening on September 12, 2024."])
    sidecar=json.loads(bind(str(local)+'.manifest.json'))
    if sidecar['content_sha256']!=digest or sidecar['cik']!='0000723254':raise ValueError('CTAS capture differs')
    facts.append(dict(ticker='CTAS',first_adjusted_trading_date='2024-09-12',new_shares=4,old_shares=1,publication_date=None,
      announcement_date_described_in_filing='2024-05-02',cusip=None,security_class='COMMON',issuer_cik='0000723254',
      document_role='EXISTING_CAPTURED_ISSUER_10K',raw_path=str(local),raw_sha256=digest,received_at_utc=sidecar['fetched_at'],
      source_url=sidecar['source_locator'],original_capture_metadata=sidecar))
    queue=load(ROOT/'data/cache/research/provider_returned_event_adjudication_queue_20260912_v1/report.json','bfc5a3b1b3060ff6805f94a48fabe98ce73c4f1cd18134d50a54929bb0e9b871')
    old=load(prior.DIRECTORY/'specific_split_fact_readback.json','f421d8b95c6542139b016a853c3ab9e7f69d76daaff79e4592918fce8e8e4d55')
    prior_keys={(x['ticker'],x['first_adjusted_trading_date']):x for x in old['specific_events']}
    new_keys={(x['ticker'],x['first_adjusted_trading_date']):x for x in facts}
    if len(new_keys)!=11:raise ValueError('Missing new denominator')
    blocked={(x['ticker'],x['session']):x['interpretation'] for x in queue['complex_action_keys']}
    rows=[]
    for event in queue['returned_events']:
        key=(event['ticker'],event['session']);row=dict(event)
        for source in event['raw_sources']:bind(source['path'],source['sha256'])
        if key in blocked:row.update(status='COMPLEX_ACTION_BLOCKED_SIMPLE_SPLIT',action_type=blocked[key],specific_simple_share_split_event_supported=False)
        elif key in prior_keys:row.update(status='PRIOR_NINE_SPECIFIC_FACTS_REFERENCED',specific_simple_share_split_event_supported=True)
        elif key in new_keys:
            fact=new_keys[key];a,b,_=event['provider_ratio_fields']
            if Fraction(str(a))/Fraction(str(b))!=Fraction(fact['new_shares'],fact['old_shares']):raise ValueError('Official/provider share ratio differs')
            fact.update(specific_simple_share_split_event_supported=True,provider_raw_event_sources=event['raw_sources'],
              full_provider_price_identity_binding_verified=False,point_in_time_verified=False,corporate_action_completeness_verified=False)
            row.update(status='NEW_ELEVEN_SPECIFIC_FACTS_SUPPORTED',specific_simple_share_split_event_supported=True,fact=fact)
        elif event['ticker'] in queue['existing_standard_evidence_tickers']:
            row.update(status='PRIOR_FIVE_EVIDENCE_REFERENCES_NOT_REEXTRACTED',specific_simple_share_split_event_supported=None)
        else:raise ValueError('Unaccounted returned event')
        row['pure_share_multiplier_admitted']=False
        rows.append(row)
    counts=dict(Counter(x['status'] for x in rows))
    if len(rows)!=32 or len({(x['ticker'],x['session']) for x in rows})!=32 or sorted(counts.values())!=[5,7,9,11]:raise ValueError('32 denominator differs')
    for p,h in LOADED.items():bind(p,h)
    for p,h in sources.items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise ValueError('Source drift')
    return dict(schema='RETURNED_32_EVENT_FACT_RECONCILIATION_NOT_IDENTITY_OR_PIT_ADMISSION',source_hashes=sources,
      returned_event_count=32,status_counts=counts,specific_new_events=facts,returned_event_statuses=rows,
      all_new_capture_attempts=list(captures.values()),prior_nine_report_sha256='f421d8b95c6542139b016a853c3ab9e7f69d76daaff79e4592918fce8e8e4d55',
      simple_split_interface_blocklist=queue['complex_action_keys'],full_ndx_historical_baseline_verified=False,
      corporate_action_completeness_verified=False,provider_price_basis_verified=False,point_in_time_verified=False,promotion_allowed=False,
      publication_and_receipt_are_separate=True,no_event_does_not_prove_no_actions=True,training_returns_generated=False,
      limitations=['Specific standard share event support does not certify full security identity continuity.',
        'LCID and LRCX require explicit pre/post security identifier mapping; new CUSIP cannot be assigned to earlier history.',
        'OCC clearing memos call themselves unofficial summaries of corporate events.',
        'Prior five source references preserved; this readback does not independently reextract those five facts.'])

if __name__=='__main__':
    result=build();path=DIRECTORY/'all_32_event_status.json'
    with path.open('xb') as stream:stream.write((json.dumps(result,indent=2,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),counts=result['status_counts'])))
