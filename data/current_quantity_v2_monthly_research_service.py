"""Explicit monthly research orchestration; no singleton, network or paper writes.

Lock order for publishing selections is paper DB -> selection DB. Compilation and
worker execution hold neither lock. Registered research is not an accepted order.
"""
from contextlib import closing
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from data.current_quantity_v2_difference_service import document
import sqlite3
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require,stamp
from data.current_quantity_v2_monthly_training import build_monthly_training_package
from data.current_quantity_v2_paper_chain import review_chain
from hashlib import sha256
from data.current_quantity_projection_v2 import project_capital_decision_v2


def _digest(value):return sha256(canonical(value)).hexdigest()


_SAFE_FAILURES=frozenset(('MONTHLY_TRAINING_READER_CONTRACT','MONTHLY_RESEARCH_ACCOUNT_CHANGED',
    'MONTHLY_RESEARCH_SUPERSEDED','MONTHLY_RESEARCH_EXPIRED','MONTHLY_ATTEMPT_IN_PROGRESS_OR_RETRY_REQUIRED',
    'MONTHLY_CONFIGURATION_REQUIRED','MONTHLY_TRAINING_ENTRY_REQUIRED','STALE_REVISION'))


def _safe_failure(error):
    if isinstance(error,ValueError) and str(error) in _SAFE_FAILURES:return str(error)
    for kind,code in ((TimeoutError,'SOURCE_TIMEOUT'),(OSError,'SOURCE_IO_ERROR'),
                      (ValueError,'SOURCE_VALIDATION_FAILED'),(KeyError,'SOURCE_FIELD_MISSING'),
                      (TypeError,'SOURCE_TYPE_INVALID')):
        if isinstance(error,kind):return code
    return 'MONTHLY_RESEARCH_INTERNAL_FAILURE'



class QuantityV2MonthlyResearchService:
    def __init__(self,*,store,registry,selection_root,training_reader=None,clock=lambda:datetime.now(timezone.utc)):
        self.store=store;self.registry=registry;self.path=Path(selection_root)/'monthly_research_selection.sqlite3'
        self.training_reader=training_reader;self.clock=clock

    def _connection(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        con=sqlite3.connect(self.path,timeout=10,isolation_level=None)
        try:
            con.execute('BEGIN IMMEDIATE')
            tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'")}
            require(tables<= {'monthly_selection','monthly_attempt_events'},'WRONG_MONTHLY_SELECTION_DATABASE')
            con.execute('CREATE TABLE IF NOT EXISTS monthly_selection(account_id TEXT PRIMARY KEY, attempt INTEGER NOT NULL, chain_hash TEXT NOT NULL, status TEXT NOT NULL, registration_id TEXT, reason TEXT)')
            con.execute('CREATE TABLE IF NOT EXISTS monthly_attempt_events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, attempt INTEGER NOT NULL, chain_hash TEXT NOT NULL, state_revision TEXT NOT NULL, request_month TEXT NOT NULL, recorded_at TEXT NOT NULL, phase TEXT NOT NULL, status TEXT NOT NULL, registration_id TEXT, reason TEXT, UNIQUE(account_id,attempt,phase))')
            con.execute("CREATE TRIGGER IF NOT EXISTS monthly_attempt_events_no_update BEFORE UPDATE ON monthly_attempt_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_ATTEMPT_EVENTS'); END")
            con.execute("CREATE TRIGGER IF NOT EXISTS monthly_attempt_events_no_delete BEFORE DELETE ON monthly_attempt_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_ATTEMPT_EVENTS'); END")
            return con
        except BaseException:con.rollback();con.close();raise

    def _get(self,account_id):
        if not self.path.exists():return None
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as con:
            return con.execute('SELECT attempt,chain_hash,status,registration_id,reason FROM monthly_selection WHERE account_id=?',(account_id,)).fetchone()

    def _begin(self,account_id,expected_revision):
        with self.store.transaction() as paper:
            state=self.store.load(paper,account_id);require(state['ledger']['revision']==expected_revision,'STALE_REVISION')
            with closing(self._connection()) as con:
                row=con.execute('SELECT attempt FROM monthly_selection WHERE account_id=?',(account_id,)).fetchone();attempt=1 if row is None else row[0]+1
                con.execute('INSERT INTO monthly_selection VALUES(?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET attempt=excluded.attempt,chain_hash=excluded.chain_hash,status=excluded.status,registration_id=NULL,reason=NULL',(account_id,attempt,_digest(state),'PENDING',None,None))
                self._event(con,account_id,attempt,'STARTED','PENDING',chain_hash=_digest(state),state_revision=state['ledger']['revision'])
                con.commit()
        return state,attempt

    def _event(self,con,account_id,attempt,phase,status,registration_id=None,reason=None,chain_hash=None,state_revision=None):
        require(phase in ('STARTED','TERMINAL'),'INVALID_ATTEMPT_EVENT_PHASE')
        if phase=='TERMINAL':
            start=con.execute("SELECT chain_hash,state_revision,request_month FROM monthly_attempt_events WHERE account_id=? AND attempt=? AND phase='STARTED'",(account_id,attempt)).fetchone()
            require(start is not None,'ATTEMPT_START_EVENT_MISSING')
            chain_hash,state_revision,request_month=start
        else:
            request_month=None
        payload=(chain_hash,status,registration_id,reason)
        existing=con.execute('SELECT chain_hash,status,registration_id,reason FROM monthly_attempt_events WHERE account_id=? AND attempt=? AND phase=?',(account_id,attempt,phase)).fetchone()
        if existing is not None:
            require(existing==payload,'ATTEMPT_TERMINAL_CONFLICT')
            return  # Idempotent terminal retry retains its original server time.
        now=stamp(self.clock())
        recorded=now.astimezone(timezone.utc).isoformat()
        if phase=='STARTED':request_month=now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
        con.execute('INSERT INTO monthly_attempt_events(account_id,attempt,chain_hash,state_revision,request_month,recorded_at,phase,status,registration_id,reason) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (account_id,attempt,chain_hash,state_revision,request_month,recorded,phase,status,registration_id,reason))

    def _fail(self,account_id,attempt,reason,event_reason=None):
        with closing(self._connection()) as con:
            self._event(con,account_id,attempt,'TERMINAL','FAILED',reason=event_reason or 'MONTHLY_RESEARCH_INTERNAL_FAILURE')
            con.execute("UPDATE monthly_selection SET status='FAILED',registration_id=NULL,reason=? WHERE account_id=? AND attempt=?",(reason,account_id,attempt));con.commit()

    def history(self,*,account_id):
        """Read recorded attempts only; absence of events is not a success claim.

        Older selections predate this journal and are not backfilled. Reads never
        initialize/migrate the DB or invoke the account, worker, reader or clock.
        """
        require(type(account_id)is str and bool(account_id.strip()),'INVALID_MONTHLY_RESEARCH_REQUEST')
        empty=dict(events=[],coverage='NO_RECORDED_HISTORY; EARLIER_ATTEMPTS_UNKNOWN',coverage_started_at=None,legacy_history_complete=False,worker_liveness='UNKNOWN',terminal_scope='SERVICE_REQUEST_COMPLETED_NOT_WORKER_TERMINATION')
        if not self.path.exists():return empty
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as con:
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='monthly_attempt_events'").fetchone() is None:return dict(empty,coverage='LEGACY_DATABASE_WITHOUT_ATTEMPT_HISTORY')
            rows=con.execute('SELECT event_id,account_id,attempt,chain_hash,state_revision,request_month,recorded_at,phase,status,registration_id,reason FROM monthly_attempt_events WHERE account_id=? ORDER BY event_id',(account_id,)).fetchall()
        keys=('event_id','account_id','attempt','chain_hash','state_revision','request_month','recorded_at','phase','status','registration_id','reason')
        events=[dict(zip(keys,row)) for row in rows]
        return dict(events=events,coverage='RECORDED_EVENTS_ONLY; EARLIER_ATTEMPTS_UNKNOWN',
                    coverage_started_at=events[0]['recorded_at'] if events else None,legacy_history_complete=False,
                    worker_liveness='UNKNOWN',terminal_scope='SERVICE_REQUEST_COMPLETED_NOT_WORKER_TERMINATION')

    @staticmethod
    def _public(result,selected):
        decision=result.get('capital_decision') if result['status']=='READY' else None
        portfolio=None
        if decision is not None:
            view=project_capital_decision_v2(decision)
            portfolio={k:deepcopy(view[k]) for k in ('as_of','available_cash_exact','investable_equity_exact','allocation_basis','target_quantities')}
            portfolio['stocks']=[{k:deepcopy(row[k]) for k in ('security_id','ticker','units','close','notional','target_weight','actual_weight') if k in row} for row in view['stocks']]
            from fractions import Fraction
            portfolio['frozen_dollar_allocations_exact']={sid:str(Fraction(decision['binding']['search_arguments']['prices'][sid])*quantity) for sid,quantity in decision['target_quantities'].items()}
            portfolio['executable_buy_quantities']=None
            portfolio['quantity_scope']='HISTORICAL_DECISION_REFERENCE_NOT_CURRENT_EXECUTION_TARGET'
        return dict(status=result['status'],account_id=result['account_id'],expected_revision=result['state_revision'],state_revision=result['state_revision'],target_month=result['target_month'],
            registration_id=result['registration_id'],decision_id=decision['decision_id'] if decision else None,research_id=decision['research_id'] if decision else None,
            selected_for_current_account=bool(selected),research_only=True,execution_blocked=True,real_account=False,account_mutated=False,orders_created=False,
            automatic_retry=False,worker_liveness='UNKNOWN',portfolio=portfolio,reason=('MONTHLY_RESEARCH_INCOMPLETE' if result['status']=='INCOMPLETE' else 'MONTHLY_RESEARCH_ATTEMPT_UNFINISHED' if result['status']=='ATTEMPT_STARTED' else 'MONTHLY_RESEARCH_FAILED' if result['status']=='FAILED' else None))

    def generate(self,*,account_id,expected_revision,retry_failed=False):
        require(type(account_id)is str and bool(account_id.strip()) and type(expected_revision)is str and bool(expected_revision) and type(retry_failed)is bool,'INVALID_MONTHLY_RESEARCH_REQUEST')
        require(callable(self.training_reader),'MONTHLY_RESEARCH_UNAVAILABLE')
        state,attempt=self._begin(account_id,expected_revision)
        try:
            supplied=deepcopy(self.training_reader(deepcopy(state)))
            require(type(supplied)is dict and set(supplied)=={'source_package','manifest_path','calendar_path','account_review_path','identities_path','held_bar_sources'},'MONTHLY_TRAINING_READER_CONTRACT')
            package=build_monthly_training_package(state,**supplied,now=stamp(self.clock()))
            require(self.store.read(account_id)==state,'MONTHLY_RESEARCH_ACCOUNT_CHANGED')
            row=self._get(account_id);require(row is not None and row[0]==attempt,'MONTHLY_RESEARCH_SUPERSEDED')
            result=self.registry.generate(state,package,retry_failed=retry_failed)
            # Freeze publication while the actual account cannot change. No paper
            # rows are written, and no source callback is called under either DB lock.
            with self.store.transaction() as paper:
                require(self.store.load(paper,account_id)==state,'MONTHLY_RESEARCH_ACCOUNT_CHANGED')
                with closing(self._connection()) as con:
                    row=con.execute('SELECT attempt FROM monthly_selection WHERE account_id=?',(account_id,)).fetchone()
                    require(row is not None and row[0]==attempt,'MONTHLY_RESEARCH_SUPERSEDED')
                    final_now=stamp(self.clock());calendar=document(package['files'][package['documents']['calendar']])
                    require(final_now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')==result['target_month'] and stamp(calendar['active_open_at'])<=final_now,'MONTHLY_RESEARCH_EXPIRED')
                    self._event(con,account_id,attempt,'TERMINAL',result['status'],registration_id=result['registration_id'] if result['status'] in ('READY','INCOMPLETE') else None)
                    con.execute('UPDATE monthly_selection SET status=?,registration_id=?,reason=NULL WHERE account_id=? AND attempt=?',(result['status'],result['registration_id'] if result['status'] in ('READY','INCOMPLETE') else None,account_id,attempt));con.commit()
            return self._public(result,result['status']=='READY')
        except Exception as error:
            self._fail(account_id,attempt,type(error).__name__,_safe_failure(error))
            if isinstance(error,ValueError) and str(error) in ('STALE_REVISION','MONTHLY_RESEARCH_ACCOUNT_CHANGED','MONTHLY_RESEARCH_SUPERSEDED','MONTHLY_RESEARCH_EXPIRED','MONTHLY_ATTEMPT_IN_PROGRESS_OR_RETRY_REQUIRED'):raise
            raise ValueError('MONTHLY_RESEARCH_UNAVAILABLE') from error

    def read(self,*,account_id,registration_id):
        state=review_chain(self.store.read(account_id));result=self.registry.read(registration_id,state)
        require(result['account_id']==account_id,'ACCOUNT_BINDING_MISMATCH')
        row=self._get(account_id)
        selected=row is not None and row[1]==_digest(state) and row[2]=='READY' and row[3]==registration_id
        return self._public(result,selected)

    def current(self,*,account_id):
        """Recover the last explicit attempt, not proof that a worker is alive."""
        state=review_chain(self.store.read(account_id));row=self._get(account_id)
        if row is not None and row[1]==_digest(state) and row[2] in ('READY','INCOMPLETE') and row[3]:
            result=self.read(account_id=account_id,registration_id=row[3])
            require(self._get(account_id)==row,'MONTHLY_RESEARCH_SUPERSEDED')
            return result
        status='UNAVAILABLE' if row is None or row[1]!=_digest(state) or row[2] not in ('PENDING','FAILED') else row[2]
        return dict(status=status,account_id=account_id,expected_revision=state['ledger']['revision'],state_revision=state['ledger']['revision'],target_month=None,
            registration_id=None,decision_id=None,research_id=None,selected_for_current_account=False,
            research_only=True,execution_blocked=True,real_account=False,account_mutated=False,orders_created=False,
            worker_liveness='UNKNOWN',automatic_retry=False,portfolio=None,reason='MONTHLY_RESEARCH_SELECTION_UNAVAILABLE' if status=='UNAVAILABLE' else 'MONTHLY_RESEARCH_ATTEMPT_UNFINISHED' if status=='PENDING' else 'MONTHLY_RESEARCH_FAILED')

    def decision_reader(self,state):
        """Current explicit selection only. Caller already holds/verified paper state."""
        state=review_chain(state);aid=state['ledger']['account_id'];row=self._get(aid)
        require(row is not None and row[1]==_digest(state) and row[2]=='READY' and row[3] is not None,'MONTHLY_RESEARCH_SELECTION_UNAVAILABLE')
        package=self.registry.decision_package(row[3],state)
        require(self._get(aid)==row,'MONTHLY_RESEARCH_SUPERSEDED')
        return package
