"""Independent source/coordinate review; no automatic chain assignment."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    folder = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1'
    sources = {}
    def read(name, expected):
        path = folder / name
        raw = path.read_bytes()
        if sha(raw) != expected:
            raise ValueError('Hard-bound evidence differs')
        sources[str(path)] = expected
        return json.loads(raw)
    nontech = read('nontechnology_business_suggestions_20260912.json', '22f9cd5073989a41f59cfba159d562da95d69dad91e9c8f32a75c415dfefdcbc')
    tech = read('technology_business_suggestions_20260912.json', 'f3e0fa46fb0cd86a6fa0e49dcea7b6a05e873564c19e2db121c3dedbfb09b7eb')
    matrix = read('local_evidence_matrix.json', '99d96c74803c3234f6564c8e5e2f76db03340b5e9f22c485783139396d372c58')
    for evidence in (nontech, tech, matrix):
        for path, digest in evidence['source_hashes'].items():
            if path in sources and sources[path] != digest:
                raise ValueError('Conflicting evidence source')
            sources[path] = digest
    def verify():
        for path, digest in sources.items():
            if sha(Path(path).read_bytes()) != digest:
                raise ValueError('Source drift: ' + path)
    verify()
    documents = {row['document_id']:row for row in matrix['documents']}
    ready = {key for key, row in documents.items() if row['excerpt'] is not None}
    left = {row['document_id'] for row in nontech['suggestions']}
    right = {row['document_id'] for row in tech['suggestions']}
    if (len(nontech['suggestions']) != 33 or len(left) != 33 or len(right) != 27
            or left & right or left | right != ready or len(ready) != 60):
        raise ValueError('33 plus 27 must exactly partition 60 ready documents')
    reviewed = []
    for row in nontech['suggestions']:
        document = documents[row['document_id']]
        section = document['excerpt']['section_text']
        start = row['paragraph_offset']
        paragraph = section[start:start+row['paragraph_characters']]
        if (sha(paragraph.encode()) != row['paragraph_sha256'] or row['paragraph_marker'] not in paragraph
                or ' '.join(paragraph.split()[:25]) != row['evidence_excerpt']
                or sha(row['evidence_excerpt'].encode()) != row['excerpt_sha256']
                or row['issuer_id'] != document['issuer_id']
                or row['source_available_date'] != document['source_available_date']):
            raise ValueError('Paragraph or issuer/date binding differs')
        expected_coordinates = []
        for date in matrix['dates']:
            links = [candidate for candidate in date['rows'] if row['document_id'] in candidate['candidate_document_ids']]
            if links:
                if any(item['issuer_id'] != row['issuer_id'] for item in links) or row['source_available_date'] > date['decision_cutoff']:
                    raise ValueError('Historical metadata cutoff mismatch')
                expected_coordinates.append(date['coordinate'])
        if expected_coordinates != row['eligible_matrix_coordinates']:
            raise ValueError('Incomplete eligible coordinate set')
        alternatives = row['alternative_risk_chains']
        item = dict(document_id=row['document_id'], ticker=row['document_ticker_label'],
            business_evidence_supports_suggested_chain=True,
            boundary_status='UNRESOLVED_EXISTING_ALTERNATIVES' if alternatives else 'DIRECT_BUSINESS_DEFINITION_MATCH',
            automatic_adoption_allowed=False, historical_interval_verified=False, point_in_time_verified=False)
        if item['ticker'] == 'CMCSA':
            paragraph, = [line for line in section.splitlines() if line.startswith('We present our operations in five reportable business segments:')]
            item.update(boundary_status='UNRESOLVED_MISSING_THEME_PARK_ALTERNATIVES',
                additional_alternatives=['consumer','travel_hospitality'],
                reason='Theme Parks is an explicit reportable segment; NBCUniversal is not solely media content.',
                contrary_paragraph_offset=section.index(paragraph), contrary_paragraph_sha256=sha(paragraph.encode()),
                contrary_excerpt=paragraph[:650])
        reviewed.append(item)
    sources[str(Path(__file__).resolve())] = sha(Path(__file__).read_bytes())
    verify()
    report = dict(schema='ndx_nontechnology_business_independent_review_v1', source_hashes=sources,
        original_author='root', reviewer='identity_review', reviewed_documents=33,
        source_paragraph_and_metadata_coordinates_verified=True,
        technology_27_and_nontechnology_33_exact_ready_partition_verified=True,
        rows=reviewed, risk_chain_assignment_performed=False, original_suggestions_modified=False,
        multi_chain_decisions_approved=False, point_in_time_verified=False, promotion_allowed=False)
    output = folder / 'nontechnology_business_independent_review_20260912.json'
    with output.open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(path=str(output), sha256=sha(output.read_bytes()), sources=len(sources),
        direct=sum(row['boundary_status']=='DIRECT_BUSINESS_DEFINITION_MATCH' for row in reviewed))))


if __name__ == '__main__':
    main()
