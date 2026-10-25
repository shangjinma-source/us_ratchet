"""Bounded, create-only upgrade evidence blobs; no selection or publication."""
from hashlib import sha256
import json
import os
from pathlib import Path
from core.strategy_account_ledger import canonical, require
from data.strategy_bounded_source_gate_v1 import _no_links

MAX_FILES = 2000
MAX_FILE_BYTES = 32*1024*1024
MAX_TOTAL_BYTES = 128*1024*1024
MAX_MANIFEST_BYTES = 2*1024*1024


def validate_files(files, hashes):
    require(type(files) is dict and type(hashes) is dict and
            0 < len(files) <= MAX_FILES and set(files) == set(hashes),
            'UPGRADE_SOURCE_DOMAIN')
    total = 0
    for name, raw in files.items():
        require(type(name) is str and 0 < len(name) <= 2048 and type(raw) is bytes
                and len(raw) <= MAX_FILE_BYTES, 'UPGRADE_SOURCE_FILE_BUDGET')
        total += len(raw)
        require(total <= MAX_TOTAL_BYTES, 'UPGRADE_SOURCE_TOTAL_BUDGET')
        require(sha256(raw).hexdigest() == hashes[name], 'UPGRADE_SOURCE_HASH')
    return total


def write_bytes(path, raw):
    _no_links(path)
    with path.open('xb') as stream:
        require(stream.write(raw) == len(raw), 'UPGRADE_STORAGE_SHORT_WRITE')
        stream.flush()
        os.fsync(stream.fileno())


def save_sources(directory, files, hashes):
    total = validate_files(files, hashes)
    directory = Path(directory)
    _no_links(directory)
    manifest = canonical(dict(schema='UPGRADE_SOURCE_BLOBS_V1',
        source_hashes=hashes, file_sizes={name: len(raw) for name, raw in files.items()},
        total_bytes=total))
    require(len(manifest) <= MAX_MANIFEST_BYTES, 'UPGRADE_MANIFEST_BUDGET')
    directory.mkdir(parents=True, exist_ok=False)
    blobs = directory/'blobs'
    blobs.mkdir()
    written = set()
    for name, raw in files.items():
        digest = hashes[name]
        if digest not in written:
            write_bytes(blobs/(digest+'.bin'), raw)
            written.add(digest)
    write_bytes(directory/'manifest.json', manifest)
    reference = dict(schema='UPGRADE_SOURCE_BLOB_REFERENCE_V1',
                     manifest_sha256=sha256(manifest).hexdigest())
    # No successful return based on memory; all persisted bytes are re-read.
    require(load_sources(directory, reference) == files, 'UPGRADE_SOURCE_READBACK')
    return reference


def load_sources(directory, reference):
    directory = Path(directory)
    _no_links(directory)
    require(type(reference) is dict and set(reference) == {'schema', 'manifest_sha256'}
            and reference['schema'] == 'UPGRADE_SOURCE_BLOB_REFERENCE_V1',
            'UPGRADE_BLOB_REFERENCE')
    path = directory/'manifest.json'
    _no_links(path)
    with path.open('rb') as stream:
        raw = stream.read(MAX_MANIFEST_BYTES+1)
    require(len(raw) <= MAX_MANIFEST_BYTES and sha256(raw).hexdigest() ==
            reference['manifest_sha256'], 'UPGRADE_MANIFEST_CHANGED')
    value = json.loads(raw)
    require(set(value) == {'schema', 'source_hashes', 'file_sizes', 'total_bytes'}
            and value['schema'] == 'UPGRADE_SOURCE_BLOBS_V1', 'UPGRADE_MANIFEST_SCHEMA')
    hashes, sizes = value['source_hashes'], value['file_sizes']
    require(type(hashes) is dict and type(sizes) is dict
            and 0 < len(hashes) <= MAX_FILES and set(hashes) == set(sizes),
            'UPGRADE_SOURCE_DOMAIN')
    require(all(type(size) is int and 0 <= size <= MAX_FILE_BYTES for size in sizes.values())
            and sum(sizes.values()) == value['total_bytes'] <= MAX_TOTAL_BYTES,
            'UPGRADE_SOURCE_TOTAL_BUDGET')
    files = {}
    for name, digest in hashes.items():
        require(type(digest) is str and len(digest) == 64 and
                all(c in '0123456789abcdef' for c in digest), 'UPGRADE_BLOB_HASH')
        path = directory/'blobs'/(digest+'.bin')
        _no_links(path)
        with path.open('rb') as stream:
            body = stream.read(sizes[name]+1)
        require(len(body) == sizes[name] and sha256(body).hexdigest() == digest,
                'UPGRADE_BLOB_CHANGED')
        files[name] = body
    validate_files(files, hashes)
    return files
