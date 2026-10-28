"""V27-only uncached byte digest; legacy shared gate remains unchanged.

Read-before/after identity, size and bounded-stream checks are preserved.
"""
from hashlib import sha256
import os
import stat
from core.strategy_account_ledger import require

MAXIMUM_SOURCE_BYTES=32*1024*1024

def _no_links(path):
    for item in (path,*path.parents):
        try:
            metadata=item.lstat()
        except FileNotFoundError:
            # Preserve the old missing-path behavior; _read_digest checks the file.
            continue
        require(not stat.S_ISLNK(metadata.st_mode) and not (getattr(metadata,'st_file_attributes',0)&0x400),
                'BOUNDED_SOURCE_LINK_REFUSED')

def _signature(stat):
    # Windows path stat and fstat disagree on ctime; compare identity/size/mtime.
    return stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns

def _read_digest(path,maximum):
    _no_links(path)
    require(path.is_file(),'BOUNDED_SOURCE_MISSING')
    before=path.stat();require(before.st_size<=maximum,'BOUNDED_SOURCE_TOO_LARGE')
    digest=sha256();total=0
    with path.open('rb') as stream:
        require(_signature(os.fstat(stream.fileno()))==_signature(before),'BOUNDED_SOURCE_READ_RACE')
        while True:
            block=stream.read(min(65536,maximum-total+1))
            if not block:break
            total+=len(block);require(total<=maximum,'BOUNDED_SOURCE_TOO_LARGE');digest.update(block)
        require(_signature(os.fstat(stream.fileno()))==_signature(before),'BOUNDED_SOURCE_READ_RACE')
    _no_links(path)
    require(total==before.st_size and _signature(path.stat())==_signature(before),'BOUNDED_SOURCE_READ_RACE')
    return digest.hexdigest()

