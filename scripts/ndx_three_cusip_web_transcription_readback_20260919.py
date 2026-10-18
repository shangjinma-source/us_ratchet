"""Bounded web-tool transcription; not a local HTTP original or interval certification."""
import argparse, hashlib, json, sys
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_three_historical_cusip_readback_20260919 as prior
BASE=prior.BASE
TRANSCRIPT=BASE/'three_cusip_web_transcription_20260919_v1/transcription.json'
TRANSCRIPT_SHA='718284f9e2e71872a789ae8acd5e525dc31772bcc6626d60bd6a06f6b0c616f5'
SELECTIONS=BASE/'three_historical_cusip_capture_20260919_v1/manifest.json'
SELECTIONS_SHA='a284757f9cc856a52353b19fbd9c9733688280cd485c89ced8266586a8cfd689'
EXPECTED={
 'ADI':('0001104659-23-015306','2023-02-09','2022-12-30','tv0261-analogdevicesinc.htm',['Analog Devices Inc.','Common Stock','032654105','December 30, 2022','February 9, 2023']),
 'BKR':('0001306550-23-007056','2023-02-03','2022-12-31','us05722g1004_020323.txt',['BAKER HUGHES CO','Class A  Common Stock','05722G100','December 31, 2022','February 3, 2023']),
 'ENPH':('0001306550-23-001244','2023-01-20','2022-12-31','us29355a1079_012023.txt',['ENPHASE ENERGY INC','Common Stock','29355A107','December 31, 2022','January 20, 2023'])}
LOADED={str(Path(__file__).resolve()):hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),**prior.LOADED}

def inspect(row,submission,cover):
    ticker=row['ticker'];fact=prior.FACTS[ticker];accession,filedate,eventdate,document,values=EXPECTED[ticker]
    if str(submission['cik']).zfill(10)!=fact['cik']:raise ValueError('Subject CIK, not reporting-person CIK, required')
    recent=submission['filings']['recent']
    if recent['accessionNumber'].count(accession)!=1:raise ValueError('Unique actual subject accession required')
    i=recent['accessionNumber'].index(accession)
    if recent['filingDate'][i]!=filedate or recent['primaryDocument'][i]!=document or recent['form'][i] not in ('SC 13G','SC 13G/A'):raise ValueError('Original SEC accession row differs')
    url=f'https://www.sec.gov/Archives/edgar/data/{int(fact["cik"])}/{accession.replace("-", "")}/{document}'
    if (row['accession'],row['filing_date'],row['event_date'],row['url'])!=(accession,filedate,eventdate,url):raise ValueError('Dated document coordinates differ')
    if [x['verbatim_value'] for x in row['excerpts']]!=values or not prior.checksum(fact['cusip']):raise ValueError('Observed factual excerpts differ')
    expected_lines=[10,12,14,16,172] if ticker=='ADI' else [17,21,24,28,275 if ticker=='BKR' else 279]
    if [x['tool_line'] for x in row['excerpts']]!=expected_lines:raise ValueError('Tool locator differs')
    started=datetime.strptime(row['tool_call_started_utc'],'%Y-%m-%d %H:%M:%S UTC');ended=datetime.strptime(row['tool_call_completed_utc'],'%Y-%m-%d %H:%M:%S UTC')
    if ended<started or ended.date().isoformat()!='2026-09-19':raise ValueError('Actual observation time differs')
    if cover['cik']!=fact['cik'] or cover['ticker']!=ticker or not cover['security_class_title'].startswith(fact['security_class']):raise ValueError('Separate original 10K cover differs')
    return dict(ticker=ticker,subject_cik=fact['cik'],cusip=fact['cusip'],security_class=fact['security_class'],accession=accession,filing_date=filedate,event_date=eventdate,source_url=url,original_10k_cover=cover,evidence_type='WEB_TOOL_OFFICIAL_DOCUMENT_TRANSCRIPTION',subject_cik_evidence='SAME_ACCESSION_IN_ORIGINAL_SEC_SUBMISSIONS',cusip_evidence='WEB_TOOL_PARSED_FACTUAL_EXCERPT',local_http_original_bytes_available=False,historical_identity_interval_verified=False,provider_binding_verified=False,point_in_time_verified=False)

def build():
    sources=dict(LOADED)
    def read(path,h):
        p=str(Path(path).resolve())
        if p in sources and sources[p]!=h:raise ValueError('Source conflict')
        raw=Path(p).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=h:raise ValueError('External source SHA differs')
        sources[p]=h;return raw
    transcription=json.loads(read(TRANSCRIPT,TRANSCRIPT_SHA));manifest=json.loads(read(SELECTIONS,SELECTIONS_SHA))
    for p,h in manifest['source_hashes'].items():read(p,h)
    if transcription['schema']!='WEB_TOOL_OFFICIAL_DOCUMENT_TRANSCRIPTION_V1' or len(transcription['rows'])!=3 or {r['ticker'] for r in transcription['rows']}!=set(EXPECTED):raise ValueError('Three-document denominator differs')
    for flag in ('full_tool_response_preserved','local_http_original_bytes_available','point_in_time_verified','provider_binding_verified','historical_identity_interval_verified'):
        if transcription[flag] is not False:raise ValueError('Transcription is not HTTP/PIT certification')
    selections={r['ticker']:r for r in manifest['selections']};rows=[]
    for row in transcription['rows']:
        t=row['ticker'];sel=selections[t];fact=prior.FACTS[t]
        submission=json.loads(prior.decode(read(sel['submissions_path'],sel['submissions_sha256'])))
        cover=prior.parse_cover(read(prior.SECROOT/fact['file'],fact['sha']),t)
        rows.append(inspect(row,submission,cover))
    prior.verify(sources)
    return dict(schema='THREE_DATED_SECURITY_WEB_TRANSCRIPTION_READBACK_V1',rows=rows,security_count=3,source_hashes=sources,transcription_reference=dict(path=str(TRANSCRIPT),sha256=TRANSCRIPT_SHA),raw_http_verified_count=0,web_transcription_accession_links_checked=3,full_tool_response_preserved=False,historical_identity_interval_verified=False,provider_binding_verified=False,point_in_time_verified=False,promotion_allowed=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();v=build();saved=prior.publish(a.output,v);prior.verify(v['source_hashes']);print(json.dumps(saved))
