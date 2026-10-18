"""Explicit capture/resolve provider for a fixed new-cash paper strategy pool.

No search, default account, broker import or automatic capture. Optional audit
storage records evidence only; without it this provider performs no disk writes.
Current class facts come from pinned reviewed admission rows, never EQUITY alone.
Consumers needing commit-time authority must hold this provider's lock through
source revalidation and store commit (DB lock before this source lock).
"""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path,PurePosixPath
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo
from data.current_quantity_v2_current_cash_plan import (
    BASIS,canonical,parse,require,build_current_cash_plan)
from data.current_quantity_projection_v2 import project_capital_decision_v2
from data.current_research_intraday_execution import fetch_intraday_chart,decode_intraday_reference

MANIFEST='tmp/current_expanded_rebased_manifest_20261015_v2.json'
VERSION='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH'
NY=ZoneInfo('America/New_York')


class CurrentQuantityV2CurrentCashSources:
    def __init__(self,*,root,snapshot_service,server_account_id,fetch=fetch_intraday_chart,
                 clock=lambda:datetime.now(timezone.utc),execution_month_mandate=None,
                 pullback_policy=None,pullback_cap_store=None,audit_storage_root=None,identity_manifest_path=MANIFEST):
        require(type(server_account_id)is str and bool(server_account_id.strip()),'FIXED_SERVER_ACCOUNT_REQUIRED')
        self.root=Path(root).resolve();self.snapshots=snapshot_service;self.account_id=server_account_id
        self.identity_manifest_path=self._path(identity_manifest_path)
        self.month_mandate=deepcopy(execution_month_mandate)
        self.audit_storage_root=Path(audit_storage_root) if audit_storage_root is not None else None
        require((pullback_policy is None)==(pullback_cap_store is None),'PULLBACK_POLICY_STORE_PAIR_REQUIRED')
        if pullback_policy is not None:
            from data.current_quantity_v2_pullback_entry import number
            require(type(pullback_policy)is dict and set(pullback_policy)=={'schema','status',
                'rebound_fraction','minimum_discount','maximum_age_seconds'}
                and pullback_policy['schema']=='V2_PULLBACK_EXECUTION_POLICY_V1'
                and pullback_policy['status']=='EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED'
                and 0<number(pullback_policy['rebound_fraction'])<1
                and 0<number(pullback_policy['minimum_discount'])<1
                and type(pullback_policy['maximum_age_seconds'])is int
                and 0<pullback_policy['maximum_age_seconds']<=120,'INVALID_PULLBACK_POLICY')
            require(callable(getattr(pullback_cap_store,'candidate',None)),'PULLBACK_CAP_STORE_REQUIRED')
        self.pullback_policy=deepcopy(pullback_policy);self.pullback_cap_store=pullback_cap_store
        self.fetch=fetch;self.clock=clock;self.lock=RLock();self._attempt=0;self._current=None

    @staticmethod
    def _path(name):
        require(type(name)is str and name and '\\' not in name and ':' not in name
            and not PurePosixPath(name).is_absolute() and all(x not in ('','.','..') for x in name.split('/')),
            'SAFE_SOURCE_PATH_REQUIRED')
        return name

    def _read(self,name):
        path=(self.root/self._path(name)).resolve()
        require(path.is_relative_to(self.root),'SOURCE_PATH_ESCAPE')
        with path.open('rb') as stream:raw=stream.read(32*1024*1024+1)
        require(len(raw)<=32*1024*1024,'SOURCE_BYTES_LIMIT');return raw

    def _now(self):
        now=self.clock();require(isinstance(now,datetime) and now.tzinfo is not None,'AWARE_CLOCK_REQUIRED');return now

    def _base(self,decision_id):
        require(type(decision_id)is str and len(decision_id)==64 and all(c in '0123456789abcdef' for c in decision_id),'DECISION_ID_REQUIRED')
        rid=decision_id[:24];bundle_reader=getattr(self.snapshots,'verified_snapshot_bundle',None)
        bundle=None
        if callable(bundle_reader):
            bundle=bundle_reader(rid);decision=bundle['decision'];snapshot=bundle['snapshot']
        else:
            # Legacy injected providers retain the full independent file checks.
            decision=self.snapshots.decision(rid);snapshot=self.snapshots.snapshot(rid)
        view=project_capital_decision_v2(decision)
        require(decision['decision_id']==snapshot['decision_id']==decision_id
            and snapshot['research_version']==VERSION and snapshot['research_id']==rid
            and snapshot['research_only']is True and snapshot['execution_blocked']is True
            and snapshot['target_quantities']==decision['target_quantities']
            and snapshot['status']==view['status'] and snapshot['as_of']==decision['decision_date']
            and snapshot['method_version']==decision['method']
            and snapshot['available_cash_exact']==decision['available_cash']
            and snapshot['sources']==decision['binding']['source_hashes'],
            'SNAPSHOT_DECISION_BINDING_MISMATCH')
        require(decision['binding']['shares']=={} and decision['holding_market_values']=={},'NEW_CASH_DECISION_REQUIRED')
        pins=decision['binding']['source_hashes'];require(0<len(pins)<=2000,'SOURCE_PIN_LIMIT')
        if bundle is not None:
            require(bundle['source_hashes']==pins and set(bundle['files'])==set(pins),'SNAPSHOT_SOURCE_BUNDLE_MISMATCH')
        files={};total=0
        for path,h in pins.items():
            raw=self._read(path) if bundle is None else bundle['files'][path]
            require(type(raw)is bytes and len(raw)<=32*1024*1024,'SOURCE_BYTES_LIMIT')
            total+=len(raw);require(total<=128*1024*1024,'SOURCE_BYTES_LIMIT')
            require(sha256(raw).hexdigest()==h,'ORIGINAL_SOURCE_CHANGED');files[path]=raw
        require(self.identity_manifest_path in files,'PINNED_MANIFEST_REQUIRED')
        return deepcopy(decision),deepcopy(snapshot),files,deepcopy(pins)

    def _identity(self,decision,files,pins,sid,session):
        meta=decision['binding']['search_arguments']['metadata'][sid]
        candidates=[c for c in parse(files[self.identity_manifest_path])['candidates'] if c.get('security_id')==sid]
        require(len(candidates)==1,'MANIFEST_IDENTITY_NOT_UNIQUE');candidate=candidates[0]
        require(candidate['ticker']==meta['ticker'] and candidate['issuer_id']==meta['issuer_id']
            and candidate['status']=='READY_CONDITIONAL' and candidate['identity_reviewed']is True,
            'CURRENT_MANIFEST_IDENTITY_REQUIRED')
        references=candidate['identity_source_references']
        require(type(references)is list and references and all(p in files for p in references),'PINNED_IDENTITY_REFERENCES_REQUIRED')
        require(not any(e['date']>decision['decision_date'] and e['date']<=session
            for e in candidate.get('true_share_events',[])),'KNOWN_POST_DECISION_UNIT_ACTION')
        matched=[];classrefs=set()
        for path in references:
            if not path.endswith('.json'):continue
            doc=parse(files[path])
            if type(doc)is not dict or type(doc.get('rows'))is not list:continue
            declared=doc.get('source_hashes',{})
            require(type(declared)is dict,'CLASS_SOURCE_HASHES_REQUIRED')
            normalized={}
            for source_name,source_hash in declared.items():
                require(type(source_name)is str,'CLASS_SOURCE_PATH_REQUIRED')
                normalized_name=self._path(source_name.replace('\\','/'))
                require(normalized_name not in normalized or normalized[normalized_name]==source_hash,
                        'CLASS_SOURCE_HASH_ALIAS_CONFLICT')
                normalized[normalized_name]=source_hash
            rows=[r for r in doc['rows'] if r.get('security_id')==sid and r.get('ticker')==meta['ticker']
                and r.get('issuer_id')==meta['issuer_id']]
            for row in rows:
                require(row.get('status')=='READY_CONDITIONAL_IDENTITY' and row.get('identity_reviewed')is True
                    and row.get('no_unresolved_identifier_conflict')is True and row.get('unresolved')==[],
                    'CLASS_ADMISSION_UNRESOLVED')
                cls=row.get('security_class');require(type(cls)is str and cls.strip(),'EXPLICIT_SECURITY_CLASS_REQUIRED')
                require(row.get('source_references'),'CLASS_SOURCE_REFERENCES_REQUIRED')
                for ref in row['source_references']:
                    require(type(ref)is str,'CLASS_SOURCE_PATH_REQUIRED')
                    name=self._path(ref.replace('\\','/'))
                    require(name in files,'CLASS_SOURCE_NOT_PINNED')
                    internal=normalized.get(name)
                    require(internal==pins[name],'CLASS_ADMISSION_SOURCE_MISMATCH');classrefs.add(name)
                matched.append(cls);classrefs.add(path)
        require(matched and len(set(matched))==1,'EXPLICIT_PINNED_CLASS_UNAVAILABLE')
        return dict(security_id=sid,ticker=meta['ticker'],issuer_id=meta['issuer_id'],security_class=matched[0],
            currency='USD',source_references=sorted({self.identity_manifest_path,*references,*classrefs}))

    def capture(self,decision_id):
        # Any new attempt immediately invalidates the previous package for this pool.
        with self.lock:
            self._attempt+=1;attempt=self._attempt;self._current=None
        started=self._now();local=started.astimezone(NY)
        # Exclusion only: avoid source/archive/network work outside the widest
        # regular-session window. Weekday/time never proves a market is open;
        # holidays, early closes and fresh quotes still use the original gates.
        require(local.weekday()<5 and 570<=local.hour*60+local.minute<960,'OUTSIDE_REGULAR_SESSION')
        decision,snapshot,files,pins=self._base(decision_id)
        session=local.date().isoformat()
        from data.current_quantity_v2_execution_month import validate_execution_month
        config=self.month_mandate
        require(type(config)is dict and set(config)=={'path','sha256'},'MONTH_MANDATE_REQUIRED')
        path=self._path(config['path']);data=self._read(path)
        require(sha256(data).hexdigest()==config['sha256'],'MONTH_MANDATE_HASH_MISMATCH')
        declaration=parse(data)
        for name,expected in declaration['source_hashes'].items():
            source=self._read(name)
            require(sha256(source).hexdigest()==expected and (name not in pins or pins[name]==expected),'EXECUTION_MONTH_SOURCE_MISMATCH')
            files[name]=source;pins[name]=expected
        require(path not in pins or pins[path]==config['sha256'],'MONTH_MANDATE_PATH_CONFLICT')
        files[path]=data;pins[path]=config['sha256']
        validate_execution_month(declaration,decision_date=decision['decision_date'],original_pins=decision['binding']['source_hashes'],
            session=session,files=files,pins=pins)
        needed=sorted(sid for sid,q in decision['target_quantities'].items() if q>0)
        identities={sid:self._identity(decision,files,pins,sid,session) for sid in needed}
        audit=None
        if self.audit_storage_root is not None:
            from data.current_quantity_v2_monthly_capture_audit import CaptureAudit
            binding=dict(scope='DECLARED_EMPTY_GENESIS',account_id=self.account_id,
                state_revision=decision['state_revision'],decision_id=decision_id,research_id=decision['research_id'],
                initial_cash_exact=decision['available_cash'],broker_balance_verified=False,actual_account_created=False)
            audit=CaptureAudit(self.audit_storage_root,None,started,genesis_binding=binding)
        try:
            if audit is not None:
                # Durable static evidence precedes the short-lived quote. This
                # creates no receipt or authority; final package/source gates stay.
                from data.current_quantity_v2_monthly_capture_audit import publish_blob
                audit.stage='STATIC_PREARCHIVE';total=0
                require(set(files)==set(pins) and len(files)<=2000,'SOURCE_BYTES_LIMIT')
                for name,source in files.items():
                    require(type(source)is bytes,'SOURCE_BYTES_LIMIT')
                    total+=len(source)
                    require(len(source)<=32*1024*1024 and total<=128*1024*1024,'SOURCE_BYTES_LIMIT')
                    require(sha256(source).hexdigest()==pins[name],'CAPTURE_AUDIT_PACKAGE_CHANGED')
                    publish_blob(audit.root,source,32*1024*1024)
                with self.lock:require(self._attempt==attempt,'CAPTURE_SUPERSEDED')
            return self._capture_admitted(decision_id,decision,snapshot,files,pins,started,session,path,needed,identities,attempt,audit)
        except Exception as error:
            with self.lock:
                if self._attempt==attempt:self._current=None
            if audit is not None:
                from data.current_quantity_v2_monthly_capture_audit import safe_reason
                error.capture_id=audit.identifier
                try:audit.finish('FAILED',self._now(),reason=safe_reason(error))
                except Exception as persistence_error:
                    persistence_error.capture_id=audit.identifier
                    raise persistence_error from error
            raise

    def audit(self,capture_id,account_id):
        require(self.audit_storage_root is not None,'CAPTURE_AUDIT_NOT_CONFIGURED')
        from data.current_quantity_v2_monthly_capture_audit import read_capture
        return read_capture(self.audit_storage_root,capture_id,account_id)

    def _capture_admitted(self,decision_id,decision,snapshot,files,pins,started,session,path,needed,identities,attempt,audit):
        namespace='generated/current_cash_capture/'+str(uuid4())+'/'
        def put(name,value,raw=False):
            path=namespace+name;require(path not in files,'GENERATED_PATH_CONFLICT')
            value=value if raw else canonical(value);files[path]=value;pins[path]=sha256(value).hexdigest();return path
        declaration=put('declaration.json',dict(scope='SERVER_DEFINED_EMPTY_PAPER_STRATEGY_GENESIS',
            account_id=self.account_id,decision_id=decision_id,started_at=started.isoformat(),
            broker_balance_verified=False,actual_account_created=False,attempt=attempt))
        account=dict(account_id=self.account_id,revision=decision['state_revision'],cash=decision['available_cash'],
            shares={},observed_at=started.isoformat(),open_orders=[],reserved_cash='0',reserved_shares={},pending_rights=[])
        genesis=dict(purpose='PAPER_INITIALIZATION_NOT_BROKER_BALANCE',account_id=self.account_id,
            research_id=decision['research_id'],decision_id=decision_id,capital_origin_revision=decision['state_revision'],
            initial_cash_exact=decision['available_cash'],target_month=session[:7],active_date=session,
            declared_at=started.isoformat(),source_references=[declaration])
        quote_receipts={};reviews={};pullback_proofs={}
        for sid in needed:
            if audit is not None:audit.stage='FETCH'
            identity=identities[sid];raw=self.fetch(identity['ticker']);captured=self._now()
            require(type(raw)is bytes and len(raw)<=4*1024*1024,'RAW_QUOTE_BYTES_REQUIRED')
            if audit is not None:audit.raw(raw,sid,identity['ticker'],captured,self._now())
            rawpath=put(sid.replace(':','_')+'.raw',raw,raw=True)
            receiptpath=put(sid.replace(':','_')+'.receipt.json',dict(security_id=sid,ticker=identity['ticker'],
                raw_path=rawpath,raw_sha256=pins[rawpath],captured_at=captured.isoformat()))
            quote_receipts[sid]=receiptpath
            if self.pullback_policy is not None:
                if audit is not None:audit.stage='PULLBACK'
                checked=self._now()
                reference=decode_intraday_reference(raw,ticker=identity['ticker'],now=checked,captured_at=captured)
                require(reference['session']==session,'PULLBACK_CAPTURE_SESSION_CHANGED')
                result=self.pullback_cap_store.candidate(raw=raw,expected_sha256=pins[rawpath],
                    security_id=sid,ticker=identity['ticker'],session=session,
                    session_open=reference['session_open'],session_close=reference['session_close'],
                    captured_at=captured.isoformat(),checked_at=checked.isoformat(),now=checked.isoformat(),
                    **{key:self.pullback_policy[key] for key in
                       ('rebound_fraction','minimum_discount','maximum_age_seconds')})
                pullback_proofs[sid]=put(sid.replace(':','_')+'.pullback.json',result['frozen_proof'])
            reviews[sid]=dict(identity,status='CONDITIONAL_CURRENT_QUOTE_IDENTITY',price_basis=BASIS,
                session=session,quote_captured_at=captured.isoformat(),reviewed_at=self._now().isoformat(),
                reference_source_hashes={rawpath:pins[rawpath],receiptpath:pins[receiptpath]},known_actions=[])
        docs=dict(execution_month_mandate=path,identities=put('identities.json',identities),current_unit_reviews=put('current_units.json',reviews),quote_receipts=quote_receipts)
        if self.pullback_policy is not None:
            docs.update(pullback_policy=put('pullback_policy.json',self.pullback_policy),pullback_proofs=pullback_proofs)
        supplied=dict(capital_decision=decision,account_state=account,genesis_declaration=genesis,
            execution_package=dict(files=files,source_hashes=pins,documents=docs))
        if audit is not None:audit.stage='VALIDATE'
        final=self._now();plan=build_current_cash_plan(**supplied,now=final.isoformat())
        require(plan['status']=='READY',plan.get('reason','CAPTURE_NOT_READY'))
        if audit is None:
            current_decision,current_snapshot,_,_=self._base(decision_id)
            require(current_decision==decision and current_snapshot==snapshot,'SNAPSHOT_CHANGED_DURING_CAPTURE')
        # This second freshness check includes source-recheck latency.
        checked=self._now();plan=build_current_cash_plan(**supplied,now=checked.isoformat())
        require(plan['status']=='READY',plan.get('reason','CAPTURE_NOT_READY'))
        receipt=None
        if audit is not None:
            audit.stage='ARCHIVE'
            receipt=audit.package(supplied['execution_package'],audit_context={k:deepcopy(supplied[k])
                for k in ('capital_decision','account_state','genesis_declaration')})
            audit.stage='SOURCE_RECHECK'
            current_decision,current_snapshot,_,_=self._base(decision_id)
            require(current_decision==decision and current_snapshot==snapshot,'SNAPSHOT_CHANGED_DURING_CAPTURE')
        with self.lock:
            require(self._attempt==attempt,'CAPTURE_SUPERSEDED')
            # Archive IO is outside the lock. Recheck freshness after that work;
            # resolution/acceptance retain their independent live rechecks.
            if audit is not None:
                plan=build_current_cash_plan(**supplied,now=self._now().isoformat())
                require(plan['status']=='READY',plan.get('reason','CAPTURE_NOT_READY'))
                audit.stage='FINAL_ADMISSION';audit.finish('CAPTURED',self._now(),receipt=receipt)
            self._current=dict(decision_id=decision_id,attempt=attempt,supplied=supplied,snapshot=snapshot)
        return dict(status='CAPTURED',decision_id=decision_id,attempt=attempt,session=session,
            selected_security_ids=needed,reference_valid_until=plan['reference_valid_until'],
            source_authenticated=False,corporate_actions_complete=False,account_created=False,
            **({'capture_id':audit.identifier} if audit is not None else {}))

    def resolve(self,decision_id):
        with self.lock:
            require(self._current is not None and self._current['decision_id']==decision_id,'CURRENT_CASH_CAPTURE_REQUIRED')
            saved=deepcopy(self._current)
        decision,snapshot,_,_=self._base(decision_id)
        config=self.month_mandate
        require(type(config)is dict and set(config)=={'path','sha256'},'MONTH_MANDATE_REQUIRED')
        monthraw=self._read(config['path'])
        require(sha256(monthraw).hexdigest()==config['sha256'],'MONTH_MANDATE_HASH_MISMATCH')
        require(saved['supplied']['execution_package']['files'].get(config['path'])==monthraw,'MONTH_MANDATE_CHANGED')
        for path,expected in parse(monthraw)['source_hashes'].items():
            require(sha256(self._read(path)).hexdigest()==expected,'EXECUTION_MONTH_SOURCE_MISMATCH')
        require(decision==saved['supplied']['capital_decision'] and snapshot==saved['snapshot'],'SNAPSHOT_CHANGED_AFTER_CAPTURE')
        plan=build_current_cash_plan(**saved['supplied'],now=self._now().isoformat())
        require(plan['status']=='READY',plan.get('reason','CURRENT_CASH_REFERENCE_EXPIRED'))
        with self.lock:
            require(self._current is not None and self._attempt==saved['attempt'],'CAPTURE_SUPERSEDED')
        return saved['supplied']

    def account_reader(self,account_id):
        with self.lock:
            require(account_id==self.account_id and self._current is not None,'CURRENT_PAPER_GENESIS_UNAVAILABLE')
            return deepcopy(self._current['supplied']['account_state'])
