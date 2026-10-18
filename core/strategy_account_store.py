"""Explicit single-strategy SQLite journal; construction and absent reads do no IO writes.

Bounded to 10,000 events / 16 MiB. Full reducer replay currently has quadratic
event-history work; this is not an unlimited long-term archival service.
"""
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
import json,os,sqlite3,tempfile
from core.strategy_account_ledger import create_account,apply_event,canonical

SCHEMA='REAL_STRATEGY_SQLITE_JOURNAL_V2'


def require(ok,reason):
    if not ok:raise ValueError(reason)


class StrategyAccountStore:
    def __init__(self,path,*,clock=None):
        self.path=Path(path).absolute()
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def _connect(self,readonly):
        require(not self.path.is_symlink(),'DATABASE_SYMLINK_REFUSED')
        require(self.path.is_file(),'ACCOUNT_NOT_INITIALIZED')
        return sqlite3.connect(self.path.as_uri()+('?mode=ro' if readonly else '?mode=rw'),uri=True,timeout=10,isolation_level=None)

    def _schema(self,connection):
        tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        require(tables=={'strategy_meta','strategy_events'},'FOREIGN_DATABASE_SCHEMA')
        expected={'strategy_meta':[('singleton','INTEGER',0,1),('schema','TEXT',1,0),('account_id','TEXT',1,0),('revision','TEXT',1,0),('initialization_id','TEXT',1,0)],
                  'strategy_events':[('ordinal','INTEGER',0,1),('event_id','TEXT',1,0),('payload','TEXT',1,0),('received_at','TEXT',1,0),('revision','TEXT',1,0)]}
        for table,columns in expected.items():
            require([(r[1],r[2],r[3],r[5]) for r in connection.execute('PRAGMA table_info('+table+')')]==columns,'FOREIGN_DATABASE_SCHEMA')
        unique_event=False
        for index in connection.execute('PRAGMA index_list(strategy_events)'):
            if index[2] and not index[4]:
                name=index[1].replace('"','""')
                if [r[2] for r in connection.execute('PRAGMA index_info("'+name+'")')]==['event_id']:unique_event=True
        require(unique_event,'FOREIGN_DATABASE_SCHEMA')
        require(not connection.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')").fetchone(),'FOREIGN_DATABASE_SCHEMA')
        row=connection.execute('SELECT singleton,schema,account_id,revision FROM strategy_meta').fetchall()
        require(len(row)==1 and row[0][0]==1 and row[0][1]==SCHEMA,'FOREIGN_DATABASE_SCHEMA')
        return row[0][2],row[0][3]

    def _read(self,connection):
        account_id,expected=self._schema(connection)
        count,total=connection.execute('SELECT COUNT(*),COALESCE(SUM(LENGTH(CAST(payload AS BLOB))),0) FROM strategy_events').fetchone()
        require(count<=10000 and total<=16*1024*1024,'JOURNAL_READ_BUDGET_EXCEEDED')
        state=create_account(account_id);last=None
        for ordinal,event_id,payload,received_at,revision in connection.execute('SELECT ordinal,event_id,payload,received_at,revision FROM strategy_events ORDER BY ordinal'):
            require(ordinal==len(state['events'])+1,'JOURNAL_SEQUENCE_INVALID')
            event=json.loads(payload)
            require(canonical(event).decode()==payload and event.get('event_id')==event_id,'EVENT_PAYLOAD_MISMATCH')
            at=datetime.fromisoformat(received_at)
            require(at.tzinfo is not None and at.utcoffset() is not None and (last is None or at>=last),'RECEIPT_TIME_INVALID');last=at
            if event.get('kind')in {'DIRECT_FILL','FILL'}:
                executed=datetime.fromisoformat(event['executed_at'])
                require(executed.tzinfo is not None and executed.utcoffset() is not None and executed<=at,'FUTURE_EXECUTED_AT')
            state,_=apply_event(state,event,expected_revision=state['revision'])
            require(state['revision']==revision,'EVENT_REVISION_MISMATCH')
        require(len(state['events'])==count and state['revision']==expected,'ACCOUNT_REVISION_MISMATCH')
        return state,last

    def initialize(self,account_id,*,operation_id):
        state=create_account(account_id)
        require(isinstance(operation_id,str) and 0<len(operation_id)<=128,'INITIALIZATION_ID_REQUIRED')
        require(not self.path.is_symlink(),'DATABASE_SYMLINK_REFUSED')
        if self.path.exists():
            with closing(self._connect(True)) as connection:
                connection.execute('BEGIN')
                current,_=self._read(connection)
                token=connection.execute('SELECT initialization_id FROM strategy_meta').fetchone()[0]
                require(current['account_id']==account_id and token==operation_id,'INITIALIZATION_CONFLICT')
                return current
        # Only this explicit method may create parent directories or a database.
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.'+self.path.name+'.initialize-',suffix='.sqlite3',dir=self.path.parent)
        os.close(fd);temporary=Path(name)
        try:
            with closing(sqlite3.connect(str(temporary),isolation_level=None)) as connection:
                try:
                    connection.execute('BEGIN IMMEDIATE')
                    connection.execute('CREATE TABLE strategy_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),schema TEXT NOT NULL,account_id TEXT NOT NULL,revision TEXT NOT NULL,initialization_id TEXT NOT NULL)')
                    connection.execute('CREATE TABLE strategy_events(ordinal INTEGER PRIMARY KEY,event_id TEXT NOT NULL UNIQUE,payload TEXT NOT NULL,received_at TEXT NOT NULL,revision TEXT NOT NULL)')
                    connection.execute('INSERT INTO strategy_meta VALUES(1,?,?,?,?)',(SCHEMA,account_id,state['revision'],operation_id))
                    connection.commit()
                except BaseException:
                    connection.rollback();raise
            # Publish only a fully committed, closed SQLite database. Hard-link
            # creation is atomic and refuses replacement of an existing target.
            with temporary.open('r+b') as handle:os.fsync(handle.fileno())
            try:os.link(temporary,self.path)
            except FileExistsError:
                return self.initialize(account_id,operation_id=operation_id)
        finally:
            temporary.unlink(missing_ok=True)
        return state

    def read(self):
        require(not self.path.is_symlink(),'DATABASE_SYMLINK_REFUSED')
        if not self.path.exists():return None
        with closing(self._connect(True)) as connection:
            connection.execute('BEGIN')
            try:return self._read(connection)[0]
            finally:connection.rollback()

    def append(self,event,*,expected_revision):
        # Reducer owns exact event fields, stale revisions, and idempotent retries.
        raw=canonical(event).decode();require(len(raw.encode())<=64*1024,'EVENT_TOO_LARGE')
        with closing(self._connect(False)) as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
                old,last=self._read(connection)
                updated,effect=apply_event(old,event,expected_revision=expected_revision)
                if len(updated['events'])==len(old['events']):
                    connection.rollback();return updated,effect
                at=self.clock()
                require(isinstance(at,datetime) and at.tzinfo is not None and at.utcoffset() is not None,'AWARE_SERVER_CLOCK_REQUIRED')
                require(last is None or at>=last,'SERVER_CLOCK_ROLLBACK')
                if event.get('kind')in {'DIRECT_FILL','FILL'}:
                    require(datetime.fromisoformat(event['executed_at'])<=at,'FUTURE_EXECUTED_AT')
                count,total=connection.execute('SELECT COUNT(*),COALESCE(SUM(LENGTH(CAST(payload AS BLOB))),0) FROM strategy_events').fetchone()
                require(count<10000 and total+len(raw.encode())<=16*1024*1024,'JOURNAL_WRITE_BUDGET_EXCEEDED')
                connection.execute('INSERT INTO strategy_events VALUES(?,?,?,?,?)',(count+1,event['event_id'],raw,at.isoformat(),updated['revision']))
                connection.execute('UPDATE strategy_meta SET revision=? WHERE singleton=1',(updated['revision'],))
                connection.commit();return updated,effect
            except BaseException:
                connection.rollback();raise
