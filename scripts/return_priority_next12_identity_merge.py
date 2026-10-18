"""Merge conditional identity evidence without promoting it to PIT certification."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'tmp/next12_base_identity_review_20261014_v1.json'
SUPPLEMENTS = ['tmp/next12_identity_admission_20261014_v1/identity_admission.json',
               'tmp/next12_identity_admission_20261014_v1/additional_identity_admission.json']
OUTPUT = 'tmp/next12_merged_identity_review_20261014_v1.json'


def prepare():
    pins = {}
    def document(path):
        raw = (ROOT/path).read_bytes()
        pins[path] = hashlib.sha256(raw).hexdigest()
        value = json.loads(raw)
        for name, expected in value['source_hashes'].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
                raise ValueError('SOURCE_CHANGED:' + name)
            if name in pins and pins[name] != expected:
                raise ValueError('SOURCE_CONFLICT:' + name)
            pins[name] = expected
        return value

    base = document(BASE)
    replacements = {}
    for path in SUPPLEMENTS:
        for row in document(path)['rows']:
            key = (row['decision_date'], row['ticker'])
            if key in replacements or row['status'] != 'READY_CONDITIONAL_IDENTITY' or row.get('unresolved'):
                raise ValueError('AMBIGUOUS_OR_UNREVIEWED_SUPPLEMENT')
            replacements[key] = dict(row, review_document=path)
    consumed = set()
    for window in base['windows']:
        for index, row in enumerate(window['candidates']):
            key = (window['decision_date'], row['ticker'])
            if key not in replacements:
                continue
            new = replacements[key]
            if row['security_id'] is not None and row['security_id'] != new['security_id']:
                raise ValueError('UNRESOLVED_IDENTITY_CONFLICT:' + row['ticker'])
            window['candidates'][index] = new
            consumed.add(key)
        window['unresolved'] = [row['ticker'] for row in window['candidates'] if not row['security_id']]
        for row in window['candidates']:
            row.update(point_in_time_certified=False, coordinate_reviewed=False)
        sids = [row['security_id'] for row in window['candidates'] if row['security_id']]
        if len(sids) != len(set(sids)):
            raise ValueError('DUPLICATE_SECURITY_DOMAIN')
    if consumed != set(replacements):
        raise ValueError('SUPPLEMENT_OUTSIDE_DECLARED_MEMBER_WINDOWS')
    pins[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return dict(status='CONDITIONAL_IDENTITIES_COMPLETE_NOT_PIT_OR_PRICE_ADMISSION'
                if not any(w['unresolved'] for w in base['windows']) else 'UNRESOLVED_IDENTITIES_REMAIN',
                windows=base['windows'], source_hashes=pins, search_calls=0, book_calls=0,
                limitations=base['limitations'] + ['Supplement official quarterly lists have unverified publication timestamps; no backdated availability assertion.'])


if __name__ == '__main__':
    result = prepare()
    with (ROOT/OUTPUT).open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(result['status'])
    print([(w['decision_date'], w['unresolved']) for w in result['windows']])
