"""Append-only, local monthly target journal. Reads never create storage."""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
import os
import tempfile
from pathlib import Path
import sqlite3
from core.strategy_account_ledger import canonical, require

class StrategyMonthlyTargetStore:
    def __init__(self,path):self.path=Path(path)
    def _initialize(self):
        if self.path.exists():return
        self.path.parent.mkdir(parents=True,exist_ok=True)
        descriptor,name=tempfile.mkstemp(prefix='.monthly-target-',suffix='.sqlite3',dir=self.path.parent)
        os.close(descriptor)
        temporary=Path(name)
        try:
            with closing(sqlite3.connect(temporary)) as con:
                con.execute('CREATE TABLE targets(ordinal INTEGER PRIMARY KEY,event_id TEXT NOT NULL UNIQUE,payload TEXT NOT NULL)')
                con.commit()
            with temporary.open('r+b') as stream:os.fsync(stream.fileno())
            # Publish a complete empty schema without replacing a concurrent
            # creator or an existing journal. Interrupted unpublished files are
            # harmless and never mistaken for an authoritative target journal.
            try:os.link(temporary,self.path)
            except FileExistsError:pass
        finally:temporary.unlink(missing_ok=True)
    def _connect(self,write=False):
        require(not any(p.is_symlink() for p in [self.path,*self.path.parents]),'TARGET_SYMLINK_REFUSED')
        if write:self._initialize()
        return sqlite3.connect(self.path.absolute().as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,isolation_level=None,timeout=10)
    def _rows(self,con):
        require({r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}=={'targets'},'TARGET_DATABASE_SCHEMA_INVALID')
        count,total=con.execute('SELECT COUNT(*),COALESCE(SUM(LENGTH(CAST(payload AS BLOB))),0) FROM targets').fetchone()
        require(count<=1000 and total<=64*1024*1024,'TARGET_HISTORY_BUDGET')
        rows=con.execute('SELECT payload FROM targets ORDER BY ordinal LIMIT 1001').fetchall()
        require(len(rows)<=1000,'TARGET_HISTORY_BUDGET')
        previous=None;result=[];size=0
        for (raw,) in rows:
            size+=len(raw.encode());require(size<=64*1024*1024,'TARGET_HISTORY_BUDGET')
            item=json.loads(raw);require(canonical(item).decode()==raw,'TARGET_NONCANONICAL')
            payload=item['payload'];require(payload['schema']=='REAL_STRATEGY_MONTHLY_TARGET_V1','TARGET_SCHEMA')
            decision=payload['decision'];require(sha256(canonical(decision['payload'])).hexdigest()==decision['decision_id'],'TARGET_DECISION_MISMATCH')
            require(payload['target_quantities']==decision['payload']['target_quantities'],'TARGET_QUANTITIES_MISMATCH')
            require(sha256(canonical(payload)).hexdigest()==item['target_id'],'TARGET_HASH_MISMATCH')
            require(payload['previous_target_id']==previous,'TARGET_CHAIN_MISMATCH')
            if result:require(payload['account_id']==result[-1]['payload']['account_id'],'TARGET_ACCOUNT_CHANGED')
            previous=item['target_id'];result.append(item)
        return result
    def history(self):
        if not self.path.exists():return []
        with closing(self._connect()) as con:return self._rows(con)
    def current(self):
        rows=self.history();return rows[-1] if rows else None
    def operation(self,event_id):
        matches=[r for r in self.history() if r['payload']['request']['event_id']==event_id]
        require(len(matches)<=1,'TARGET_EVENT_DUPLICATE');return matches[0] if matches else None
    def append(self,payload):
        item=dict(target_id=sha256(canonical(payload)).hexdigest(),payload=deepcopy(payload))
        raw=canonical(item).decode();require(len(raw.encode())<=8*1024*1024,'TARGET_TOO_LARGE')
        with closing(self._connect(True)) as con:
            try:
                con.execute('BEGIN IMMEDIATE')
                rows=self._rows(con)
                for old in rows:
                    if old['payload']['request']['event_id']==payload['request']['event_id']:
                        require(old==item,'TARGET_EVENT_CONFLICT');con.rollback();return old
                require(payload['previous_target_id']==(rows[-1]['target_id'] if rows else None),'STALE_TARGET')
                require(not rows or payload['account_id']==rows[-1]['payload']['account_id'],'TARGET_ACCOUNT_CHANGED')
                require(len(rows)<1000 and sum(len(canonical(r)) for r in rows)+len(raw.encode())<=64*1024*1024,'TARGET_HISTORY_BUDGET')
                con.execute('INSERT INTO targets VALUES(?,?,?)',(len(rows)+1,payload['request']['event_id'],raw));con.commit();return item
            except BaseException:con.rollback();raise
