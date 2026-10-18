"""Independent root review of eight additional bounded business excerpts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1'
DIRECT = {'PEP','COST','MAR','MDLZ','KHC'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build():
    path = FOLDER / 'additional_eight_business_suggestions_20260912.json'
    expected = 'd5e0ffa51d5087d6f6f0dd8656c6bcb9a9d9a72102f791b93bd6b11fe335a28d'
    raw = path.read_bytes()
    if sha(raw) != expected:
        raise ValueError('Original suggestions changed')
    proposal = json.loads(raw)
    sources = dict(proposal['source_hashes']) | {str(path):expected,
        str(Path(__file__).resolve()):sha(Path(__file__).read_bytes())}
    for name, digest in sources.items():
        if sha(Path(name).read_bytes()) != digest:
            raise ValueError('Bound source drift')
    addendum = json.loads((FOLDER / 'punctuation_excerpt_addendum_20260912.json').read_bytes())
    documents = {d['document_id']:d for d in addendum['documents']}
    notes = {
        'PEP':'Beverages and convenient foods directly match consumer products.',
        'COST':'The paragraph explicitly identifies membership warehouses as the principal business; e-commerce distribution does not itself change the retail business definition.',
        'MAR':'Hotel operation, franchising and licensing directly match travel/hospitality.',
        'MDLZ':'The paragraph expressly says primarily snacks and describes branded food products.',
        'KHC':'Food and beverage brands and six consumer product platforms directly match consumer.',
        'PCAR':'Truck production/parts, finance and leasing, and industrial winch activities require consistent handling of ancillary segments.',
        'CHTR':'Broadband/cable and Spectrum Reach advertising are explicit; retain the proposed cross-chain boundary without assuming segment dominance.',
        'ALGN':'Primary medical devices, dental CAD/CAM software and consumer complementary products are explicit; retain conservative pending status until precedence is fixed.',
    }
    rows = []
    for row in proposal['suggestions']:
        document = documents[row['document_id']]
        section = document['excerpt']['section_text']
        paragraph = section[row['paragraph_offset']:row['paragraph_offset']+row['paragraph_characters']]
        if (sha(section.encode()) != row['section_sha256'] or sha(paragraph.encode()) != row['paragraph_sha256']
            or ' '.join(paragraph.split()[:25]) != row['evidence_excerpt']
            or document['issuer_id'] != row['issuer_id']):
            raise ValueError('Independent paragraph or identity reconstruction differs')
        ticker = row['document_ticker_label']
        rows.append(dict(document_id=row['document_id'],issuer_id=row['issuer_id'],ticker=ticker,
            suggested_chain=row['suggested_risk_chain'],paragraph_sha256=row['paragraph_sha256'],
            independent_business_definition_match=ticker in DIRECT,
            eligible_for_conditional_research_mapping=ticker in DIRECT,review_note=notes[ticker],
            classification_valid_interval_verified=False,point_in_time_verified=False))
    if len(rows)!=8 or {r['ticker'] for r in rows}!=set(notes):
        raise ValueError('Complete eight-document review required')
    return dict(schema='ndx_additional_business_independent_root_review_v1',source_hashes=sources,results=rows,
        reviewer_role='ROOT_INDEPENDENT_OF_SUGGESTION_AUTHOR',direct_business_match_documents=5,
        pending_boundary_documents=3,retained_unsupported_documents=15,
        original_mapping_modified=False,registry_modified=False,returns_or_prices_read=False,
        portfolio_risk_admission=False,point_in_time_verified=False,promotion_allowed=False)


if __name__ == '__main__':
    result = build()
    path = FOLDER / 'additional_business_independent_root_review_20260912.json'
    with path.open('x',encoding='utf8') as stream:
        json.dump(result,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(path=str(path),sha256=sha(path.read_bytes()))))
