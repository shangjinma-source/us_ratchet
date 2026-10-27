"""Offline validation of three saved SEC original filing cover identities."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'tmp/historical_news_identity_20261027/cover_evidence'


def source_guard(receipt, source, first_exposure):
    cik=str(int(receipt['cik'])).zfill(10)
    if str(int(source['cik'])).zfill(10)!=cik:
        raise ValueError('SUBMISSIONS_CIK_MISMATCH')
    recent=source['filings']['recent']
    if recent['accessionNumber'].count(receipt['accession'])!=1:
        raise ValueError('NONUNIQUE_ACCESSION')
    index=recent['accessionNumber'].index(receipt['accession'])
    expected=('https://www.sec.gov/Archives/edgar/data/'+str(int(cik))+'/'+
              receipt['accession'].replace('-','')+'/'+recent['primaryDocument'][index])
    if receipt['url']!=expected:raise ValueError('OFFICIAL_DOCUMENT_URL_MISMATCH')
    if receipt['first_exposure']!=first_exposure:raise ValueError('BASELINE_EXPOSURE_MISMATCH')
    if recent['acceptanceDateTime'][index]!=receipt['acceptance']:
        raise ValueError('ACCEPTANCE_MISMATCH')


def context_identifier(soup, context_id, cik):
    nodes=soup.find_all(id=context_id)
    if len(nodes)!=1 or nodes[0].name.lower().split(':')[-1]!='context':
        raise ValueError('NONUNIQUE_OR_INVALID_CONTEXT')
    identifiers=nodes[0].find_all(lambda tag:tag.name.lower().split(':')[-1]=='identifier')
    if len(identifiers)!=1:raise ValueError('NONUNIQUE_CONTEXT_IDENTIFIER')
    identifier=identifiers[0]
    if identifier.get('scheme')!='http://www.sec.gov/CIK':
        raise ValueError('CONTEXT_IDENTIFIER_SCHEME')
    if identifier.get_text(strip=True).zfill(10)!=cik:
        raise ValueError('CONTEXT_ENTITY_CIK_MISMATCH')
    return identifier


def main():
    receipts=json.loads((DIRECTORY/'receipts.json').read_bytes())
    mapping=json.loads((DIRECTORY.parent/'mapping_candidate.json').read_bytes())
    pin=mapping['source_hashes']['book']
    baseline_raw=(ROOT/pin['path']).read_bytes()
    if sha256(baseline_raw).hexdigest()!=pin['sha256']:raise ValueError('BASELINE_BOOK_PIN_MISMATCH')
    baseline=json.loads(baseline_raw)
    exposure_dates={}
    for row in baseline['daily_ledger']:
        for sid, quantity in row['shares'].items():
            if quantity:exposure_dates.setdefault(sid,[]).append(row['date'])
    for row in baseline['order_log']:
        if row.get('event')=='ASSUMED_NEXT_OPEN_FILLED':
            exposure_dates.setdefault(row['security_id'],[]).append(row['date'])
    output=[]
    concepts=('dei:EntityCentralIndexKey','dei:TradingSymbol','dei:Security12bTitle',
              'dei:EntityRegistrantName','dei:DocumentPeriodEndDate')
    for receipt in receipts:
        raw=(DIRECTORY/(receipt['ticker']+'.html')).read_bytes()
        if receipt['status']!=200 or sha256(raw).hexdigest()!=receipt['sha256']:
            raise ValueError('ORIGINAL_FILING_PIN_MISMATCH')
        submissions=(ROOT/receipt['submissions_path']).read_bytes()
        if sha256(submissions).hexdigest()!=receipt['submissions_sha256']:
            raise ValueError('SUBMISSIONS_PIN_MISMATCH')
        source=json.loads(submissions)
        sid='research:security:'+receipt['ticker'].lower()
        source_guard(receipt,source,min(exposure_dates[sid]))
        recent=source['filings']['recent']
        index=recent['accessionNumber'].index(receipt['accession'])
        if recent['acceptanceDateTime'][index]!=receipt['acceptance']:
            raise ValueError('ACCEPTANCE_MISMATCH')
        if datetime.fromisoformat(receipt['acceptance'].replace('Z','+00:00'))>=datetime.fromisoformat(receipt['first_exposure']).replace(tzinfo=timezone.utc):
            raise ValueError('NOT_PRE_EXPOSURE')
        soup=BeautifulSoup(raw,'html.parser');fields={}
        for concept in concepts:
            nodes=soup.find_all(attrs={'name':concept})
            if len(nodes)!=1:raise ValueError('NONUNIQUE_COVER_FIELD:'+concept)
            node=nodes[0];fields[concept]=dict(value=node.get_text(' ',strip=True),context=node.get('contextref'))
        contexts={row['context'] for row in fields.values()}
        if len(contexts)!=1:raise ValueError('COVER_CONTEXT_MISMATCH')
        cik=str(int(receipt['cik'])).zfill(10)
        identifier=context_identifier(soup,next(iter(contexts)),cik)
        if fields['dei:EntityCentralIndexKey']['value']!=cik or fields['dei:TradingSymbol']['value']!=receipt['ticker']:
            raise ValueError('ISSUER_TICKER_MISMATCH')
        output.append(dict(research_security_id='research:security:'+receipt['ticker'].lower(),cik=cik,
            evidence_status='ORIGINAL_SEC_COVER_PRE_EXPOSURE_IDENTITY_VERIFIED',
            identity_anchor_acceptance=receipt['acceptance'],first_exposure=receipt['first_exposure'],
            cover_fields=fields,context_identifier=identifier.get_text(strip=True),receipt=receipt,
            applicability='Issuer and listed share class at this filing anchor; no claim of every intervening day or future corporate-action continuity.'))
    result=dict(status='THREE_PRE_EXPOSURE_COVERS_VERIFIED',rows=output,network_requests=3,
        baseline_book=pin,
        point_in_time_certified=False,baseline_modified=False,
        limitations=['Acceptance is linked by accession to saved official submissions; not an independently fetched SGML header.',
          'Original filing retrieved now; receipt time is not historical acquisition time.',
          'Identity proof does not certify completeness or nonrevision of future financial feature inputs.'])
    (DIRECTORY/'verified_mapping_supplement.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(status=result['status'],tickers=[r['cover_fields']['dei:TradingSymbol']['value'] for r in output])))


if __name__=='__main__':main()
