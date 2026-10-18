"""Hard-bound retrospective business mapping, distinct from portfolio risk admission."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
FOLDER = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1'
BINDINGS = {
 'coverage': (ROOT / 'data/cache/research/dynamic_frozen_v2/full_membership_coverage_20260912_v2.json', 'eb15d117e6b3c07a41decf1666b5dfbcfda2fd25ee00ea05b5df680d7473dd64'),
 'matrix': (FOLDER / 'local_evidence_matrix.json', '99d96c74803c3234f6564c8e5e2f76db03340b5e9f22c485783139396d372c58'),
 'technology': (FOLDER / 'technology_business_suggestions_20260912.json', 'f3e0fa46fb0cd86a6fa0e49dcea7b6a05e873564c19e2db121c3dedbfb09b7eb'),
 'nontechnology': (FOLDER / 'nontechnology_business_suggestions_20260912.json', '22f9cd5073989a41f59cfba159d562da95d69dad91e9c8f32a75c415dfefdcbc'),
 'technology_review': (FOLDER / 'technology_business_independent_root_review_20260912.json', 'cfe29a071a189f11c3cb4e5876363c308cfd80bbc7dd1b365db7411458c54688'),
 'nontechnology_review': (FOLDER / 'nontechnology_business_independent_review_20260912.json', '944107267a24bb3fada56d7362fce89101ab4f27f8f2a88199457a1de17a381b'),
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read_bound(path, expected):
    raw = Path(path).read_bytes()
    if _sha(raw) != expected:
        raise ValueError('Externally bound evidence SHA mismatch: ' + str(path))
    return json.loads(raw)


def _assemble(dates, documents, proposals, approved):
    """Internal deterministic mapping only; this function does not authenticate inputs."""
    output = deepcopy(dates)
    audit = []
    sid_issuers = {}
    for date in output:
        candidates = date['candidates']
        if len({row['security_id'] for row in candidates}) != len(candidates):
            raise ValueError('Repeated security in candidate denominator')
        per_issuer = {}
        for candidate in candidates:
            sid, issuer = candidate['security_id'], candidate['issuer_id']
            if sid in sid_issuers and sid_issuers[sid] != issuer:
                raise ValueError('Stable SID changed issuer')
            sid_issuers[sid] = issuer
            if 'conditional_business_chain' in candidate:
                raise ValueError('Already mapped input not accepted')
            if issuer not in per_issuer:
                prior = [doc for doc in documents.values() if doc['issuer_id'] == issuer
                         and doc['source_available_date'] and doc['source_available_date'] <= date['decision_cutoff']]
                ids = [doc['document_id'] for doc in prior]
                authorized = [identifier for identifier in ids if identifier in approved]
                all_chains = {proposals[identifier]['suggested_risk_chain'] for identifier in ids if identifier in proposals}
                if not prior:
                    status = 'UNKNOWN_NO_PRIOR_DOCUMENT'
                elif len(all_chains) > 1:
                    status = 'UNKNOWN_CONFLICTING_DOCUMENT_CHAINS'
                elif not authorized:
                    status = 'UNKNOWN_NO_INDEPENDENT_DIRECT_MATCH'
                elif any(identifier not in approved for identifier in ids):
                    status = 'UNKNOWN_ADDITIONAL_DOCUMENT_REVIEW_INCOMPLETE'
                else:
                    status = 'CONDITIONAL_DATED_DOCUMENT_BUSINESS_MATCH'
                chain = approved[authorized[0]] if status == 'CONDITIONAL_DATED_DOCUMENT_BUSINESS_MATCH' else None
                if authorized and len({approved[key] for key in authorized}) > 1:
                    chain, status = None, 'UNKNOWN_CONFLICTING_APPROVED_CHAINS'
                per_issuer[issuer] = dict(issuer_id=issuer, chain=chain, status=status,
                    prior_document_ids=ids, independent_direct_match_document_ids=authorized)
            resolution = per_issuer[issuer]
            candidate['conditional_business_chain'] = resolution['chain']
        audit.append(dict(coordinate=deepcopy(date['coordinate']), decision_cutoff=date['decision_cutoff'],
            complete_security_denominator=len(candidates), complete_issuer_denominator=len(per_issuer),
            conditionally_mapped_security_count=sum(row['conditional_business_chain'] is not None for row in candidates),
            issuer_resolutions=list(per_issuer.values())))
    return output, audit


def build_conditional_business_mapping():
    """Read only fixed reviewed artifacts; caller may separately create an immutable report."""
    evidence = {key:_read_bound(path, digest) for key, (path, digest) in BINDINGS.items()}
    sources = {str(SOURCE):LOADED_SHA}
    for key, value in evidence.items():
        path, expected = BINDINGS[key]
        for name, digest in {**value['source_hashes'], str(path):expected}.items():
            if name in sources and sources[name] != digest:
                raise ValueError('Contradictory source closure')
            sources[name] = digest
    def verify():
        for path, expected in sources.items():
            if _sha(Path(path).read_bytes()) != expected:
                raise ValueError('Bound source drift: ' + path)
    verify()
    documents = {row['document_id']:row for row in evidence['matrix']['documents']}
    if len(documents) != 83:
        raise ValueError('Original 83-document denominator required')
    proposals = {}
    for group in ('technology','nontechnology'):
        for row in evidence[group]['suggestions']:
            key = row['document_id']
            if key in proposals:
                raise ValueError('Overlapping suggestion document')
            document = documents[key]
            section = document['excerpt']['section_text']
            paragraph = section[row['paragraph_offset']:row['paragraph_offset']+row['paragraph_characters']]
            if (row['issuer_id'] != document['issuer_id'] or row['raw_sha256'] != document['raw_sha256']
                    or row['source_available_date'] != document['source_available_date']
                    or _sha(paragraph.encode()) != row['paragraph_sha256']
                    or _sha(Path(document['raw_path']).read_bytes()) != document['raw_sha256']):
                raise ValueError('Suggestion/raw paragraph linkage differs')
            proposals[key] = row
    if len(proposals) != 60:
        raise ValueError('Full 60 reviewed-document suggestions required')
    approved = {}
    for review in evidence['technology_review']['results']:
        proposal = proposals[review['document_id']]
        if (review['issuer_id'] != proposal['issuer_id'] or review['suggested_chain'] != proposal['suggested_risk_chain']
                or review['paragraph_sha256'] != proposal['paragraph_sha256']):
            raise ValueError('Independent technology review linkage differs')
        if review['eligible_for_conditional_research_mapping'] is True and review['independent_business_definition_match'] is True:
            approved[review['document_id']] = review['suggested_chain']
    for review in evidence['nontechnology_review']['rows']:
        proposal = proposals[review['document_id']]
        if review['ticker'] != proposal['document_ticker_label']:
            raise ValueError('Independent nontechnology review linkage differs')
        if review['boundary_status'] == 'DIRECT_BUSINESS_DEFINITION_MATCH' and review['business_evidence_supports_suggested_chain'] is True:
            approved[review['document_id']] = proposal['suggested_risk_chain']
    if len(approved) != 36 or len({documents[key]['issuer_id'] for key in approved}) != 35:
        raise ValueError('Exact 36 direct documents / 35 issuers required')
    dates = evidence['coverage']['dates']
    if len(dates) != 15 or len({json.dumps(date['coordinate'],sort_keys=True) for date in dates}) != 15:
        raise ValueError('Complete independent 15-cohort denominator required')
    if any(len(date['candidates']) != 101 for date in dates):
        raise ValueError('Original complete 101-security proxy denominator required')
    mapped, audit = _assemble(dates, documents, proposals, approved)
    verify()
    return dict(schema='ndx_conditional_business_mapping_research_v1', source_hashes=sources, dates=mapped,
        audit=audit, date_count=15, input_security_rows=1515, direct_reviewed_documents=36, direct_reviewed_issuers=35,
        new_candidate_field='conditional_business_chain', original_candidate_fields_preserved=True,
        mapping_scope='RETROSPECTIVE_DATED_DOCUMENT_INTERPRETATION_ONLY',
        review_authority='EXTERNAL_HARD_SHA_REVIEW_ARTIFACTS_NOT_SELF_SIGNED_FLAGS',
        historical_document_rule='ALL_AVAILABLE_DOCUMENTS_REQUIRE_CONSISTENT_INDEPENDENT_DIRECT_REVIEW',
        original_registry_modified=False, original_risk_fields_modified=False,
        source_publication_metadata_independently_verified=False, classification_valid_interval_verified=False,
        full_membership_verified=False, point_in_time_verified=False, portfolio_risk_admission=False,
        training_performed=False, promotion_allowed=False)
