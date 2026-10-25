"""Copy hash-verified daily archives into an isolated, create-only source root.

Logical evidence names are preserved byte-for-byte. This does not approve a
policy, register an account, fetch data, or change production evidence.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath

from core.strategy_account_ledger import canonical, require
from data.strategy_daily_session_capture import pinned, reject_links
from data.strategy_verified_context_monthly_normalizer_v1 import derive_identity_binding


def prepare(*, root, terminal_reference, output):
    root = Path(root).absolute()
    reject_links(root)
    directory = root / output
    reject_links(directory)
    require(directory.resolve().is_relative_to(root.resolve()) and
            directory.resolve() != root.resolve() and not directory.exists(),
            'PAPER_PARENT_OUTPUT_MUST_BE_NEW')
    terminal_raw = pinned(root, terminal_reference)
    terminal = json.loads(terminal_raw)
    require(terminal.get('status') == 'DYNAMIC_DOMAIN_PACKET_SAVED' and
            terminal.get('packets'), 'PAPER_PARENT_TERMINAL_REQUIRED')
    files = {}
    parents = {}

    def include(name, raw):
        require(isinstance(name, str) and '\\' not in name and ':' not in name and
                not PurePosixPath(name).is_absolute() and
                all(part not in ('', '.', '..') for part in name.split('/')),
                'PAPER_PARENT_LOGICAL_PATH')
        require(name not in files or files[name] == raw, 'PAPER_PARENT_SOURCE_CONFLICT')
        files[name] = raw
        require(len(files) <= 20000 and sum(map(len, files.values())) <= 256*1024*1024,
                'PAPER_PARENT_SOURCE_BUDGET')

    for sid, packet in sorted(terminal['packets'].items()):
        raw = pinned(root, packet['receipt_reference'])
        receipt = json.loads(raw)
        manifest = json.loads(pinned(root, packet['manifest_reference']))
        require(receipt.get('schema') == 'SERVER_REVIEWED_DAILY_EVIDENCE_V1' and
                receipt.get('normalization_reviewed') is True and
                receipt.get('unresolved_units') == [] and receipt.get('pending_rights') == [] and
                receipt['execution_session']['date'] == terminal['session'],
                'PAPER_PARENT_REVIEW_REQUIRED')
        require(set(manifest) == set(receipt['source_sha256']), 'PAPER_PARENT_SOURCE_DOMAIN')
        closure = {}
        for name, reference in manifest.items():
            require(reference['sha256'] == receipt['source_sha256'][name], 'PAPER_PARENT_MANIFEST_HASH')
            closure[name] = pinned(root, reference)
            include(name, closure[name])
        inputs = json.loads(closure[receipt['normalized_inputs_path']])
        require(set(inputs['histories']) == {sid}, 'PAPER_PARENT_SECURITY_DOMAIN')
        name = 'paper-parent-inputs/' + sha256(raw).hexdigest() + '.json'
        include(name, raw)
        parents[sid] = dict(path=name, sha256=sha256(raw).hexdigest())

    # All input bytes and collisions are checked before any output is created.
    directory.mkdir(parents=True, exist_ok=False)
    try:
        for name, raw in sorted(files.items()):
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            reject_links(path)
            with path.open('xb') as stream:
                stream.write(raw)
            require(path.read_bytes() == raw, 'PAPER_PARENT_COPY_READBACK')
        identities = {}
        for sid, reference in parents.items():
            raw = derive_identity_binding(root=directory, parent_reference=reference, security_id=sid)
            name = 'paper-parent-identities/' + sha256(raw).hexdigest() + '.json'
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(raw)
            identities[sid] = dict(path=name, sha256=sha256(raw).hexdigest())
        result = dict(status='PAPER_PARENT_WORKSPACE_PREPARED_NOT_REGISTERED',
            original_terminal=terminal_reference, session=terminal['session'],
            parents=parents, identities=identities, source_files=len(files),
            account_mutated=False, scheduler_changed=False, policy_approved=False)
        with (directory/'preparation.json').open('xb') as stream:
            stream.write(canonical(result))
        return result
    except BaseException:
        with (directory/'failed.json').open('xb') as stream:
            stream.write(canonical(dict(status='FAILED_PRESERVED_NOT_REGISTERED')))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--terminal', required=True)
    parser.add_argument('--terminal-sha256', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(root=args.root, output=args.output,
        terminal_reference=dict(path=args.terminal, sha256=args.terminal_sha256))))
