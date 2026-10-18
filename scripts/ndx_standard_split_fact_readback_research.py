"""Strict event facts from bound clearing memos and dated issuer filings."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'data/cache/research/standard_split_official_evidence_20260912_v1'
MANIFESTS={'manifest.json':'cec2ed74cdcf0fadd117f7a35c567db8b9adf1efee9b5b87f45796d7a90474e7',
           'supplement_manifest.json':'99fb04f4b6b57c3935120f797fd7a0b5956c50e81bcab6e3e09d343b5804b134',
           'mnst_updated_manifest.json':'a7db98d05c3faf840bccf6d26eb5f236f6a4f648c0b624f7476551a7e7811d5a'}
OCC=(('AMZN','2022-06-06',20,1,'023135106','amzn_20220606_miax'),
     ('CPRT','2022-11-04',2,1,'217204106','cprt_20221104_miax'),
     ('CPRT','2023-08-22',2,1,'217204106','cprt_20230822_miax'),
     ('DXCM','2022-06-13',4,1,'252131107','dxcm_20220613_occ50507_miax'),
     ('MNST','2023-03-28',2,1,'61174X109','mnst_20230328_updated_miax'),
     ('ODFL','2024-03-28',2,1,'679580100','odfl_20240328_occ54255_miax'),
     ('PCAR','2023-02-08',3,2,'693718108','pcar_20230208_miax'))


def only(pattern,text):
    matches=re.findall(pattern,text,re.I)
    if len(matches)!=1:raise ValueError('Ambiguous/missing event field: '+pattern)
    return matches[0]


def parse_occ(text,*,ticker,session,new_shares,old_shares,cusip):
    text=' '.join(text.split())
    found=only(r'\('+re.escape(ticker)+r'\) has announced a (\d+) for (\d+) stock split\.',text)
    ratio=tuple(map(int,found))
    if ratio!=(new_shares,old_shares):raise ValueError('Common-stock ratio differs; do not use option contract multiplier')
    date_pattern=r'([A-Za-z]+ \d{1,2}, \d{4})'
    def date_after(prefix):return datetime.strptime(only(prefix+date_pattern,text),'%B %d, %Y').date().isoformat()
    ex_date=date_after(r'The Ex-distribution Date is ')
    effective=date_after(r'Effective Date:\s*')
    if ex_date!=session or effective!=session:raise ValueError('Trading ex-date differs')
    found_cusip=only(r'CUSIP:\s*([A-Z0-9]{9})\b',text)
    if found_cusip!=cusip:raise ValueError('Underlying CUSIP differs')
    short=only(r'Ex-Date:\s*(\d{1,2}/\d{1,2}/\d{2,4})\b',text)
    fmt='%m/%d/%Y' if len(short.split('/')[-1])==4 else '%m/%d/%y'
    if datetime.strptime(short,fmt).date().isoformat()!=session:raise ValueError('Header ex-date contradicts event')
    return dict(ticker=ticker,first_adjusted_trading_date=ex_date,new_shares=new_shares,old_shares=old_shares,
                cusip=found_cusip,publication_date=date_after(r'^#\d+ Date:\s*'),
                payable_date=date_after(r'The Payable Date is '),record_date=date_after(r'The Record Date is '),
                document_role='CLEARING_MEMO_HOSTED_BY_EXCHANGE',clearing_memo_calls_itself_unofficial_summary=True,
                option_contract_terms_not_used_as_equity_identity=True)


def build():
    from pypdf import PdfReader
    sources={};captures={}
    def bind(path,expected=None):
        path=Path(path).resolve();raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if expected is not None and digest!=expected:raise ValueError('Bound source differs: '+str(path))
        if str(path) in sources and sources[str(path)]!=digest:raise ValueError('Source conflict')
        sources[str(path)]=digest;return raw
    for name,expected in MANIFESTS.items():
        manifest=json.loads(bind(DIRECTORY/name,expected))
        for path,digest in manifest['source_hashes'].items():bind(path,digest)
        for capture in manifest['captures']:
            captures[capture['name']]=capture
            if capture.get('raw_path'):bind(capture['raw_path'],capture['raw_sha256'])
    def pdf(name):
        capture=captures[name]
        if capture.get('http_status')!=200:raise ValueError('Required evidence was not received')
        return ' '.join(' '.join(page.extract_text().split()) for page in PdfReader(capture['raw_path']).pages)
    facts=[]
    for ticker,session,new_shares,old_shares,cusip,name in OCC:
        fact=parse_occ(pdf(name),ticker=ticker,session=session,new_shares=new_shares,old_shares=old_shares,cusip=cusip)
        fact.update(raw_path=captures[name]['raw_path'],raw_sha256=captures[name]['raw_sha256'],received_at_utc=captures[name]['received_at_utc'])
        facts.append(fact)
    text=pdf('tsla_20220825_issuer_8k')
    if not all(fragment in text for fragment in ('Exhibit 99.1 Tesla Announces a Three-for-One Stock Split','August 5, 2022','two additional shares of common stock for each then-held share','Trading will begin on a stock split-adjusted basis on August 25, 2022.')):
        raise ValueError('Tesla official announcement differs')
    capture=captures['tsla_20220825_issuer_8k']
    facts.append(dict(ticker='TSLA',first_adjusted_trading_date='2022-08-25',new_shares=3,old_shares=1,publication_date='2022-08-05',
                      payable_date='2022-08-24',record_date='2022-08-17',cusip=None,document_role='ISSUER_HOSTED_FILED_8K_EXHIBIT_99_1',
                      raw_path=capture['raw_path'],raw_sha256=capture['raw_sha256'],received_at_utc=capture['received_at_utc']))
    local=ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec/issuer_0001327567/000132756722000028/panw-20220731.htm'
    # Independently located existing filing; bind the original sidecar content digest.
    local_sha='5f4071022cf04772daf691408b315fafa155fc20593ac5eb38a9b1c18e871a32'
    soup=BeautifulSoup(bind(local,local_sha),'html.parser');text=' '.join(soup.get_text(' ',strip=True).split())
    if not all(fragment in text for fragment in ('three -for-one stock split','two additional shares for every share held on the record date','trading will begin on a split-adjusted basis on September 14, 2022.')):
        raise ValueError('Local PANW event differs')
    sidecar=Path(str(local)+'.manifest.json');meta=json.loads(bind(sidecar))
    if meta['content_sha256']!=local_sha or meta['accession_number']!='0001327567-22-000028':raise ValueError('PANW original capture metadata differs')
    facts.append(dict(ticker='PANW',first_adjusted_trading_date='2022-09-14',new_shares=3,old_shares=1,publication_date=None,
                      announcement_date_described_in_filing='2022-08-22',payable_date='2022-09-13',record_date='2022-09-06',cusip=None,
                      document_role='ALREADY_CAPTURED_ISSUER_ANNUAL_FILING',raw_path=str(local),raw_sha256=local_sha,existing_capture_metadata=meta))
    queue_path=ROOT/'data/cache/research/provider_returned_event_adjudication_queue_20260912_v1/report.json'
    queue=json.loads(bind(queue_path,'bfc5a3b1b3060ff6805f94a48fabe98ce73c4f1cd18134d50a54929bb0e9b871'))
    by_event={(row['ticker'],row['session']):row for row in queue['returned_events']}
    for fact in facts:
        event=by_event[(fact['ticker'],fact['first_adjusted_trading_date'])]
        if event['provider_ratio_fields'][:2]!=[fact['new_shares'],fact['old_shares']]:raise ValueError('Official/provider event ratio differs')
        fact['provider_raw_event_sources']=event['raw_sources']
        fact['specific_simple_share_split_event_supported']=True
        fact['full_provider_price_identity_binding_verified']=False
        fact['all_future_adjustments_verified']=False
        for source in event['raw_sources']:bind(source['path'],source['sha256'])
    blocklist=[dict(ticker=row['ticker'],event_date=row['session'],reason=row['interpretation'],simple_split_interface_allowed=False,
                    replacement_needed='Dated security/distribution accounting including cash-in-lieu or ADR/class mapping, and separate quote-basis evidence') for row in queue['complex_action_keys']]
    bind(Path(__file__).resolve())
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Source drift')
    return dict(schema='NINE_SPECIFIC_EQUITY_SPLIT_EVENTS_EVIDENCED_RESEARCH_ONLY',source_hashes=sources,specific_events=facts,
                specific_event_count=9,ticker_count=8,simple_split_interface_blocklist=blocklist,
                all_capture_attempts=list(captures.values()),event_dates_are_not_receipt_dates=True,
                share_split_event_support_is_not_global_price_normalization_authority=True,
                missing_later_event_examples=['MNST 2026-08-11','PANW 2024-12-16'],
                full_ndx_historical_baseline_verified=False,point_in_time_verified=False,promotion_allowed=False,no_config_modified=True)


if __name__=='__main__':
    path=DIRECTORY/'specific_split_fact_readback.json'
    if path.exists():raise FileExistsError(path)
    report=build()
    with path.open('xb') as stream:stream.write((json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n').encode())
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),events=9,tickers=8)))
