"""Source-bound manual research suggestions; never write the classification registry."""
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1/local_evidence_matrix.json'
MATRIX_SHA = '99d96c74803c3234f6564c8e5e2f76db03340b5e9f22c485783139396d372c58'
# Manually chosen from the bound business paragraphs, never from return data.
# Each marker locates an exact paragraph; the artifact preserves its hash and an excerpt.
REVIEW = {
 'AMD': ('diversified_technology', ['ai_accelerator','analog_power'], 'We are a global semiconductor company primarily offering:', 'CPU, GPU, embedded and semi-custom products coexist; the dated filing does not justify treating all exposure as AI acceleration.'),
 'KLAC': ('semiconductor_equipment', [], 'KLA Corporation and its majority-owned subsidiaries', 'Wafer, reticle, integrated-circuit process control and inspection equipment directly match this chain.'),
 'LRCX': ('semiconductor_equipment', [], 'We are a global supplier of innovative wafer fabrication equipment', 'Wafer fabrication equipment supplier; customer memory or foundry activity is not the issuer business model.'),
 'MU': ('memory', [], 'We are an industry leader in innovative memory', 'Explicit DRAM, NAND and NOR products support the memory chain.'),
 'ADSK': ('cloud_application_software', [], 'We are a global leader in 3D design', 'Engineering and creative application software; broad CAD use is not semiconductor EDA evidence.'),
 'MSFT': ('diversified_technology', ['cloud_application_software'], 'Our products include operating systems', 'Software, cloud, devices, games and advertising span chains; a software-only choice needs an independently fixed dominance convention.'),
 'FISV': ('fintech_payments', [], 'Fiserv, Inc. is a leading global provider of payments', 'Payment processing, financial technology and banking services explicitly match the financial chain; ticker continuity is a separate identity question.'),
 'MCHP': ('analog_power', [], 'We develop, manufacture and sell smart, connected and secure embedded control', 'Embedded control solutions directly fall under the controlled analog/power/embedded definition.'),
 'CSCO': ('network_optical', ['cybersecurity','diversified_technology'], 'Cisco designs and sells a broad range', 'Networking is explicit, but security, collaboration and applications also coexist; dominance is not certified by this excerpt.'),
 'INTU': ('fintech_payments', ['cloud_application_software'], 'Intuit helps consumers and small businesses prosper', 'Financial management, compliance and tax products match financial software; marketing is a material alternative exposure requiring review.'),
 'ANSS': ('cloud_application_software', ['eda_ip'], 'develops and globally markets engineering simulation software', 'General engineering simulation across industries supports application software; semiconductor-specific tools alone cannot establish issuer-wide EDA classification.'),
 'NVDA': ('ai_accelerator', [], 'NVIDIA pioneered accelerated computing', 'GPU architecture and accelerated computing explicitly span its dated platforms; this definition includes GPU products, not only AI revenue.'),
 'CTSH': ('other_explicit', ['cloud_application_software','diversified_technology'], 'Cognizant is one of the world', 'Explicit IT consulting, development, integration and outsourcing services; the dictionary has no dedicated IT-services chain, so do not silently equate consulting with subscription software.'),
 'ON': ('analog_power', ['automotive','energy_technology'], 'We provide intelligent power and intelligent sensing solutions', 'Power and sensing semiconductor solutions are the business; automotive and solar are end markets, not by themselves a substitute chain.'),
 'PANW': ('cybersecurity', [], 'Palo Alto Networks, Inc. is a global cybersecurity provider', 'Explicit cybersecurity provider; network security is not optical-network equipment.'),
 'WDAY': ('cloud_application_software', ['fintech_payments'], 'Workday is a leading provider of enterprise cloud applications', 'Enterprise cloud applications cover finance and human resources; finance functionality creates an overlap requiring a consistent rule.'),
 'SPLK': ('cloud_application_software', ['cybersecurity'], 'Splunk provides innovative solutions', 'Data-system software supports both observability and cybersecurity; do not infer single security dominance from a product use case.'),
 'CDW': ('diversified_technology', ['other_explicit'], 'a leading multi-brand provider of information technology', 'Multi-brand hardware, software, cloud and services distribution spans technology chains; reseller/service exposure is not identical to an original manufacturer.'),
 'NXPI': ('analog_power', ['wireless_semiconductor','diversified_technology'], 'We provide leading solutions that leverage our combined portfolio', 'Embedded, mixed-signal and power management coexist with RF and security; single-chain choice requires explicit portfolio-dominance review.'),
 'MDB': ('cloud_application_software', [], 'MongoDB is the developer data platform company', 'Database and related developer services directly support software/infrastructure classification.'),
 'CRWD': ('cybersecurity', [], 'Founded in 2011, CrowdStrike reinvented cybersecurity', 'Explicit threat detection and prevention platform; cloud delivery does not override security business purpose.'),
 'ZM': ('cloud_application_software', ['media_communications'], 'Zoom enables users to connect to others', 'Cloud-native communication application platform; communication-service overlap remains, without assuming a telecom network operator.'),
 'PYPL': ('fintech_payments', [], 'PayPal Holdings, Inc. was incorporated', 'Digital payments platform and merchant/consumer money movement directly match payments.'),
 'TTD': ('platform_advertising', [], 'offers a self-service, cloud-based ad-buying platform', 'Advertising campaigns and spend-linked platform fees identify ad technology rather than generic cloud software.'),
 'ZS': ('cybersecurity', [], 'We anticipate, secure, and simplify', 'Zero-trust platform secures users, data and applications; networking vocabulary does not imply optical equipment.'),
 'MRVL': ('diversified_technology', ['network_optical','analog_power'], 'is a leading supplier of infrastructure semiconductor solutions', 'Infrastructure SoCs combine analog, mixed-signal and digital functions across several markets; optical/network product evidence does not alone prove issuer-wide dominance.'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build_report():
    raw = MATRIX.read_bytes()
    if sha(raw) != MATRIX_SHA:
        raise ValueError('Matrix differs from reviewed hard-bound artifact')
    matrix = json.loads(raw)
    taxonomy_path = ROOT / 'config/candidate_taxonomy_v2.yaml'
    taxonomy_raw = taxonomy_path.read_bytes()
    taxonomy = yaml.safe_load(taxonomy_raw)
    sources = dict(matrix['source_hashes'])
    sources.update({str(MATRIX): MATRIX_SHA, str(taxonomy_path): sha(taxonomy_raw),
                    str(Path(__file__).resolve()): sha(Path(__file__).read_bytes())})
    for path, expected in sources.items():
        if sha(Path(path).read_bytes()) != expected:
            raise ValueError('Source closure drift: ' + path)
    documents = {row['document_id']: row for row in matrix['documents']}
    for cohort in matrix['dates']:
        for candidate in cohort['rows']:
            for identifier in candidate['candidate_document_ids']:
                document = documents[identifier]
                if (document['issuer_id'] != candidate['issuer_id'] or
                        document['source_available_date'] > cohort['decision_cutoff']):
                    raise ValueError('Matrix issuer/cutoff link invalid')
    suggestions = []
    for document in matrix['documents']:
        ticker = document['tickers']
        if ticker not in REVIEW or document['excerpt'] is None:
            continue
        chain, alternatives, marker, rationale = REVIEW[ticker]
        if any(key not in taxonomy['risk_chains'] for key in [chain] + alternatives):
            raise ValueError('Uncontrolled vocabulary')
        section = document['excerpt']['section_text']
        if sha(section.encode()) != document['excerpt']['section_text_sha256']:
            raise ValueError('Section content digest differs')
        matches = [line for line in section.splitlines() if marker in line]
        if len(matches) != 1:
            raise ValueError('Business paragraph locator not unique: ' + ticker)
        paragraph = matches[0]
        # AMD introductory sentence is immediately followed by the actual product list.
        if ticker == 'AMD':
            start = section.index(paragraph)
            paragraph = section[start:section.index('From time to time', start)].rstrip()
        offset = section.index(paragraph)
        quote = paragraph[:720]
        eligible = [cohort['coordinate'] for cohort in matrix['dates']
                    if any(document['document_id'] in row['candidate_document_ids'] for row in cohort['rows'])]
        suggestions.append(dict(document_id=document['document_id'], issuer_id=document['issuer_id'],
            document_ticker_label=ticker, form=document['form'], source_available_date=document['source_available_date'],
            source_date_status='EXISTING_MANIFEST_METADATA_NOT_INDEPENDENTLY_REVERIFIED',
            raw_path=document['raw_path'], raw_sha256=document['raw_sha256'],
            section_sha256=document['excerpt']['section_text_sha256'],
            paragraph_offset=offset, paragraph_characters=len(paragraph), paragraph_sha256=sha(paragraph.encode()),
            evidence_excerpt=quote, excerpt_sha256=sha(quote.encode()), excerpt_is_truncated=len(quote)<len(paragraph),
            suggested_risk_chain=chain, alternative_risk_chains=alternatives, rationale=rationale,
            ambiguity_status='PORTFOLIO_OR_DICTIONARY_BOUNDARY_REVIEW_REQUIRED' if alternatives else 'DIRECT_BUSINESS_MATCH_PENDING_INDEPENDENT_REVIEW',
            eligible_matrix_coordinates=eligible, risk_chain_assigned=False, independently_approved=False,
            point_in_time_verified=False, classification_valid_interval_verified=False))
    if len(suggestions) != 27 or set(row['document_ticker_label'] for row in suggestions) != set(REVIEW):
        raise ValueError('Expected 26 issuer labels / 27 documents, including both Lam filings')
    for path, expected in sources.items():
        if sha(Path(path).read_bytes()) != expected:
            raise ValueError('Source changed during review build')
    return dict(schema='ndx_local_technology_business_suggestions_v1', source_hashes=sources,
        source_document_denominator=83, source_ready_document_denominator=60,
        reviewed_issuer_labels=26, reviewed_documents=27, suggestions=suggestions,
        review_scope='MANUAL_OPERATIVE_BUSINESS_PARAGRAPHS_WITH_FULL_SECTION_CONTENT_BINDING',
        full_section_every_sentence_reviewed=False, segment_revenue_dominance_verified=False,
        matrix_all_15_dates_issuer_and_metadata_cutoff_links_verified=True,
        suggested_labels_automatically_usable=False, old_registry_modified=False,
        return_or_price_values_read=False, classification_based_on_returns=False,
        risk_chains_assigned=False, publication_times_independently_verified=False,
        point_in_time_verified=False, promotion_allowed=False)


if __name__ == '__main__':
    report = build_report()
    output = MATRIX.parent / 'technology_business_suggestions_20260912.json'
    with output.open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(path=str(output), sha256=sha(output.read_bytes()), documents=len(report['suggestions']))))
