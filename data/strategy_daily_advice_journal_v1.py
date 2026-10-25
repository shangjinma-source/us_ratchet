"""Independent immutable generation audit. No fills, delivery or price certification."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from core.strategy_account_difference import require, timestamp


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


class DailyAdviceJournalV1:
    def __init__(self, path, *, clock=None):
        self.path = Path(path).absolute()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @contextmanager
    def _connection(self, *, readonly=False):
        database = self._open(readonly=readonly)
        try:
            with database:
                yield database
        finally:
            database.close()

    def _open(self, *, readonly=False):
        for item in (self.path, *self.path.parents):
            require(not item.is_symlink() and not (item.exists() and
                    getattr(item.stat(), 'st_file_attributes', 0) & 1024), 'JOURNAL_LINK_REJECTED')
        for suffix in ('-wal', '-shm', '-journal'):
            require(not Path(str(self.path)+suffix).is_symlink(), 'JOURNAL_LINK_REJECTED')
        if readonly:
            return sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True, timeout=5)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute('CREATE TABLE IF NOT EXISTS advice_events (sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, account_id TEXT NOT NULL, body BLOB NOT NULL, digest TEXT NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS advice_returns (event_id TEXT NOT NULL, ordinal INTEGER NOT NULL, body BLOB NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(event_id, ordinal))')
        return connection

    def append(self, event, *, now):
        require(re.fullmatch('[a-f0-9]{32}', event['event_id']) is not None, 'EVENT_ID_INVALID')
        require(timestamp(event['started_at']) <= timestamp(event['generated_at']) <= now,
                'EVENT_TIME_INVALID')
        require(event['displayed'] is False and event['evidence_complete'] is False,
                'AUDIT_CANNOT_CERTIFY_DELIVERY_OR_SOURCE')
        require(type(event['account_id']) is str and bool(event['account_id']), 'ACCOUNT_ID_REQUIRED')
        require(event['response_sha256'] == hashlib.sha256(encoded(event['response'])).hexdigest(), 'RESPONSE_HASH_MISMATCH')
        self._validate_event(event, event['event_id'], event['account_id'], now)
        raw = encoded(event)
        require(len(raw) <= 2*1024*1024, 'EVENT_TOO_LARGE')
        digest = hashlib.sha256(raw).hexdigest()
        with self._connection() as database:
            database.execute('BEGIN IMMEDIATE')
            old = database.execute('SELECT body,digest,account_id FROM advice_events WHERE event_id=?', (event['event_id'],)).fetchone()
            if old:
                require(bytes(old[0]) == raw, 'EVENT_ID_CONFLICT')
                require(old[1] == digest and old[2] == event['account_id'], 'EVENT_STORAGE_BINDING_MISMATCH')
            else:
                database.execute('INSERT INTO advice_events(event_id,account_id,body,digest) VALUES(?,?,?,?)',
                                 (event['event_id'], event['account_id'], raw, digest))
        return digest

    def _validate_event(self, event, event_id, account_id, now):
        require(event.get('schema') == 'DAILY_GENERATED_ADVICE_V1', 'EVENT_SCHEMA_INVALID')
        require(event['event_id'] == event_id and event['account_id'] == account_id,
                'EVENT_ACCOUNT_BINDING_MISMATCH')
        require(timestamp(event['started_at']) <= timestamp(event['generated_at']) <= now,
                'EVENT_TIME_INVALID')
        response = event['response']
        require(response.get('account_revision') == event['account_revision'] and
                response.get('target_id') == event['target_id'], 'RESPONSE_BINDING_MISMATCH')
        require(response.get('status') in {'READY', 'HOLD', 'WAIT'}, 'RESPONSE_STATUS_INVALID')
        require(response['status'] == 'READY' or not response.get('new_orders'), 'WAIT_HAS_ORDERS')
        require(event['response_sha256'] == hashlib.sha256(encoded(response)).hexdigest(),
                'RESPONSE_HASH_MISMATCH')
        require(event['displayed'] is False and event['evidence_complete'] is False,
                'AUDIT_CANNOT_CERTIFY_DELIVERY_OR_SOURCE')

    def _returns(self, database, event, event_digest, now):
        rows = database.execute('SELECT ordinal,body,digest FROM advice_returns WHERE event_id=? ORDER BY ordinal',
                                (event['event_id'],)).fetchall()
        previous_digest = event_digest
        previous_time = timestamp(event['generated_at'])
        previous_status = event['response']['status']
        for index, (ordinal, raw, digest) in enumerate(rows):
            require(ordinal == index and hashlib.sha256(raw).hexdigest() == digest,
                    'RETURN_HASH_OR_SEQUENCE_INVALID')
            item = json.loads(raw)
            require(set(item) == {'schema','event_id','event_sha256','ordinal','previous_sha256','status','checked_at'},
                    'RETURN_SCHEMA_INVALID')
            require(item['schema'] == 'DAILY_ADVICE_RETURN_V1' and item['event_id'] == event['event_id']
                    and item['event_sha256'] == event_digest and item['ordinal'] == index
                    and item['previous_sha256'] == previous_digest, 'RETURN_BINDING_INVALID')
            checked = timestamp(item['checked_at'])
            require(previous_time <= checked <= now, 'RETURN_TIME_INVALID')
            require(item['status'] in {previous_status, 'WAIT'}, 'RETURN_STATUS_UPGRADE_REJECTED')
            previous_time, previous_status, previous_digest = checked, item['status'], digest
        return rows, previous_digest, previous_time, previous_status

    def record_return(self, event_id, disposition):
        require(set(disposition) == {'status','checked_at'}, 'RETURN_FIELDS_INVALID')
        now = self.clock()
        with self._connection() as database:
            database.execute('BEGIN IMMEDIATE')
            row = database.execute('SELECT body,digest,account_id FROM advice_events WHERE event_id=?',(event_id,)).fetchone()
            require(row is not None, 'EVENT_REQUIRED')
            raw, event_digest, account_id = row
            require(hashlib.sha256(raw).hexdigest() == event_digest, 'JOURNAL_HASH_MISMATCH')
            event = json.loads(raw)
            self._validate_event(event, event_id, account_id, now)
            rows, previous_digest, previous_time, previous_status = self._returns(database,event,event_digest,now)
            require(previous_time <= timestamp(disposition['checked_at']) <= now, 'RETURN_TIME_INVALID')
            require(disposition['status'] in {previous_status,'WAIT'}, 'RETURN_STATUS_UPGRADE_REJECTED')
            item = dict(disposition, schema='DAILY_ADVICE_RETURN_V1', event_id=event_id,
                        event_sha256=event_digest, ordinal=len(rows), previous_sha256=previous_digest)
            raw = encoded(item)
            database.execute('INSERT INTO advice_returns VALUES(?,?,?,?)',
                             (event_id,len(rows),raw,hashlib.sha256(raw).hexdigest()))

    def page(self, *, account_id, after=0, limit=20):
        require(type(after) is int and after >= 0 and type(limit) is int and 1 <= limit <= 100,
                'PAGINATION_INVALID')
        if not self.path.exists():
            return dict(items=[], next_cursor=after)
        with self._connection(readonly=True) as database:
            rows = database.execute('SELECT sequence,body,digest,event_id FROM advice_events WHERE account_id=? AND sequence>? ORDER BY sequence LIMIT ?', (account_id,after,limit)).fetchall()
            items=[]
            for sequence, raw, digest, event_id in rows:
                require(hashlib.sha256(raw).hexdigest()==digest,'JOURNAL_HASH_MISMATCH')
                event=json.loads(raw)
                self._validate_event(event,event_id,account_id,self.clock())
                returns, _, _, final_status = self._returns(database,event,digest,self.clock())
                # Public allowlist deliberately excludes raw source paths and source response.
                items.append(dict(event_id=event_id,event_sha256=digest,generated_at=event['generated_at'],
                    target_id=event['target_id'], generated_status=event['response'].get('status'),
                    new_orders=[self._public_order(event,order) for order in event['response'].get('new_orders',[])], evidence_complete=False,
                    displayed=False, response_sha256=event['response_sha256'],
                    final_return_status=final_status if returns else 'NOT_RECORDED',
                    followup_status='NOT_ADMITTED'))
        return dict(items=items,next_cursor=rows[-1][0] if rows else after)

    @staticmethod
    def _public_order(event, order):
        result = {key: order[key] for key in ('security_id','side','quantity','limit_price') if key in order}
        quote = event['response'].get('reference_quotes', {}).get(order.get('security_id'), {})
        if quote.get('security_id') == order.get('security_id') and type(quote.get('ticker')) is str:
            result['ticker'] = quote['ticker']
        return result
