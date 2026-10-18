"""Manual business evidence suggestions; no classification registry mutation."""
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1/local_evidence_matrix.json'
MATRIX_SHA = '99d96c74803c3234f6564c8e5e2f76db03340b5e9f22c485783139396d372c58'
# Explicitly reviewed operative paragraphs; alternatives retain dictionary ambiguity.
REVIEW = {
    'AEP': ('energy_utilities', [], 'AEP was incorporated under the laws', 'Public utility holding company and electric generation, transmission and distribution subsidiaries.'),
    'CSX': ('industrial', [], 'CSX Corporation, together with its subsidiaries', 'Rail freight and intermodal logistics match industrial transport services.'),
    'AMGN': ('biotech_pharma', [], 'is a biotechnology company committed to unlocking', 'Discovery, development, manufacture and delivery of human therapeutics.'),
    'EA': ('media_communications', ['consumer'], 'Electronic Arts is a global leader in digital interactive entertainment.', 'Games and interactive content publishing; software implementation does not establish enterprise software exposure.'),
    'ATVI': ('media_communications', ['consumer'], 'Activision Blizzard, Inc. is a leading global developer', 'Interactive entertainment publisher; announced acquisition is not proof of completed identity continuity.'),
    'CTAS': ('industrial', ['other_explicit'], 'Cintas Corporation (Cintas, Company, we, us or our)', 'Uniform rental, facility and workplace safety services are business services; consumer apparel retail is not the described model.'),
    'PAYX': ('cloud_application_software', ['fintech_payments','other_explicit'], 'We are a leading human capital management', 'HCM software and HR services coexist with payroll, benefits and insurance; do not infer financial dominance solely from payroll.'),
    'ROST': ('consumer', [], 'operate two brands of off-price retail apparel', 'Off-price apparel and home fashion retail.'),
    'FAST': ('industrial', [], 'Fastenal Company (together with our subsidiaries', 'Industrial and construction supplies distributed primarily business to business.'),
    'REGN': ('biotech_pharma', [], 'Regeneron Pharmaceuticals, Inc. is a fully integrated biotechnology', 'Discovers, develops, manufactures and commercializes medicines.'),
    'IDXX': ('healthcare', ['other_explicit'], 'IDEXX was incorporated in Delaware in 1983.', 'Veterinary diagnostics dominate the described modalities; dictionary diagnostic scope includes no explicit species rule, while water testing remains a separate exposure.'),
    'BIIB': ('biotech_pharma', [], 'Biogen is a global biopharmaceutical company', 'Therapeutic discovery and medicines for neurological disease.'),
    'VRTX': ('biotech_pharma', [], 'We are a global biotechnology company that invests', 'Biotechnology medicines and clinical pipeline.'),
    'ODFL': ('industrial', [], 'We are one of the largest North American less-than-truckload', 'Freight carrier; paragraph explicitly states over 98 percent historical revenue from LTL transportation.'),
    'GILD': ('biotech_pharma', [], 'is a biopharmaceutical company that has pursued', 'Innovative medicines targeting HIV, hepatitis and cancer.'),
    'CPRT': ('internet_ecommerce', ['automotive','industrial'], 'We are a leading global provider of online auctions and vehicle remarketing', 'Online vehicle auctions and remarketing differ from vehicle manufacture; dictionary market-platform versus automotive-service boundary remains open.'),
    'SIRI': ('media_communications', [], 'We operate two complementary audio entertainment businesses', 'Audio entertainment businesses SiriusXM and Pandora.'),
    'DLTR': ('consumer', [], 'We are a leading operator of discount variety stores', 'Discount variety retail stores.'),
    'TTWO': ('media_communications', ['consumer'], 'We are a leading developer, publisher, and marketer of interactive entertainment', 'Interactive entertainment content publishing across consoles, PC and mobile.'),
    'ISRG': ('healthcare', [], 'Intuitive brings nearly three decades of experience', 'Robotic assisted surgical solutions address clinical care; robotics wording does not make this general industrial automation.'),
    'SGEN': ('biotech_pharma', [], 'Seagen is a biotechnology company that develops', 'Develops and commercializes cancer therapeutics.'),
    'EBAY': ('internet_ecommerce', ['fintech_payments','platform_advertising'], 'As a global commerce leader and third-party marketplace', 'Third-party marketplace with paid-sales, payment and advertising fees; market platform is explicit, single revenue dominance not independently quantified.'),
    'NFLX': ('media_communications', [], 'leading entertainment services with approximately 222 million', 'Subscription television, films and entertainment content.'),
    'BKNG': ('travel_hospitality', ['internet_ecommerce'], 'Our mission to make it easier for everyone to experience the world', 'Travel reservations are expressly within the travel dictionary, although delivered by online platforms.'),
    'DXCM': ('healthcare', [], 'We are a medical device company primarily focused', 'Continuous glucose monitoring medical devices.'),
    'CMCSA': ('media_communications', [], 'We are a global media and technology company with three primary businesses', 'Cable communications, NBCUniversal and Sky share the combined media/communications chain.'),
    'TMUS': ('media_communications', [], 'As of December 31, 2021, we provide wireless services', 'Wireless communications operator; not a wireless semiconductor vendor.'),
    'TSLA': ('automotive', ['energy_technology'], 'We design, develop, manufacture, sell and lease high-performance fully electric vehicles', 'Electric vehicles and energy generation/storage coexist; automotive dominance requires segment evidence and cannot be assumed from ticker.'),
    'LULU': ('consumer', [], 'lululemon athletica inc. is principally a designer', 'Athletic apparel and accessories design, distribution and retail.'),
    'KDP': ('consumer', [], 'Keurig Dr Pepper Inc. is a leading beverage company', 'Beverages and consumer brewing systems.'),
    'WBA': ('healthcare', ['consumer'], 'Walgreens Boots Alliance is the largest retail pharmacy', 'Retail pharmacy and daily living merchandise cross medical services and consumer retail; keep ambiguity explicit.'),
    'MRNA': ('biotech_pharma', [], 'Moderna is pioneering a new class of medicines', 'Messenger RNA medicines and vaccines, not computing software despite analogy in the filing.'),
    'GEHC': ('healthcare', [], 'is a leading global medical technology, pharmaceutical diagnostics', 'Medical imaging, ultrasound, patient care and diagnostics.'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build_report():
    raw = MATRIX.read_bytes()
    if sha(raw) != MATRIX_SHA:
        raise ValueError('Reviewed matrix changed')
    matrix = json.loads(raw)
    dictionary_path = ROOT / 'config/candidate_taxonomy_v2.yaml'
    dictionary_raw = dictionary_path.read_bytes()
    dictionary = yaml.safe_load(dictionary_raw)['risk_chains']
    sources = dict(matrix['source_hashes'])
    sources.update({str(MATRIX): MATRIX_SHA, str(dictionary_path): sha(dictionary_raw),
                    str(Path(__file__).resolve()): sha(Path(__file__).read_bytes())})
    def verify_sources():
        for path, expected in sources.items():
            if sha(Path(path).read_bytes()) != expected:
                raise ValueError('Source drift: ' + path)
    verify_sources()
    suggestions = []
    for document in matrix['documents']:
        ticker = document['tickers']
        if ticker not in REVIEW or document['excerpt'] is None:
            continue
        chain, alternatives, marker, rationale = REVIEW[ticker]
        if any(label not in dictionary for label in [chain] + alternatives):
            raise ValueError('Uncontrolled risk label')
        section = document['excerpt']['section_text']
        if sha(section.encode()) != document['excerpt']['section_text_sha256']:
            raise ValueError('Section digest differs')
        matches = [line for line in section.splitlines() if marker in line]
        if len(matches) != 1:
            raise ValueError('Unique operative paragraph required: ' + ticker)
        paragraph = matches[0]
        quote = ' '.join(paragraph.split()[:25])
        coordinates = []
        for cohort in matrix['dates']:
            linked = [row for row in cohort['rows'] if document['document_id'] in row['candidate_document_ids']]
            if linked:
                if any(row['issuer_id'] != document['issuer_id'] for row in linked) or document['source_available_date'] > cohort['decision_cutoff']:
                    raise ValueError('Issuer or existing metadata cutoff mismatch')
                coordinates.append(cohort['coordinate'])
        suggestions.append(dict(document_id=document['document_id'], issuer_id=document['issuer_id'],
            document_ticker_label=ticker, form=document['form'], source_available_date=document['source_available_date'],
            source_date_status='EXISTING_MANIFEST_METADATA_NOT_INDEPENDENTLY_REVERIFIED',
            raw_path=document['raw_path'], raw_sha256=document['raw_sha256'],
            section_sha256=document['excerpt']['section_text_sha256'], paragraph_marker=marker,
            paragraph_offset=section.index(paragraph), paragraph_characters=len(paragraph), paragraph_sha256=sha(paragraph.encode()),
            evidence_excerpt=quote, excerpt_sha256=sha(quote.encode()),
            suggested_risk_chain=chain, alternative_risk_chains=alternatives, rationale=rationale,
            ambiguity_status='DICTIONARY_BOUNDARY_REVIEW_REQUIRED' if alternatives else 'DIRECT_BUSINESS_MATCH_PENDING_INDEPENDENT_REVIEW',
            eligible_matrix_coordinates=coordinates, risk_chain_assigned=False, independently_approved=False,
            point_in_time_verified=False, classification_valid_interval_verified=False))
    if len(suggestions) != 33 or {r['document_ticker_label'] for r in suggestions} != set(REVIEW):
        raise ValueError('Expected all 33 remaining documents exactly once')
    verify_sources()
    return dict(schema='ndx_local_nontechnology_business_suggestions_v1', source_hashes=sources,
        reviewed_documents=33, suggestions=suggestions, full_section_every_sentence_reviewed=False,
        segment_revenue_dominance_verified=False, suggested_labels_automatically_usable=False,
        old_registry_modified=False, return_or_price_values_read=False, classification_based_on_returns=False,
        risk_chains_assigned=False, publication_times_independently_verified=False,
        point_in_time_verified=False, promotion_allowed=False)


if __name__ == '__main__':
    report = build_report()
    output = MATRIX.parent / 'nontechnology_business_suggestions_20260912.json'
    with output.open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(path=str(output), sha256=sha(output.read_bytes()), documents=33)))
