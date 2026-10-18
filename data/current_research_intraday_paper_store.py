"""Explicit, lazy SQLite storage for the independent intraday paper ledger only."""
from contextlib import closing
import json
from copy import deepcopy
from pathlib import Path
import sqlite3
from data.current_research_intraday_paper_ledger import review_intraday_paper_ledger,apply_intraday_paper_event
from data.current_research_intraday_continuation_ledger import SCHEMA as V2,review_continuation_ledger,apply_continuation_event
from data.current_research_intraday_retarget_ledger import SCHEMA as V3,apply_retarget_event
from data.current_research_intraday_retarget_evidence import SCHEMA as ENVELOPE,review_source_verified_retarget
from data.current_research_intraday_retarget_continuation_chain import (
    SCHEMA as CHAIN,LEDGER_SCHEMA as V4,review_retarget_continuation_chain,apply_retarget_chain_event)


def _require(ok,reason):
    if not ok:raise ValueError(reason)


class IntradayPaperStore:
    def __init__(self,directory):
        self.path=Path(directory)/'intraday_paper.sqlite3'

    def _connect(self,*,create=False):
        if create:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            return sqlite3.connect(str(self.path),timeout=10,isolation_level=None)
        _require(self.path.is_file(),'INTRADAY_PAPER_ACCOUNT_NOT_FOUND')
        return sqlite3.connect(self.path.resolve().as_uri()+'?mode=rw',uri=True,timeout=10,isolation_level=None)

    @staticmethod
    def _id(value):
        _require(isinstance(value,str) and bool(value.strip()),'EXPLICIT_ID_REQUIRED')

    @staticmethod
    def _encode(value):
        return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)

    @staticmethod
    def _schema(connection):
        connection.execute('CREATE TABLE IF NOT EXISTS intraday_accounts (account_id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE, state_json TEXT NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS intraday_continuations (operation_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, proposal_id TEXT NOT NULL, expected_revision TEXT NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS intraday_retargets (operation_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, proposal_id TEXT NOT NULL, expected_revision TEXT NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS intraday_retarget_chains (operation_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, proposal_id TEXT NOT NULL, expected_revision TEXT NOT NULL)')

    @staticmethod
    def _load_row(row,account_id):
        _require(row is not None,'INTRADAY_PAPER_ACCOUNT_NOT_FOUND')
        proposal_id,operation_id,encoded=row
        payload=json.loads(encoded)
        if payload.get('schema')==CHAIN:state=review_retarget_continuation_chain(payload)['ledger']
        else:state=review_source_verified_retarget(payload)['ledger'] if payload.get('schema')==ENVELOPE else payload
        _require(state['account_id']==account_id,'ACCOUNT_BINDING_MISMATCH')
        _require(state['acceptance']['proposal']['proposal_id']==proposal_id,'PROPOSAL_BINDING_MISMATCH')
        if state.get('schema') not in (V3,V4):review_continuation_ledger(state)
        else:_require(payload.get('schema')==(CHAIN if state.get('schema')==V4 else ENVELOPE),'RETARGET_SOURCE_ENVELOPE_REQUIRED')
        return state

    @staticmethod
    def _row(connection,account_id):
        return connection.execute('SELECT proposal_id,operation_id,state_json FROM intraday_accounts WHERE account_id=?',(account_id,)).fetchone()

    def accept(self,account_id,proposal_id,operation_id,factory):
        """Factory executes once under the write lock; it must obtain now there.

        Exact retries return current stored state without re-accepting an expired
        reference. This is local transactional idempotence, not a broker action.
        """
        for value in (account_id,proposal_id,operation_id):self._id(value)
        _require(callable(factory),'FACTORY_REQUIRED')
        with closing(self._connect(create=True)) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                self._schema(connection)
                row=self._row(connection,account_id)
                if row is not None:
                    _require(row[0]==proposal_id and row[1]==operation_id,'ACCOUNT_ALREADY_ACCEPTED')
                    state=self._load_row(row,account_id)
                else:
                    used=connection.execute('SELECT account_id FROM intraday_accounts WHERE operation_id=?',(operation_id,)).fetchone()
                    _require(used is None and connection.execute('SELECT 1 FROM intraday_continuations WHERE operation_id=?',(operation_id,)).fetchone() is None,'ACCEPT_OPERATION_ALREADY_USED')
                    _require(connection.execute('SELECT 1 FROM intraday_retargets WHERE operation_id=?',(operation_id,)).fetchone() is None,'ACCEPT_OPERATION_ALREADY_USED')
                    _require(connection.execute('SELECT 1 FROM intraday_retarget_chains WHERE operation_id=?',(operation_id,)).fetchone() is None,'ACCEPT_OPERATION_ALREADY_USED')
                    state=factory()
                    review_intraday_paper_ledger(state)
                    _require(state['account_id']==account_id and state['acceptance']['proposal']['proposal_id']==proposal_id,'FACTORY_BINDING_MISMATCH')
                    _require(not state['events'],'INITIAL_ACCEPTANCE_ONLY')
                    connection.execute('INSERT INTO intraday_accounts VALUES (?,?,?,?)',(account_id,proposal_id,operation_id,self._encode(state)))
                connection.commit();return state
            except Exception:
                connection.rollback();raise

    def accept_continuation(self,account_id,proposal_id,operation_id,expected_revision,factory):
        """factory(current_state) reads its clock after the transaction lock."""
        for value in (account_id,proposal_id,operation_id,expected_revision):self._id(value)
        _require(callable(factory),'FACTORY_REQUIRED')
        with closing(self._connect()) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                self._schema(connection)
                before=self._load_row(self._row(connection,account_id),account_id)
                prior=connection.execute('SELECT account_id,proposal_id,expected_revision FROM intraday_continuations WHERE operation_id=?',(operation_id,)).fetchone()
                if prior is not None:
                    _require(prior==(account_id,proposal_id,expected_revision),'CONFLICTING_CONTINUATION_OPERATION')
                    history=before['genesis'] if before.get('schema') in (V3,V4) else before
                    matches=[o for o in history.get('operations',[]) if o['kind']=='ACCEPT' and o['operation_id']==operation_id]
                    _require(len(matches)==1 and matches[0]['evidence']['proposal']['proposal_id']==proposal_id and matches[0]['expected_revision']==expected_revision,'CONTINUATION_RECEIPT_LINEAGE_MISMATCH')
                    connection.commit();return before
                _require(connection.execute('SELECT 1 FROM intraday_accounts WHERE operation_id=?',(operation_id,)).fetchone() is None,'INITIAL_OPERATION_ID_REUSED')
                _require(connection.execute('SELECT 1 FROM intraday_retargets WHERE operation_id=?',(operation_id,)).fetchone() is None,'RETARGET_OPERATION_ID_REUSED')
                _require(connection.execute('SELECT 1 FROM intraday_retarget_chains WHERE operation_id=?',(operation_id,)).fetchone() is None,'RETARGET_CHAIN_OPERATION_ID_REUSED')
                _require(before.get('schema') not in (V3,V4),'USE_RETARGET_CONTINUATION_REQUIRED')
                _require(before['revision']==expected_revision,'STALE_ACCOUNT_REVISION')
                after=factory(deepcopy(before))
                review_continuation_ledger(after)
                _require(after.get('schema')==V2 and after['account_id']==account_id and after['acceptance']==before['acceptance'],'CONTINUATION_ACCOUNT_BINDING_MISMATCH')
                old_operations=before.get('operations',[])
                _require(after['genesis']==(before['genesis'] if before.get('schema')==V2 else before)
                         and after['operations'][:-1]==old_operations and len(after['operations'])==len(old_operations)+1,'CONTINUATION_MUST_APPEND_ONE_ACCEPTANCE')
                last=after['operations'][-1]
                _require(last['kind']=='ACCEPT' and last['operation_id']==operation_id and last['expected_revision']==expected_revision
                         and last['evidence']['proposal']['proposal_id']==proposal_id,'CONTINUATION_OPERATION_BINDING_MISMATCH')
                _require(all(after[k]==before[k] for k in ('cash','shares','fees','events')),'CONTINUATION_CHANGED_ASSETS')
                connection.execute('UPDATE intraday_accounts SET state_json=? WHERE account_id=?',(self._encode(after),account_id))
                connection.execute('INSERT INTO intraday_continuations VALUES (?,?,?,?)',(operation_id,account_id,proposal_id,expected_revision))
                connection.commit();return after
            except Exception:
                connection.rollback();raise

    def accept_retarget(self,account_id,proposal_id,operation_id,expected_revision,factory):
        """Replace the same account row with a source envelope under one lock."""
        for value in (account_id,proposal_id,operation_id,expected_revision):self._id(value)
        _require(callable(factory),'FACTORY_REQUIRED')
        with closing(self._connect()) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                self._schema(connection)
                before=self._load_row(self._row(connection,account_id),account_id)
                prior=connection.execute('SELECT account_id,proposal_id,expected_revision FROM intraday_retargets WHERE operation_id=?',(operation_id,)).fetchone()
                if prior is not None:
                    _require(prior==(account_id,proposal_id,expected_revision),'CONFLICTING_RETARGET_OPERATION')
                    evidence=before.get('retarget_acceptance',{})
                    _require(before.get('schema') in (V3,V4) and evidence.get('operation_id')==operation_id
                        and evidence['proposal']['proposal_id']==proposal_id
                        and before['genesis']['revision']==expected_revision,'RETARGET_RECEIPT_LINEAGE_MISMATCH')
                    connection.commit();return before
                for table in ('intraday_accounts','intraday_continuations','intraday_retarget_chains'):
                    _require(connection.execute('SELECT 1 FROM '+table+' WHERE operation_id=?',(operation_id,)).fetchone() is None,'OPERATION_ID_ALREADY_USED')
                _require(before.get('schema') not in (V3,V4),'SECOND_RETARGET_NOT_SUPPORTED')
                _require(before['revision']==expected_revision,'STALE_ACCOUNT_REVISION')
                envelope=factory(deepcopy(before))
                review_source_verified_retarget(envelope)
                after=envelope['ledger'];evidence=after['retarget_acceptance']
                _require(after['account_id']==account_id and after['genesis']==before,'RETARGET_GENESIS_MISMATCH')
                _require(evidence['proposal']['proposal_id']==proposal_id and evidence['operation_id']==operation_id,'RETARGET_OPERATION_BINDING_MISMATCH')
                _require(not after['retarget_events'] and all(after[key]==before[key] for key in ('cash','shares','fees','events','acceptance','acceptance_id')),'RETARGET_CHANGED_ASSETS_OR_HISTORY')
                connection.execute('UPDATE intraday_accounts SET state_json=? WHERE account_id=?',(self._encode(envelope),account_id))
                connection.execute('INSERT INTO intraday_retargets VALUES (?,?,?,?)',(operation_id,account_id,proposal_id,expected_revision))
                connection.commit();return after
            except Exception:
                connection.rollback();raise

    def accept_retarget_chain(self,account_id,proposal_id,operation_id,expected_revision,factory):
        """factory(current complete payload) must obtain now inside this write lock.

        The original account row remains the sole owner of all assets. Exact
        successful retries return its latest ledger without invoking the factory.
        """
        for value in (account_id,proposal_id,operation_id,expected_revision):self._id(value)
        _require(callable(factory),'FACTORY_REQUIRED')
        with closing(self._connect()) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                self._schema(connection)
                row=self._row(connection,account_id);before=self._load_row(row,account_id)
                payload=json.loads(row[2])
                prior=connection.execute('SELECT account_id,proposal_id,expected_revision FROM intraday_retarget_chains WHERE operation_id=?',(operation_id,)).fetchone()
                if prior is not None:
                    _require(prior==(account_id,proposal_id,expected_revision),'CONFLICTING_RETARGET_CHAIN_OPERATION')
                    _require(payload.get('schema')==CHAIN,'RETARGET_CHAIN_RECEIPT_LINEAGE_MISMATCH')
                    matches=[o for o in payload['operations'] if o['kind']=='ACCEPT' and o['operation_id']==operation_id]
                    _require(len(matches)==1 and matches[0]['proposal']['proposal_id']==proposal_id and matches[0]['expected_revision']==expected_revision,'RETARGET_CHAIN_RECEIPT_LINEAGE_MISMATCH')
                    connection.commit();return before
                for table in ('intraday_accounts','intraday_continuations','intraday_retargets'):
                    _require(connection.execute('SELECT 1 FROM '+table+' WHERE operation_id=?',(operation_id,)).fetchone() is None,'OPERATION_ID_ALREADY_USED')
                _require(payload.get('schema') in (ENVELOPE,CHAIN),'RETARGET_SOURCE_ENVELOPE_REQUIRED')
                _require(before['revision']==expected_revision,'STALE_ACCOUNT_REVISION')
                after_payload=factory(deepcopy(payload))
                _require(after_payload.get('schema')==CHAIN,'RETARGET_CHAIN_REQUIRED')
                review_retarget_continuation_chain(after_payload);after=after_payload['ledger']
                old_operations=payload['operations'] if payload.get('schema')==CHAIN else []
                genesis=payload['genesis'] if payload.get('schema')==CHAIN else payload
                _require(after_payload['genesis']==genesis and after_payload['operations'][:-1]==old_operations and len(after_payload['operations'])==len(old_operations)+1,'CHAIN_MUST_APPEND_ONE_ACCEPTANCE')
                last=after_payload['operations'][-1]
                _require(last['kind']=='ACCEPT' and last['operation_id']==operation_id and last['expected_revision']==expected_revision and last['proposal']['proposal_id']==proposal_id,'RETARGET_CHAIN_OPERATION_BINDING_MISMATCH')
                _require(after['account_id']==account_id and all(after[k]==before[k] for k in ('cash','shares','fees','events','retarget_events','acceptance','acceptance_id','retarget_acceptance','retarget_acceptance_id','target_quantities','genesis')),'RETARGET_CHAIN_CHANGED_ASSETS_OR_HISTORY')
                connection.execute('UPDATE intraday_accounts SET state_json=? WHERE account_id=?',(self._encode(after_payload),account_id))
                connection.execute('INSERT INTO intraday_retarget_chains VALUES (?,?,?,?)',(operation_id,account_id,proposal_id,expected_revision))
                connection.commit();return after
            except Exception:
                connection.rollback();raise

    def read_retarget_envelope(self,account_id):
        self._id(account_id)
        _require(self.path.is_file(),'INTRADAY_PAPER_ACCOUNT_NOT_FOUND')
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10,isolation_level=None)) as connection:
            row=self._row(connection,account_id)
            state=self._load_row(row,account_id)
            _require(state.get('schema') in (V3,V4),'RETARGET_ACCEPTANCE_REQUIRED')
            return json.loads(row[2])

    def read(self,account_id):
        self._id(account_id)
        _require(self.path.is_file(),'INTRADAY_PAPER_ACCOUNT_NOT_FOUND')
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10,isolation_level=None)) as connection:
            exists=connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='intraday_accounts'").fetchone()
            _require(exists is not None,'INTRADAY_PAPER_ACCOUNT_NOT_FOUND')
            return self._load_row(self._row(connection,account_id),account_id)

    def record_event(self,account_id,event,*,now):
        """now may be a server clock callable, evaluated only after lock acquisition."""
        self._id(account_id)
        with closing(self._connect()) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                row=self._row(connection,account_id)
                before=self._load_row(row,account_id)
                _require(isinstance(event,dict),'EVENT_OBJECT_REQUIRED')
                if 'recorded_at' not in event:
                    for previous in before['events']:
                        if previous['event_id']==event.get('event_id'):
                            request={k:v for k,v in previous.items() if k!='recorded_at'}
                            _require(request==event,'CONFLICTING_EVENT_ID')
                            connection.commit();return before
                current_time=now() if callable(now) else now
                recorded=deepcopy(event)
                if 'recorded_at' not in recorded:recorded['recorded_at']=current_time.isoformat()
                if before.get('schema')==V4:
                    payload=apply_retarget_chain_event(json.loads(row[2]),recorded,now=current_time)
                    after=payload['ledger']
                else:
                    apply=apply_retarget_event if before.get('schema')==V3 else apply_continuation_event if before.get('schema')==V2 else apply_intraday_paper_event
                    after=apply(before,recorded,now=current_time)
                    payload=after
                if after!=before:
                    if before.get('schema')==V3:
                        payload=json.loads(row[2]);payload['ledger']=after
                        review_source_verified_retarget(payload)
                    connection.execute('UPDATE intraday_accounts SET state_json=? WHERE account_id=?',(self._encode(payload),account_id))
                connection.commit();return after
            except Exception:
                connection.rollback();raise
