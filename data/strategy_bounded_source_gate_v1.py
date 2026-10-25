"""Uncached full-byte source/config gate with bounded streaming reads.

Each call checks every approved file again. Only identical absolute paths within
that one call are deduplicated; accounts, targets, policy and signals are never cached.
"""
from hashlib import sha256
import os
from pathlib import Path,PurePosixPath
import re
from types import MappingProxyType
from core.strategy_account_ledger import require
from data.strategy_dynamic_source_gate import DYNAMIC_SOURCE_PATHS

MAXIMUM_SOURCE_BYTES=32*1024*1024

def _no_links(path):
    for item in (path,*path.parents):
        require(not item.is_symlink() and not (item.exists() and getattr(item.lstat(),'st_file_attributes',0)&0x400),'BOUNDED_SOURCE_LINK_REFUSED')

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

class BoundedSourceGateV1:
    def __init__(self,*,root,source_pins,configuration_pins=None):
        require(type(source_pins)is dict and DYNAMIC_SOURCE_PATHS<=set(source_pins),'BOUNDED_SOURCE_SCOPE')
        self.root=Path(root).absolute();self.executing=Path(__file__).absolute().parents[1]
        self.sources=MappingProxyType(dict(source_pins));self.configurations=MappingProxyType(dict(configuration_pins or {}))
        require(len(self.sources)+len(self.configurations)<=2000,'BOUNDED_SOURCE_COUNT')
        for pins in (self.sources,self.configurations):
            for name,digest in pins.items():
                require(type(name)is str and '\\' not in name and ':' not in name and not PurePosixPath(name).is_absolute() and all(p not in ('','.','..') for p in name.split('/')),'BOUNDED_SOURCE_PATH')
                require(type(digest)is str and re.fullmatch('[0-9a-f]{64}',digest),'BOUNDED_SOURCE_HASH')
        for name in self.sources.keys()&self.configurations.keys():require(self.sources[name]==self.configurations[name],'BOUNDED_SOURCE_CONFLICT')
        self()
    def require_scope(self,pins):
        require(type(pins)is dict and all(self.sources.get(name)==digest for name,digest in pins.items()),'BOUNDED_GATE_SCOPE_MISMATCH')
    def __call__(self):
        seen={}
        def check(path,digest,maximum):
            key=os.path.normcase(str(path))
            if key in seen:
                require(seen[key]==digest,'BOUNDED_SOURCE_CONFLICT');return
            require(_read_digest(path,maximum)==digest,'BOUNDED_SOURCE_CHANGED');seen[key]=digest
        for name,digest in self.sources.items():
            check(self.root/name,digest,MAXIMUM_SOURCE_BYTES)
            check(self.executing/name,digest,MAXIMUM_SOURCE_BYTES)
        for name,digest in self.configurations.items():check(self.root/name,digest,1024*1024)
