"""Adopt reviewed monthly data only; never create a target or broker order.

The deployment supplies a fixed code gate and initial data snapshot. This
module is not mounted in production. Account locking follows the existing
target publisher's account-before-target order, then commits the release CAS.
"""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
from core.strategy_account_ledger import canonical
from data.strategy_account_release_activation import MonthlyReleaseActivation as LegacyActivation
from datetime import datetime, timezone
from pathlib import Path

from core.strategy_account_ledger import apply_event, create_account, require
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_account_runtime import ScopedAccountStore
from data.strategy_account_active_release_store import ActiveMonthlyReleaseStore
from data.strategy_profiled_ready_release import validate_ready_release
from data.strategy_profiled_runtime_archive import configuration_for_target
from scripts.prepare_real_monthly_release import _read


SNAPSHOT_FIELDS = {'registry_path', 'registry_sha256', 'archive_path', 'archive_sha256'}


class ProfiledActiveReleaseStore(ActiveMonthlyReleaseStore):
    def __init__(self,*,root):
        super().__init__(root=root)
        self.path=self.root/'data/strategy_account/profiled_active_monthly_releases_v1.sqlite3'
        self._safe_storage()


class ProfiledMonthlyReleaseActivation:
    def __init__(self, *, root, initial_snapshot, validate_code, legacy_anchor, clock=None):
        require(callable(validate_code), 'ACTIVATION_SOURCE_GATE_REQUIRED')
        require(type(initial_snapshot) is dict and set(initial_snapshot) == SNAPSHOT_FIELDS,
                'ACTIVATION_INITIAL_SNAPSHOT_INVALID')
        self.root = Path(root).absolute()
        self.initial = deepcopy(initial_snapshot)
        self.gate = validate_code
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.accounts = ScopedAccountStore(self.root/'data/strategy_account/real_strategy.sqlite3', clock=self.clock)
        self.targets = StrategyMonthlyTargetStore(self.root/'data/strategy_account/monthly_targets.sqlite3')
        self.releases = ProfiledActiveReleaseStore(root=self.root)
        require(type(legacy_anchor)is dict and set(legacy_anchor)=={'revision','record_sha256','snapshot'},'LEGACY_MIGRATION_ANCHOR_REQUIRED')
        self.legacy_anchor=deepcopy(legacy_anchor)
        self.legacy=LegacyActivation(root=self.root,initial_snapshot=self.initial,validate_code=self.gate,clock=self.clock)

    def _legacy_snapshot(self):
        # Replay old ready evidence, not merely its stored pointer. Old adoption
        # uses the same account lock as our final adoption check.
        row=self.legacy.releases.current()
        snapshot=self.legacy.snapshot()
        require(snapshot['revision']==self.legacy_anchor['revision'] and
                (sha256(canonical(row)).hexdigest() if row is not None else None)==self.legacy_anchor['record_sha256'] and
                snapshot==self.legacy_anchor['snapshot'],'LEGACY_MIGRATION_ANCHOR_CHANGED')
        require(self.legacy.releases.current()==row,'LEGACY_MIGRATION_READ_CHANGED')
        return snapshot

    def snapshot(self):
        self.gate()
        legacy=self._legacy_snapshot()
        active = self.releases.current()
        if active is None:
            return dict({name:legacy[name] for name in SNAPSHOT_FIELDS},revision=0)
        self._validate_saved(active)
        return dict({name:active['payload'][name] for name in SNAPSHOT_FIELDS}, revision=active['revision'])

    def _validate_saved(self, active):
        """Replay admission at adoption time, without treating it as fresh data.

        The account may legitimately have changed since adoption. Its verified
        journal must still contain the exact revision reviewed by this receipt.
        Current-month and execution freshness checks remain the router's job.
        """
        payload = active['payload']
        adopted = datetime.fromisoformat(payload['adopted_at'])
        now = self.clock()
        require(isinstance(now, datetime) and now.utcoffset() is not None
                and adopted.utcoffset() is not None and adopted <= now,
                'ACTIVATION_SAVED_CLOCK_INVALID')
        state = self.accounts.read()
        require(state is not None, 'ACCOUNT_NOT_INITIALIZED')
        historical = create_account(state['account_id'])
        for event in state['events']:
            if historical['revision'] == payload['account_revision']:
                break
            historical, _ = apply_event(historical, event['payload'], expected_revision=historical['revision'])
        require(historical['revision'] == payload['account_revision'],
                'ACTIVATION_SAVED_ACCOUNT_REVISION_MISSING')
        reviewed = validate_ready_release(root=self.root, receipt_path=payload['ready_path'],
            receipt_sha256=payload['ready_sha256'], account_state=historical, clock=lambda:adopted)
        require(all(reviewed[name] == payload[name] for name in SNAPSHOT_FIELDS)
                and reviewed['configuration']['target_month'] == payload['target_month']
                and reviewed['account_revision'] == payload['account_revision'],
                'ACTIVATION_SAVED_RECEIPT_BINDING_MISMATCH')
        self.gate()
        return reviewed

    def adopt(self, *, receipt_path, receipt_sha256, expected_release_revision):
        self.gate()
        legacy=self._legacy_snapshot()
        prior = self.releases.current()
        revision = prior['revision'] if prior else 0
        if prior:
            self._validate_saved(prior)
        # A committed retry returns the old adoption without inventing a new
        # timestamp, and never restores it over a newer release.
        if prior and (prior['payload']['ready_path'], prior['payload']['ready_sha256']) == (receipt_path, receipt_sha256):
            return prior
        require(revision == expected_release_revision, 'STALE_ACTIVE_RELEASE')
        old_snapshot = prior['payload'] if prior else legacy
        state = self.accounts.read()
        require(state is not None, 'ACCOUNT_NOT_INITIALIZED')
        target = self.targets.current()
        target_id = target['target_id'] if target else None
        reviewed = validate_ready_release(root=self.root, receipt_path=receipt_path,
            receipt_sha256=receipt_sha256, account_state=state, clock=self.clock)
        new_snapshot = {name:reviewed[name] for name in SNAPSHOT_FIELDS}
        # Preserve exact old entries: no silent historical rebinding or removal.
        for kind in ('registry','archive'):
            old=_read(self.root,old_snapshot[kind+'_path'],old_snapshot[kind+'_sha256'])
            new=_read(self.root,new_snapshot[kind+'_path'],new_snapshot[kind+'_sha256'])
            if kind=='registry':
                old_profiles=old.get('profiles',[]);new_profiles=new.get('profiles',[])
                require(all(row in new_profiles for row in old_profiles),'PROFILE_ASSIGNMENT_HISTORY_CHANGED')
                if old.get('schema')=='PROFILED_MONTHLY_RELEASES_V1':
                    ref=old['original_registry'];old=_read(self.root,ref['path'],ref['sha256'])
                require(new.get('schema')=='PROFILED_MONTHLY_RELEASES_V1','PROFILE_REGISTRY_REQUIRED')
                ref=new['original_registry'];new=_read(self.root,ref['path'],ref['sha256'])
            else:
                require(old.get('schema') in {'REAL_STRATEGY_RUNTIME_ARCHIVE_V1','PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1'} and new.get('schema')=='PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1','PROFILE_ARCHIVE_REQUIRED')
            require(all(entry in new['entries'] for entry in old['entries']),'ACTIVATION_HISTORY_NOT_PRESERVED')
        if target:
            configuration_for_target(root=self.root, archive_path=new_snapshot['archive_path'],
                archive_sha256=new_snapshot['archive_sha256'], target=target)
        self.gate()
        # No network work occurs in this short transaction. All normal target
        # publications also lock the account before writing their own store.
        with closing(self.accounts._connect(False)) as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
                current, _ = self.accounts._read(connection)
                require(current['revision'] == state['revision'], 'ACCOUNT_CHANGED_DURING_ACTIVATION')
                latest_target = self.targets.current()
                require((latest_target['target_id'] if latest_target else None) == target_id,
                        'TARGET_CHANGED_DURING_ACTIVATION')
                # Re-read immutable evidence under the lock so file changes
                # between preparation and adoption cannot be committed.
                checked = validate_ready_release(root=self.root, receipt_path=receipt_path,
                    receipt_sha256=receipt_sha256, account_state=current, clock=self.clock)
                require(checked == reviewed, 'ACTIVATION_EVIDENCE_CHANGED')
                self.gate()
                require(self._legacy_snapshot()==legacy,'LEGACY_MIGRATION_CHANGED_DURING_ADOPTION')
                payload = dict(new_snapshot, ready_path=receipt_path, ready_sha256=receipt_sha256,
                    target_month=reviewed['configuration']['target_month'],
                    account_revision=current['revision'], adopted_at=self.clock().isoformat())
                return self.releases.adopt(payload, expected_revision=expected_release_revision)
            finally:
                connection.rollback()
