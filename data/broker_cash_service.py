"""Broker cash endpoints backed by one locked account/transfer snapshot."""
from contextlib import closing, contextmanager, ExitStack
from pathlib import Path
import sqlite3


class BrokerCashService:
    def __init__(self, *, account_store, transfer_store, allocation_store, lock, clock, validate_sources):
        self.account_store = account_store
        self.transfer_store = transfer_store
        self.allocation_store = allocation_store
        self.lock = lock
        self.clock = clock
        self.validate_sources = validate_sources

    @contextmanager
    def snapshot(self):
        # Shared ROA lock plus DELETE-journal read locks prevent even another
        # process committing account/transfer changes during allocation commit.
        # Only the allocation sidecar is written; this is not a multi-DB write.
        with self.lock, ExitStack() as stack:
            self.validate_sources()
            connections = []
            for path in (self.account_store.path, self.transfer_store.path):
                connection = stack.enter_context(closing(sqlite3.connect(
                    Path(path).absolute().as_uri() + '?mode=ro', uri=True, timeout=10,
                    isolation_level=None)))
                if connection.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
                    raise ValueError('CASH_SNAPSHOT_JOURNAL_MODE_UNSUPPORTED')
                connection.execute('BEGIN')
                connections.append(connection)
            account, _ = self.account_store._read(connections[0])
            transfers = self.transfer_store._read(connections[1])
            yield account, transfers
            self.validate_sources()

    def read(self):
        with self.snapshot() as (account, transfers):
            result = self.allocation_store.read(account=account, transfers=transfers, now=self.clock())
            return dict(result, account_id=account['account_id'], account_revision=account['revision'],
                        transfer_revision=transfers['revision'], account_written=False)

    def save(self, body):
        if type(body) is not dict or set(body) != {'event_id', 'document'}:
            raise ValueError('BROKER_CASH_REQUEST_FIELDS')
        with self.snapshot() as (account, transfers):
            return self.allocation_store.save(body['event_id'], body['document'],
                account=account, transfers=transfers, now=self.clock())
