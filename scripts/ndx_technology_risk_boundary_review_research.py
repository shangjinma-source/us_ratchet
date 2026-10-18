"""Author adversarial review of proposed labels; no independent approval."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECT = {'KLAC', 'LRCX', 'MU', 'ADSK', 'FISV', 'MCHP', 'NVDA', 'ON',
          'PANW', 'MDB', 'CRWD', 'PYPL', 'TTD', 'ZS'}
SPECIAL = {
 'AMD': ('server and embedded processors, semi-custom', 'DIVERSIFIED_LABEL_IS_PLAUSIBLE_NOT_APPROVED',
         'GPU, CPU and embedded products support multiple exposures. Do not assign all AMD to AI, or treat the acquisition described as pending in this dated filing as already completed.'),
 'MSFT': ('Our products include operating systems', 'DIVERSIFIED_VS_SOFTWARE_RULE_REQUIRED',
          'Operating systems and applications coexist with games and devices. Neither a generic software nor diversified bucket has an approved dominance rule.'),
 'MRVL': ('We serve these five end markets with a broad portfolio', 'INCOMPLETE_ALTERNATIVE_SET_IN_ORIGINAL_SUGGESTION',
          'Compute, networking, security, electro-optics AND storage are explicit. The original alternate list omitted memory despite the controlled definition including storage controllers. Alternatives are not a complete exposure partition.'),
 'CDW': ('We are vendor, technology and consumption model unbiased', 'DISTRIBUTOR_VS_PRODUCT_EXPOSURE_RULE_REQUIRED',
         'Multi-brand vendor products are distributed and integrated. Do not equate reseller economics with the chip/software manufacturers it sells; diversified is a candidate categorization, not a proven risk model.'),
 'CTSH': ('Cognizant is one of the world', 'IT_SERVICES_DICTIONARY_GAP',
          'Consulting, integration and business-process services are explicit; other_explicit is not a unique new issuer-specific chain and cannot serve as a hidden way around the common-chain concentration cap.'),
 'SPLK': ('Our solutions for cybersecurity', 'SECURITY_AND_OBSERVABILITY_COEXIST',
          'Both security and observability are explicit. A single cybersecurity or application-software assignment requires a fixed rule, not optimization against holdings or returns.'),
 'ANSS': ('Our power analysis and optimization software suite', 'ACTUAL_EDA_PRODUCT_EVIDENCE_CONFIRMED',
          'The dated filing explicitly discusses power analysis and optimization from electronic-design prototyping through system sign-off. EDA overlap is substantive, not only a semiconductor customer end market; broad engineering simulation also remains.'),
 'NXPI': ('We provide leading solutions that leverage our combined portfolio', 'MIXED_ANALOG_RF_EMBEDDED_PORTFOLIO',
          'RF, mixed-signal, power and embedded systems are explicit. Automotive sales alone do not resolve the semiconductor-chain boundary.'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    folder = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1'
    original_path = folder / 'technology_business_suggestions_20260912.json'
    original_raw = original_path.read_bytes()
    expected = 'f3e0fa46fb0cd86a6fa0e49dcea7b6a05e873564c19e2db121c3dedbfb09b7eb'
    if sha(original_raw) != expected:
        raise ValueError('Original sealed suggestions differ')
    original = json.loads(original_raw)
    sources = dict(original['source_hashes'])
    sources[str(original_path)] = expected
    sources[str(Path(__file__).resolve())] = sha(Path(__file__).read_bytes())
    matrix = json.loads((folder / 'local_evidence_matrix.json').read_bytes())
    documents = {row['document_id']: row for row in matrix['documents']}
    for path, digest in sources.items():
        if sha(Path(path).read_bytes()) != digest:
            raise ValueError('Source drift: ' + path)
    rows = []
    for proposal in original['suggestions']:
        ticker = proposal['document_ticker_label']
        row = dict(document_id=proposal['document_id'], document_ticker_label=ticker,
            original_suggested_chain=proposal['suggested_risk_chain'],
            status='DIRECT_PRODUCT_DEFINITION_MATCH_REVIEWABLE' if ticker in DIRECT else 'UNRESOLVED_RULE_OR_EXPOSURE_BOUNDARY',
            single_chain_business_definition_supported=ticker in DIRECT,
            automatic_adoption_allowed=False, independent_approval=False,
            historical_valid_interval_verified=False, point_in_time_verified=False)
        if ticker in SPECIAL:
            marker, issue, reason = SPECIAL[ticker]
            section = documents[proposal['document_id']]['excerpt']['section_text']
            matches = [line for line in section.splitlines() if marker in line]
            if len(matches) != 1:
                raise ValueError('Expected unique supporting paragraph: ' + ticker)
            paragraph = matches[0]
            row.update(issue=issue, reason=reason, additional_evidence=dict(
                paragraph_offset=section.index(paragraph), paragraph_characters=len(paragraph),
                paragraph_sha256=sha(paragraph.encode()), excerpt=paragraph[:900],
                excerpt_truncated=len(paragraph)>900))
        elif ticker == 'ON':
            row['reason'] = 'Power and sensing products match analog_power; automotive/solar are customer uses, so those alternatives do not themselves block product-definition classification.'
        elif ticker not in DIRECT:
            row['reason'] = 'Original multiple-chain alternatives remain unresolved; no automatic precedence rule exists in the controlled dictionary.'
        else:
            row['reason'] = 'Dated operative products directly match the controlled chain definition; source timing, issuer linkage and independent review remain separate requirements.'
        rows.append(row)
    report = dict(schema='ndx_technology_risk_boundary_author_review_v1', source_hashes=sources,
        reviewer_role='ORIGINAL_SUGGESTION_AUTHOR_ADVERSARIAL_SECOND_PASS_NOT_INDEPENDENT_APPROVAL',
        reviewed_documents=len(rows), direct_product_definition_issuer_count=len(DIRECT),
        direct_product_definition_document_count=sum(row['single_chain_business_definition_supported'] for row in rows),
        rows=rows, old_suggestions_modified=False, old_registry_modified=False,
        risk_chain_assignment_performed=False, returns_or_rankings_read=False,
        taxonomy_build_performed=False, point_in_time_verified=False, promotion_allowed=False)
    for path, digest in sources.items():
        if sha(Path(path).read_bytes()) != digest:
            raise ValueError('Source drift after review')
    output = folder / 'technology_risk_boundary_author_review_20260912.json'
    with output.open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(path=str(output), sha256=sha(output.read_bytes()), direct_issuers=len(DIRECT), documents=len(rows))))


if __name__ == '__main__':
    main()
