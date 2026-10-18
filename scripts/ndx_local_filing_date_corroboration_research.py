"""Corroborate 83 local accession dates without refetching annual reports."""
from collections import Counter,defaultdict
from datetime import date,timedelta
import csv
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
MATRIX=ROOT/'data/cache/research/local_business_excerpt_research_20260912_v1/local_evidence_matrix.json'
MATRIX_SHA='99d96c74803c3234f6564c8e5e2f76db03340b5e9f22c485783139396d372c58'


def build():
    sources={}
    def read(path,sha=None):
        path=Path(path).resolve();raw=path.read_bytes();actual=hashlib.sha256(raw).hexdigest()
        if sha is not None and actual!=sha:raise ValueError('Bound source differs')
        sources[str(path)]=actual;return json.loads(raw)
    matrix=read(MATRIX,MATRIX_SHA)
    docs=matrix['documents']
    if len(docs)!=83:raise ValueError('Exact original document denominator required')
    targets={row['document_id'].rsplit(':',1)[-1]:row for row in docs}
    ciks={row['issuer_id'].split(':')[-1] for row in docs}
    paths=[ROOT/row for row in subprocess.check_output(['rg','--files','--no-ignore','data/cache'],cwd=ROOT,text=True,encoding='utf8').splitlines()]
    submissions=defaultdict(list);facts=defaultdict(list);sidecar_audits=[]
    def sidecar(path):
        manifest=Path(str(path)+'.manifest.json')
        if not manifest.exists():return dict(manifest_present=False)
        value=read(manifest)
        if value.get('content_sha256')!=sources[str(path.resolve())] or value.get('content_bytes')!=path.stat().st_size:
            raise ValueError('Local capture sidecar content binding differs')
        return dict(manifest_present=True,manifest_path=str(manifest),
            metadata_content_sha256=value.get('content_sha256'),
            content_binding_matches=value.get('content_sha256')==sources[str(path.resolve())],
            source_url=value.get('source_locator',value.get('source_url')),fetched_at=value.get('fetched_at'),created_at=value.get('created_at'))
    for path in paths:
        if ('submission' not in str(path).lower() or path.suffix!='.json' or path.name.endswith('.manifest.json')
                or not any(cik in path.name for cik in ciks)):continue
        payload=read(path);table=payload.get('filings',{}).get('recent',payload)
        if not isinstance(table.get('accessionNumber'),list):continue
        arrays={key:table.get(key) for key in ('accessionNumber','filingDate','reportDate','acceptanceDateTime','form','primaryDocument')}
        count=len(arrays['accessionNumber'])
        if any(value is not None and len(value)!=count for value in arrays.values()):raise ValueError('Submission arrays unequal')
        receipt=sidecar(path)
        for i,accession in enumerate(arrays['accessionNumber']):
            if accession not in targets:continue
            record={key:(value[i] if value is not None else None) for key,value in arrays.items()}
            submissions[accession].append(dict(source_type='SEC_SUBMISSIONS_JSON_LOCAL_CAPTURE',path=str(path),
                sha256=sources[str(path.resolve())],cik=payload.get('cik'),raw_fields=record,capture_metadata=receipt))
    for cik in sorted(ciks):
        path=ROOT/'data/cache/candidate_pools/ndx_fundamentals/raw_companyfacts'/('CIK'+cik+'.json')
        if not path.exists():continue
        payload=read(path);matches=defaultdict(lambda:dict(filed=set(),forms=set(),count=0))
        for namespace,concepts in payload.get('facts',{}).items():
            for concept,fact in concepts.items():
                for unit,values in fact.get('units',{}).items():
                    for item in values:
                        accession=item.get('accn')
                        if accession not in targets:continue
                        record=matches[accession];record['filed'].add(item.get('filed'));record['forms'].add(item.get('form'));record['count']+=1
        receipt=sidecar(path)
        for accession,record in matches.items():
            facts[accession].append(dict(source_type='SEC_COMPANYFACTS_XBRL_FACT_FILED_FIELD_LOCAL_CAPTURE',path=str(path),
                sha256=sources[str(path.resolve())],cik=payload.get('cik'),filed_dates=sorted(record['filed']),
                forms=sorted(record['forms']),matching_fact_count=record['count'],capture_metadata=receipt,
                fact_period_end_is_not_filing_date=True,filing_content_authenticity_proven=False))
    descriptors_path=ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/review_pack/sec_review_documents.csv'
    raw=descriptors_path.read_bytes();sources[str(descriptors_path)]=hashlib.sha256(raw).hexdigest()
    descriptors={row['issuer_id']+':'+row['accession_number']:row for row in csv.DictReader(raw.decode('utf-8-sig').splitlines())}
    rows=[]
    for document in docs:
        accession=document['document_id'].rsplit(':',1)[-1];submission=submissions[accession];companyfacts=facts[accession]
        filed={record['raw_fields']['filingDate'] for record in submission if record['raw_fields']['filingDate']}
        filed.update(day for record in companyfacts for day in record['filed_dates'] if day)
        if len(filed)>1:status='CONFLICTING_RAW_FILED_DATES'
        elif filed:
            actual=next(iter(filed));available=document['source_available_date']
            if available==(date.fromisoformat(actual)+timedelta(days=1)).isoformat():status='LOCAL_RAW_FILED_PLUS_ONE_CALENDAR_DAY_MATCH'
            elif available==actual:status='LOCAL_RAW_FILED_SAME_DAY_MATCH'
            else:status='LOCAL_RAW_FILED_DIFFERS_FROM_AVAILABLE_POLICY'
        else:status='NO_LOCAL_RAW_ACCESSION_FILED_CORROBORATION'
        descriptor=descriptors[document['document_id']]
        issuer_cik=int(document['issuer_id'].split(':')[-1])
        for evidence in submission:
            if (evidence['cik'] is not None and int(evidence['cik'])!=issuer_cik
                    or evidence['raw_fields']['form']!=document['form']
                    or evidence['raw_fields']['primaryDocument']!=Path(document['raw_path']).name):
                raise ValueError('Accession issuer/form/primary-document linkage differs')
        for evidence in companyfacts:
            if int(evidence['cik'])!=issuer_cik or evidence['forms']!=[document['form']]:
                raise ValueError('Companyfacts accession issuer/form differs')
        rows.append(dict(document_id=document['document_id'],tickers=document['tickers'],issuer_id=document['issuer_id'],
            accession_number=accession,form=document['form'],source_available_date=document['source_available_date'],
            document_url=descriptor['document_url'],raw_document_path=document['raw_path'],raw_document_sha256=document['raw_sha256'],
            status=status,corroborating_filed_dates=sorted(filed),submission_evidence=submission,companyfacts_evidence=companyfacts,
            acceptance_datetime_available=any(record['raw_fields']['acceptanceDateTime'] for record in submission),
            raw_filing_report_date_available=any(record['raw_fields']['reportDate'] for record in submission),
            original_document_authenticity_independently_verified=False,publication_at_historical_cutoff_verified=False))
    for filename in ('data/ndx_filing_identity.py','data/ndx_fundamentals.py','data/ndx_current_taxonomy.py'):
        path=ROOT/filename;sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    sources[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for path,sha in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Source changed during audit')
    return dict(schema='ndx_local_filing_date_corroboration_v1',document_count=len(rows),documents=rows,
        status_counts=dict(Counter(row['status'] for row in rows)),
        raw_submission_accession_count=sum(bool(row['submission_evidence']) for row in rows),
        raw_companyfacts_accession_count=sum(bool(row['companyfacts_evidence']) for row in rows),
        acceptance_datetime_count=sum(row['acceptance_datetime_available'] for row in rows),
        submission_metadata_missing_document_ids=[row['document_id'] for row in rows if not row['submission_evidence']],
        remaining_gaps=['21 documents lack local submissions filingDate/reportDate/acceptanceDateTime arrays.',
            'Companyfacts filed corroborates accession date, not historical raw-document authenticity or exact acceptance time.',
            'Local captures were obtained later; conservative filed+1 policy is not proof of historical publication availability.'],
        raw_document_report_date_count=sum(row['raw_filing_report_date_available'] for row in rows),
        source_hashes=sources,policy_explanation='Historical fundamentals available_date is filed plus one calendar day; filing_identity propagates available_date. Current taxonomy selector separately uses filingDate itself.',
        date_semantics='reportDate is fiscal report period; filingDate is SEC metadata filing date; acceptanceDateTime is separate SEC metadata timestamp; local receipt does not prove historical availability.',
        new_network_fetch_performed=False,raw_annual_reports_refetched=False,metadata_corroboration_is_not_raw_document_authenticity=True,
        point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    output=ROOT/'data/cache/research/local_business_excerpt_research_20260912_v1/local_filing_date_corroboration_20260912.json'
    if output.exists():raise FileExistsError(output)
    report=build();raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with output.open('xb') as stream:stream.write(raw)
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(raw).hexdigest(),
        status_counts=report['status_counts'],submission_count=report['raw_submission_accession_count'],
        companyfacts_count=report['raw_companyfacts_accession_count'],acceptance_datetime_count=report['acceptance_datetime_count'])))
