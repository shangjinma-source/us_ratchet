"""Read-only candidate evidence inventory; no historical-to-current identity join approval."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research'
ANCHORS = {
    'manifest': ('latest_all_ndx_conditional_manifest_20260919_v1/manifest.json', 'be842f56db29f989af87885079c8807334089b36334c4c8c743d9ab2c33007e2'),
    'four': ('four_issuer_filing_identity_20260912_v1/dated_identity_adjudication.json', 'a70551b92c2154b9b1efe5eadb35b1f3c0f34b1c9a858506e3a2085df888d8a4'),
    'seven': ('seven_dated_identity_assembly_20260919_v1/identities.json', 'ed810b2fc1626e05f3c1edee10212645dad37435461b8b7e8d01dcba1354e7c2'),
    'lite': ('lite_cusip_pdf_capture_20260919_v1/seven_security_readback.json', '6f105091409cfb881dc9e016101cc4cf72dcf7bb634861a381100875873bf022'),
    'documents': ('local_business_excerpt_research_20260912_v1/local_evidence_matrix.json', '99d96c74803c3234f6564c8e5e2f76db03340b5e9f22c485783139396d372c58'),
    'mapping': ('local_business_excerpt_research_20260912_v1/conditional_business_mapping_v2_20260912.json', '11999dd237ae04d1a52601550033675fe0e1bdc184b58505350d49c5e281b72e'),
    'facts': ('identity_public_source_probe_20260912_v1/extracted_facts_20260912.json', 'dfe62747ebce89e8545e6d89d1435803663b3cf8a153ba205be66ba8b513c4e5'),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    sources = {str(Path(__file__).resolve()): sha(__file__)}
    values = {}
    for name, (relative, expected) in ANCHORS.items():
        path = (BASE / relative).resolve()
        if sha(path) != expected:
            raise ValueError('Sealed evidence changed: ' + name)
        sources[str(path)] = expected
        values[name] = json.loads(path.read_text(encoding='utf-8'))
    documents = []
    for original in values['documents']['documents']:
        item = {k: v for k, v in original.items() if k != 'excerpt'}
        path = Path(item['raw_path']).resolve()
        if sha(path) != item['raw_sha256']:
            raise ValueError('Original annual document differs')
        sources[str(path)] = item['raw_sha256']
        soup = BeautifulSoup(path.read_bytes(), 'lxml')
        fields = {}
        for node in soup.find_all(attrs={'name': True}):
            name = node.get('name', '')
            if name.lower() in ('dei:entitycentralindexkey', 'dei:tradingsymbol', 'dei:security12btitle', 'dei:documentperiodenddate'):
                fields.setdefault(name.lower(), []).append(dict(context=node.get('contextref'), text=node.get_text(' ', strip=True)))
        item['observed_inline_cover_fields'] = fields
        item['cover_fields_are_unadjudicated_multivalues'] = True
        documents.append(item)
    identity_path = ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2/security_identity.csv'
    sources[str(identity_path.resolve())] = sha(identity_path)
    local = list(csv.DictReader(identity_path.open(encoding='utf-8-sig')))
    dated = []
    for label in ('four', 'seven'):
        for item in values[label]['rows']:
            dated.append(dict(source=label, fact=item))
    dated.extend(dict(source='lite', fact=item) for item in values['lite']['dated_facts'])
    historical = [item for period in values['mapping']['dates'] for item in period['candidates']]
    resolutions = [item for period in values['mapping']['audit'] for item in period['issuer_resolutions']]
    rows = []
    for channel in values['manifest']['rows']:
        ticker, issuer = channel['ticker'], channel['conditional_issuer_id']
        cik = channel['current_reported_cik']
        same_issuer_documents = [d for d in documents if d['issuer_id'] == issuer]
        candidates = [r for r in local if r['issuer_id'] == issuer and ticker in r['ticker_set'].split(';')]
        facts = [r for r in dated if r['fact']['ticker'] == ticker and str(r['fact'].get('issuer_cik', r['fact'].get('subject_cik', r['fact'].get('subject_issuer_cik', '')))).zfill(10) == cik]
        old = [r for r in historical if r['issuer_id'] == issuer and r['ticker'] == ticker]
        reviewed = [r for r in resolutions if r['issuer_id'] == issuer and r['status'] == 'CONDITIONAL_DATED_DOCUMENT_BUSINESS_MATCH']
        chains = sorted({r['chain'] for r in reviewed})
        old_chains = sorted({c for r in old for c in r['local_risk_chain_evidence']})
        rows.append(dict(ticker=ticker, current_issuer_id=issuer,
            fit127_date_coverage_only=channel['conditional_numeric_fit_date_coverage_only'],
            dated_security_fact_candidates=facts,
            local_cusip_mapping_candidates=candidates,
            same_current_cik_annual_document_ids=[d['document_id'] for d in same_issuer_documents],
            historical_conditional_business_chain_candidates=chains,
            historical_original_risk_labels=old_chains,
            historical_business_document_ids=sorted({d for r in reviewed for d in r['independent_direct_match_document_ids']}),
            returned_split_like_events=channel['raw_returned_split_events'],
            special_dated_meta_event=values['facts']['nasdaq_meta_event'] if ticker == 'META' else None,
            evidence_tier=('DATED_CUSIP_CLASS_FACT_CANDIDATE' if facts else 'LOCAL_CUSIP_MAPPING_ONLY' if candidates else 'CURRENT_CIK_ONLY_IN_SCANNED_SOURCES'),
            selected_security_id=None, selected_risk_chain=None,
            gaps=['CURRENT_TO_DATED_SECURITY_CONTINUITY_NOT_PROVEN', 'LATEST_PROVIDER_SECURITY_BINDING_NOT_PROVEN',
                  'LATEST_RISK_CLASSIFICATION_INTERVAL_NOT_PROVEN', 'POINT_IN_TIME_MEMBERSHIP_NOT_PROVEN'],
            identity_join_approved=False, risk_input_admitted=False, point_in_time_verified=False, promotion_allowed=False))
    ready = [r for r in rows if r['fit127_date_coverage_only']]
    if len(rows) != 101 or len(ready) != 96 or len(documents) != 83:
        raise ValueError('Sealed denominator differs')
    result = dict(schema='LATEST_SECURITY_SOURCE_CANDIDATE_INVENTORY_DRAFT_V1', cutoff='2026-09-17',
        rows=rows, annual_documents=documents, sources=sources,
        counts=dict(observed_channels=101, fit127_channels=96, annual_documents=83,
            ready_by_tier=dict(Counter(r['evidence_tier'] for r in ready)),
            ready_with_annual_documents=sum(bool(r['same_current_cik_annual_document_ids']) for r in ready),
            ready_with_reviewed_historical_business_candidates=sum(bool(r['historical_conditional_business_chain_candidates']) for r in ready),
            ready_with_original_historical_risk_labels=sum(bool(r['historical_original_risk_labels']) for r in ready),
            admitted_security_coordinates=0, admitted_latest_risk_chains=0),
        nport_limit='Original fund XML has security title/CUSIP/LEI but no security ticker or issuer CIK; local mapping is not a historical identity certificate.',
        annual_cover_limit='Multivalue inline facts only; same CIK locates candidate documents, not current share-class continuity. No name joins.',
        source_verification_scope='Top sealed evidence bytes and 83 annual raw bytes only; this draft does not re-certify recursive historical closures.',
        derived_sources_are_candidates_not_new_adjudications=True, new_security_ids_created=False,
        training_performed=False, point_in_time_verified=False, promotion_allowed=False)
    for path, expected in sources.items():
        if sha(path) != expected:
            raise ValueError('Inventory source drift')
    return result


if __name__ == '__main__':
    result = build()
    output = BASE / 'latest_security_source_inventory_20260919_v1/inventory_draft.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=True, indent=2, allow_nan=False)
    print(json.dumps({'path': str(output), 'sha256': sha(output), 'counts': result['counts']}))
