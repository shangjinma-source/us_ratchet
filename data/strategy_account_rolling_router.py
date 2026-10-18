"""Operation-scoped dispatch over caller-approved immutable release snapshots.

This module does not approve or publish releases. The provider owns admission;
the existing router still validates archived evidence and runtime source pins.
No deployed composition uses this adapter until it is explicitly admitted.
"""
from contextlib import contextmanager
from functools import wraps
from types import MappingProxyType
import re

from core.strategy_account_ledger import require
from data.strategy_account_monthly_router import MonthlyRuntimeRouter
from data.strategy_account_archived_holding_charts import ArchivedHoldingCharts
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources


_BINDINGS = ('registry_path', 'registry_sha256', 'archive_path', 'archive_sha256')


def _snapshot(value):
    require(type(value) is dict and set(value) == set(_BINDINGS) | {'revision'},
            'ROLLING_SNAPSHOT_INVALID')
    require(all(type(value[key]) is str and value[key] for key in _BINDINGS),
            'ROLLING_SNAPSHOT_INVALID')
    require(type(value['revision']) is int and value['revision'] >= 0,
            'ROLLING_SNAPSHOT_REVISION_INVALID')
    for key in ('registry_path', 'archive_path'):
        CurrentQuantityV2CurrentCashSources._path(value[key])
    for key in ('registry_sha256', 'archive_sha256'):
        require(re.fullmatch(r'[0-9a-f]{64}', value[key]), 'ROLLING_SNAPSHOT_HASH_INVALID')
    # Scalars only: a detached read-only mapping cannot change mid-operation.
    return MappingProxyType(dict(value))


def _scoped(method):
    @wraps(method)
    def invoke(self, *args, **kwargs):
        with self.snapshot_operation():
            return method(self, *args, **kwargs)
    return invoke


class RollingMonthlyRuntimeRouter(MonthlyRuntimeRouter):
    def __init__(self, *, snapshot_provider, initial_snapshot, **kwargs):
        require(callable(snapshot_provider), 'ROLLING_SNAPSHOT_PROVIDER_REQUIRED')
        initial = _snapshot(initial_snapshot)
        require(not any(key in kwargs for key in _BINDINGS), 'ROLLING_DUPLICATE_BINDINGS')
        super().__init__(**kwargs, **{key: initial[key] for key in _BINDINGS})
        self._snapshot_provider = snapshot_provider
        self._active_snapshot = None
        self._loading_snapshot = False

    @contextmanager
    def snapshot_operation(self):
        """One provider read for the entire operation, including nested calls.

        Callers may wrap a compound read in this scope. Other threads serialize
        on the existing service lock; reentrant calls reuse the same snapshot.
        Provider errors never fall back to the initial or previous snapshot.
        """
        with self.lock:
            if self._active_snapshot is not None:
                yield self._active_snapshot
                return
            require(not self._loading_snapshot, 'ROLLING_PROVIDER_REENTRY')
            self._loading_snapshot = True
            try:
                snapshot = _snapshot(self._snapshot_provider())
            finally:
                self._loading_snapshot = False
            previous = {key: getattr(self, key) for key in _BINDINGS}
            self._active_snapshot = snapshot
            try:
                for key in _BINDINGS:
                    setattr(self, key, snapshot[key])
                yield snapshot
            finally:
                for key, value in previous.items():
                    setattr(self, key, value)
                self._active_snapshot = None

    current = _scoped(MonthlyRuntimeRouter.current)
    generate = _scoped(MonthlyRuntimeRouter.generate)
    preview = _scoped(MonthlyRuntimeRouter.preview)
    validate_current_target_pins = _scoped(MonthlyRuntimeRouter.validate_current_target_pins)
    resolve_identity = _scoped(MonthlyRuntimeRouter.resolve_identity)
    valuation = _scoped(MonthlyRuntimeRouter.valuation)
    _for_target = _scoped(MonthlyRuntimeRouter._for_target)
    _selection_configuration = _scoped(MonthlyRuntimeRouter._selection_configuration)


class RollingArchivedHoldingCharts(ArchivedHoldingCharts):
    def __init__(self, *, service, account_id, bootstrap_configuration=None, display_sources=None):
        require(isinstance(service, RollingMonthlyRuntimeRouter), 'ROLLING_CHART_SERVICE_REQUIRED')
        self.service = service
        super().__init__(root=service.root, account_store=service.accounts,
            account_id=account_id, target_store=service.targets,
            archive_path=service.archive_path, archive_sha256=service.archive_sha256,
            shared_lock=service.lock, bootstrap_configuration=bootstrap_configuration,
            display_sources=display_sources)

    def bars(self, **kwargs):
        with self.service.snapshot_operation() as snapshot:
            previous = self.archive_path, self.archive_sha256
            try:
                self.archive_path = snapshot['archive_path']
                self.archive_sha256 = snapshot['archive_sha256']
                return super().bars(**kwargs)
            finally:
                self.archive_path, self.archive_sha256 = previous
