"""Root independent semantic review of the author's source-bound suggestions."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECT = {'KLAC','LRCX','MU','ADSK','FISV','MCHP','NVDA','ON','PANW','MDB','CRWD','PYPL','TTD','ZS'}
PENDING = {
    'AMD': 'CPUs, GPUs and embedded processors coexist; diversified suggestion is plausible but does not quantify common-chain risk.',
    'MSFT': 'Cloud, applications, devices, gaming and advertising are explicit; issuer-wide single-chain dominance remains unadjudicated.',
    'CSCO': 'Networking, security and applications coexist; one broad opening paragraph does not establish exclusive networking exposure.',
    'INTU': 'Financial management and tax coexist with marketing products; financial software is explicit but cross-chain boundary remains.',
    'ANSS': 'The actual business section includes electronic-design power analysis and system sign-off; software-only versus EDA boundary remains.',
    'CTSH': 'Professional consulting and integration are explicit; neither enterprise software nor other_explicit is an automatic economic-risk assignment.',
    'WDAY': 'Enterprise cloud applications include financial software; dictionary precedence between purpose and delivery is unresolved.',
    'SPLK': 'Security and observability are both explicit product classes; no demonstrated single-chain dominance.',
    'CDW': 'Distribution and integrated services span hardware/software/security; no single manufacturer or cloud chain follows.',
    'NXPI': 'RF, mixed signal, embedded and power products coexist; original alternatives are not exhaustive certification.',
    'ZM': 'Communications applications overlap the dictionary communications-service category; needs a consistent precedence rule.',
    'MRVL': 'The full section explicitly lists storage controllers; add memory to the possible exposures, not an automatic assignment.',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build():
    folder = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1'
    source = folder / 'technology_business_suggestions_20260912.json'
    source_sha = 'f3e0fa46fb0cd86a6fa0e49dcea7b6a05e873564c19e2db121c3dedbfb09b7eb'
    raw = source.read_bytes()
    if sha(raw) != source_sha:
        raise ValueError('Original author artifact changed')
    original = json.loads(raw)
    matrix_path = folder / 'local_evidence_matrix.json'
    matrix = json.loads(matrix_path.read_bytes())
    sources = dict(original['source_hashes'])
    sources.update({str(source): source_sha, str(Path(__file__).resolve()): sha(Path(__file__).read_bytes())})
    for path, expected in sources.items():
        if sha(Path(path).read_bytes()) != expected:
            raise ValueError('Bound evidence drift')
    documents = {d['document_id']: d for d in matrix['documents']}
    results = []
    for row in original['suggestions']:
        document = documents[row['document_id']]
        section = document['excerpt']['section_text']
        paragraph = section[row['paragraph_offset']:row['paragraph_offset']+row['paragraph_characters']]
        if sha(section.encode()) != row['section_sha256'] or sha(paragraph.encode()) != row['paragraph_sha256']:
            raise ValueError('Independent exact paragraph reconstruction differs')
        if row['evidence_excerpt'] != paragraph[:720] or sha(row['evidence_excerpt'].encode()) != row['excerpt_sha256']:
            raise ValueError('Author excerpt differs from original paragraph')
        ticker = row['document_ticker_label']
        if ticker not in DIRECT | set(PENDING):
            raise ValueError('Unreviewed label')
        results.append(dict(document_id=row['document_id'], issuer_id=row['issuer_id'], ticker=ticker,
            suggested_chain=row['suggested_risk_chain'], paragraph_sha256=row['paragraph_sha256'],
            independent_business_definition_match=ticker in DIRECT,
            review_note=PENDING.get(ticker, 'Operative product description directly matches the existing dictionary; downstream industries or cloud delivery do not change this product-level match.'),
            eligible_for_conditional_research_mapping=ticker in DIRECT,
            automatic_registry_assignment_allowed=False, classification_interval_verified=False,
            publication_date_verified=False, point_in_time_verified=False))
    if len(results) != 27 or {r['ticker'] for r in results} != DIRECT | set(PENDING):
        raise ValueError('Complete 26 issuers / 27 documents required')
    return dict(schema='ndx_technology_business_independent_root_review_v1', source_hashes=sources,
        reviewer_role='ROOT_INDEPENDENT_OF_SUGGESTION_AUTHOR', results=results,
        direct_business_match_issuers=14, direct_business_match_documents=15,
        pending_boundary_issuers=12, mapping_registry_written=False, returns_or_prices_read=False,
        portfolio_risk_admission=False, point_in_time_verified=False, promotion_allowed=False)


if __name__ == '__main__':
    result = build()
    path = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1/technology_business_independent_root_review_20260912.json'
    with path.open('x', encoding='utf8') as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(path=str(path), sha256=sha(path.read_bytes()))))
