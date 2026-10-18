"""Inventory already local dated business evidence; never assign risk labels."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_business_heading_excerpt_research as extraction


def main():
    sources = {}
    def read(path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and expected != digest:
            raise ValueError('Business evidence source differs: ' + str(path))
        if str(path) in sources and sources[str(path)] != digest:
            raise ValueError('Source changed during matrix read')
        sources[str(path)] = digest
        return raw
    read(__file__)
    read(extraction.__file__)
    coverage_path = ROOT / 'data/cache/research/dynamic_frozen_v2/full_membership_coverage_20260912_v2.json'
    coverage = json.loads(read(coverage_path, 'eb15d117e6b3c07a41decf1666b5dfbcfda2fd25ee00ea05b5df680d7473dd64'))
    documents_path = ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2/review_pack/sec_review_documents.csv'
    read(documents_path, '37564a6f9de5fa5d7ef79109248b6a4003379d201b90e5a3e612952a1d15aba6')
    documents = pd.read_csv(documents_path, dtype=str, keep_default_na=False)
    referenced = {}
    dates = []
    for cohort in coverage['dates']:
        rows = []
        for candidate in cohort['candidates']:
            if candidate['unambiguous_local_risk_evidence']:
                continue
            prior = documents.loc[documents.issuer_id.eq(candidate['issuer_id'])
                & documents.source_available_date.ne('')
                & documents.source_available_date.le(cohort['decision_cutoff'])]
            identifiers = []
            for record in prior.to_dict('records'):
                key = record['issuer_id'] + ':' + record['accession_number']
                if key in referenced and referenced[key] != record:
                    raise ValueError('Conflicting local filing descriptors')
                referenced[key] = record
                identifiers.append(key)
            rows.append(dict(ticker=candidate['ticker'], security_id=candidate['security_id'],
                issuer_id=candidate['issuer_id'], candidate_document_ids=identifiers,
                publication_date_status='EXISTING_MANIFEST_METADATA_NOT_INDEPENDENTLY_REVERIFIED',
                risk_chain_assigned=False))
        dates.append(dict(coordinate=cohort['coordinate'], decision_cutoff=cohort['decision_cutoff'], rows=rows,
            missing_risk_count=len(rows), with_prior_local_document_count=sum(bool(row['candidate_document_ids']) for row in rows)))
    prepared = []
    for key, record in sorted(referenced.items()):
        raw = read(record['raw_path'], record['raw_sha256'])
        manifest = json.loads(read(record['raw_manifest_path'], record['raw_manifest_sha256']))
        if (manifest['content_sha256'] != record['raw_sha256'] or manifest['content_bytes'] != len(raw)
                or manifest['issuer_id'] != record['issuer_id'] or manifest['accession_number'] != record['accession_number']
                or manifest['evidence_available_date'] != record['source_available_date']):
            raise ValueError('Business document manifest linkage differs')
        prepared.append((key, record, raw))
    def extract(item):
        key, record, raw = item
        result = dict(document_id=key, issuer_id=record['issuer_id'], tickers=record['tickers'], form=record['form'],
            source_available_date=record['source_available_date'], raw_path=record['raw_path'],
            raw_sha256=record['raw_sha256'], old_extraction_status=record['extraction_status'],
            old_section_character_count=record['section_text_chars'], risk_chain_assigned=False)
        if record['form'] not in ('10-K', '10-K/A'):
            result.update(status='RAW_VERIFIED_UNSUPPORTED_FORM_MANUAL_BOUNDARY_REVIEW_REQUIRED', excerpt=None)
        else:
            try:
                result.update(status='DOM_EXCERPT_READY_FOR_MANUAL_REVIEW',
                    excerpt=extraction.extract_business_heading_excerpt(raw))
            except ValueError as error:
                result.update(status='RAW_VERIFIED_UNSUPPORTED_LAYOUT_MANUAL_BOUNDARY_REVIEW_REQUIRED',
                    excerpt=None, extraction_rejection=str(error))
        return result
    with ThreadPoolExecutor(max_workers=3) as pool:
        excerpts = list(pool.map(extract, prepared))
    for path, digest in list(sources.items()):
        read(path, digest)
    report = dict(schema='ndx_local_risk_business_evidence_matrix_v1', source_hashes=sources, dates=dates,
        documents=excerpts, unique_document_count=len(excerpts),
        strict_dom_excerpt_count=sum(row['excerpt'] is not None for row in excerpts),
        scope='EXISTING_LOCAL_BUSINESS_SOURCE_HEADROOM_FOR_MISSING_RISK_CLASSIFICATIONS',
        old_review_registry_modified=False, new_network_capture_performed=False,
        return_or_price_values_read=False, classification_based_on_returns=False,
        risk_chains_assigned=False, publication_times_independently_verified=False,
        full_membership_verified=False, point_in_time_verified=False, promotion_allowed=False)
    output = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1/local_evidence_matrix.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf8') as handle:
        json.dump(report, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write('\n')
    print(json.dumps(dict(path=str(output), sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        unique_documents=report['unique_document_count'], strict_excerpts=report['strict_dom_excerpt_count'],
        first_last=[{key:value for key,value in row.items() if key != 'rows'} for row in (dates[0], dates[-1])],
        source_count=len(sources))))


if __name__ == '__main__':
    main()
