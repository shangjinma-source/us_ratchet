"""Eight dated business suggestions; retain all 15 unsupported documents."""
import hashlib
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1'
REVIEW = {
 'PCAR': ('automotive', ['industrial','other_explicit'], 'PACCAR is a multinational company operating in three principal industry segments:',
          'Commercial truck manufacturing and parts match automotive, but the filing also identifies finance/leasing and industrial winches; no unapproved dominant-segment threshold is imposed.'),
 'PEP': ('consumer', [], 'We were incorporated in Delaware in 1919',
         'Beverages and convenient foods are explicit branded consumer products.'),
 'COST': ('consumer', [], 'Costco Wholesale Corporation and its subsidiaries',
          'Membership warehouses retail goods; an own retail e-commerce sales channel does not by itself establish an independent marketplace-platform business.'),
 'MAR': ('travel_hospitality', [], 'We are a worldwide operator, franchisor, and licensor of hotel',
         'Hotel, residential and timeshare lodging brands are operated/franchised/licensed; the travel definition does not require owning hotel real estate.'),
 'CHTR': ('media_communications', ['platform_advertising'], 'We are a leading broadband connectivity company and cable operator',
          'Owned broadband/cable and voice/mobile services explicitly match communications. The same paragraph also describes Spectrum Reach advertising/production; preserve that overlap without assuming financial dominance.'),
 'ALGN': ('healthcare', ['consumer','cloud_application_software'], 'is a global medical device company primarily engaged',
          'Orthodontic devices, dental scanners and dental CAD/CAM are explicitly medical/dental purpose. Complementary consumer products and software are disclosed; any single-chain precedence requires independent review.'),
 'MDLZ': ('consumer', [], 'We make and sell primarily snacks',
          'Snack, cheese, grocery and powdered beverage products directly match consumer brands.'),
 'KHC': ('consumer', [], 'We are driving transformation at The Kraft Heinz Company',
         'The operating overview explicitly identifies food and beverage brands and consumer product platforms.'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build_report():
    path = FOLDER / 'punctuation_excerpt_addendum_20260912.json'
    raw = path.read_bytes()
    if sha(raw) != 'b67e8aa79b2615ac068065598eef9798734e578066e481b19eb8770d58f5588c':
        raise ValueError('Hard-bound addendum differs')
    addendum = json.loads(raw)
    matrix_path = FOLDER / 'local_evidence_matrix.json'
    matrix_raw = matrix_path.read_bytes()
    if sha(matrix_raw) != '99d96c74803c3234f6564c8e5e2f76db03340b5e9f22c485783139396d372c58':
        raise ValueError('Original matrix differs')
    matrix = json.loads(matrix_raw)
    dictionary_path = ROOT / 'config/candidate_taxonomy_v2.yaml'
    dictionary_raw = dictionary_path.read_bytes()
    vocabulary = yaml.safe_load(dictionary_raw)['risk_chains']
    sources = dict(addendum['source_hashes'])
    sources.update({str(path):sha(raw), str(matrix_path):sha(matrix_raw),
        str(dictionary_path):sha(dictionary_raw), str(Path(__file__).resolve()):sha(Path(__file__).read_bytes())})
    def verify():
        for source, expected in sources.items():
            if sha(Path(source).read_bytes()) != expected:
                raise ValueError('Source drift: ' + source)
    verify()
    suggestions = []
    unsupported = []
    for document in addendum['documents']:
        if document['excerpt'] is None:
            unsupported.append(document)
            continue
        ticker = document['tickers']
        chain, alternatives, marker, reason = REVIEW[ticker]
        if any(label not in vocabulary for label in [chain]+alternatives):
            raise ValueError('Uncontrolled vocabulary')
        section = document['excerpt']['section_text']
        if sha(section.encode()) != document['excerpt']['section_text_sha256']:
            raise ValueError('Section digest differs')
        matches = [line for line in section.splitlines() if marker in line]
        if len(matches) != 1:
            raise ValueError('Nonunique business paragraph: ' + ticker)
        paragraph = matches[0]
        if ticker == 'PCAR':
            offset = section.index(paragraph)
            paragraph = section[offset:section.index('\nTRUCKS', offset)]
        coordinates = []
        for date in matrix['dates']:
            links = [row for row in date['rows'] if document['document_id'] in row['candidate_document_ids']]
            if links:
                if any(row['issuer_id'] != document['issuer_id'] for row in links) or document['source_available_date'] > date['decision_cutoff']:
                    raise ValueError('Issuer/metadata date linkage differs')
                coordinates.append(date['coordinate'])
        excerpt = ' '.join(paragraph.split()[:25])
        suggestions.append(dict(document_id=document['document_id'],issuer_id=document['issuer_id'],
            document_ticker_label=ticker,source_available_date=document['source_available_date'],
            raw_path=document['raw_path'],raw_sha256=document['raw_sha256'],
            section_sha256=document['excerpt']['section_text_sha256'],paragraph_offset=section.index(paragraph),
            paragraph_characters=len(paragraph),paragraph_sha256=sha(paragraph.encode()),
            evidence_excerpt=excerpt,excerpt_sha256=sha(excerpt.encode()),suggested_risk_chain=chain,
            alternative_risk_chains=alternatives,rationale=reason,eligible_matrix_coordinates=coordinates,
            ambiguity_status='DICTIONARY_BOUNDARY_REVIEW_REQUIRED' if alternatives else 'DIRECT_BUSINESS_MATCH_PENDING_INDEPENDENT_REVIEW',
            independent_review_approved=False,risk_chain_assigned=False,point_in_time_verified=False,
            classification_valid_interval_verified=False))
    if len(suggestions)!=8 or len(unsupported)!=15 or {row['document_ticker_label'] for row in suggestions}!=set(REVIEW):
        raise ValueError('Complete eight suggestions plus fifteen unsupported required')
    verify()
    return dict(schema='ndx_additional_eight_business_suggestions_v1',source_hashes=sources,suggestions=suggestions,
        unsupported_documents=unsupported,reviewed_documents=8,retained_unsupported_documents=15,
        original_ready_document_count=60,total_ready_document_count=68,original_matrix_document_denominator=83,
        old_matrix_modified=False,old_mapping_v1_modified=False,old_registry_modified=False,
        full_section_every_sentence_reviewed=False,classification_based_on_returns=False,
        source_date_status='EXISTING_MANIFEST_METADATA_NOT_INDEPENDENTLY_REVERIFIED',
        risk_chain_assignment_performed=False,point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    report=build_report()
    output=FOLDER/'additional_eight_business_suggestions_20260912.json'
    with output.open('x',encoding='utf8') as stream:
        json.dump(report,stream,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(path=str(output),sha256=sha(output.read_bytes()),reviewed=8,unsupported=15)))
