"""Bind already captured SEC header excerpts to all 83 business documents."""
from collections import Counter
from datetime import datetime,timedelta
import csv
import hashlib
import io
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/candidate_pools/ndx_fundamentals/sic_history_v1'
PREVIOUS=ROOT/'data/cache/research/local_business_excerpt_research_20260912_v1/local_filing_date_corroboration_20260912.json'
PREVIOUS_SHA='1d3dfe7df2710a2bee31d599e3dab38dcb0a75255d1e8459c3798f7d1dd457ad'


def parse_header(raw,*,accession,cik,form):
    text=raw.decode('latin-1').replace('\r\n','\n')
    if text.count('<SEC-HEADER>')!=1 or text.count('</SEC-HEADER>')!=1:raise ValueError('Unique complete SEC header required')
    def one(pattern):
        values=re.findall(pattern,text,re.MULTILINE)
        if len(values)!=1:raise ValueError('Unique header field required: '+pattern)
        return values[0].strip()
    actual=one(r'^ACCESSION NUMBER:[ \t]*(.*)$')
    actual_form=one(r'^CONFORMED SUBMISSION TYPE:[ \t]*(.*)$')
    cik_values=[int(value) for value in re.findall(r'^[ \t]*CENTRAL INDEX KEY:[ \t]*(\d+)[ \t]*$',text,re.MULTILINE)]
    if (actual!=accession or actual_form!=form or cik_values.count(cik)!=1
            or len(cik_values)!=len(set(cik_values))):raise ValueError('Header accession/CIK/form differs')
    filed=one(r'^FILED AS OF DATE:[ \t]*(\d{8})[ \t]*$')
    period=one(r'^CONFORMED PERIOD OF REPORT:[ \t]*(\d{8})[ \t]*$')
    accepted=one(r'^<ACCEPTANCE-DATETIME>(\d{14})[ \t]*$')
    return dict(accession_number=actual,cik=cik,form=actual_form,all_header_filer_ciks=cik_values,
        multiple_filer_header=len(cik_values)>1,issuer_exclusive_filing_claim=False,
        filing_date=datetime.strptime(filed,'%Y%m%d').date().isoformat(),
        report_period_date=datetime.strptime(period,'%Y%m%d').date().isoformat(),
        acceptance_datetime_raw=accepted,acceptance_clock_naive=datetime.strptime(accepted,'%Y%m%d%H%M%S').isoformat(),
        acceptance_timezone='UNKNOWN_NOT_DECLARED_IN_CAPTURED_HEADER',acceptance_instant_utc=None)


def build():
    sources={}
    def read(path,expected=None):
        path=Path(path).resolve();raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        if expected is not None and sha!=expected:raise ValueError('Bound source SHA differs')
        sources[str(path)]=sha;return raw
    previous=json.loads(read(PREVIOUS,PREVIOUS_SHA));sources.update(previous['source_hashes'])
    manifest=json.loads(read(BASE/'raw_header_index.csv.manifest.json'))
    raw_index=read(BASE/'raw_header_index.csv','afabac88cc7c5f785df3b59e6b181914e2371794ece4940b128c0ef1fbbe8ce6')
    if manifest['content_sha256']!=hashlib.sha256(raw_index).hexdigest() or manifest['content_bytes']!=len(raw_index):
        raise ValueError('Original header index manifest differs')
    index=list(csv.DictReader(io.StringIO(raw_index.decode('utf-8-sig'))))
    statuses=list(csv.DictReader(io.StringIO(read(BASE/'download_status.csv').decode('utf-8-sig'))))
    results=[];clock_differences=[]
    for document in previous['documents']:
        accession=document['accession_number'];cik=int(document['issuer_id'].split(':')[-1])
        record,=[row for row in index if row['accession_number']==accession and int(row['cik'])==cik]
        path=BASE/'raw_headers'/str(cik)/(accession+'.header.txt')
        raw=read(path,record['content_sha256'])
        expected_url=f'https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace("-","")}/{accession}.txt'
        if len(raw)!=int(record['content_bytes']) or Path(record['path']).resolve()!=path.resolve() or record['source_url']!=expected_url:
            raise ValueError('Header source path/URL/length differs')
        facts=parse_header(raw,accession=accession,cik=cik,form=document['form'])
        if (facts['filing_date']!=record['filed_date'] or facts['acceptance_datetime_raw']!=record['acceptance_datetime']
                or document['corroborating_filed_dates']!=[facts['filing_date']]):raise ValueError('Header date conflicts with local metadata')
        policy=(datetime.fromisoformat(facts['filing_date'])+timedelta(days=1)).date().isoformat()
        if policy!=document['source_available_date']:raise ValueError('Available date is not exact filed+1 policy')
        observed=[]
        for source in document['submission_evidence']:
            fields=source['raw_fields']
            if fields['filingDate']!=facts['filing_date'] or fields['reportDate']!=facts['report_period_date']:
                raise ValueError('Submission/header filing or report date conflicts')
            if fields['acceptanceDateTime']:
                # Compare displayed clocks only. Do not infer timezone from an offset pattern.
                stamp=datetime.fromisoformat(fields['acceptanceDateTime'].replace('Z','+00:00'))
                seconds=(stamp.replace(tzinfo=None)-datetime.fromisoformat(facts['acceptance_clock_naive'])).total_seconds()
                observed.append(dict(submission_acceptance_raw=fields['acceptanceDateTime'],
                    header_to_submission_display_clock_difference_seconds=seconds,timezone_adjudicated=False))
                clock_differences.append(seconds)
        status=[row for row in statuses if row['accession_number']==accession and int(row['cik'])==cik]
        results.append(dict(document_id=document['document_id'],tickers=document['tickers'],issuer_id=document['issuer_id'],
            header_path=str(path),header_sha256=sources[str(path.resolve())],header_bytes=len(raw),source_url=expected_url,
            source_available_date=document['source_available_date'],facts=facts,
            filled_missing_submission_date_detail=not bool(document['submission_evidence']),
            submission_clock_observations=observed,original_download_status=status,
            exact_header_http_receipt_time=None,exact_header_http_status=None,
            original_index_manifest_generated_at=manifest.get('generated_at'),
            index_generation_time_is_not_individual_header_receipt=True,
            capture_representation='LOCAL_PREFIX_THROUGH_SEC_HEADER_END_PLUS_NEWLINE_NOT_FULL_HTTP_BODY',
            publication_date_corroborated_by_local_header=True,original_raw_annual_authenticity_verified=False))
    for filename in ('scripts/ndx_sic_readiness.py','data/ndx_sic_history.py',__file__):read(ROOT/filename)
    for path,sha in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Source changed during review')
    return dict(schema='ndx_local_sec_header_date_evidence_v1',documents=results,document_count=len(results),
        raw_header_filing_date_count=len(results),raw_header_acceptance_clock_count=len(results),
        previously_missing_submission_documents_supplemented=sum(row['filled_missing_submission_date_detail'] for row in results),
        all83_filed_plus_one_policy_verified=len(results)==83,source_hashes=sources,
        submission_display_clock_difference_seconds_counts=dict(Counter(str(value) for value in clock_differences)),
        timezone_status='UNKNOWN_NO_NORMATIVE_SPEC_FOR_HEADER_FIELD_BOUND',
        source_integrity_means_local_content_binding_not_external_authentication=True,
        new_filing_http_requests_performed=False,old_cache_modified=False,
        exact_historical_publication_instant_verified=False,point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    output=PREVIOUS.parent/'local_sec_header_date_evidence_20260912.json'
    if output.exists():raise FileExistsError(output)
    report=build();raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with output.open('xb') as stream:stream.write(raw)
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(raw).hexdigest(),count=report['document_count'],
        previously_missing_supplemented=report['previously_missing_submission_documents_supplemented'],
        clock_differences=report['submission_display_clock_difference_seconds_counts'])))
