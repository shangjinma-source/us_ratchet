"""Read-only saved completion inventory and present-day source drift census."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research/base_window_snapshot_20260912_v1'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def build():
    rows, expected = [], {}
    for directory in sorted(p for p in BASE.iterdir() if p.is_dir() and p.name.isdigit()):
        candidates = sorted(directory.glob('index_*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        if not candidates:
            raise ValueError('Missing index: ' + str(directory))
        path = candidates[0]
        index = json.loads(path.read_bytes())
        manifest_path = Path(index['manifest']['path'])
        if digest(manifest_path) != index['manifest']['sha256']:
            raise ValueError('Manifest drift: ' + str(manifest_path))
        manifest = json.loads(manifest_path.read_bytes())
        final = index.get('finalization') or {}
        for source in (manifest.get('source_hashes', {}), final.get('source_hashes', {})):
            for name, sha in source.items():
                expected.setdefault(name, {}).setdefault(sha, set()).add(directory.name)
        rows.append(dict(date=directory.name, index_path=str(path), index_sha256=digest(path),
                         status=index['status'], planned=index['planned'], completed=len(index['completed']),
                         final_status=final.get('status'), final_completed=final.get('completed'),
                         declared_source_closure_verified=final.get('source_closure_verified'),
                         manifest=index['manifest'], typed_context=manifest['typed_context'],
                         existing_audits=[dict(path=str(p), sha256=digest(p)) for p in directory.glob('*audit*.json')]))
    drift, matched = [], 0
    for name, versions in sorted(expected.items()):
        path = Path(name)
        actual = digest(path) if path.is_file() else None
        if len(versions) == 1 and actual in versions:
            matched += 1
        else:
            drift.append(dict(path=name, observed_sha256=actual,
                              historical_expectations=[dict(sha256=k, dates=sorted(v)) for k, v in versions.items()]))
    typed = []
    for row in rows:
        ref = row['typed_context']
        actual = digest(Path(ref['path']))
        typed.append(dict(date=row['date'], **ref, observed_sha256=actual, matches=actual == ref['sha256']))
    return dict(schema='ndx_base_snapshot_present_source_inventory_v1', dates=rows,
                saved_completed=sum(r['completed'] for r in rows), planned=sum(r['planned'] for r in rows),
                distinct_source_paths=len(expected), matching_source_paths=matched, source_drift=drift,
                typed_context_checks=typed, current_full_closure_verified=not drift,
                no_fitter_or_evaluator_called=True, saved_status_is_current_validation=False,
                PIT=False, promotion_allowed=False)


if __name__ == '__main__':
    result = build()
    output = BASE / 'present_source_inventory_20260919.json'
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(path=str(output), sha256=digest(output), completed=result['saved_completed'],
                         sources=result['distinct_source_paths'], drift=len(result['source_drift']),
                         typed_all_match=all(r['matches'] for r in result['typed_context_checks']))))
