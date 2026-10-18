"""Review existing dated identities; retain unresolved rows, no market/search IO."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'tmp/next12_candidate_source_manifest_20261014_v1.json'
BRIDGES = 'tmp/next12_identity_action_review_20261014_v1.json'
HON = 'tmp/next12_primary_capture_20261014_v1/hon_distribution.response.bin'
OUTPUT = 'tmp/next12_base_identity_review_20261014_v1.json'


def prepare():
    pins = {}

    def read(path, expected=None):
        raw = (ROOT / path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('SOURCE_CHANGED:' + path)
        pins[path] = digest
        return raw

    manifest = json.loads(read(MANIFEST))
    bridges = json.loads(read(BRIDGES))
    for document in (manifest, bridges):
        for path, digest in document['source_hashes'].items():
            read(path, digest)
    hon_raw = read(HON).decode('utf-8', errors='replace')
    if '438516205' not in hon_raw:
        raise ValueError('HON_SUCCESSOR_PRIMARY_IDENTIFIER_MISSING')
    overrides = {row['ticker']: row for row in bridges['identity_bridges']}
    windows = []
    for window in manifest['windows']:
        decision = window['decision_date']
        rows = []
        for candidate in window['candidates']:
            ticker = candidate['ticker']
            available = [row for row in candidate['identity_candidates']
                         if row['identity_status'] == 'resolved' and row['available_from'] <= decision]
            unique = {(row['security_id'], row['issuer_id']) for row in available}
            sid, issuer = next(iter(unique)) if len(unique) == 1 else (None, None)
            references = [MANIFEST]
            basis = 'UNIQUE_EXISTING_DATED_REGISTRY_CONDITIONAL_CONTINUITY'
            limitation = 'Registry availability precedes cutoff; later corporate changes still require explicit lifecycle review.'
            if ticker in overrides:
                bridge = overrides[ticker]
                sid = bridge['sid']
                issuer = 'issuer:' + sid.split(':')[1]
                references = [BRIDGES]
                basis = bridge['status']
                limitation = bridge['gap']
            if ticker == 'HON' and decision >= '2026-06-29':
                sid, issuer = 'security:0000773840:438516205', 'issuer:0000773840'
                references = [BRIDGES, HON]
                basis = 'OFFICIAL_POST_REVERSE_SPLIT_PARENT_IDENTITY'
                limitation = 'New parent units require separate compound-action execution and nominal-price restoration.'
            rows.append(dict(ticker=ticker, decision_date=decision, security_id=sid, issuer_id=issuer,
                             status='REVIEWED_CONDITIONAL_BASE_IDENTITY' if sid else 'REQUIRES_ADDITIONAL_DATED_IDENTITY',
                             basis=basis, source_references=references, limitation=limitation,
                             point_in_time_certified=False, coordinate_reviewed=False))
        windows.append(dict(decision_date=decision, candidates=rows,
                            unresolved=[row['ticker'] for row in rows if row['security_id'] is None]))
    pins[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return dict(status='BASE_IDENTITIES_REVIEWED_WITH_EXPLICIT_GAPS_NOT_SEARCH_ADMISSION', windows=windows,
                source_hashes=pins, search_calls=0, book_calls=0,
                limitations=['FER uses a conditional same-issuer/class bridge; later CUSIP evidence is not claimed known earlier.',
                             'Seven new member identities and other registry-date gaps require a separately pinned supplement.',
                             'A unique registry entry does not certify absence of later identity actions.'])


if __name__ == '__main__':
    result = prepare()
    with (ROOT / OUTPUT).open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps([dict(date=w['decision_date'], unresolved=w['unresolved']) for w in result['windows']]))
