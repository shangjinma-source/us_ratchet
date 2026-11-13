"""Append-only local transfer journal, separate from the strategy account."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from core.broker_internal_transfers import create_transfers, apply_transfer_event


class TransferStore:
    def __init__(self, path, account_id, clock=None):
        self.path = Path(path)
        self.account_id = account_id
        create_transfers(account_id)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS transfer_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL, event_id TEXT NOT NULL,
                payload TEXT NOT NULL, recorded_at TEXT NOT NULL,
                resulting_revision TEXT NOT NULL,
                UNIQUE(account_id,event_id))''')
            connection.commit()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute('PRAGMA synchronous=FULL')
        return connection

    def _read(self, connection):
        state = create_transfers(self.account_id)
        rows = connection.execute('''SELECT payload,recorded_at,resulting_revision
            FROM transfer_events WHERE account_id=? ORDER BY sequence''',
            (self.account_id,)).fetchall()
        for payload, recorded_at, revision in rows:
            state = apply_transfer_event(state, json.loads(payload),
                expected_revision=state['revision'], now=datetime.fromisoformat(recorded_at))
            if state['revision'] != revision:
                raise ValueError('STORED_TRANSFER_REVISION_MISMATCH')
        return state

    def read(self):
        connection = self._connect()
        try:
            return self._read(connection)
        finally:
            connection.close()

    def append(self, event, *, expected_revision):
        connection = self._connect()
        try:
            connection.execute('BEGIN IMMEDIATE')
            before = self._read(connection)
            now = self.clock()
            after = apply_transfer_event(before, event,
                expected_revision=expected_revision, now=now)
            if after['revision'] != before['revision']:
                connection.execute('''INSERT INTO transfer_events
                    (account_id,event_id,payload,recorded_at,resulting_revision)
                    VALUES (?,?,?,?,?)''', (self.account_id,event['event_id'],
                    json.dumps(event,sort_keys=True,allow_nan=False),now.isoformat(),after['revision']))
            connection.commit()
            return after
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
