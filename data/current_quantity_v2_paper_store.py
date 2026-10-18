"""Explicit independent V2 SQLite store. No default database or import side effects."""
from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from data.current_quantity_v2_difference_plan import require, stamp
from data.current_quantity_v2_paper_ledger import accept_proposal
from data.current_quantity_v2_paper_chain import create_chain,review_chain,accept_continuation,record_chain_event


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


class QuantityV2PaperStore:
    def __init__(self,dbpath):
        self.path=Path(dbpath)

    @staticmethod
    def identifier(value):
        require(type(value)is str and bool(value.strip()),'EXPLICIT_ID_REQUIRED')

    @staticmethod
    def schema(connection,*,empty_allowed=False):
        names={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'")}
        expected={'v2_accounts':[('account_id','TEXT',0,1),('state_json','TEXT',1,0)],
                  'v2_accept_operations':[('operation_id','TEXT',0,1),('request_json','TEXT',1,0)]}
        if not names and empty_allowed:return
        require(names==set(expected),'WRONG_PAPER_DATABASE_SCHEMA')
        for name,columns in expected.items():
            actual=[(r[1],r[2],r[3],r[5]) for r in connection.execute('PRAGMA table_info('+name+')')]
            require(actual==columns,'WRONG_PAPER_TABLE_SCHEMA')

    @contextmanager
    def transaction(self,*,create=False):
        if create:self.path.parent.mkdir(parents=True,exist_ok=True)
        else:require(self.path.is_file(),'PAPER_DATABASE_NOT_FOUND')
        with closing(sqlite3.connect(str(self.path) if create else self.path.resolve().as_uri()+'?mode=rw',
                    uri=not create,timeout=10,isolation_level=None)) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                self.schema(connection,empty_allowed=create)
                if create:
                    connection.execute('CREATE TABLE IF NOT EXISTS v2_accounts(account_id TEXT PRIMARY KEY, state_json TEXT NOT NULL)')
                    connection.execute('CREATE TABLE IF NOT EXISTS v2_accept_operations(operation_id TEXT PRIMARY KEY, request_json TEXT NOT NULL)')
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback();raise

    def load(self,connection,account_id):
        row=connection.execute('SELECT state_json FROM v2_accounts WHERE account_id=?',(account_id,)).fetchone()
        require(row is not None,'PAPER_ACCOUNT_NOT_FOUND')
        state=review_chain(json.loads(row[0]))
        require(state['ledger']['account_id']==account_id,'ACCOUNT_BINDING_MISMATCH')
        return state

    def read(self,account_id):
        self.identifier(account_id);require(self.path.is_file(),'PAPER_DATABASE_NOT_FOUND')
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as connection:
            self.schema(connection)
            return self.load(connection,account_id)

    def retry(self,connection,operation_id,request):
        row=connection.execute('SELECT request_json FROM v2_accept_operations WHERE operation_id=?',(operation_id,)).fetchone()
        if row is None:return None
        require(row[0]==encode(request),'OPERATION_ID_CONFLICT')
        return self.load(connection,request['account_id'])

    def save(self,connection,account_id,state):
        review_chain(state)
        connection.execute('INSERT INTO v2_accounts(account_id,state_json) VALUES(?,?) ON CONFLICT(account_id) DO UPDATE SET state_json=excluded.state_json',
                           (account_id,encode(state)))

    def accept(self,*,account_id,proposal_id,operation_id,factory,clock=lambda:datetime.now(timezone.utc)):
        """factory(now)->{proposal,account_state}; first invocation only, under DB lock."""
        for value in (account_id,proposal_id,operation_id):self.identifier(value)
        request=dict(kind='INITIAL',account_id=account_id,proposal_id=proposal_id)
        with self.transaction(create=True) as connection:
            previous=self.retry(connection,operation_id,request)
            if previous is not None:return previous
            require(connection.execute('SELECT 1 FROM v2_accounts WHERE account_id=?',(account_id,)).fetchone() is None,'ACCOUNT_ALREADY_EXISTS')
            supplied=factory(stamp(clock()))
            require(set(supplied)=={'proposal','account_state'} and supplied['proposal']['proposal_id']==proposal_id
                    and supplied['account_state']['account_id']==account_id,'INITIAL_FACTORY_BINDING_MISMATCH')
            # Recheck clock after potentially slow source validation.
            state=create_chain(accept_proposal(**supplied,now=stamp(clock())))
            self.save(connection,account_id,state)
            connection.execute('INSERT INTO v2_accept_operations VALUES(?,?)',(operation_id,encode(request)))
            return deepcopy(state)

    def accept_continuation(self,*,account_id,proposal_id,operation_id,expected_revision,factory,
                            clock=lambda:datetime.now(timezone.utc)):
        """factory(current_chain,now)->proposal; reloading evidence is caller responsibility."""
        for value in (account_id,proposal_id,operation_id,expected_revision):self.identifier(value)
        request=dict(kind='CONTINUATION',account_id=account_id,proposal_id=proposal_id,expected_revision=expected_revision)
        with self.transaction() as connection:
            previous=self.retry(connection,operation_id,request)
            if previous is not None:return previous
            state=self.load(connection,account_id)
            require(state['ledger']['revision']==expected_revision,'STALE_REVISION')
            proposal=factory(deepcopy(state),stamp(clock()))
            require(proposal['proposal_id']==proposal_id,'CONTINUATION_FACTORY_BINDING_MISMATCH')
            state=accept_continuation(state,proposal,acceptance_id=operation_id,now=stamp(clock()))
            self.save(connection,account_id,state)
            connection.execute('INSERT INTO v2_accept_operations VALUES(?,?)',(operation_id,encode(request)))
            return deepcopy(state)

    def accept_monthly_retarget(self,*,account_id,proposal_id,operation_id,expected_revision,factory,
                                clock=lambda:datetime.now(timezone.utc)):
        """Same account, new monthly mandate; factory/source guard follows continuation.

        Caller retaining a source guard must hold it until this transaction exits.
        Exact retries bypass source lookup and clock, returning the latest chain.
        """
        from data.current_quantity_v2_paper_chain import accept_monthly_retarget
        for value in (account_id,proposal_id,operation_id,expected_revision):self.identifier(value)
        request=dict(kind='MONTHLY_RETARGET',account_id=account_id,proposal_id=proposal_id,
                     expected_revision=expected_revision)
        with self.transaction() as connection:
            previous=self.retry(connection,operation_id,request)
            if previous is not None:return previous
            state=self.load(connection,account_id)
            require(state['ledger']['revision']==expected_revision,'STALE_REVISION')
            proposal=factory(deepcopy(state),stamp(clock()))
            require(proposal['proposal_id']==proposal_id,'MONTHLY_FACTORY_BINDING_MISMATCH')
            state=accept_monthly_retarget(state,proposal,acceptance_id=operation_id,now=stamp(clock()))
            self.save(connection,account_id,state)
            connection.execute('INSERT INTO v2_accept_operations VALUES(?,?)',(operation_id,encode(request)))
            return deepcopy(state)

    def record_event(self,*,account_id,event,clock=lambda:datetime.now(timezone.utc)):
        self.identifier(account_id)
        with self.transaction() as connection:
            state=self.load(connection,account_id)
            require(type(event)is dict,'INVALID_EVENT')
            for saved in state['ledger']['events']:
                if saved['event_id']==event.get('event_id'):
                    comparison=saved if 'recorded_at' in event else {k:v for k,v in saved.items() if k!='recorded_at'}
                    require(comparison==event,'EVENT_ID_CONFLICT');return state
            require(connection.execute('SELECT 1 FROM v2_accept_operations WHERE operation_id=?',(event.get('event_id'),)).fetchone() is None,'OPERATION_ID_CONFLICT')
            now=stamp(clock());record=deepcopy(event)
            record.setdefault('recorded_at',now.isoformat())
            state=record_chain_event(state,record,now=now)
            self.save(connection,account_id,state)
            return deepcopy(state)
