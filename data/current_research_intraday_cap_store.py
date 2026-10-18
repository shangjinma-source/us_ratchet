"""Transactional conservative session caps; no import-time filesystem writes."""
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
import re
import sqlite3
import json
from hashlib import sha256


class PersistentIntradayCapStore:
    def __init__(self, path):
        self.path = Path(path)

    def lower(self, *, research_id, security_id, ticker, session, observed_cap, event_id, prepare_callback=None):
        if not re.fullmatch('[0-9a-f]{24}', research_id) or not isinstance(security_id,str) or not security_id or not re.fullmatch('[A-Z0-9.\\-]{1,15}',ticker):
            raise ValueError('INVALID_CAP_IDENTITY')
        if date.fromisoformat(session).isoformat()!=session or not re.fullmatch('[0-9a-f]{32}',event_id):
            raise ValueError('INVALID_CAP_SESSION_OR_EVENT')
        value=Decimal(observed_cap)
        if not value.is_finite() or value<=0 or value*100!=(value*100).to_integral_value() or value*100>2**63-1:
            raise ValueError('INVALID_CAP_CENTS')
        cents=int(value*100); key=(research_id,security_id,ticker,session)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path,timeout=15,isolation_level=None)) as connection:
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('BEGIN IMMEDIATE')
            try:
                connection.execute('CREATE TABLE IF NOT EXISTS session_caps (research_id TEXT NOT NULL, security_id TEXT NOT NULL, ticker TEXT NOT NULL, session TEXT NOT NULL, cents INTEGER NOT NULL CHECK(cents>0), origin_event TEXT NOT NULL, PRIMARY KEY(research_id,security_id,ticker,session))')
                previous=connection.execute('SELECT cents,origin_event FROM session_caps WHERE research_id=? AND security_id=? AND ticker=? AND session=?',key).fetchone()
                if previous is not None and (type(previous[0]) is not int or previous[0]<=0 or not isinstance(previous[1],str) or not re.fullmatch('[0-9a-f]{32}',previous[1])):
                    raise ValueError('CORRUPT_CAP_ROW')
                final=min(cents,previous[0]) if previous else cents
                origin=previous[1] if previous and previous[0]<=cents else event_id
                metadata=dict(cap=str(Decimal(final)/100),cap_before=None if previous is None else str(Decimal(previous[0])/100),prior_cap_event_id=previous[1] if previous else None,cap_origin_event_id=origin)
                if prepare_callback is not None:
                    package=prepare_callback(dict(metadata))
                    raw=json.dumps(package,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
                    connection.execute('CREATE TABLE IF NOT EXISTS cap_outbox (event_id TEXT PRIMARY KEY, research_id TEXT NOT NULL, security_id TEXT NOT NULL, ticker TEXT NOT NULL, session TEXT NOT NULL, package BLOB NOT NULL, sha256 TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0 CHECK(published IN (0,1)))')
                    connection.execute('INSERT INTO cap_outbox(event_id,research_id,security_id,ticker,session,package,sha256) VALUES (?,?,?,?,?,?,?)',(event_id,*key,raw,sha256(raw).hexdigest()))
                connection.execute('INSERT INTO session_caps VALUES (?,?,?,?,?,?) ON CONFLICT(research_id,security_id,ticker,session) DO UPDATE SET cents=excluded.cents,origin_event=excluded.origin_event',(*key,final,origin))
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return dict(metadata,**({'publication':package} if prepare_callback is not None else {}))

    def lower_with_outbox(self, *, prepare_callback, **kwargs):
        """The callback freezes evidence in memory; cap and bytes commit together."""
        if not callable(prepare_callback):
            raise ValueError('OUTBOX_PREPARER_REQUIRED')
        return self.lower(prepare_callback=prepare_callback,**kwargs)

    def recover(self, journal, *, research_id, security_id, ticker, session):
        """Publish committed original bytes only. Never produces a fresh quote."""
        if not self.path.exists():
            return []
        key=(research_id,security_id,ticker,session)
        with closing(sqlite3.connect(self.path,timeout=15,isolation_level=None)) as connection:
            tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not tables:
                return []
            if 'session_caps' not in tables:
                raise ValueError('CAP_SCHEMA_MISSING')
            rows=connection.execute('SELECT event_id,package,sha256 FROM cap_outbox WHERE research_id=? AND security_id=? AND ticker=? AND session=? AND published=0 ORDER BY rowid',key).fetchall() if 'cap_outbox' in tables else []
            receipts=[]
            for event_id,raw,digest in rows:
                if not isinstance(raw,bytes) or sha256(raw).hexdigest()!=digest:
                    raise ValueError('OUTBOX_HASH_MISMATCH')
                package=json.loads(raw)
                if package['receipt']['event_id']!=event_id:
                    raise ValueError('OUTBOX_EVENT_MISMATCH')
                receipt=journal.publish_prepared(package)
                # If this mark fails, re-publishing exact bytes is idempotent.
                connection.execute('PRAGMA synchronous=FULL')
                connection.execute('BEGIN IMMEDIATE')
                try:
                    connection.execute('UPDATE cap_outbox SET published=1 WHERE event_id=?',(event_id,))
                    connection.commit()
                except BaseException:
                    connection.rollback();raise
                receipts.append(receipt)
            origin=connection.execute('SELECT origin_event,cents FROM session_caps WHERE research_id=? AND security_id=? AND ticker=? AND session=?',key).fetchone()
            if origin:
                if not isinstance(origin[0],str) or not re.fullmatch('[0-9a-f]{32}',origin[0]):
                    raise ValueError('CORRUPT_CAP_ORIGIN')
                sealed=connection.execute('SELECT package,sha256 FROM cap_outbox WHERE event_id=? AND research_id=? AND security_id=? AND ticker=? AND session=?',(origin[0],*key)).fetchone() if 'cap_outbox' in tables else None
                if sealed is None:
                    raise ValueError('CAP_ORIGIN_TRUSTED_RECEIPT_MISSING')
                raw,digest=sealed
                if not isinstance(raw,bytes) or sha256(raw).hexdigest()!=digest:
                    raise ValueError('OUTBOX_HASH_MISMATCH')
                package=json.loads(raw)
                journal.validate_prepared(package)
                receipt=package['receipt']
                if receipt['event_id']!=origin[0] or receipt['event_path']!=f'events/{session}/{origin[0]}.json':
                    raise ValueError('CAP_ORIGIN_RECEIPT_MISMATCH')
                event=journal.read_event(receipt['event_path'],expected_sha256=receipt['event_sha256'])
                security=event.get('research_binding',{}).get('selected_security',{})
                response=event.get('response',{})
                matching=[row for row in response.get('stocks',[]) if row.get('ticker')==ticker and row.get('session')==session and row.get('status')=='AVAILABLE']
                if event.get('research_id')!=research_id or response.get('research_id')!=research_id or security.get('security_id')!=security_id or security.get('ticker')!=ticker or len(matching)!=1 or type(origin[1]) is not int or origin[1]<=0:
                    raise ValueError('ROW_ORIGIN_CAP_MISMATCH')
                limit=Decimal(matching[0]['limit_price'])
                if not limit.is_finite() or limit*100!=origin[1] or matching[0].get('cap_origin_event_id')!=origin[0]:
                    raise ValueError('ROW_ORIGIN_CAP_MISMATCH')
            return receipts

    def read_scope_evidence(self, journal, *, research_id, security_id, ticker, session, current_event_id):
        """Read committed original outbox bytes, without recovery or publication.

        This verifies local committed integrity, not externally authenticated time.
        Only cap dependency edges are traversed; observation sequence gaps from
        unrelated or failed requests are not evidence of a missing cap ancestor.
        """
        from fractions import Fraction
        def require(condition, reason):
            if not condition:
                raise ValueError(reason)
        require(isinstance(research_id, str) and re.fullmatch('[0-9a-f]{24}', research_id), 'INVALID_CAP_IDENTITY')
        require(isinstance(security_id, str) and bool(security_id) and isinstance(ticker, str) and re.fullmatch(r'[A-Z0-9.\-]{1,15}', ticker), 'INVALID_CAP_IDENTITY')
        require(date.fromisoformat(session).isoformat() == session and isinstance(current_event_id, str) and re.fullmatch('[0-9a-f]{32}', current_event_id), 'INVALID_CAP_SESSION_OR_EVENT')
        require(self.path.is_file(), 'CAP_DATABASE_MISSING')
        key = (research_id, security_id, ticker, session)
        frozen = {}; hashes = {}; packages = {}; records = {}; receipts = {}
        maximum_bytes = 128 * 1024 * 1024
        with closing(sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True, isolation_level=None)) as connection:
            connection.execute('BEGIN')
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            require({'session_caps', 'cap_outbox'} <= tables, 'CAP_OUTBOX_SCHEMA_MISSING')
            caprow = connection.execute('SELECT cents,origin_event FROM session_caps WHERE research_id=? AND security_id=? AND ticker=? AND session=?', key).fetchone()
            require(caprow is not None and type(caprow[0]) is int and caprow[0] > 0, 'CAP_SCOPE_MISSING_OR_INVALID')
            count, size = connection.execute('SELECT COUNT(*),COALESCE(SUM(length(package)),0) FROM cap_outbox WHERE research_id=? AND security_id=? AND ticker=? AND session=?', key).fetchone()
            require(count <= 1000 and size <= maximum_bytes, 'CAP_EVIDENCE_LIMIT_EXCEEDED')
            queue = [current_event_id]
            while queue:
                identifier = queue.pop()
                if identifier in records:
                    continue
                require(isinstance(identifier, str) and re.fullmatch('[0-9a-f]{32}', identifier), 'INVALID_CAP_DEPENDENCY')
                row = connection.execute('SELECT rowid,package,sha256,published FROM cap_outbox WHERE event_id=? AND research_id=? AND security_id=? AND ticker=? AND session=?', (identifier, *key)).fetchone()
                require(row is not None, 'CAP_DEPENDENCY_OR_CURRENT_OUTBOX_MISSING')
                index, raw, digest, published = row
                require(isinstance(raw, bytes) and sha256(raw).hexdigest() == digest, 'OUTBOX_HASH_MISMATCH')
                package = json.loads(raw)
                files = journal.validate_prepared(package)
                receipt = package['receipt']
                require(receipt['event_id'] == identifier and receipt['event_path'] == f'events/{session}/{identifier}.json', 'OUTBOX_EVENT_MISMATCH')
                event = json.loads(files[receipt['event_path']])
                security = event.get('research_binding', {}).get('selected_security', {})
                response = event.get('response', {})
                stocks = [stock for stock in response.get('stocks', []) if stock.get('ticker') == ticker and stock.get('session') == session and stock.get('status') == 'AVAILABLE']
                require(event.get('research_id') == research_id and response.get('research_id') == research_id and response.get('status') == 'AVAILABLE' and security.get('security_id') == security_id and security.get('ticker') == ticker and len(stocks) == 1, 'OUTBOX_SCOPE_OR_AVAILABLE_MISMATCH')
                stock = stocks[0]
                limit = Fraction(stock['limit_price']); observed = Fraction(stock['observed_cap'])
                require(limit > 0 and (limit * 100).denominator == 1 and observed >= limit, 'INVALID_OUTBOX_CAP')
                prior = stock.get('prior_cap_event_id'); origin = stock.get('cap_origin_event_id')
                require(origin is not None and prior != identifier, 'INVALID_CAP_DEPENDENCY')
                for name, content in files.items():
                    require(name not in frozen or frozen[name] == content, 'CONFLICTING_OUTBOX_FILE')
                    frozen[name] = content
                require(sum(map(len, frozen.values())) <= maximum_bytes, 'CAP_EVIDENCE_LIMIT_EXCEEDED')
                records[identifier] = (index, stock, limit, observed)
                receipts[identifier] = receipt
                packages[identifier] = digest
                hashes[receipt['event_path']] = receipt['event_sha256']
                queue.extend(link for link in (prior, origin) if link is not None and link != identifier)
            for identifier, (index, stock, limit, observed) in records.items():
                prior = stock.get('prior_cap_event_id'); origin = stock['cap_origin_event_id']
                if prior is None:
                    require(stock.get('cap_before') is None and limit == observed and origin == identifier, 'CAP_CHAIN_MISMATCH')
                else:
                    ancestor = records[prior]
                    require(ancestor[0] < index and Fraction(stock['cap_before']) == ancestor[2], 'CAP_CHAIN_MISMATCH')
                    expected_origin = ancestor[1]['cap_origin_event_id'] if ancestor[2] <= observed else identifier
                    require(limit == min(ancestor[2], observed) and origin == expected_origin, 'CAP_CHAIN_MISMATCH')
                require(records[origin][2] == limit, 'CAP_ORIGIN_VALUE_MISMATCH')
            current = records[current_event_id]
            require(current[2] * 100 == caprow[0] and current[1]['cap_origin_event_id'] == caprow[1], 'CURRENT_CAP_ROW_MISMATCH')
            # Compare against original bytes, never mint a new receipt from disk.
            root = Path(journal.root).resolve()
            for name, content in frozen.items():
                path = (root / name).resolve()
                require(path.is_relative_to(root), 'JOURNAL_PATH_OUTSIDE_ROOT')
                require(path.is_file() and path.stat().st_size == len(content) and path.stat().st_size <= 32 * 1024 * 1024, 'JOURNAL_ORIGINAL_SIZE_MISMATCH')
                require(path.read_bytes() == content, 'JOURNAL_ORIGINAL_BYTES_MISMATCH')
        return dict(event_hashes=hashes, frozen_files=frozen, current_receipt=receipts[current_event_id],
                    scope=dict(research_id=research_id, security_id=security_id, ticker=ticker, session=session),
                    cap_row=dict(cap=str(Decimal(caprow[0]) / 100), origin_event=caprow[1]),
                    outbox_package_hashes=packages,
                    dependency_event_ids=sorted(records, key=lambda identifier: records[identifier][0]),
                    read_only=True, integrity_scope='LOCAL_COMMITTED_OUTBOX_BYTES_NOT_EXTERNAL_TIMESTAMP')
