"""Candidate addon to existing ROA cash route. No alternate cash endpoint."""
from contextlib import contextmanager, closing
from datetime import datetime, timedelta
from threading import Lock
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse
from starlette.concurrency import run_in_threadpool
from core.strategy_account_ledger import apply_event
from .audit import audit_cash_changes
from .validation import validate_classification
from .store import ClassificationService
from .profit import amount_profit


class FlowAddon:
    def __init__(self, *, roa_service, root, configuration, clock):
        if set(configuration)!={'schema','baseline','ledger','sidecar_path'} or configuration['schema']!='ROA_FLOW_CLASSIFICATION_CONFIG_V1':raise ValueError('FLOW_CONFIG_FIELDS')
        self.roa=roa_service;self.account=roa_service.account_service;self.root=Path(root).resolve();self.config=configuration;self.clock=clock
        self.profit_lock=Lock()
        self.store=ClassificationService(path=self.local(configuration['sidecar_path']),account_id=self.account.account_id,
            read_accounts=lambda:(self.baseline()[1],self.account.audit_state()),account_operation=self.operation,
            receipt_resolver=self.receipt,performance_baseline_at=datetime.fromisoformat(self.baseline()[0]['effective_at']),clock=clock)
    def local(self,name):
        if type(name)is not str or not name.startswith('data/strategy_account/') or '\\' in name or ':' in name or any(part in ('','.','..') for part in name.split('/')):raise ValueError('FLOW_PATH_INVALID')
        raw=self.root/name
        if any(p.is_symlink() for p in [raw,*raw.parents]):raise ValueError('FLOW_PATH_INVALID')
        path=raw.resolve()
        if not path.is_relative_to(self.root/'data/strategy_account'):raise ValueError('FLOW_PATH_INVALID')
        return path
    def baseline(self):
        documents=[]
        for key in ('baseline','ledger'):
            ref=self.config[key];raw=self.local(ref['path']).read_bytes()
            if sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('BASELINE_SOURCE_CHANGED')
            documents.append(json.loads(raw))
        return documents
    @contextmanager
    def operation(self):
        # Shared ROA lock plus short read transaction prevents an independent
        # account writer committing between account read and sidecar commit.
        # It is NOT a distributed atomic transaction; no account writes occur.
        with self.roa.lock:
            with closing(sqlite3.connect(self.account.store.path.as_uri()+'?mode=ro',uri=True,isolation_level=None,timeout=10)) as connection:
                if connection.execute('PRAGMA journal_mode').fetchone()[0].lower()!='delete':raise ValueError('ACCOUNT_JOURNAL_MODE_UNSUPPORTED')
                connection.execute('BEGIN');connection.execute('SELECT revision FROM strategy_meta').fetchone()
                try:yield
                finally:connection.rollback()
    def receipt(self,account_id,event_id):
        if account_id!=self.account.account_id:raise ValueError('ACCOUNT_MISMATCH')
        with closing(sqlite3.connect(self.account.store.path.as_uri()+'?mode=ro',uri=True)) as connection:
            row=connection.execute('SELECT received_at FROM strategy_events WHERE event_id=?',(event_id,)).fetchone()
        return datetime.fromisoformat(row[0]) if row else None
    def records(self):
        with closing(sqlite3.connect(self.store.path.resolve().as_uri()+'?mode=ro',uri=True)) as connection:
            rows=connection.execute('SELECT cash_event_id,payload FROM classifications WHERE account_id=? ORDER BY cash_event_id',(self.account.account_id,)).fetchall()
        return {event:json.loads(payload) for event,payload in rows}
    def validate_existing(self,document,baseline_account,current,baseline):
        result=validate_classification(baseline=baseline_account,current=current,document=document,now=self.clock())
        received=self.receipt(current['account_id'],document['cash_event_id'])
        if received is None or received.utcoffset() is None:raise ValueError('TRUSTED_CONFIRMATION_RECEIPT_REQUIRED')
        times=[datetime.fromisoformat(item['effective_at']) for item in document['items']]
        if any(t>received for t in times):raise ValueError('FLOW_AFTER_CASH_CONFIRMATION')
        if any(t<datetime.fromisoformat(baseline['effective_at']) for t in times):raise ValueError('PRE_BASELINE_FACT_RECONCILIATION_REQUIRED')
        return result
    def current(self, *, include_profit=False, _transfer_checked=False):
        if not _transfer_checked and getattr(self,'transfer_reconciliation',None) is not None:
            return self.transfer_reconciliation.cash_view(include_profit=include_profit)
        with self.operation():
            baseline,old=self.baseline();current=self.account.audit_state();documents=self.records()
            audit=audit_cash_changes(baseline=old,current=current);state=old;revisions={}
            for record in current['events'][len(old['events']):]:
                before=state['revision'];state,_=apply_event(state,record['payload'],expected_revision=before);revisions[record['payload']['event_id']]=(before,state['revision'])
            unresolved=[];classified=[];blocked=None
            for row in audit['confirmations']:
                row['before_revision'],row['after_revision']=revisions[row['event_id']]
                row['received_at']=self.receipt(current['account_id'],row['event_id']).isoformat();row['received_at_scope']='RECORDING_TIME_NOT_FLOW_TIME'
                document=documents.get(row['event_id'])
                if document:
                    row['document']=document;row['document_sha256']=sha256(json.dumps(document,sort_keys=True,separators=(',',':')).encode()).hexdigest();row['classification_state']='CLASSIFIED'
                    classified.append(row)
                    try:
                        result=self.validate_existing(document,old,current,baseline)
                        if result['performance_blocked']:blocked=result['performance_reason'];row['classification_state']='REPAIR_REQUIRED'
                    except ValueError as error:blocked=str(error);row['classification_state']='REPAIR_REQUIRED'
                elif row['unexplained_net_change']!='0':unresolved.append(row)
        # No account/ROA lock held during network valuation.
        profit=None;reason=blocked;valid_until=None
        if not unresolved and blocked is None:
            try:
                if not include_profit:reason='VALUATION_PENDING'
                else:
                    valuation=self.account.valuation()
                    profit=amount_profit(baseline=baseline,baseline_account=old,current_account=current,valuation=valuation,classifications=documents,now=self.clock())
                    times=[datetime.fromisoformat(valuation['valued_at'])]+[datetime.fromisoformat(r['observed_at'].replace('Z','+00:00')) for r in valuation['holdings']]
                    valid_until=(min(times)+timedelta(seconds=120)).isoformat()
            except ValueError as error:reason=str(error)
        elif unresolved:reason='UNCLASSIFIED_CASH_CHANGE'
        with self.operation():
            if self.account.audit_state()!=current or self.records()!=documents or self.baseline()!=[baseline,old]:raise ValueError('STALE_PERFORMANCE_SNAPSHOT')
        return dict(classifications_sha256=sha256(json.dumps(documents,sort_keys=True,separators=(',',':')).encode()).hexdigest(),profit_valid_until=valid_until,account_id=current['account_id'],revision=current['revision'],unresolved=unresolved,classified=classified,profit=profit,performance_reason=reason,return_fraction=None,maximum_drawdown_fraction=None,account_mutated=False)
    def profit_current(self):
        if not self.profit_lock.acquire(blocking=False):raise ValueError('VALUATION_ALREADY_RUNNING')
        try:return self.current(include_profit=True)
        finally:self.profit_lock.release()
    def save(self,body):
        reconciliation=getattr(self,'transfer_reconciliation',None)
        if reconciliation is not None and reconciliation.read()['transfer_events']:
            raise ValueError('USE_TRANSFER_RECONCILIATION')
        if set(body) not in ({'expected_revision','document'},{'expected_revision','document','expected_document_sha256'}):raise ValueError('BODY_FIELDS')
        result=self.store.save(**body)
        return dict(result,account_revision=body['expected_revision'])


def attach_flow(*, prepared, root, configuration, clock, validate_sources):
    addon=FlowAddon(roa_service=prepared['roa_service'],root=root,configuration=configuration,clock=clock)
    router=APIRouter()
    async def invoke(operation):
        def guarded():
            validate_sources();result=operation();validate_sources();return result
        try:return JSONResponse(await run_in_threadpool(guarded),headers={'Cache-Control':'no-store'})
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):return JSONResponse(dict(status='UNAVAILABLE',reason='FLOW_RECONCILIATION_REQUIRED',account_mutated=False),status_code=409,headers={'Cache-Control':'no-store'})
    @router.get('/api/strategy-account/cash-classification')
    async def current(request:Request):
        if request.query_params:return JSONResponse({'reason':'UNSUPPORTED_PARAMETERS'},status_code=422)
        return await invoke(addon.current)
    @router.get('/api/strategy-account/cash-classification/profit')
    async def profit(request:Request):
        if request.query_params:return JSONResponse({'reason':'UNSUPPORTED_PARAMETERS'},status_code=422)
        return await invoke(addon.profit_current)
    @router.post('/api/strategy-account/cash-classification')
    async def save(request:Request):
        if request.query_params:return JSONResponse({'reason':'UNSUPPORTED_PARAMETERS'},status_code=422)
        raw=bytearray()
        async for part in request.stream():
            raw.extend(part)
            if len(raw)>16384:return JSONResponse({'reason':'BODY_TOO_LARGE'},status_code=422)
        def unique_fields(items):
            result={}
            for key,value in items:
                if key in result:raise ValueError('DUPLICATE_JSON_FIELD')
                result[key]=value
            return result
        def invalid_constant(value):raise ValueError('INVALID_JSON_CONSTANT')
        try:
            body=json.loads(raw,object_pairs_hook=unique_fields,parse_constant=invalid_constant)
            if type(body)is not dict:raise ValueError('BODY_OBJECT_REQUIRED')
        except (ValueError,UnicodeError,RecursionError):
            return JSONResponse({'reason':'INVALID_JSON'},status_code=422)
        return await invoke(lambda:addon.save(body))
    @router.get('/static/strategy_cash_classification.js')
    async def asset():
        await run_in_threadpool(validate_sources)
        return FileResponse(Path(__file__).with_name('strategy_cash_classification.js'),media_type='application/javascript')
    prepared['router'].include_router(router)
    return dict(prepared,cash_classification=addon)
