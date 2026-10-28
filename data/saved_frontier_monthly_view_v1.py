"""Separate persistent proposal bindings; never change signed monthly targets.

An interrupted generation can leave an original target without its proposal.
Reads fail closed in that state; retrying the same generation repairs it without
reselection. This module grants no market evidence or execution authorization.
"""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import json
import sqlite3
import os
import tempfile
from functools import lru_cache

from core.saved_monthly_frontier_proposal import build_frontier_proposal
from core.strategy_account_ledger import canonical, require
from data.strategy_daily_session_capture import reject_links


@lru_cache(maxsize=1)
def _expected_proposal_bytes(target_bytes):
    # Pure reconstruction only. Every read still verifies persisted bytes.
    # Immutable full-content key and bytes result cannot alias caller objects.
    return canonical(build_frontier_proposal(target=json.loads(target_bytes)))


class SavedFrontierProposalStore:
    def __init__(self, path):
        self.path = Path(path)

    def _check_path(self):
        reject_links(self.path)
        for path in (self.path, Path(str(self.path) + '-journal'),
                     Path(str(self.path) + '-wal'), Path(str(self.path) + '-shm')):
            reject_links(path)
            if path.exists():
                require(path.is_file() and path.stat().st_nlink == 1,
                        'FRONTIER_STORAGE_ALIAS_FORBIDDEN')

    def _initialize(self):
        self._check_path()
        require(self.path.parent.is_dir(), 'FRONTIER_STORAGE_PARENT_REQUIRED')
        if self.path.exists():
            return
        descriptor, name = tempfile.mkstemp(prefix='.frontier-', suffix='.sqlite3', dir=self.path.parent)
        os.close(descriptor)
        temporary = Path(name)
        try:
            with closing(sqlite3.connect(temporary)) as connection:
                connection.execute('CREATE TABLE frontier_proposals '
                                   '(target_id TEXT PRIMARY KEY, document BLOB NOT NULL)')
                connection.commit()
            with temporary.open('r+b') as stream:
                os.fsync(stream.fileno())
            try:
                os.link(temporary, self.path)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)

    def _connect(self, write=False):
        self._check_path()
        if write:
            self._initialize()
        else:
            require(self.path.is_file(), 'FRONTIER_PROPOSAL_REQUIRED')
        self._check_path()
        return sqlite3.connect(self.path.absolute().as_uri() + ('?mode=rw' if write else '?mode=ro'),
                               uri=True, timeout=30)

    def bind(self, target):
        proposal = build_frontier_proposal(target=target)
        document = canonical(proposal)
        with closing(self._connect(True)) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            old = connection.execute('SELECT document FROM frontier_proposals WHERE target_id=?',
                                     (target['target_id'],)).fetchone()
            if old:
                require(bytes(old[0]) == document, 'FRONTIER_PROPOSAL_CHANGED')
            else:
                connection.execute('INSERT INTO frontier_proposals VALUES (?, ?)',
                                   (target['target_id'], document))
        return deepcopy(proposal)

    def read(self, target):
        expected = _expected_proposal_bytes(canonical(target))
        with closing(self._connect()) as connection:
            row = connection.execute('SELECT document FROM frontier_proposals WHERE target_id=?',
                                     (target['target_id'],)).fetchone()
        require(row is not None, 'FRONTIER_PROPOSAL_REQUIRED')
        require(bytes(row[0]) == expected, 'FRONTIER_PROPOSAL_CHANGED')
        return json.loads(row[0])


class SavedFrontierMonthlyView:
    """API display facade; keep original monthly router in risk/execution internals."""
    def __init__(self, *, monthly, proposals, validate_sources):
        self.monthly = monthly
        self.proposals = proposals
        self.validate_sources = validate_sources

    @property
    def accounts(self):
        return self.monthly.accounts

    @property
    def selection(self):
        return self.monthly.selection

    def _month(self):
        return self.monthly._month()

    def snapshot_operation(self):
        return self.monthly.snapshot_operation()

    def _view(self, target, proposal):
        return dict(deepcopy(target), proposal_id=proposal['proposal_id'],
                    frontier_proposal=deepcopy(proposal),
                    risk_monthly_targets=deepcopy(proposal['payload']['proposed_target_quantities']))

    def current(self):
        with self.monthly.snapshot_operation():
            self.validate_sources()
            target = self.monthly.current()
            if target is None:
                return None
            proposal = self.proposals.read(target)
            self.validate_sources()
            require(self.monthly.current() == target, 'TARGET_CHANGED_DURING_PREVIEW')
            return self._view(target, proposal)

    def generate(self, **request):
        with self.monthly.snapshot_operation():
            self.validate_sources()
            target = self.monthly.generate(**request)
            proposal = self.proposals.bind(target)
            self.validate_sources()
            # A replay may legitimately return a historical target. Preserve the
            # original service's idempotency rather than select again.
            return self._view(target, proposal)

    def require_proposal(self, *, target_id, expected_proposal_id):
        view = self.current()
        require(view is not None and view['target_id'] == target_id, 'STALE_TARGET')
        require(view['proposal_id'] == expected_proposal_id, 'STALE_FRONTIER_PROPOSAL')
        return deepcopy(view['frontier_proposal'])
