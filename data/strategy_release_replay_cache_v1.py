"""Bounded pure-result cache; every hit revalidates full source bytes.

Not installed in production. Callers must include every non-file input in the
key and route every file dependency through ReadDependencies.read.
"""
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from threading import RLock

from core.strategy_account_ledger import require
from data.strategy_monthly_file_sized_v1 import MonthlyFileConfiguration


class ReadDependencies:
    def __init__(self):
        self.references = {}

    @staticmethod
    def checked_read(root, path, digest, limit):
        root = Path(root)
        target = root / path
        require(not any(item.is_symlink() or
            (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400)
            for item in (target, *target.parents)), 'REPLAY_DEPENDENCY_LINK_REFUSED')
        reader = MonthlyFileConfiguration(root=root, path=path,
            sha256_value=digest, clock=None)
        return reader._read(path, digest, limit)

    def read(self, root, path, digest, limit=32*1024*1024):
        # Preserve the lexical root: do not resolve away a later alias change.
        root = str(Path(root).absolute())
        key = (root, path, limit)
        prior = self.references.get(key)
        require(prior is None or prior == digest, 'REPLAY_DEPENDENCY_CONFLICT')
        value = self.checked_read(root, path, digest, limit)
        self.references[key] = digest
        require(len(self.references) <= 10000, 'REPLAY_DEPENDENCY_BUDGET')
        return value

    def verify(self):
        for (root, path, limit), digest in self.references.items():
            self.checked_read(root, path, digest, limit)


class VerifiedReplayCache:
    def __init__(self, capacity=2):
        require(type(capacity) is int and 0 < capacity <= 8, 'REPLAY_CACHE_CAPACITY')
        self.capacity = capacity
        self.entries = OrderedDict()
        self.lock = RLock()

    def resolve(self, key, compute):
        with self.lock:
            if key in self.entries:
                dependencies, result = self.entries.pop(key)
                # On verification failure discard the entry and propagate;
                # never return the cached value or retry using stale bytes.
                dependencies.verify()
                self.entries[key] = (dependencies, result)
                return deepcopy(result)
            dependencies = ReadDependencies()
            result = compute(dependencies)
            dependencies.verify()
            self.entries[key] = (dependencies, deepcopy(result))
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)
            return deepcopy(result)
