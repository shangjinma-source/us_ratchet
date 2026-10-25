"""Server-owned paper run, with no registration and no client admission inputs.

Context loaders are fixed server configuration, not request handlers. Capture and
admission run outside the coordinator lock; acceptance/publication use its CAS.
One create-only claim prevents automatic retries after unregistered partial IO.
An admission committed before acceptance is resumed without repeating cap work.
"""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json
import os

from core.strategy_account_ledger import canonical
from data.strategy_paper_application_descriptor_v2 import require,stamp,sessions,SCOPE,NY
from backtest.current_strategy_prospective_paper_book_v2 import _context
from backtest.current_strategy_prospective_paper_admission_reader_v2 import registered_evidence
from data.strategy_prospective_paper_cap_store_v2 import ProspectivePersistentCaps
from data.strategy_prospective_paper_daily_capture_v2 import load_prospective_daily_archive
from data.strategy_prospective_paper_source_capture_v2 import capture_prospective_sources
from data.strategy_prospective_paper_unit_review_v2 import review_prospective_execution_sources
from data.strategy_prospective_paper_settlement_v2 import accepted_references
from data.current_quantity_v2_completed_session_minutes import capture,fetch_bytes
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
from data.current_quantity_v2_late_unit_review import BoundedLateUnitReview
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_prospective_paper_cap_daily_v2 import project_paper_cap_daily
from data.strategy_prospective_paper_selection_v2 import verify_empty_paper_target, prospective_target_training_context

SOURCE='backtest/current_strategy_prospective_paper_run_once_v2.py'


def digest(value):return sha256(canonical(value)).hexdigest()


class ProspectivePaperRunOnce:
    def __init__(self,*,root,authority,coordinator,admission_store,daily_context,
                 identity_resolver,securities,training_context,cap_release_path,clock=None,
                 market_fetch=None,halt_fetch=None,action_fetch=None,rss_fetch=None,
                 minute_fetch=None,settlement_batch=None,fault=None,monthly_source_loader=None):
        self.root=Path(root).absolute();self.authority=deepcopy(authority)
        self.coordinator=coordinator;self.admissions=admission_store
        self.daily_context=daily_context;self.identity=identity_resolver
        self.securities=deepcopy(securities);self.training=deepcopy(training_context)
        source_clock=clock or (lambda:datetime.now(timezone.utc))
        self.clock=lambda:source_clock()
        self.transports=dict(market_fetch=market_fetch,halt_fetch=halt_fetch,
                             action_fetch=action_fetch,rss_fetch=rss_fetch)
        self.minute_fetch=minute_fetch or fetch_bytes;self.fault=fault or (lambda phase:None)
        self.monthly_source_loader=monthly_source_loader
        # Fixed server source cursor. Advancing it authorizes a new capture, not
        # evidence admission; original decoders/reviewers still verify every byte.
        self.settlement_batch=settlement_batch or (lambda pending:'initial')
        app=_context(authority,self.clock());require(SOURCE in app['code_sha256'],'PAPER_RUNNER_PIN_REQUIRED')
        require(coordinator.authority==authority==admission_store.authority,'PAPER_RUNNER_AUTHORITY')
        self.directory=self.root/app['storage']['evidence']/'run-once'
        self.cap_release_path=cap_release_path
        self.risk_store=MonthlyPeakExitStore(self.directory.parent/'risk.sqlite3')
        require(self.risk_store.path.is_file(),'PAPER_RUN_RISK_RECOVERY_REQUIRED')

    def _now(self):return stamp(self.clock())

    def publish_monthly(self):
        from backtest.current_strategy_paper_monthly_publish_v2 import publish_monthly_target
        require(callable(self.monthly_source_loader),'PAPER_MONTHLY_SOURCE_NOT_CONFIGURED')
        return publish_monthly_target(coordinator=self.coordinator,admission_store=self.admissions,
            source_loader=self.monthly_source_loader,clock=self.clock)

    def _save(self,path,value):
        for p in [path,*path.parents]:
            require(not p.is_symlink() and (not p.exists() or not getattr(p.lstat(),'st_file_attributes',0)&0x400),
                    'PAPER_RUNNER_LINK')
        with path.open('xb') as stream:
            stream.write(canonical(value));stream.flush();os.fsync(stream.fileno())

    def _claim(self,operation):
        path=self.directory/digest(operation)[:24]
        # Validate ancestors before creating anything, including same-root links.
        for p in [path,*path.parents]:
            require(not p.is_symlink() and (not p.exists() or not getattr(p.lstat(),'st_file_attributes',0)&0x400),
                    'PAPER_RUNNER_LINK')
        require(not path.exists(),'PAPER_RUN_PARTIAL_REQUIRES_RECOVERY')
        path.mkdir(parents=True,exist_ok=False)
        self._save(path/'started.json',dict(operation_id=operation,started_at=self._now().isoformat()))
        return path

    def _apply_registered(self,record,book,target):
        result=record['result'];operation=record['operation_id']
        if record['kind']=='DECISION':
            if result.get('decision_bytes') is None:return dict(status=result['status'],operation_id=operation)
            evidence=json.loads(result['decision_bytes']);now=self._now()
            if evidence['account_revision']!=book['revision'] or evidence['target_id']!=target:
                return dict(status='REGISTERED_DECISION_STALE_NOT_ACCEPTED',operation_id=operation)
            local=now.astimezone(NY)
            if now>=stamp(evidence['valid_until']) or (local.hour,local.minute)!=(10,0):
                return dict(status='REGISTERED_DECISION_EXPIRED_NOT_ACCEPTED',operation_id=operation)
            request=dict(kind='ACCEPT',operation_id=operation,expected_revision=book['revision'],
                         decision_bytes=result['decision_bytes'].decode())
        else:
            evidence=json.loads(result['settlement_bytes'])
            previous=next((r for r in book['operations'] if r['request']['operation_id']==operation),None)
            if previous:return dict(status='SETTLEMENT_ALREADY_RECORDED',operation_id=operation,
                                    outcome=previous['outcome'])
            require(evidence['account_revision']==book['revision'],'PAPER_RUN_SETTLEMENT_STALE')
            request=dict(kind='SETTLE',operation_id=operation,expected_revision=book['revision'],
                settlement_bytes=result['settlement_bytes'].decode(),minutes=evidence['minutes'],
                observed_through=evidence['observed_through'])
        changed=self.coordinator.apply(request)
        return dict(status='PAPER_OPERATION_RECORDED',operation_id=operation,
                    revision=changed['revision'],outcome=changed['operations'][-1]['outcome'])

    def run_once(self):
        # These reads deliberately fail on missing registration/DB; never initialize.
        admitted=self.admissions.load();book=self.coordinator.read()
        self.admissions.validate_risk_store(self.risk_store,admitted)
        target=self.coordinator.current_target_id();now=self._now();app=_context(self.authority,now)
        calendar=sessions(self.authority['descriptor_arguments']['calendar_bytes'],app['calendar_sha256'])
        pending={k:v for k,v in book['orders'].items() if v['closed'] is None}
        if pending:
            if any(now<stamp(o['session_close']) for o in pending.values()):return dict(status='WAIT_PENDING_SESSION_CLOSE')
            batch=self.settlement_batch(deepcopy(pending))
            require(type(batch) is str and 0<len(batch)<=200,'PAPER_RUN_SERVER_BATCH_REQUIRED')
            claim='settle-batch:'+digest(dict(pending=pending,batch=batch))
            path=self.directory/digest(claim)[:24]
            if (path/'admission.json').exists():
                pointer=json.loads(self.admissions._read(path/'admission.json',4*1024*1024))
                operation='settle:'+digest(dict(pending=pending,source_sha256=pointer['source_sha256']))
                registered=registered_evidence(self.admissions,operation_id=operation)
                require(registered is not None and registered['kind']=='SETTLEMENT' and
                    registered['inputs']['arguments']['source_hashes']==pointer['source_sha256'] and
                    {k:v for k,v in registered['inputs']['arguments']['book']['orders'].items() if v['closed'] is None}==pending,
                    'PAPER_RUN_SETTLEMENT_POINTER_NOT_REGISTERED')
                return self._apply_registered(registered,book,target)
            if (path/'duplicate.json').exists():return dict(status='WAIT_NEW_SETTLEMENT_EVIDENCE')
            path=self._claim(claim)
            try:
                args=self._settlement_arguments(book,admitted,pending,path,app,calendar)
                minutes={oid:json.loads(args['files'][refs['minutes']])['minutes'] for oid,refs in args['captures'].items()}
                for prior in book['operations']:
                    request=prior['request']
                    if request['kind']=='SETTLE' and request['minutes']==minutes:
                        self._save(path/'duplicate.json',dict(status='UNCHANGED_MINUTES_NOT_RECORDED',
                            source_sha256=args['source_hashes']))
                        return dict(status='WAIT_NEW_SETTLEMENT_EVIDENCE')
                operation='settle:'+digest(dict(pending=pending,source_sha256=args['source_hashes']))
                self._save(path/'admission.json',dict(source_sha256=args['source_hashes']))
                self.admissions.produce_and_archive_settlement(operation,args)
                self.fault('after_admission_before_accept')
                return self._apply_registered(registered_evidence(self.admissions,operation_id=operation),book,target)
            except BaseException:
                self._save(path/'failed.json',dict(status='FAILED_PRESERVED'));raise
        if target is None:return dict(status='WAIT_MONTHLY_TARGET')
        day=now.astimezone(NY).date().isoformat()
        operation='decision:'+digest(dict(revision=book['revision'],target=target,session=day))
        registered=registered_evidence(self.admissions,operation_id=operation)
        if registered:return self._apply_registered(registered,book,target)
        row=next((r for r in calendar if r['date']==day),None)
        if not row or not app['plan']['first_session']['date']<=day<=app['plan']['terminal_session']['date']:
            return dict(status='OUTSIDE_REGISTERED_STUDY')
        if not stamp(row['decision_at'])<=now<stamp(row['decision_until']):return dict(status='WAIT_OR_MISSED_DECISION_WINDOW')
        waiting=self.directory/digest(operation)[:24]/'waiting.json'
        if waiting.exists():
            saved=json.loads(self.admissions._read(waiting,4*1024*1024))
            require(saved['operation_id']==operation,'PAPER_RUN_WAIT_BINDING')
            return dict(status=saved['status'],operation_id=operation)
        path=self._claim(operation)
        try:
            context=self.daily_context(book,target)
            if context.get('status')=='HOLD_EMPTY_TARGET':
                empty=context['empty_arguments']
                require(empty['book']==book and empty['authority']==self.authority,'PAPER_RUN_EMPTY_SNAPSHOT_CHANGED')
                checked=verify_empty_paper_target(**empty)
                require(checked['target_id']==target,'PAPER_RUN_EMPTY_TARGET_CHANGED')
                self._save(path/'waiting.json',dict(status=checked['status'],operation_id=operation))
                return dict(status=checked['status'],operation_id=operation)
            loaded=load_prospective_daily_archive(**context,clock=self.clock)
            daily=loaded['daily_arguments']
            require(daily['book']==book and daily['authority']==self.authority and
                    loaded['verified']['target_id']==target,'PAPER_RUN_DAILY_SNAPSHOT_CHANGED')
            daily['admitted_decisions']=admitted['decisions'];daily['admitted_settlements']=admitted['settlements']
            risk=project_paper_cap_daily(daily_arguments=daily,risk_store=self.risk_store,
                                        cap_release_path=self.cap_release_path)
            if risk['status']!='DAILY_SIGNAL_READY':
                self._save(path/'waiting.json',dict(status=risk['status'],operation_id=operation))
                return dict(status=risk['status'],operation_id=operation)
            effective=risk['signal']['effective_target_quantities']
            if all(effective.get(sid,0)==book['shares'].get(sid,0)
                   for sid in set(effective)|set(book['shares'])):
                self._save(path/'waiting.json',dict(status='HOLD',operation_id=operation,
                    evidence_id=risk['signal']['evidence_id']))
                return dict(status='HOLD',operation_id=operation)
            training=prospective_target_training_context(selection_result=daily['selection_result'],
                selection_arguments=daily['selection_arguments'])
            captured=capture_prospective_sources(book=book,authority=self.authority,
                admitted_decisions=admitted['decisions'],admitted_settlements=admitted['settlements'],
                identity_resolver=self.identity,securities=self.securities,
                target_quantities=risk['signal']['effective_target_quantities'],
                window_start=training['training_closed_at'],output_directory=path/'sources',
                clock=self.clock,**{k:v for k,v in self.transports.items() if v is not None})
            reviewed=review_prospective_execution_sources(book=book,authority=self.authority,
                admitted_decisions=admitted['decisions'],admitted_settlements=admitted['settlements'],
                securities=self.securities,market_capture=captured['market_capture'],
                action_package=captured['action_capture'],clock=self.clock,**training)
            caps=ProspectivePersistentCaps(root=self.root,book=book,authority=self.authority,
                admitted_decisions=admitted['decisions'],admitted_settlements=admitted['settlements'],
                clock=lambda:self._now().isoformat())
            try:
                market=reviewed['market_capture'];units=reviewed['unit_review']
                envelope=canonical(dict(schema='PROSPECTIVE_PAPER_EXECUTION_ADMISSION_V1',scope=SCOPE,
                    descriptor_sha256=book['descriptor_sha256'],account_id=book['account_id'],account_revision=book['revision'],
                    target_id=target,daily_evidence_id=risk['signal']['evidence_id'],
                    cap_namespace_id=caps.namespace_id,source_sha256=market['source_hashes'],
                    unit_review_sha256=digest(units),
                    sell_source_sha256=market['source_hashes'],sell_unit_review_sha256=digest(units),
                    available_at=self._now().isoformat()))
                self.admissions.produce_and_archive_decision(operation,dict(daily_arguments=daily,
                    execution_admission_bytes=envelope,trusted_execution_admission_sha256=sha256(envelope).hexdigest(),
                    market_capture=market,unit_review=units,
                    sell_market_capture=market,sell_unit_review=units,
                    caps=caps,risk_store=self.risk_store,
                    cap_release_path=self.cap_release_path),daily_archive={
                        'directory':context['directory'],'trusted_complete_sha256':context['trusted_complete_sha256']})
            finally:caps.close()
            self.fault('after_admission_before_accept')
            return self._apply_registered(registered_evidence(self.admissions,operation_id=operation),book,target)
        except BaseException:
            self._save(path/'failed.json',dict(status='FAILED_PRESERVED'));raise

    def _settlement_arguments(self,book,admitted,pending,path,app,calendar):
        files={}
        def merge(new):
            for p,raw in new.items():
                require(p not in files or files[p]==raw,'PAPER_RUN_ORIGIN_PATH_CONFLICT');files[p]=raw
        for hashed in {o['decision_sha256'] for o in pending.values()}:
            record=registered_evidence(self.admissions,decision_sha256=hashed)
            require(record is not None,'PAPER_RUN_ORIGIN_NOT_REGISTERED')
            args=record['inputs']['arguments']
            for key in ('market_capture','sell_market_capture'):
                if args.get(key):merge(args[key]['files'])
        refs=accepted_references(book=book,authority=self.authority,admitted_decisions=admitted['decisions'],
            admitted_settlements=admitted['settlements'],files=files,
            source_hashes={p:sha256(b).hexdigest() for p,b in files.items()},now=self._now())
        captures={};reviews={}
        actions=PaperActionEvidenceSources(clock=self.clock,**{
            k:v for k,v in dict(fetch=self.transports['action_fetch'],rss_fetch=self.transports['rss_fetch']).items() if v is not None})
        for oid,ref in refs.items():
            row=next(r for r in calendar if r['close']==pending[oid]['session_close'])
            prefix='m/'+digest(oid)[:16];directory=path/prefix
            capture(directory=directory,security_id=ref['security_id'],ticker=ref['ticker'],session=row['date'],
                session_open=row['open'],session_close=row['close'],calendar_source_reference='sha256:'+app['calendar_sha256'],
                fetch=self.minute_fetch,clock=self.clock)
            names=dict(raw='response.bin',receipt='receipt.json',started='started.json',minutes='minutes.json')
            captures[oid]={k:prefix+'/'+v for k,v in names.items()}
            merge({prefix+'/'+name:(directory/name).read_bytes() for name in names.values()})
            late=BoundedLateUnitReview(action_sources=actions,clock=self.clock).capture(reference=ref,
                capture_raw=files[captures[oid]['raw']],captured_at=self._now(),origin_files=files,
                account_id=book['account_id'],state_revision=book['revision'])
            merge(late['files']);reviews[oid]=late['review_path']
        return dict(book=book,authority=self.authority,admitted_decisions=admitted['decisions'],
            admitted_settlements=admitted['settlements'],captures=captures,unit_reviews=reviews,files=files,
            source_hashes={p:sha256(b).hexdigest() for p,b in files.items()})


