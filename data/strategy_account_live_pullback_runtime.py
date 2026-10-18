"""Live V2 adapter fork: original capture controls bars; checked clock permits at most 1s vendor lead. Old research module remains frozen."""
"""Explicit experimental entry policy and lazy research-only cap storage.

Policy parameters are implementation hypotheses, not calibrated performance or
user-approved numerical preferences. Import and construction perform no writes.
"""
from pathlib import Path
from threading import RLock

from data.strategy_account_live_pullback_cap_store import PullbackCapStore


EXPERIMENTAL_POLICY = {
    'schema': 'V2_PULLBACK_EXECUTION_POLICY_V1',
    'status': 'EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED',
    'rebound_fraction': '1/2',
    'minimum_discount': '1/200',
    'maximum_age_seconds': 120,
}


class LazyPullbackCapStore:
    """Initialize separate research storage only on explicit quote generation."""

    def __init__(self, path, *, clock, max_history_rows, max_history_bytes):
        self.path = Path(path)
        self.clock = clock
        self.max_history_rows = max_history_rows
        self.max_history_bytes = max_history_bytes
        self._lock = RLock()
        self._store = None

    def candidate(self, **parameters):
        with self._lock:
            if self._store is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._store = PullbackCapStore(self.path, clock=self.clock,
                    max_history_rows=self.max_history_rows,
                    max_history_bytes=self.max_history_bytes)
            store = self._store
        return store.candidate(**parameters)
