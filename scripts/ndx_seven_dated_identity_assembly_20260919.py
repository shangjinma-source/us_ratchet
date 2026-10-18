"""Seven explicit dated identities for conditional retrospective accounting only."""
import argparse,gzip,hashlib,io,json,re,sys
from pathlib import Path
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_three_cusip_web_transcription_readback_20260919 as web
BASE=web.BASE
OLD=BASE/'four_issuer_filing_identity_20260912_v1/dated_identity_adjudication.json'
OLD_SHA='a70551b92c2154b9b1efe5eadb35b1f3c0f34b1c9a858506e3a2085df888d8a4'
NEW=BASE/'three_cusip_web_transcription_20260919_v1/readback.json'
NEW_SHA='d6eb603467df281896f51fc6d5315845d4f9ea43e7d0373effff4f0cf4b52da4'
FTNT_MANIFEST=BASE/'standard_split_registry_20260912_v2/ftnt_manifest.json'
FTNT_MANIFEST_SHA='b768a2b4a563ca910a2d3464b322d437d41f178cf603dd4573d8fd88f263613d'
FTNT_COVER=web.prior.SECROOT/'issuer_0001262039/000126203922000008/ftnt-20211231.htm'
FTNT_COVER_SHA='7a6377da85756b0991757024982fafec576034f1c59a58ff901efd5be29d870c'
COORDINATES={
 'AMAT':('0000006951','038222105'),'AVGO':('0001730168','11135F101'),
 'BKR':('0001701605','05722G100'),'CDNS':('0000813672','127387108'),
 'ENPH':('0001463101','29355A107'),'FTNT':('0001262039','34959E109'),'ADI':('0000006281','032654105')}
CLASS_TITLES={
 'ADI':'Common Stock $0.16 2/3 par value per share',
 'AMAT':'Common Stock, par value $.01 per share',
 'AVGO':'Common Stock, $0.001 par value',
 'BKR':'Class A Common Stock, $0.0001 Par Value per Share',
 'CDNS':'Common Stock, $0.01 par value per share',
 'ENPH':'Common Stock, $0.00001 par value per share',
 'FTNT':'Common Stock, $0.001 Par Value'}
LOADED={**web.LOADED,str(Path(web.__file__).resolve()):hashlib.sha256(Path(web.__file__).read_bytes()).hexdigest(),str(Path(__file__).resolve()):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

def cover_fields(raw,ticker,cik):
    soup=BeautifulSoup(web.prior.decode(raw).decode('utf-8'),'html.parser')
    def nodes(field):return [n for n in soup.find_all() if n.get('name','').lower()=='dei:'+field.lower()]
    ciks={n.get_text(' ',strip=True) for n in nodes('EntityCentralIndexKey')}
    symbols=[n for n in nodes('TradingSymbol') if n.get_text(' ',strip=True)==ticker]
    if ciks!={cik} or len(symbols)!=1:raise ValueError('Actual issuer/ticker cover differs')
    titles=[n.get_text(' ',strip=True) for n in nodes('Security12bTitle') if n.get('contextref')==symbols[0].get('contextref')]
    if len(titles)!=1 or 'common' not in titles[0].lower():raise ValueError('Same-position common class required')
    return titles[0]

def validate_rows(rows):
    if len(rows)!=7 or {r['ticker'] for r in rows}!=set(COORDINATES):raise ValueError('Exact seven-security denominator required')
    for r in rows:
        cik,cusip=COORDINATES[r['ticker']]
        if (r['issuer_id'],r['subject_cik'],r['cusip'],r['security_id'])!=(f'issuer:{cik}',cik,cusip,f'security:{cik}:{cusip}'):raise ValueError('Exact issuer/security coordinates required')
        if not isinstance(r['security_class'],str) or ' '.join(r['security_class'].split())!=CLASS_TITLES[r['ticker']]:raise ValueError('Exact source-bound class differs')
        for flag in ('continuous_interval_verified','provider_binding_verified','point_in_time_verified'):
            if r[flag] is not False:raise ValueError('Dated evidence cannot upgrade interval/provider/PIT')
        if 'available_date' in r or 'evidence_available_date' in r:raise ValueError('No backdated availability')

def validate_report(value):
    validate_rows(value['rows'])
    if value['schema']!='SEVEN_DATED_IDENTITY_CONDITIONAL_ACCOUNTING_ASSEMBLY_V1' or value['conditional_window']!={'start':'2023-03-31','end':'2023-05-01'}:raise ValueError('Exact conditional window/schema required')
    if any(type(value[k]) is not int or value[k]!=7 for k in ('security_count','issuer_count')):raise ValueError('Exact denominator required')
    if value['interval_stability_assumption']!='EXPLICIT_CONDITIONAL_STABILITY_BETWEEN_DATED_SNAPSHOTS_NOT_FULL_LEGAL_INTERVAL_CERTIFICATION':raise ValueError('Explicit conditional assumption required')
    for key in ('continuous_identity_interval_verified','provider_price_binding_verified','point_in_time_verified','promotion_allowed','execution_performed','legacy_bridge_called','early_evidence_availability_inferred'):
        if value[key] is not False:raise ValueError('No permission or evidence-scope upgrade')

def build():
    sources=dict(LOADED)
    def read(path,h):
        p=str(Path(path).resolve())
        if p in sources and sources[p]!=h:raise ValueError('Source conflict')
        raw=Path(p).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=h:raise ValueError('Hard source differs')
        sources[p]=h;return raw
    def report(path,h):
        value=json.loads(read(path,h))
        for p,digest in value['source_hashes'].items():read(p,digest)
        return value
    old=report(OLD,OLD_SHA);new=report(NEW,NEW_SHA)
    if new!=web.build():raise ValueError('Web accession/cover reconstruction differs')
    transcription=json.loads(read(web.TRANSCRIPT,web.TRANSCRIPT_SHA));rows=[]
    for ticker in sorted(COORDINATES):
        cik,cusip=COORDINATES[ticker]
        common=dict(ticker=ticker,subject_cik=cik,issuer_id=f'issuer:{cik}',cusip=cusip,security_id=f'security:{cik}:{cusip}',continuous_interval_verified=False,provider_binding_verified=False,point_in_time_verified=False)
        if ticker in ('AMAT','AVGO','CDNS'):
            original=next(r for r in old['rows'] if r['ticker']==ticker)
            if (original['issuer_cik'],original['cusip'],original['security_id'])!=(cik,cusip,common['security_id']):raise ValueError('Sealed dated identity differs')
            text=web.prior.decode(read(original['cusip_subject_cik_primary_source'],old['source_hashes'][original['cusip_subject_cik_primary_source']])).decode('utf-8')
            header,body=text.split('</SEC-HEADER>',1);subject=header.split('SUBJECT COMPANY:',1)[1].split('FILED BY:',1)[0]
            if re.findall(r'CENTRAL INDEX KEY:\s*(\d+)',subject)!=[cik] or cusip not in BeautifulSoup(body,'html.parser').get_text():raise ValueError('Original subject/CUSIP differs')
            title=cover_fields(read(original['filing_cover_path'],old['source_hashes'][original['filing_cover_path']]),ticker,cik)
            if title!=original['security_class_cover']:raise ValueError('Cover title differs')
            receipt_path=original['cusip_subject_cik_primary_source']+'.json';receipt=json.loads(read(receipt_path,old['source_hashes'][receipt_path]))
            if receipt['received_at_utc']!=original['received_at_utc'] or receipt['sha256']!=old['source_hashes'][original['cusip_subject_cik_primary_source']]:raise ValueError('Actual receipt differs')
            evidence=dict(type='SEC_ORIGINAL_SUBMISSION_HEADER_COVER_AND_SEPARATE_10K',dated_adjudication=original,actual_http_receipt=receipt)
        elif ticker in ('ADI','BKR','ENPH'):
            original=next(r for r in new['rows'] if r['ticker']==ticker)
            if (original['subject_cik'],original['cusip'])!=(cik,cusip):raise ValueError('Web subject/CUSIP differs')
            title=original['original_10k_cover']['security_class_title']
            evidence=dict(type='WEB_TOOL_OFFICIAL_DOCUMENT_TRANSCRIPTION_PLUS_SEC_SUBMISSIONS_AND_10K',dated_readback=original,tool_observation=next(r for r in transcription['rows'] if r['ticker']==ticker),local_http_original_cusip_document_available=False)
        else:
            manifest=report(FTNT_MANIFEST,FTNT_MANIFEST_SHA);capture=manifest['captures'][0]
            if len(manifest['captures'])!=1 or capture['raw_sha256']!='9758ad88b5c2538b6e04df12a16d36bdbb35e682520c76ea76e1d1ea1a4cf371':raise ValueError('Specific MIAX memo required')
            from pypdf import PdfReader
            pdf=' '.join(PdfReader(io.BytesIO(read(capture['raw_path'],capture['raw_sha256']))).pages[0].extract_text().split())
            for marker in ('#50626','June 22, 2022','Fortinet, Inc. (FTNT)','Common Shares','CUSIP:34959E109','June 23, 2022'):
                if marker not in pdf:raise ValueError('MIAX dated security fields differ')
            title=cover_fields(read(FTNT_COVER,FTNT_COVER_SHA),ticker,cik)
            evidence=dict(type='MIAX_HOSTED_OCC_ADJUSTMENT_MEMO_AND_SEPARATE_SEC_10K',memo_date='2022-06-22',ex_date='2022-06-23',receipt=capture,cover_path=str(FTNT_COVER),memo_cik_link='CROSS_DOCUMENT_TICKER_COMMON_CLASS_CONDITIONAL_NOT_CIK_IN_MEMO',memo_is_not_complete_legal_identity_certification=True)
        rows.append(dict(**common,security_class=title,evidence=evidence))
    validate_rows(rows);web.prior.verify(sources)
    result=dict(schema='SEVEN_DATED_IDENTITY_CONDITIONAL_ACCOUNTING_ASSEMBLY_V1',rows=rows,security_count=7,issuer_count=7,conditional_window={'start':'2023-03-31','end':'2023-05-01'},interval_stability_assumption='EXPLICIT_CONDITIONAL_STABILITY_BETWEEN_DATED_SNAPSHOTS_NOT_FULL_LEGAL_INTERVAL_CERTIFICATION',source_hashes=sources,continuous_identity_interval_verified=False,provider_price_binding_verified=False,point_in_time_verified=False,promotion_allowed=False,execution_performed=False,legacy_bridge_called=False,early_evidence_availability_inferred=False)
    validate_report(result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();v=build();saved=web.prior.publish(a.output,v);web.prior.verify(v['source_hashes']);print(json.dumps(saved))
