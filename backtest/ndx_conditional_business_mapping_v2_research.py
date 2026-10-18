"""Add independently reviewed punctuation excerpts without changing frozen v1."""
from copy import deepcopy
from pathlib import Path
from backtest import ndx_conditional_business_mapping_research as previous

SOURCE=Path(__file__).resolve()
LOADED=previous._sha(SOURCE.read_bytes())
ADDITIONS={
 'excerpts':('punctuation_excerpt_addendum_20260912.json','b67e8aa79b2615ac068065598eef9798734e578066e481b19eb8770d58f5588c'),
 'suggestions':('additional_eight_business_suggestions_20260912.json','d5e0ffa51d5087d6f6f0dd8656c6bcb9a9d9a72102f791b93bd6b11fe335a28d'),
 'review':('additional_business_independent_root_review_20260912.json','515d506e7535eb229269faf0e6d8a887985215a7bd097b9105e29d86fbe7c368'),
}


def _merge_addendum(documents,proposals,approved,excerpts,suggestions,reviews):
    """Private structural validator; authentication belongs to the hard-bound entrypoint."""
    documents,proposals,approved=deepcopy((documents,proposals,approved))
    seen=set()
    for item in excerpts:
        key=item['document_id']
        if key in seen or key not in documents:
            raise ValueError('Addendum must reference unique original documents')
        seen.add(key)
        old=documents[key]
        if old['excerpt'] is not None:
            raise ValueError('Cannot replace any original ready document')
        for field in ('issuer_id','raw_path','raw_sha256','source_available_date'):
            if item[field]!=old[field]:raise ValueError('Original raw identity/date binding changed')
        if item['excerpt'] is not None:
            section=item['excerpt']['section_text']
            if previous._sha(section.encode())!=item['excerpt']['section_text_sha256']:
                raise ValueError('New section SHA mismatch')
            documents[key]=deepcopy(item)
    new_proposals={}
    for item in suggestions:
        key=item['document_id']
        if key in proposals or key in new_proposals or key not in seen:
            raise ValueError('Suggestion may only extend prior unsupported documents')
        document=documents[key]
        if document['excerpt'] is None:raise ValueError('Unparsed document cannot be suggested')
        section=document['excerpt']['section_text']
        paragraph=section[item['paragraph_offset']:item['paragraph_offset']+item['paragraph_characters']]
        if (previous._sha(paragraph.encode())!=item['paragraph_sha256'] or
                item['issuer_id']!=document['issuer_id'] or item['raw_sha256']!=document['raw_sha256'] or
                item['source_available_date']!=document['source_available_date']):
            raise ValueError('New proposal paragraph/raw/date mismatch')
        new_proposals[key]=item
    review_ids=set()
    for item in reviews:
        key=item['document_id']
        if key not in new_proposals or key in review_ids:raise ValueError('Review exact new proposal denominator required')
        review_ids.add(key);proposal=new_proposals[key]
        if (item['issuer_id']!=proposal['issuer_id'] or item['suggested_chain']!=proposal['suggested_risk_chain']
                or item['paragraph_sha256']!=proposal['paragraph_sha256']):
            raise ValueError('Independent review differs from new proposal')
        if item['eligible_for_conditional_research_mapping'] is True and item['independent_business_definition_match'] is True:
            approved[key]=item['suggested_chain']
    if review_ids!=set(new_proposals):raise ValueError('Missing independent review row')
    proposals.update(new_proposals)
    return documents,proposals,approved


def build_conditional_business_mapping_v2():
    base=previous.build_conditional_business_mapping()
    sources=dict(base['source_hashes']);sources[str(SOURCE)]=LOADED
    extras={}
    for key,(name,digest) in ADDITIONS.items():
        path=previous.FOLDER/name
        extras[key]=previous._read_bound(path,digest)
        for source,sha in {**extras[key]['source_hashes'],str(path):digest}.items():
            if source in sources and sources[source]!=sha:raise ValueError('Conflicting addendum source closure')
            sources[source]=sha
    def verify():
        for path,sha in sources.items():
            if previous._sha(Path(path).read_bytes())!=sha:raise ValueError('Source closure drift')
    verify()
    evidence={key:previous._read_bound(path,sha) for key,(path,sha) in previous.BINDINGS.items()}
    documents={row['document_id']:row for row in evidence['matrix']['documents']}
    proposals={row['document_id']:row for group in ('technology','nontechnology') for row in evidence[group]['suggestions']}
    approved={row['document_id']:row['suggested_chain'] for row in evidence['technology_review']['results']
              if row['eligible_for_conditional_research_mapping'] is True and row['independent_business_definition_match'] is True}
    approved.update({row['document_id']:proposals[row['document_id']]['suggested_risk_chain']
        for row in evidence['nontechnology_review']['rows'] if row['boundary_status']=='DIRECT_BUSINESS_DEFINITION_MATCH'
        and row['business_evidence_supports_suggested_chain'] is True})
    documents,proposals,approved=_merge_addendum(documents,proposals,approved,
        extras['excerpts']['documents'],extras['suggestions']['suggestions'],extras['review']['results'])
    if (len(documents)!=83 or len(proposals)!=68 or len(approved)!=41
            or len({documents[key]['issuer_id'] for key in approved})!=40
            or sum(row['excerpt'] is None for row in documents.values())!=15):
        raise ValueError('Complete 83 documents / 68 parsed / 41 approved documents / 40 issuers required')
    dates,audit=previous._assemble(evidence['coverage']['dates'],documents,proposals,approved)
    verify()
    result=deepcopy(base)
    result.update(schema='ndx_conditional_business_mapping_research_v2',source_hashes=sources,dates=dates,audit=audit,
        direct_reviewed_documents=41,direct_reviewed_issuers=40,ready_document_count=68,
        retained_unsupported_documents=[row for row in documents.values() if row['excerpt'] is None],
        old_mapping_v1_modified=False,original_ready_60_document_sections_replaced=False)
    return result
