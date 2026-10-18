"""Explicit isolated simulation persistence; no production defaults or scheduling.

STARTED survives process failure before transformation. Recovery commits only an
already persisted prepared result, never accepts arbitrary replacement output.
"""
from contextlib import contextmanager, closing
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import sqlite3

from backtest.current_quantity_v2_simulated_settlement import _rebuild
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require


def revision(simulation):
    _rebuild(simulation)
    return sha256(canonical(simulation)).hexdigest()


class SimulationStore:
    def __init__(self, path): self.path = Path(path)

    @staticmethod
    def _schema(connection, create=False):
        names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'")}
        expected={'isolated_simulations','isolated_simulation_operations'}
        require(names == expected or (create and not names), 'WRONG_SIMULATION_DATABASE')
        if not names:
            connection.execute('CREATE TABLE isolated_simulations (id TEXT PRIMARY KEY, revision TEXT NOT NULL, state TEXT NOT NULL)')
            connection.execute('CREATE TABLE isolated_simulation_operations (id TEXT PRIMARY KEY, simulation_id TEXT NOT NULL, expected_revision TEXT NOT NULL, request TEXT NOT NULL, status TEXT NOT NULL, result_revision TEXT, result_state TEXT, recovered INTEGER NOT NULL DEFAULT 0, recovery_evidence TEXT)')
        columns={r[1] for r in connection.execute('PRAGMA table_info(isolated_simulation_operations)')}
        require(columns=={'id','simulation_id','expected_revision','request','status','result_revision','result_state','recovered','recovery_evidence'}, 'SIMULATION_STORE_SCHEMA_VERSION_MISMATCH')

    @contextmanager
    def _transaction(self, create=False):
        require(create or self.path.is_file(), 'SIMULATION_DATABASE_NOT_FOUND')
        if create: self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10, isolation_level=None)) as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
                self._schema(connection, create)
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _load(connection, simulation_id):
        row=connection.execute('SELECT revision,state FROM isolated_simulations WHERE id=?',(simulation_id,)).fetchone()
        require(row is not None, 'SIMULATION_NOT_FOUND')
        state=json.loads(row[1])
        require(state['simulation_id']==simulation_id and revision(state)==row[0], 'SIMULATION_STORE_CHANGED')
        return dict(revision=row[0], simulation=state)

    def read(self, simulation_id):
        require(self.path.is_file(), 'SIMULATION_DATABASE_NOT_FOUND')
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as connection:
            self._schema(connection)
            return self._load(connection,simulation_id)

    def create(self, simulation):
        digest=revision(simulation); sid=simulation['simulation_id']
        with self._transaction(create=True) as connection:
            existing=connection.execute('SELECT revision FROM isolated_simulations WHERE id=?',(sid,)).fetchone()
            require(existing is None or existing[0]==digest, 'SIMULATION_ALREADY_EXISTS')
            if existing is None:
                connection.execute('INSERT INTO isolated_simulations VALUES(?,?,?)',(sid,digest,canonical(simulation).decode()))
            return self._load(connection,sid)

    def inspect_operations(self, simulation_id):
        """Read a consistent recovery inventory without creating or changing the DB.

        Status is evidence of persistence only; STARTED/FAILED are not permission
        to repeat a capture or search. Recovery still uses the original request.
        """
        require(self.path.is_file(), 'SIMULATION_DATABASE_NOT_FOUND')
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as connection:
            connection.execute('BEGIN')
            self._schema(connection)
            current = self._load(connection, simulation_id)
            rows = connection.execute(
                'SELECT id,expected_revision,request,status,result_revision,recovered,recovery_evidence '
                'FROM isolated_simulation_operations WHERE simulation_id=? ORDER BY rowid',
                (simulation_id,)).fetchall()
            operations = []
            for identifier, expected, request, status, result, recovered, evidence in rows:
                require(status in ('STARTED', 'FAILED', 'PREPARED', 'COMPLETE'), 'INVALID_OPERATION_STATUS')
                operations.append(dict(operation_id=identifier, expected_revision=expected,
                    request=json.loads(request), status=status, result_revision=result,
                    recovered=bool(recovered), recovery_evidence=json.loads(evidence) if evidence else None))
            return dict(simulation_id=simulation_id, revision=current['revision'], operations=operations)

    @staticmethod
    def _operation(connection, operation_id, simulation_id, expected_revision, request):
        row=connection.execute('SELECT simulation_id,expected_revision,request,status,result_revision,result_state,recovered FROM isolated_simulation_operations WHERE id=?',(operation_id,)).fetchone()
        if row is not None:
            require(row[:3]==(simulation_id,expected_revision,canonical(request).decode()), 'SIMULATION_OPERATION_CONFLICT')
        return row

    def apply(self, *, simulation_id, expected_revision, operation_id, request, transform):
        require(type(operation_id)is str and operation_id.strip(), 'SIMULATION_OPERATION_ID_REQUIRED')
        require(type(request)is dict and type(request.get('kind'))is str and request['kind'].strip(), 'SIMULATION_OPERATION_KIND_REQUIRED')
        # Commit intent before any search/capture; a crashed process cannot make
        # the next process believe the economic operation never happened.
        with self._transaction() as connection:
            operation=self._operation(connection,operation_id,simulation_id,expected_revision,request)
            state=self._load(connection,simulation_id)
            if operation is not None:
                require(operation[3]=='COMPLETE', 'SIMULATION_OPERATION_INCOMPLETE_NO_AUTOMATIC_RETRY')
                return dict(state,operation_result_revision=operation[4],operation_id=operation_id,replayed=True,recovered=bool(operation[6]))
            require(state['revision']==expected_revision, 'STALE_SIMULATION_REVISION')
            require(connection.execute("SELECT 1 FROM isolated_simulation_operations WHERE simulation_id=? AND status!='COMPLETE'",(simulation_id,)).fetchone() is None,
                    'SIMULATION_OPERATION_PENDING')
            connection.execute('INSERT INTO isolated_simulation_operations (id,simulation_id,expected_revision,request,status) VALUES(?,?,?,?,?)',
                (operation_id,simulation_id,expected_revision,canonical(request).decode(),'STARTED'))
        try:
            result=transform(deepcopy(state['simulation']))
            self._prepare_result(simulation_id=simulation_id,expected_revision=expected_revision,
                operation_id=operation_id,request=request,simulation=result)
            return self._commit(simulation_id=simulation_id,expected_revision=expected_revision,
                operation_id=operation_id,request=request,recovered=False)
        except Exception:
            with self._transaction() as connection:
                connection.execute("UPDATE isolated_simulation_operations SET status='FAILED' WHERE id=? AND status='STARTED'",(operation_id,))
            raise

    def _prepare_result(self, *, simulation_id, expected_revision, operation_id, request, simulation, recovery_evidence=None):
        result_revision=revision(simulation)
        with self._transaction() as connection:
            operation=self._operation(connection,operation_id,simulation_id,expected_revision,request)
            require(operation is not None and (operation[3]=='STARTED' or
                    (operation[3]=='FAILED' and recovery_evidence is not None)), 'SIMULATION_OPERATION_NOT_STARTED')
            current=self._load(connection,simulation_id)
            require(current['revision']==expected_revision, 'STALE_SIMULATION_REVISION')
            before=current['simulation']
            require(simulation['simulation_id']==simulation_id and simulation['origin']==before['origin']
                    and simulation['model']==before['model']
                    and simulation['batches'][:len(before['batches'])]==before['batches'],
                    'SIMULATION_HISTORY_REWRITE')
            if 'valuation' in before:
                require(simulation.get('valuation',{}).get('registration')==before['valuation']['registration'],
                        'SIMULATION_HISTORY_REWRITE')
            connection.execute("UPDATE isolated_simulation_operations SET status='PREPARED',result_revision=?,result_state=?,recovery_evidence=? WHERE id=?",
                (result_revision,canonical(simulation).decode(),canonical(recovery_evidence).decode() if recovery_evidence is not None else None,operation_id))

    def recover_monthly(self, *, simulation_id, expected_revision, operation_id, request):
        """Import only this operation's bound external monthly result, read-only."""
        with self._transaction() as connection:
            operation=self._operation(connection,operation_id,simulation_id,expected_revision,request)
            require(operation is not None, 'SIMULATION_OPERATION_NOT_STARTED')
            current=self._load(connection,simulation_id)
            pending=operation[3] not in ('COMPLETE','PREPARED')
            if pending:require(current['revision']==expected_revision, 'STALE_SIMULATION_REVISION')
        if pending:
            from backtest.current_quantity_v2_monthly_simulation import read_bound_monthly_result
            simulation,evidence=read_bound_monthly_result(request,current['simulation'],expected_revision)
            self._prepare_result(simulation_id=simulation_id,expected_revision=expected_revision,
                operation_id=operation_id,request=request,simulation=simulation,recovery_evidence=evidence)
        return self.recover(simulation_id=simulation_id,expected_revision=expected_revision,
            operation_id=operation_id,request=request)

    def recover(self, *, simulation_id, expected_revision, operation_id, request):
        """Commit this attempt's persisted output only; no computation or input replacement."""
        return self._commit(simulation_id=simulation_id,expected_revision=expected_revision,
            operation_id=operation_id,request=request,recovered=True)

    def _commit(self, *, simulation_id, expected_revision, operation_id, request, recovered):
        with self._transaction() as connection:
            operation=self._operation(connection,operation_id,simulation_id,expected_revision,request)
            require(operation is not None, 'SIMULATION_OPERATION_NOT_STARTED')
            current=self._load(connection,simulation_id)
            if operation[3]=='COMPLETE':
                return dict(current,operation_result_revision=operation[4],operation_id=operation_id,
                            replayed=True,recovered=bool(operation[6]))
            require(operation[3]=='PREPARED', 'SIMULATION_PREPARED_RESULT_UNAVAILABLE')
            require(current['revision']==expected_revision, 'STALE_SIMULATION_REVISION')
            simulation=json.loads(operation[5])
            require(revision(simulation)==operation[4], 'SIMULATION_PREPARED_RESULT_CHANGED')
            connection.execute('UPDATE isolated_simulations SET revision=?,state=? WHERE id=?',
                (operation[4],operation[5],simulation_id))
            connection.execute("UPDATE isolated_simulation_operations SET status='COMPLETE',recovered=? WHERE id=?",(int(recovered),operation_id))
            return dict(revision=operation[4],simulation=simulation,operation_result_revision=operation[4],
                        operation_id=operation_id,replayed=False,recovered=recovered)
