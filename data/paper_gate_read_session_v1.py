"""One validation invocation only: bounded immutable bytes, final full rehash.

A candidate dependency for a future bundle loader; not a global Path patch,
not a replacement for registration semantics or dynamic account admission.
"""
from hashlib import sha256
from pathlib import Path
import os
from data.strategy_bounded_source_gate_v1 import _no_links, _signature, _read_digest


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


class PaperGateReadSessionV1:
    def __init__(self, root, *, maximum_total=128*1024*1024, maximum_file=32*1024*1024):
        self.root = Path(root).absolute()
        _no_links(self.root)
        self.maximum_total = maximum_total
        self.maximum_file = maximum_file
        self.cache = {}
        self.total = 0
        self.reads = 0
        self.reuses = 0
        self.closed = False

    def bind(self, name, expected):
        need(not self.closed, "READ_SESSION_CLOSED")
        candidate = Path(name)
        path = candidate if candidate.is_absolute() else self.root/candidate
        _no_links(path)
        path = path.resolve()
        need(path.is_relative_to(self.root.resolve()), "READ_SESSION_OUTSIDE_ROOT")
        need(type(expected) is str and len(expected) == 64 and
             all(c in "0123456789abcdef" for c in expected), "READ_SESSION_HASH_INVALID")
        key = os.path.normcase(str(path))
        if key in self.cache:
            prior_path, digest, raw = self.cache[key]
            need(digest == expected, "READ_SESSION_CONFLICT")
            self.reuses += 1
            return path, raw
        need(len(self.cache) < 2000, "READ_SESSION_FILE_BUDGET")
        before = path.stat()
        need(before.st_size <= self.maximum_file and
             self.total+before.st_size <= self.maximum_total, "READ_SESSION_BYTE_BUDGET")
        with path.open("rb") as stream:
            need(_signature(os.fstat(stream.fileno())) == _signature(before), "READ_SESSION_RACE")
            raw = stream.read(self.maximum_file+1)
            need(_signature(os.fstat(stream.fileno())) == _signature(before), "READ_SESSION_RACE")
        _no_links(path)
        need(len(raw) == before.st_size and _signature(path.stat()) == _signature(before), "READ_SESSION_RACE")
        need(sha256(raw).hexdigest() == expected, "READ_SESSION_CHANGED")
        self.cache[key] = (path, expected, raw)
        self.total += len(raw)
        self.reads += 1
        return path, raw

    def finish(self):
        need(not self.closed, "READ_SESSION_CLOSED")
        self.closed = True
        try:
            for path, digest, raw in self.cache.values():
                need(_read_digest(path, self.maximum_file) == digest, "READ_SESSION_FINAL_CHANGED")
            return dict(unique_files=self.reads, reused_binds=self.reuses,
                        full_byte_passes=2, total_bytes=self.total,
                        scope="ONE_VALIDATION_INVOCATION", registration_admitted=False)
        finally:
            self.cache.clear()

    def abort(self):
        self.closed = True
        self.cache.clear()
