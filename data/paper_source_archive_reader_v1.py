"""Verify unregistered source archives without relying on original temp paths."""
import json
import re
from pathlib import Path, PurePosixPath
from hashlib import sha256
from core.strategy_account_ledger import require
from data.strategy_daily_session_capture import reject_links


def read_archive(directory, parent_sha256):
    require(type(parent_sha256) is str and re.fullmatch('[a-f0-9]{64}', parent_sha256), 'PAPER_ARCHIVE_ID')
    root = Path(directory).absolute()
    reject_links(root)
    folder = root / parent_sha256

    def read(path, maximum):
        reject_links(path)
        require(path.resolve().is_relative_to(root.resolve()) and path.stat().st_size <= maximum, 'PAPER_ARCHIVE_PATH_OR_SIZE')
        return path.read_bytes()

    raw = read(folder/'manifest.json', 1024*1024)
    manifest = json.loads(raw)
    complete = json.loads(read(folder/'complete.json', 4096))
    require(complete == dict(manifest_sha256=sha256(raw).hexdigest(), readback_verified=True), 'PAPER_ARCHIVE_INCOMPLETE')
    require(manifest['status'] == 'UNREGISTERED_SOURCE_ARCHIVE' and manifest['parent_sha256'] == parent_sha256
            and manifest['registration_created'] is False, 'PAPER_ARCHIVE_SCOPE')
    require(type(manifest['files']) is dict and 0 < len(manifest['files']) <= 2000, 'PAPER_ARCHIVE_DOMAIN')
    payload = {}; total = 0
    for name, digest in manifest['files'].items():
        require(type(name) is str and name and '\\' not in name and ':' not in name
                and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,
                'PAPER_ARCHIVE_LOGICAL_PATH')
        require(type(digest) is str and re.fullmatch('[a-f0-9]{64}', digest), 'PAPER_ARCHIVE_BLOB_ID')
        body = read(root/'blobs'/(digest+'.bin'), 32*1024*1024)
        total += len(body)
        require(total <= 64*1024*1024 and sha256(body).hexdigest() == digest, 'PAPER_ARCHIVE_BLOB_CHANGED')
        payload[name] = body
    parent_raw = payload['parent-receipt.json']
    require(sha256(parent_raw).hexdigest() == parent_sha256, 'PAPER_ARCHIVE_PARENT_CHANGED')
    parent = json.loads(parent_raw)
    config = json.loads(payload['configuration.json'])
    require(config['security_id'] == manifest['security_id'] and config.get('release_sha256') is None,
            'PAPER_ARCHIVE_SECURITY_OR_RELEASE')
    files = {name[len('source-root/'):]: body for name,body in payload.items() if name.startswith('source-root/')}
    require(set(files) == set(parent['source_sha256']), 'PAPER_ARCHIVE_SOURCE_DOMAIN')
    for name,digest in parent['source_sha256'].items():
        require(sha256(files[name]).hexdigest() == digest, 'PAPER_ARCHIVE_SOURCE_CHANGED')
    return dict(receipt_bytes=parent_raw, files=files, manifest=manifest,
                registration_created=False, source_admission_performed=False)
