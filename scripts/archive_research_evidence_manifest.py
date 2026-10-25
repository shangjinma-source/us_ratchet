"""Archive explicitly listed research evidence without certifying its conclusions."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def archive_manifest(manifest_path, output):
    manifest_path = Path(manifest_path).resolve()
    output = Path(output).resolve()
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get('status') != 'RESEARCH_EVIDENCE_SNAPSHOT_NOT_VALIDATION':
        raise ValueError('EXPLICIT_EVIDENCE_ONLY_SCOPE_REQUIRED')
    entries = manifest.get('files')
    if not isinstance(entries, dict) or not entries:
        raise ValueError('NONEMPTY_EXPLICIT_FILE_MANIFEST_REQUIRED')
    validated = {}
    for name, expected in entries.items():
        path = (ROOT / name).resolve()
        relative = path.relative_to(ROOT).as_posix()
        if relative != name or path == output:
            raise ValueError('CANONICAL_REPOSITORY_PATH_REQUIRED:' + name)
        raw = path.read_bytes()
        if len(raw) != expected['bytes'] or sha256(raw).hexdigest() != expected['sha256']:
            raise ValueError('SOURCE_CHANGED:' + name)
        validated[name] = path
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation keeps earlier evidence snapshots immutable.
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        archive.writestr('EVIDENCE_MANIFEST.json', manifest_bytes)
        for name, path in sorted(validated.items()):
            raw = path.read_bytes()
            if sha256(raw).hexdigest() != entries[name]['sha256']:
                raise ValueError('SOURCE_CHANGED_DURING_ARCHIVE:' + name)
            archive.writestr(name, raw)
    with zipfile.ZipFile(output) as archive:
        if archive.read('EVIDENCE_MANIFEST.json') != manifest_bytes:
            raise ValueError('MANIFEST_READBACK_MISMATCH')
        for name, expected in entries.items():
            raw = archive.read(name)
            if len(raw) != expected['bytes'] or sha256(raw).hexdigest() != expected['sha256']:
                raise ValueError('EVIDENCE_READBACK_MISMATCH:' + name)
    result = dict(status='EVIDENCE_ARCHIVE_READBACK_VERIFIED_NOT_RESEARCH_VALIDATION',
                  archive=str(output), files=len(entries),
                  archive_bytes=output.stat().st_size,
                  sha256=sha256(output.read_bytes()).hexdigest(),
                  manifest_sha256=sha256(manifest_bytes).hexdigest())
    result_path = output.with_suffix('.readback.json')
    with result_path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    print(json.dumps(archive_manifest(options.manifest, options.output)))


if __name__ == '__main__':
    main()
