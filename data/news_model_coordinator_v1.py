"""Shared conservative model reservations. No TTL takeover of a live process."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4


class ModelCoordinator:
    def __init__(self, cache, *, clock=None):
        self.path = Path(cache) / 'model_reservations_v1.sqlite3'
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('CREATE TABLE IF NOT EXISTS reservations '
                           '(id TEXT PRIMARY KEY, started REAL, units INTEGER, pid INTEGER, '
                           'created REAL, status TEXT, entrypoint TEXT)')
        return connection

    @contextmanager
    def reserve(self, entrypoint, *, units=1):
        from data.news_refresh_service import owner_alive, process_identity
        if entrypoint not in ('investment', 'event', 'refresh') or type(units) is not int or not 1 <= units <= 4:
            raise ValueError('INVALID_MODEL_RESERVATION')
        now = self.clock().timestamp()
        identifier = uuid4().hex
        with closing(self.connection()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            rows = connection.execute('SELECT id,started,units,pid,created,status FROM reservations').fetchall()
            if any(row[1] > now for row in rows):
                raise ValueError('MODEL_BUDGET_CLOCK_REVERSED')
            for row in rows:
                if row[5] == 'RUNNING':
                    if owner_alive(row[3], row[4]):
                        raise ValueError('SHARED_MODEL_ALREADY_RUNNING')
                    connection.execute('UPDATE reservations SET status=? WHERE id=?', ('ORPHANED', row[0]))
            recent = [row for row in rows if now-row[1] < 86400]
            if sum(row[2] for row in recent)+units > 24:
                raise ValueError('SHARED_MODEL_DAILY_BUDGET_EXHAUSTED')
            if any(now-row[1] < 60 for row in recent):
                raise ValueError('SHARED_MODEL_COOLDOWN')
            pid, created = process_identity()
            connection.execute('INSERT INTO reservations VALUES (?,?,?,?,?,?,?)',
                               (identifier, now, units, pid, created, 'RUNNING', entrypoint))
        outcome = 'FAILED'
        try:
            yield identifier
            outcome = 'FINISHED'
        finally:
            with closing(self.connection()) as connection, connection:
                connection.execute('UPDATE reservations SET status=? WHERE id=?', (outcome, identifier))
