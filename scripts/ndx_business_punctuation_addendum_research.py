"""Create-only addendum for previously unsupported 10-K punctuation layouts."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.ndx_business_heading_punctuation_research import extract_business_heading_punctuation, LOADED_SOURCES


def build():
    matrix_path = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1/local_evidence_matrix.json'
    expected = '99d96c74803c3234f6564c8e5e2f76db03340b5e9f22c485783139396d372c58'
    raw = matrix_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Original full matrix changed')
    matrix = json.loads(raw)
    sources = dict(matrix['source_hashes']) | LOADED_SOURCES | {
        str(matrix_path): expected,
        str(Path(__file__).resolve()): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    def verify():
        for path, expected_sha in sources.items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected_sha:
                raise ValueError('Original evidence drift')
    verify()
    documents = []
    for document in matrix['documents']:
        if document['excerpt'] is not None:
            continue
        row = {key: value for key, value in document.items() if key != 'excerpt'}
        row['excerpt'] = None
        if document['form'] != '10-K':
            row['status'] = 'UNSUPPORTED_20F_LAYOUT'
        else:
            try:
                row['excerpt'] = extract_business_heading_punctuation(Path(document['raw_path']).read_bytes())
                row['status'] = 'PUNCTUATION_EXCERPT_READY_FOR_REVIEW'
            except ValueError as error:
                row['status'] = 'UNSUPPORTED_LAYOUT_RETAINED'
                row['reason'] = str(error)
        documents.append(row)
    ready = [r for r in documents if r['excerpt'] is not None]
    if len(documents) != 23 or {r['tickers'] for r in ready} != {'PCAR','PEP','COST','MAR','CHTR','ALGN','MDLZ','KHC'}:
        raise ValueError('Exact previously unsupported/additional denominators changed')
    verify()
    return dict(schema='ndx_business_punctuation_addendum_v1', source_hashes=sources,
        source_document_count=83, original_ready_count=60, additional_ready_count=8,
        remaining_unsupported_count=15, documents=documents,
        source_date_status='EXISTING_MANIFEST_METADATA_NOT_INDEPENDENTLY_REVERIFIED',
        old_matrix_modified=False, risk_chains_assigned=False, point_in_time_verified=False, promotion_allowed=False)


if __name__ == '__main__':
    result = build()
    output = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1/punctuation_excerpt_addendum_20260912.json'
    with output.open('x', encoding='utf8') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(path=str(output), sha256=hashlib.sha256(output.read_bytes()).hexdigest())))
