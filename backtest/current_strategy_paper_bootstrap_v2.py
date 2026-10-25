"""Explicit create-once initialization for an already registered V2 paper study."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
from contextlib import closing

from core.strategy_account_ledger import canonical
from data.strategy_paper_application_descriptor_v2 import require, stamp
from data.strategy_daily_session_capture import reject_links
from backtest.current_strategy_prospective_paper_book_v2 import _context
from backtest.current_strategy_prospective_paper_admission_store_v2 import ProspectivePaperAdmissionStore
from backtest.current_strategy_prospective_paper_admission_reader_v2 import registered_selection
from backtest.current_strategy_prospective_paper_coordinator_v2 import ProspectivePaperCoordinator
from data.strategy_prospective_paper_selection_v2 import verify_prospective_target
from data.strategy_prospective_paper_cap_store_v2 import ProspectivePersistentCaps

SOURCE='backtest/current_strategy_paper_bootstrap_v2.py'


def initialize_registered_paper(*,root,authority,clock=None,fault=None):
    clock=clock or (lambda:datetime.now(timezone.utc));fault=fault or (lambda phase:None)
    root=Path(root).absolute();reject_links(root)
    app=_context(authority,clock())
    require(SOURCE in app['code_sha256'],'PAPER_BOOTSTRAP_CODE_PIN_REQUIRED')
    namespace=(root/app['storage']['ledger']).parent
    started=namespace/'bootstrap.started.json';complete=namespace/'bootstrap.complete.json'
    failed=namespace/'bootstrap.failed.json'
    for path in (namespace,started,complete,failed):reject_links(path)
    owner=dict(account_id=app['account_id'],descriptor_sha256=authority['descriptor_arguments']['trusted_descriptor_sha256'],
               registration_sha256=authority['trusted_registration_sha256'])
    def save(path,value):
        with path.open('xb') as stream:
            stream.write(canonical(value));stream.flush();os.fsync(stream.fileno())
    store=ProspectivePaperAdmissionStore(root=root,authority=authority,clock=clock)
    def verify(result):
        saved=registered_selection(store,result['decision_id'])
        require(saved['selection_result']==result,'PAPER_BOOTSTRAP_TARGET_CHANGED')
        return verify_prospective_target(result,**saved['selection_arguments'])
    coordinator=ProspectivePaperCoordinator(root=root,authority=authority,
        admission_loader=store.load,target_verifier=verify,clock=clock)
    risk_path=root/app['storage']['evidence']/'risk.sqlite3'
    if complete.exists():
        require(not failed.exists() and json.loads(store._read(complete))['owner']==owner,
                'PAPER_BOOTSTRAP_RECOVERY_REQUIRED')
        book=coordinator.read()
        require(risk_path.is_file(),'PAPER_BOOTSTRAP_RISK_MISSING')
        caps=ProspectivePersistentCaps(root=root,book=book,authority=authority,
            admitted_decisions=store.load()['decisions'],admitted_settlements=store.load()['settlements'],clock=clock)
        caps.close()
        return dict(status='ALREADY_INITIALIZED',account_id=book['account_id'])
    require(not started.exists() and not failed.exists(),'PAPER_BOOTSTRAP_RECOVERY_REQUIRED')
    first=app['plan']['first_session'];now=stamp(clock())
    require(stamp(first['decision_at'])<=now<stamp(first['decision_until']),'PAPER_BOOTSTRAP_OUTSIDE_FIRST_WINDOW')
    for key in ('ledger','targets','caps','evidence'):
        path=root/app['storage'][key];reject_links(path)
        require(not path.exists(),'PAPER_BOOTSTRAP_EXISTING_STATE')
    namespace.mkdir(parents=True,exist_ok=True)
    save(started,dict(owner=owner,started_at=now.isoformat()))
    try:
        store.initialize();book=coordinator.initialize();fault('after_book')
        caps=ProspectivePersistentCaps(root=root,book=book,authority=authority,
            admitted_decisions={},admitted_settlements={},clock=clock,initialize=True)
        caps.close()
        with risk_path.open('xb'):pass
        with closing(sqlite3.connect(risk_path)) as connection:
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('CREATE TABLE risk_state(account_id TEXT PRIMARY KEY,state TEXT NOT NULL)')
            connection.commit()
        require(coordinator.read()==book,'PAPER_BOOTSTRAP_READBACK')
        finished=stamp(clock());_context(authority,finished)
        require(now<=finished<stamp(first['decision_until']),'PAPER_BOOTSTRAP_WINDOW_EXPIRED')
        save(complete,dict(owner=owner,completed_at=finished.isoformat(),initial_revision=book['revision']))
        return dict(status='INITIALIZED',account_id=book['account_id'],cash=book['cash'],orders_created=False)
    except BaseException as error:
        save(failed,dict(owner=owner,error=type(error).__name__,reason=str(error)))
        raise
