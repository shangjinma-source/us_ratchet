"""Two dated, explicitly conditional cross-document security relations; no price binding."""
import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_corrected_frontier_single_refit_archive_research import publish

BASE = ROOT / 'data/cache/research'
EVENTS = BASE / 'remaining_standard_split_evidence_20260912_v1/all_32_event_status.json'
EVENTS_SHA = '99119e5c3664b272d65eec498fb18714feb4fa7aa43e0ceff9682c79df8cafae'
CASES = {
    'NFLX': dict(cik='0001065280', cusip='64110L106', company='Netflix, Inc.', cover_company='Netflix, Inc.',
        title='Common stock, par value $0.001 per share', period='December 31 , 2021',
        context='i66fd02da20774fd6837df0bb906b0279_D20210101-20211231',
        memo_number='57556', memo_date='November 04, 2025', event='2025-11-17', event_text='November 17, 2025', ex_date='11/17/2025',
        memo='remaining_standard_split_evidence_20260912_v1/nflx_miax.response.bin',
        memo_sha='e0787891b7c8019d98487913b9a280c63dc1796edfbf485ed12d153f71faf0e8',
        cover='data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec/issuer_0001065280/000106528022000036/nflx-20211231.htm',
        cover_sha='715132c514321aebd9f369a3f53fd7ea51c4c3144aa25d74a313c2ad56573fdc'),
    'PANW': dict(cik='0001327567', cusip='697435105', company='Palo Alto Networks, Inc.', cover_company='Palo Alto Networks, Inc',
        title='Common stock, $0.0001 par value per share', period='July 31 , 2022',
        context='i2a8f4b76af2c43cf9f2e797666ce3c0f_D20210801-20220731',
        memo_number='55607', memo_date='November 26, 2024', event='2024-12-16', event_text='December 16, 2024', ex_date='12/16/2024',
        memo='remaining_standard_split_evidence_20260912_v1/panw_miax.response.bin',
        memo_sha='c0cf86f8d0603da0be4d494fa9d185fbef92708d10ed84d2bf6b4106858b8d04',
        cover='data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec/issuer_0001327567/000132756722000028/panw-20220731.htm',
        cover_sha='5f4071022cf04772daf691408b315fafa155fc20593ac5eb38a9b1c18e871a32'),
}
FALSE = ('memo_contains_subject_cik', 'direct_single_document_cusip_cik_proof',
         'latest_security_interval_verified', 'provider_security_binding_verified',
         'corporate_action_completeness_verified', 'legal_training_input_ready',
         'point_in_time_verified', 'promotion_allowed', 'execution_authorized', 'fit_performed')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


LOADED = {str(p):sha(p) for p in (Path(__file__).resolve(),Path(publish.__code__.co_filename).resolve())}


def pdf_payload(raw, ticker):
    if ticker == 'PANW':
        boundary=b'--ewq7Bq2HrlMj-57HCsr4tSbI9v6f-hvgeEf'
        prefix=boundary+b'\r\nContent-Disposition: form-data; name="file"; filename="PANW_Split_55607.pdf"\r\nContent-Type: application/octet-stream\r\nContent-Transfer-Encoding: binary\r\n\r\n'
        suffix=b'\r\n'+boundary+b'--\r\n'
        if not raw.startswith(prefix) or not raw.endswith(suffix) or raw.count(boundary)!=2:
            raise ValueError('Exact single PANW multipart file required')
        raw=raw[len(prefix):-len(suffix)]
    if not raw.startswith(b'%PDF'):
        raise ValueError('Actual PDF bytes required')
    return raw


def relation(ticker, memo_text, cover_bytes):
    spec=CASES[ticker]
    text=' '.join(memo_text.split())
    fragments=[f"#{spec['memo_number']}",f"Date: {spec['memo_date']}",
        f"100 {spec['company']} ({ticker}) Common Shares",f"CUSIP:{spec['cusip']}",
        'This Information Memo provides an unofficial summary',
        f"Ex-Date: {spec['ex_date']}",f"The Ex-distribution Date is {spec['event_text']}.",
        f"Effective Date:{spec['event_text']}"]
    for fragment in fragments:
        if text.count(fragment)!=1:
            raise ValueError('Unique explicit memo security clause required: '+fragment)
    if re.findall(r'CUSIP:\s*([A-Z0-9]{9})',text)!=[spec['cusip']]:
        raise ValueError('Conflicting memo CUSIP')
    clause="(NFLX) has announced a 10 for 1 stock split, subject to the filing of an amendment to the Company's Amended and Restated Certificate of Incorporation."
    if ticker=='NFLX' and text.count(clause)!=1:
        raise ValueError('NFLX contingent charter clause must be preserved')
    soup=BeautifulSoup(cover_bytes,'lxml')
    expected={'dei:entitycentralindexkey':spec['cik'],'dei:entityregistrantname':spec['cover_company'],
        'dei:tradingsymbol':ticker,'dei:security12btitle':spec['title'],'dei:documentperiodenddate':spec['period']}
    observed={}
    for name,value in expected.items():
        nodes=[n for n in soup.find_all(attrs={'name':True}) if n['name'].lower()==name]
        if len(nodes)!=1 or nodes[0].get('contextref')!=spec['context'] or ' '.join(nodes[0].get_text(' ',strip=True).split())!=value:
            raise ValueError('Unique same-context original SEC cover differs: '+name)
        observed[name]={'text':' '.join(nodes[0].get_text(' ',strip=True).split()),'context':nodes[0].get('contextref')}
    return dict(ticker=ticker,conditional_research_security_id=f"security:{spec['cik']}:{spec['cusip']}",
        issuer_id='issuer:'+spec['cik'],cusip=spec['cusip'],security_class=spec['title'],
        memo_security_fragments=fragments,memo_document_date=spec['memo_date'],memo_action_date=spec['event'],
        memo_is_unofficial_summary=True,nflx_charter_filing_condition_preserved=ticker=='NFLX',
        contingent_clause=clause if ticker=='NFLX' else None,
        original_cover_fields=observed,
        class_relation='EXPLICIT_CONDITIONAL_COMMON_SHARES_TO_SINGLE_SEC_COMMON_STOCK_CLASS',
        issuer_link_method='EXACT_TICKER_AND_EXPLICIT_COMMON_CLASS_AND_COMPANY_WITH_FIXED_PANW_TERMINAL_PERIOD_VARIATION',
        company_punctuation_difference_explicit=ticker=='PANW',
        source_dates_are_distinct=True,latest_interval_assumption='UNCHANGED_SECURITY_CLASS_20260318_TO_20260917_NOT_VERIFIED',
        risk_chain_assigned=False,**dict.fromkeys(FALSE,False))


def verify(sources):
    for path,expected in LOADED.items():
        if sources.get(path)!=expected:
            raise ValueError('Loaded source omitted or changed')
    for path,expected in sources.items():
        if sha(path)!=expected:
            raise ValueError('Source bytes changed: '+path)


def build():
    from pypdf import PdfReader
    sources=dict(LOADED)
    sources[str(EVENTS)]=EVENTS_SHA
    for spec in CASES.values():
        sources[str(BASE/spec['memo'])]=spec['memo_sha']
        sources[str(ROOT/spec['cover'])]=spec['cover_sha']
    verify(sources)
    events=json.loads(EVENTS.read_text(encoding='utf-8'))
    rows=[]
    for ticker,spec in CASES.items():
        event=[e for e in events['specific_new_events'] if e['ticker']==ticker]
        if len(event)!=1 or event[0]['cusip']!=spec['cusip'] or event[0]['first_adjusted_trading_date']!=spec['event']:
            raise ValueError('Hard adjudicated dated action differs')
        raw=(BASE/spec['memo']).read_bytes();pdf=pdf_payload(raw,ticker)
        text='\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
        row=relation(ticker,text,(ROOT/spec['cover']).read_bytes())
        row.update(memo_raw_path=str(BASE/spec['memo']),memo_raw_sha256=spec['memo_sha'],
            embedded_pdf_sha256=hashlib.sha256(pdf).hexdigest(),memo_normalized_text_sha256=hashlib.sha256(' '.join(text.split()).encode()).hexdigest(),
            original_cover_path=str(ROOT/spec['cover']),original_cover_sha256=spec['cover_sha'],
            memo_source_url=event[0]['source_url'],memo_received_at_utc=event[0]['received_at_utc'])
        rows.append(row)
    verify(sources)
    return dict(schema='NFLX_PANW_DATED_CONDITIONAL_CROSS_DOCUMENT_IDENTITIES_V1',rows=rows,security_count=2,
        source_hashes=sources,scope='TWO_EXPLICIT_DATED_CONDITIONAL_RELATIONS_NOT_LATEST_INTERVAL_CERTIFICATION',
        class_relation_is_explicit_research_judgment=True,existing_fifteen_plan_modified=False,
        risk_chains_assigned=False,**dict.fromkeys(FALSE,False))


def publish_verified(path,value):
    verify(value['source_hashes'])
    reference=publish(path,value)
    verify(value['source_hashes'])
    return reference


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    print(json.dumps(publish_verified(args.output,build())))
