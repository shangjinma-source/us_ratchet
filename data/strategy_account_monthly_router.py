"""Server-owned monthly runtime dispatch; not wired into production routes.

One router owns one account/target pair. Publication changes affect explicit
selection only; quotes bind to the saved target's archived configuration.

Deployment is pending: router/archive/release executing source pins must join
the reviewed admission scope, and chart/identity API adapters need explicit
wiring. The existing build_runtime pin set alone does not certify this router.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
from zoneinfo import ZoneInfo
import re

from core.strategy_account_ledger import canonical, require
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_account_runtime import ScopedAccountStore, build_runtime, RUNTIME_PATHS
from data.strategy_account_monthly_release import resolve_monthly_runtime, validate_account_identity_coverage
from data.strategy_account_runtime_archive import configuration_for_target, require_archived_configuration
from data.strategy_account_identity import PinnedStrategyIdentity


class MonthlyRuntimeRouter:
    def __init__(self, *, root, registry_path, registry_sha256, archive_path,
                 archive_sha256, clock=None, runtime_builder=build_runtime, identity_configuration=None, migration_control=None):
        self.root = Path(root).resolve()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.registry_path, self.registry_sha256 = registry_path, registry_sha256
        self.archive_path, self.archive_sha256 = archive_path, archive_sha256
        self._builder = runtime_builder
        self._identity_configuration = deepcopy(identity_configuration)
        self._migration_control = deepcopy(migration_control)
        if self._migration_control is not None:
            control = self._migration_control
            require(type(control) is dict and set(control) ==
                    {'purpose','target_month','configuration','allowed_reasons'}
                    and control['purpose'] == 'MIGRATION_CONTROL', 'INVALID_MIGRATION_CONTROL')
            require(type(control['target_month']) is str
                    and re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',control['target_month']),
                    'INVALID_MIGRATION_MONTH')
            require(type(control['configuration']) is dict
                    and control['configuration'].get('target_month') == control['target_month'],
                    'MIGRATION_CONFIGURATION_MONTH_MISMATCH')
            require(control['allowed_reasons'] == ['INITIAL','EXPLICIT_RECONFIGURE'],
                    'INVALID_MIGRATION_REASONS')
        storage = self.root/'data'/'strategy_account'
        self.accounts = ScopedAccountStore(storage/'real_strategy.sqlite3', clock=self.clock)
        self.targets = StrategyMonthlyTargetStore(storage/'monthly_targets.sqlite3')
        self.lock = RLock()
        self._runtimes = {}

    def _month(self):
        now = self.clock()
        require(isinstance(now, datetime) and now.utcoffset() is not None, 'AWARE_SERVER_CLOCK_REQUIRED')
        return now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')

    def current(self):
        with self.lock:
            return self.targets.current()

    def _runtime(self, configuration):
        key = sha256(canonical(configuration)).hexdigest()
        if key not in self._runtimes:
            require(len(self._runtimes) < 100, 'RUNTIME_CACHE_BUDGET')
            runtime = self._builder(root=self.root, configuration=deepcopy(configuration), clock=self.clock)
            require(runtime.accounts.path.resolve() == self.accounts.path.resolve()
                    and runtime.targets.path.resolve() == self.targets.path.resolve(), 'RUNTIME_STORAGE_MISMATCH')
            runtime.accounts = self.accounts
            runtime.selection.store = self.accounts
            runtime.targets = self.targets
            runtime.lock = self.lock
            runtime.selection.lock = self.lock
            self._runtimes[key] = runtime
        runtime = self._runtimes[key]
        runtime.selection._pins()
        executing_root = Path(__file__).resolve().parents[1]
        for path in RUNTIME_PATHS:
            require(sha256((executing_root/path).read_bytes()).hexdigest()
                    == configuration['runtime_pins'][path], 'EXECUTING_COMPOSITION_SOURCE_CHANGED')
        return runtime

    def _for_target(self, target):
        configuration = configuration_for_target(root=self.root, archive_path=self.archive_path,
            archive_sha256=self.archive_sha256, target=target)
        return self._runtime(configuration), configuration

    def _selection_configuration(self, state, reason):
        control = self._migration_control
        if (control is not None and self._month() == control['target_month']
                and reason in control['allowed_reasons']):
            configuration = deepcopy(control['configuration'])
            require_archived_configuration(root=self.root,archive_path=self.archive_path,
                archive_sha256=self.archive_sha256,configuration=configuration)
            closed = datetime.fromisoformat(configuration['training_closed_at'])
            require(closed.utcoffset() is not None and closed <= self.clock(),
                    'MIGRATION_TRAINING_NOT_CLOSED')
            if state is not None:
                validate_account_identity_coverage(self.root,configuration,state)
            return configuration
        return resolve_monthly_runtime(root=self.root,registry_path=self.registry_path,
            registry_sha256=self.registry_sha256,clock=self.clock,account_state=state)

    def generate(self, *, event_id, reason, expected_revision, previous_target_id):
        require(type(event_id) is str and 0 < len(event_id) <= 128, 'TARGET_EVENT_ID_REQUIRED')
        require(reason in {'INITIAL','MONTHLY_SELECTION','EXPLICIT_RECONFIGURE'}, 'EXPLICIT_GENERATION_REASON_REQUIRED')
        request = dict(event_id=event_id, reason=reason, expected_revision=expected_revision,
                       previous_target_id=previous_target_id)
        with self.lock:
            old = self.targets.operation(event_id)
            if old:
                require(old['payload']['request'] == request, 'TARGET_EVENT_CONFLICT')
                return old
            prior = self.targets.current()
            require(previous_target_id == (prior['target_id'] if prior else None), 'STALE_TARGET')
            state = self.accounts.read()
            require(state is not None and state['revision'] == expected_revision, 'STALE_REVISION')
            configuration = self._selection_configuration(state, reason)
            require_archived_configuration(root=self.root, archive_path=self.archive_path,
                archive_sha256=self.archive_sha256, configuration=configuration)
            return self._runtime(configuration).generate(**request)

    def preview(self):
        with self.lock:
            target = self.targets.current()
            require(target is not None, 'NO_MONTHLY_TARGET')
            require(target['payload']['target_month'] == self._month(), 'MONTHLY_TARGET_REQUIRED')
            runtime, configuration = self._for_target(target)
            state = self.accounts.read()
            require(state is not None, 'ACCOUNT_NOT_INITIALIZED')
            validate_account_identity_coverage(self.root, configuration, state)
            return runtime.preview()

    def validate_current_target_pins(self):
        with self.lock:
            target = self.targets.current()
            require(target is not None, 'NO_MONTHLY_TARGET')
            runtime, _ = self._for_target(target)
            runtime.selection._pins()

    def resolve_identity(self, ticker):
        """Resolve a recorded ticker using server-approved identity evidence only."""
        with self.lock:
            target = self.targets.current()
            state = self.accounts.read()
            if target is None:
                if self._identity_configuration is None:
                    configuration = resolve_monthly_runtime(root=self.root, registry_path=self.registry_path,
                        registry_sha256=self.registry_sha256, clock=self.clock, account_state=state)
                else:
                    configuration = deepcopy(self._identity_configuration)
                    if state is not None:
                        validate_account_identity_coverage(self.root, configuration, state)
                require_archived_configuration(root=self.root, archive_path=self.archive_path,
                    archive_sha256=self.archive_sha256, configuration=configuration)
                self._runtime(configuration)
            else:
                _, configuration = self._for_target(target)
                if state is not None:
                    validate_account_identity_coverage(self.root, configuration, state)
            return PinnedStrategyIdentity(self.root, configuration['identity_manifest'],
                                           configuration['identity_sha256'])(ticker)

    def valuation(self, state):
        with self.lock:
            target = self.targets.current()
            if target is None:
                configuration = self._selection_configuration(state, 'INITIAL')
                runtime = self._runtime(configuration)
            else:
                runtime, configuration = self._for_target(target)
                validate_account_identity_coverage(self.root, configuration, state)
            return runtime.valuation(state)
