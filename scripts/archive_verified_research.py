"""Preserve a completed synthetic research run and its declared pinned sources."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--original-input', type=Path, required=True)
    parser.add_argument('--extra', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    run = options.run.resolve()
    summary = json.loads((run / 'summary.json').read_bytes())
    review = json.loads((run / 'independent_prefix_review.json').read_bytes())
    if summary['status'] != 'COMPLETE' or review['status'] != 'COMPLETE_DECLARED_INTERVAL_REVIEW_PASS':
        raise ValueError('COMPLETE_REVIEW_REQUIRED')
    inputs = json.loads((run / 'execution_inputs.json').read_bytes())
    if sha256(options.original_input.read_bytes()).hexdigest() != inputs['original_assembled_sha256']:
        raise ValueError('ORIGINAL_INPUT_CHANGED')
    files, pending = {}, []

    def add(path, expected=None):
        path = (ROOT / path).resolve()
        name = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        actual = sha256(raw).hexdigest()
        if expected is not None and actual != expected:
            raise ValueError('SOURCE_HASH_CHANGED:' + name)
        if name not in files:
            files[name] = dict(sha256=actual, bytes=len(raw))
            if path.suffix.lower() == '.json':
                pending.append(path)

    add(run / 'execution_inputs.json', summary['execution_inputs_sha256'])
    add(options.original_input)
    for path in run.iterdir():
        if path.is_file():
            if '.pending.' in path.name:
                raise ValueError('UNFINISHED_ATOMIC_WRITE')
            add(path)
    for path in options.extra:
        add(path)
    # Only explicit provenance maps are followed; never sweep unrelated files.
    while pending:
        document = json.loads(pending.pop().read_bytes())
        if not isinstance(document, dict):
            continue
        mappings = [document.get('source_hashes', {}), document.get('action_source_hashes', {})]
        if isinstance(document.get('assembled'), dict):
            mappings.append(document['assembled'].get('source_hashes', {}))
        for mapping in mappings:
            if isinstance(mapping, dict):
                for name, expected in mapping.items():
                    if isinstance(expected, str) and len(expected) == 64:
                        add(Path(name), expected)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    manifest = dict(status='VERIFIED_LOCAL_RESEARCH_ARCHIVE', git_commit=commit,
                    original_run=run.relative_to(ROOT).as_posix(), files=files,
                    scope='Synthetic research and explicitly pinned evidence only; no production account backup.',
                    restore='Extract under an empty repository checkout at git_commit; preserve relative paths. No files are deleted or moved by creation.')
    options.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(options.output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        archive.writestr('RESEARCH_ARCHIVE_MANIFEST.json', json.dumps(manifest, indent=2))
        for name in sorted(files):
            raw = (ROOT / name).read_bytes()
            if sha256(raw).hexdigest() != files[name]['sha256']:
                raise ValueError('SOURCE_CHANGED_DURING_ARCHIVE:' + name)
            archive.writestr(name, raw)
    with zipfile.ZipFile(options.output) as archive:
        for name, item in files.items():
            if sha256(archive.read(name)).hexdigest() != item['sha256']:
                raise ValueError('ARCHIVE_READBACK_MISMATCH:' + name)
    result = dict(status='ARCHIVE_READBACK_VERIFIED', path=str(options.output),
                  sha256=sha256(options.output.read_bytes()).hexdigest(), files=len(files),
                  uncompressed_bytes=sum(item['bytes'] for item in files.values()),
                  archive_bytes=options.output.stat().st_size, git_commit=commit)
    options.output.with_suffix('.manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
