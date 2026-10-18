"""Transactional storage for isolated paper plans; never reads the broker account."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from data.current_research_fill_ledger import (
    initialize_paper_ledger, apply_paper_fill, review_paper_ledger,
    apply_paper_order_event, activate_paper_plan, migrate_paper_ledger,
)


class ResearchPaperStore:
    """Explicit directory, immutable plans and a continuing paper account.

    A write transaction covers read, revision validation and state replacement.
    Separate processes therefore cannot both accept the same prior revision.
    No instance is created on import and no production path is a default.
    """

    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / 'research_paper.sqlite3'
        with closing(self._connect()) as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS research_paper_accounts '
                               '(account_id TEXT PRIMARY KEY, state_json TEXT NOT NULL)')

    def _connect(self):
        return sqlite3.connect(str(self.path), timeout=10, isolation_level=None)

    @staticmethod
    def _encode(state):
        return json.dumps(state, sort_keys=True, ensure_ascii=False, allow_nan=False,
                          separators=(',', ':'))

    @staticmethod
    def _read_raw(connection, account_id):
        row = connection.execute('SELECT state_json FROM research_paper_accounts '
                                 'WHERE account_id = ?', (account_id,)).fetchone()
        if row is None:
            raise ValueError('PAPER_ACCOUNT_NOT_FOUND')
        state = json.loads(row[0])
        if state['account_id'] != account_id:
            raise ValueError('PAPER_ACCOUNT_ID_MISMATCH')
        return state

    @classmethod
    def _load(cls, connection, account_id):
        state = cls._read_raw(connection, account_id)
        review_paper_ledger(state)  # Validate persisted lineage before reuse.
        return state

    def create(self, account_id, plan):
        candidate = initialize_paper_ledger(plan, account_id)
        with closing(self._connect()) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                row = connection.execute('SELECT 1 FROM research_paper_accounts '
                                         'WHERE account_id = ?', (account_id,)).fetchone()
                if row:
                    state = self._load(connection, account_id)
                    if state['plan'] != candidate['plan']:
                        raise ValueError('PAPER_ACCOUNT_ALREADY_BOUND_TO_ANOTHER_PLAN')
                else:
                    state = candidate
                    connection.execute('INSERT INTO research_paper_accounts VALUES (?, ?)',
                                       (account_id, self._encode(state)))
                connection.commit()
                return state
            except Exception:
                connection.rollback()
                raise

    def read(self, account_id):
        with closing(self._connect()) as connection:
            return self._load(connection, account_id)

    def record_fill(self, account_id, event):
        return self._update(account_id, lambda state: apply_paper_fill(state, event))

    def record_order_event(self, account_id, event):
        return self._update(account_id, lambda state: apply_paper_order_event(state, event))

    def activate_plan(self, account_id, plan, event):
        return self._update(account_id, lambda state: activate_paper_plan(state, plan, event))

    def migrate(self, account_id, expected_revision):
        def convert(state):
            if state.get('schema') == 'PAPER_LEDGER_V2':
                review_paper_ledger(state)
                converted = state
            else:
                converted = migrate_paper_ledger(state)
            if state['revision'] != expected_revision:
                raise ValueError('STALE_ACCOUNT_REVISION')
            return converted
        return self._update(account_id, convert, legacy=True)

    def _update(self, account_id, operation, *, legacy=False):
        with closing(self._connect()) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                before = (self._read_raw if legacy else self._load)(connection, account_id)
                after = operation(before)
                if after != before:
                    connection.execute('UPDATE research_paper_accounts SET state_json = ? '
                                       'WHERE account_id = ?', (self._encode(after), account_id))
                connection.commit()
                return after
            except Exception:
                connection.rollback()
                raise

    def review(self, account_id):
        return review_paper_ledger(self.read(account_id))
