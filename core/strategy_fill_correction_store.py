"""Append-only price amendments; the original account journal is immutable.

An exclusive transaction on the account database serializes amendments with
account writes and cash-classification reads. It changes no account rows.
"""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import json
import sqlite3
from core.strategy_account_ledger import canonical, number, require

class FillCorrectionStore:
    def __init__(self, account_store):
        self.account=account_store
        self.path=account_store.path.with_name(account_store.path.stem+'.fill_corrections.sqlite3')
    def _read(self, connection, state):
        records=[];prices={};ids=set()
        original={r['payload']['event_id']:r['payload'] for r in state['events']}
        rows=connection.execute('SELECT ordinal,event_id,payload,received_at FROM fill_corrections ORDER BY ordinal').fetchall()
        require(len(rows)<=10000,'CORRECTION_READ_BUDGET')
        for ordinal,event_id,raw,received_at in rows:
            require(ordinal==len(records)+1 and event_id not in ids,'CORRECTION_SEQUENCE_INVALID');ids.add(event_id)
            record=json.loads(raw);require(canonical(record).decode()==raw,'CORRECTION_PAYLOAD_INVALID')
            require(record['event']['event_id']==event_id and record['account_id']==state['account_id'],'CORRECTION_ACCOUNT_MISMATCH')
            event=record['event'];fill=original.get(event['fill_id'])
            require(fill is not None and fill['kind'] in {'FILL','DIRECT_FILL'} and
                    sha256(canonical(fill)).hexdigest()==record['original_fill_sha256'],'CORRECTION_ORIGINAL_FILL_CHANGED')
            previous=prices.get(event['fill_id'],Fraction(fill['price']))
            require(previous==Fraction(record['previous_price']),'CORRECTION_PRICE_CHAIN_INVALID')
            price=number(event['price']);require(price>0,'POSITIVE_FILL_PRICE')
            require(datetime.fromisoformat(received_at).utcoffset() is not None,'CORRECTION_TIME_INVALID')
            prices[event['fill_id']]=price;records.append(dict(record,received_at=received_at))
        return records
    def read(self, state):
        require(not self.path.is_symlink(),'CORRECTION_SYMLINK_REFUSED')
        if not self.path.exists():return []
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=10)) as connection:
            return self._read(connection,state)
    def append(self, event, *, expected_revision):
        require(set(event)=={'kind','event_id','fill_id','price','previous_price','reason'} and event['kind']=='FILL_PRICE_CORRECTION','CORRECTION_FIELDS')
        require(type(event['reason'])is str and 0<len(event['reason'].strip())<=1000,'CORRECTION_REASON_REQUIRED')
        price=number(event['price']);require(price>0,'POSITIVE_FILL_PRICE')
        require(not self.path.is_symlink(),'CORRECTION_SYMLINK_REFUSED')
        with closing(self.account._connect(False)) as guard:
            guard.execute('BEGIN EXCLUSIVE')
            try:
                state,_=self.account._read(guard)
                records=self.read(state)
                existing=next((r for r in records if r['event']['event_id']==event['event_id']),None)
                if existing:
                    require(existing['event']==event,'EVENT_ID_CONFLICT');return existing
                require(state['revision']==expected_revision,'STALE_REVISION')
                fill=next((r['payload'] for r in state['events'] if r['payload']['event_id']==event['fill_id']),None)
                require(fill is not None and fill['kind'] in {'FILL','DIRECT_FILL'},'UNKNOWN_FILL')
                previous=next((r['event']['price'] for r in reversed(records) if r['event']['fill_id']==event['fill_id']),fill['price'])
                require(number(event['previous_price'])==Fraction(previous),'STALE_FILL_PRICE')
                require(price!=Fraction(previous),'UNCHANGED_FILL_PRICE')
                with closing(sqlite3.connect(str(self.path),timeout=10,isolation_level=None)) as connection:
                    connection.execute('BEGIN IMMEDIATE')
                    try:
                        connection.execute('CREATE TABLE IF NOT EXISTS fill_corrections(ordinal INTEGER PRIMARY KEY,event_id TEXT NOT NULL UNIQUE,payload TEXT NOT NULL,received_at TEXT NOT NULL)')
                        records=self._read(connection,state)
                        existing=next((r for r in records if r['event']['event_id']==event['event_id']),None)
                        if existing:
                            require(existing['event']==event,'EVENT_ID_CONFLICT');connection.rollback();return existing
                        require(state['revision']==expected_revision,'STALE_REVISION')
                        fill=next((r['payload'] for r in state['events'] if r['payload']['event_id']==event['fill_id']),None)
                        require(fill is not None and fill['kind'] in {'FILL','DIRECT_FILL'},'UNKNOWN_FILL')
                        previous=next((r['event']['price'] for r in reversed(records) if r['event']['fill_id']==event['fill_id']),fill['price'])
                        require(price!=Fraction(previous),'UNCHANGED_FILL_PRICE')
                        require(len(records)<10000,'CORRECTION_WRITE_BUDGET')
                        record=dict(account_id=state['account_id'],account_revision=state['revision'],event=deepcopy(event),original_fill_sha256=sha256(canonical(fill)).hexdigest(),previous_price=previous)
                        at=datetime.now(timezone.utc).isoformat()
                        connection.execute('INSERT INTO fill_corrections VALUES(?,?,?,?)',(len(records)+1,event['event_id'],canonical(record).decode(),at))
                        connection.commit();return dict(record,received_at=at)
                    except BaseException:connection.rollback();raise
            finally:guard.rollback()
