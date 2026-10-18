"""Server-injected same-month sources; optional research cap writes at capture only.

No account DB writes, search or fabricated unit review. Resolve is read-only.
"""
import base64
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo
from data.current_quantity_v2_current_cash_plan import canonical, parse, require, SCOPE
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.current_quantity_v2_difference_service import CurrentQuantityV2DifferenceService, decode_execution_package
from data.current_quantity_v2_paper_chain import review_chain, build_continuation
from data.current_research_intraday_execution import fetch_intraday_chart,decode_intraday_reference
from data.current_quantity_v2_current_cash_continuation import frozen_pullback_policy


class CurrentCashContinuationSources:
    """unit_review_reader(snapshot) -> {files, source_hashes, unit_continuity_path}.

    snapshot contains verified origin rows/identity, new raw receipt pins and
    capture times. Reader supplies external reviewed bytes, never client fields.
    The declaration is checked for consistency, not certified as externally true.
    Review bytes are frozen at capture, not a revocable registry. resolve verifies
    that frozen snapshot; it does not claim to reread external review documents.
    Caller holds lock DB->source through acceptance commit. resolve never fetches.
    """
    def __init__(self, *, root, unit_review_reader, fetch=fetch_intraday_chart,
                 clock=lambda: datetime.now(timezone.utc),pullback_policy=None,pullback_cap_store=None,audit_storage_root=None):
        self.root=Path(root).resolve();self.unit_review_reader=unit_review_reader
        self.audit_storage_root=Path(audit_storage_root) if audit_storage_root is not None else None
        self.fetch=fetch;self.clock=clock;self.lock=RLock();self._attempt=0;self._current=None
        require((pullback_policy is None)==(pullback_cap_store is None),'PULLBACK_POLICY_STORE_PAIR_REQUIRED')
        require(pullback_cap_store is None or callable(getattr(pullback_cap_store,'candidate',None)),
                'PULLBACK_CAP_STORE_REQUIRED')
        self.pullback_policy=deepcopy(pullback_policy);self.pullback_cap_store=pullback_cap_store

    def _now(self):
        now=self.clock();require(isinstance(now,datetime) and now.tzinfo is not None,'AWARE_CLOCK_REQUIRED');return now

    def _read(self,path):
        CurrentQuantityV2CurrentCashSources._path(path)
        resolved=(self.root/path).resolve();require(resolved.is_relative_to(self.root),'SOURCE_PATH_ESCAPE')
        with resolved.open('rb') as stream:raw=stream.read(32*1024*1024+1)
        require(len(raw)<=32*1024*1024,'SOURCE_BYTES_LIMIT');return raw

    def capture(self, verified_chain):
        with self.lock:
            self._attempt+=1;attempt=self._attempt;self._current=None
        require(callable(self.unit_review_reader),'UNIT_REVIEW_SOURCE_UNAVAILABLE')
        state=review_chain(verified_chain);ledger=state['ledger'];original=ledger.get('active_monthly_acceptance',ledger['acceptance'])['proposal']
        require(original.get('target_scope')==SCOPE,'CURRENT_CASH_SCOPE_REQUIRED')
        policy=frozen_pullback_policy(original)
        if policy is not None:
            require(policy==self.pullback_policy and self.pullback_cap_store is not None,
                    'CONTINUATION_PULLBACK_SERVER_CONFIGURATION_REQUIRED')
        require(all(o['closed'] in ('FILLED','CANCELLED','EXPIRED') for o in ledger['orders'].values())
            and ledger['reserved_cash']=='0' and not any(ledger['reserved_shares'].values()),'PRIOR_ORDERS_OPEN')
        now=self._now();require(now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')==original['target_month'],'RESELECT_REQUIRED')
        frozen=original['causal_inputs']['frozen_execution_package'];pins=deepcopy(frozen['source_hashes'])
        files={};disk=set();total=0
        for path,h in pins.items():
            CurrentQuantityV2CurrentCashSources._path(path)
            if path in frozen['files_base64']:
                raw=base64.b64decode(frozen['files_base64'][path],validate=True)
            else:raw=self._read(path);disk.add(path)
            total+=len(raw);require(total<=128*1024*1024 and len(raw)<=32*1024*1024,'SOURCE_BYTES_LIMIT')
            require(sha256(raw).hexdigest()==h,'ORIGINAL_SOURCE_CHANGED');files[path]=raw
        audit=None
        if self.audit_storage_root is not None:
            from data.current_quantity_v2_monthly_capture_audit import CaptureAudit
            audit=CaptureAudit(self.audit_storage_root,state,self._now(),state_context_required=True)
        try:return self._capture_admitted(state,original,policy,files,pins,disk,attempt,audit)
        except Exception as error:
            with self.lock:
                if attempt==self._attempt:self._current=None
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

    def _capture_admitted(self,state,original,policy,files,pins,disk,attempt,audit):
        ledger=state['ledger']
        namespace='generated/current_cash_continuation/'+str(uuid4())+'/'
        def put(name,value,raw=False):
            path=namespace+name;require(path not in pins,'GENERATED_PATH_CONFLICT')
            content=value if raw else canonical(value);files[path]=content;pins[path]=sha256(content).hexdigest();return path
        needed={s for m in (ledger['shares'],ledger['target_quantities']) for s,q in m.items() if q>0}
        securities={s:deepcopy(original['securities'][s]) for s in needed}
        quotes={};captures={};pullback_proofs={}
        for sid in sorted(needed):
            if audit is not None:audit.stage='FETCH'
            raw=self.fetch(securities[sid]['ticker']);captured=self._now()
            require(type(raw)is bytes and len(raw)<=4*1024*1024,'RAW_QUOTE_BYTES_REQUIRED')
            if audit is not None:audit.raw(raw,sid,securities[sid]['ticker'],captured,self._now())
            rawpath=put(sid.replace(':','_')+'.raw',raw,raw=True)
            receipt=put(sid.replace(':','_')+'.receipt.json',dict(security_id=sid,ticker=securities[sid]['ticker'],
                raw_path=rawpath,raw_sha256=pins[rawpath],captured_at=captured.isoformat()))
            quotes[sid]=receipt;captures[sid]=dict(captured_at=captured.isoformat(),source_hashes={rawpath:pins[rawpath],receipt:pins[receipt]})
            if policy is not None:
                if audit is not None:audit.stage='PULLBACK'
                checked=self._now();ref=decode_intraday_reference(raw,ticker=securities[sid]['ticker'],
                    now=checked,captured_at=captured)
                result=self.pullback_cap_store.candidate(raw=raw,expected_sha256=pins[rawpath],
                    security_id=sid,ticker=securities[sid]['ticker'],session=ref['session'],
                    session_open=ref['session_open'],session_close=ref['session_close'],
                    captured_at=captured.isoformat(),checked_at=checked.isoformat(),now=checked.isoformat(),
                    **{key:policy[key] for key in ('rebound_fraction','minimum_discount','maximum_age_seconds')})
                pullback_proofs[sid]=put(sid.replace(':','_')+'.pullback.json',result['frozen_proof'])
        snapshot=dict(account_id=ledger['account_id'],revision=ledger['revision'],target_month=original['target_month'],
            execution_target_id=original['execution_target_id'],securities=securities,
            origins={r['security_id']:deepcopy(r) for r in original['rows'] if r['security_id'] in needed},
            current_receipts=captures,quote_files={p:files[p] for row in captures.values() for p in row['source_hashes']})
        snapshot['origin_files']={p:files[p] for row in snapshot['origins'].values() for p in row['source_hashes']}
        require(callable(self.unit_review_reader),'UNIT_REVIEW_SOURCE_UNAVAILABLE')
        if audit is not None:audit.stage='REVIEW'
        reviewed=self.unit_review_reader(deepcopy(snapshot))
        require(type(reviewed)is dict and set(reviewed)=={'files','source_hashes','unit_continuity_path'},'UNIT_REVIEW_SOURCE_UNAVAILABLE')
        require(set(reviewed['files'])==set(reviewed['source_hashes']),'UNIT_REVIEW_CLOSURE_REQUIRED')
        for path,raw in reviewed['files'].items():
            CurrentQuantityV2CurrentCashSources._path(path)
            require(type(raw)is bytes and sha256(raw).hexdigest()==reviewed['source_hashes'][path],'UNIT_REVIEW_SOURCE_CHANGED')
            require(path not in pins or (pins[path]==reviewed['source_hashes'][path] and files[path]==raw),'SOURCE_PATH_CONFLICT')
            files[path]=raw;pins[path]=reviewed['source_hashes'][path]
        require(reviewed['unit_continuity_path'] in reviewed['files'],'UNIT_DOCUMENT_REQUIRED')
        decision=original['causal_inputs']['capital_decision']
        refs=sorted({p for row in securities.values() for p in row['source_references']})
        package=dict(files=files,source_hashes=pins,documents=dict(capital_decision=put('capital.json',decision),
            identities=put('identities.json',dict(securities=securities,source_references=refs)),
            unit_continuity=reviewed['unit_continuity_path'],quote_receipts=quotes))
        if policy is not None:
            package['documents'].update(pullback_policy=put('pullback_policy.json',policy),pullback_proofs=pullback_proofs)
        if audit is not None:audit.stage='VALIDATE'
        self._validate(package,state)
        receipt=None
        if audit is not None:
            audit.stage='ARCHIVE';receipt=audit.package(package,audit_context=dict(verified_state=state))
            audit.stage='SOURCE_RECHECK'
            for path in disk:require(sha256(self._read(path)).hexdigest()==pins[path],'ORIGINAL_SOURCE_CHANGED')
        with self.lock:
            require(attempt==self._attempt,'CAPTURE_SUPERSEDED')
            self._validate(package,state)  # Include any wait for publication lock.
            if audit is not None:
                audit.stage='FINAL_ADMISSION';audit.finish('CAPTURED',self._now(),receipt=receipt)
            self._current=dict(package=deepcopy(package),state=deepcopy(state),disk=disk,attempt=attempt,
                account_id=ledger['account_id'],decision_id=decision['decision_id'])
        return dict(status='CAPTURED',account_id=ledger['account_id'],decision_id=decision['decision_id'],
            revision=ledger['revision'],attempt=attempt,source_authenticated=False,account_mutated=False,
            **({'capture_id':audit.identifier} if audit is not None else {}))

    def _validate(self,package,state):
        CurrentQuantityV2DifferenceService._package_identity(package)
        ledger=state['ledger'];needed={s for m in (ledger['shares'],ledger['target_quantities']) for s,q in m.items() if q}
        now=self._now();inputs=decode_execution_package(package,needed=needed,now=now)
        build_continuation(state,execution_inputs=inputs,now=self._now())

    def resolve(self,account_id,decision_id):
        with self.lock:
            require(self._current is not None,'CONTINUATION_CAPTURE_REQUIRED');saved=deepcopy(self._current)
        require((account_id,decision_id)==(saved['account_id'],saved['decision_id']),'CAPTURE_ACCOUNT_DECISION_MISMATCH')
        for path in saved['disk']:
            require(sha256(self._read(path)).hexdigest()==saved['package']['source_hashes'][path],'ORIGINAL_SOURCE_CHANGED')
        self._validate(saved['package'],saved['state'])
        with self.lock:
            require(self._current is not None and self._attempt==saved['attempt'],'CAPTURE_SUPERSEDED')
            self._validate(saved['package'],saved['state'])
        return deepcopy(saved['package'])
