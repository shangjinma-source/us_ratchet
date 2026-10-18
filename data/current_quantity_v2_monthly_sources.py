"""Explicit monthly capture and durable immutable bytes; no production instance.

Readers are server-owned. An object capture(snapshot) may fetch review evidence
once per explicit capture; its read(snapshot) (or __call__) must replay frozen
bytes without fetching. Legacy callbacks remain read-only. Neither may search
or invent action clearance. Hold lock DB->source
through acceptance commit. Restart has no current authority.
"""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_service import CurrentQuantityV2DifferenceService,document
from data.current_quantity_v2_difference_plan import require,stamp,number
from data.current_quantity_projection_v2 import project_capital_decision_v2
from data.current_quantity_v2_paper_chain import review_chain
from data.current_quantity_v2_monthly_retarget import active_proposal,build_monthly_retarget,active_entry_policy
from data.current_quantity_v2_monthly_service import QuantityV2MonthlySourceBridge
from data.current_research_intraday_execution import fetch_intraday_chart,decode_intraday_reference
from data.current_research_intraday_journal import _publish as publish_bytes
from data.current_quantity_v2_monthly_capture_audit import CaptureAudit,read_capture,safe_reason


class QuantityV2MonthlySources:
    def __init__(self,*,storage_root,decision_reader,review_reader,fetch=fetch_intraday_chart,
                 clock=lambda:datetime.now(timezone.utc),pullback_policy=None,pullback_cap_store=None):
        self.storage_root=Path(storage_root);self.decision_reader=decision_reader;self.review_reader=review_reader
        self.fetch=fetch;self.clock=clock;self.lock=RLock();self._attempt=0;self._current=None
        require((pullback_policy is None)==(pullback_cap_store is None),'PULLBACK_POLICY_STORE_PAIR_REQUIRED')
        require(pullback_cap_store is None or callable(getattr(pullback_cap_store,'candidate',None)),'PULLBACK_CAP_STORE_REQUIRED')
        if pullback_policy is not None:
            require(type(pullback_policy)is dict and set(pullback_policy)=={'schema','status','rebound_fraction','minimum_discount','maximum_age_seconds'}
                    and pullback_policy['schema']=='V2_PULLBACK_EXECUTION_POLICY_V1'
                    and pullback_policy['status']=='EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED'
                    and 0<number(pullback_policy['rebound_fraction'])<1 and 0<number(pullback_policy['minimum_discount'])<1
                    and type(pullback_policy['maximum_age_seconds'])is int
                    and 0<pullback_policy['maximum_age_seconds']<=120,'INVALID_PULLBACK_POLICY')
        self.pullback_policy=deepcopy(pullback_policy);self.pullback_cap_store=pullback_cap_store

    def _now(self):return stamp(self.clock())

    @staticmethod
    def _identity(package):
        identity=CurrentQuantityV2DifferenceService._package_identity(package)
        for path in package['files']:CurrentQuantityV2CurrentCashSources._path(path)
        return identity

    def _review(self,snapshot,*,capture=False):
        reader=self.review_reader
        replay=getattr(reader,'read',None)
        if not callable(replay):replay=reader
        require(callable(replay),'MONTHLY_SOURCE_READER_REQUIRED')
        method=getattr(reader,'capture',None) if capture else replay
        if not callable(method):method=replay
        return deepcopy(method(deepcopy(snapshot)))

    def _base(self,state):
        from data.current_quantity_v2_monthly_retarget import require_supported_monthly_entry_policy
        policy=active_entry_policy(state['ledger'])
        if policy is not None:
            require_supported_monthly_entry_policy(state['ledger'],self.pullback_policy)
            require(self.pullback_cap_store is not None,'PULLBACK_MONTHLY_POLICY_REQUIRED')
        require(callable(self.decision_reader) and (callable(getattr(self.review_reader,'read',None))
            or callable(self.review_reader)),'MONTHLY_SOURCE_READER_REQUIRED')
        base=deepcopy(self.decision_reader(deepcopy(state)));identity=self._identity(base)
        require(set(base['documents'])=={'capital_decision','target_mandate','identities'},'MONTHLY_BASE_DOCUMENT_FIELDS')
        d,m,i=(document(base['files'][base['documents'][k]]) for k in ('capital_decision','target_mandate','identities'))
        project_capital_decision_v2(d);ledger=state['ledger'];old=active_proposal(ledger)
        require(all(o['closed'] for o in ledger['orders'].values()) and number(ledger['reserved_cash'])==0
            and not any(ledger['reserved_shares'].values()),'PRIOR_ORDERS_OPEN')
        now=self._now();b=d['binding'];previous=old['causal_inputs']['capital_decision']
        oldmonth=old.get('target_month') or old['causal_inputs']['target_mandate']['target_month']
        require(m['account_id']==ledger['account_id'] and m['capital_decision_id']==d['decision_id']
            and m['target_month']>oldmonth and m['target_month']==now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
            and previous['decision_date']<d['decision_date']<=m['active_date']<=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
            and m['active_date'][:7]==m['target_month'],'NEW_MONTHLY_DECISION_REQUIRED')
        require(b['state_revision']==ledger['revision'] and b['shares']==ledger['shares']
            and number(b['available_cash'])==number(ledger['cash']),'MONTHLY_ACCOUNT_MISMATCH')
        require(all(base['source_hashes'].get(p)==h for p,h in b['source_hashes'].items()),'CAPITAL_SOURCE_CHANGED')
        needed={s for mapping in (ledger['shares'],d['target_quantities']) for s,q in mapping.items() if q}
        require(set(i['securities'])==needed and i['source_references']
            and all(p in base['source_hashes'] for p in i['source_references']),'COMPLETE_IDENTITY_DOMAIN_REQUIRED')
        return base,identity,d,i,needed

    def _validate(self,package,state):
        bridge=QuantityV2MonthlySourceBridge(store=None,resolver=lambda *args:deepcopy(package),clock=self.clock)
        did=document(package['files'][package['documents']['capital_decision']])['decision_id']
        args,_=bridge._evidence(state,did,self._now())
        return build_monthly_retarget(state,proposal_inputs=args,now=self._now())

    def _publish(self,package,identifier):
        root=self.storage_root.absolute();root.mkdir(parents=True,exist_ok=True);root=root.resolve()
        require(not self.storage_root.is_symlink(),'STORAGE_SYMLINK')
        blobs=root/'blobs';events=root/'captures'
        for path in (blobs,events):
            require(path.resolve().is_relative_to(root),'STORAGE_PATH_ESCAPE');path.mkdir(exist_ok=True)
        for name,raw in package['files'].items():
            path=blobs/package['source_hashes'][name]
            require(path.resolve().is_relative_to(root),'STORAGE_PATH_ESCAPE')
            if path.exists():
                require(path.stat().st_size==len(raw),'STORED_BLOB_CONFLICT')
            publish_bytes(path,raw)
        manifest=canonical(dict(documents=package['documents'],source_hashes=package['source_hashes']))
        target=events/(identifier+'.json');require(target.resolve().is_relative_to(root),'STORAGE_PATH_ESCAPE')
        publish_bytes(target,manifest)
        return dict(path=str(target),sha256=sha256(manifest).hexdigest(),root=str(root))

    def _read_saved(self,saved):
        receipt=saved['receipt'];root=Path(receipt['root']);path=Path(receipt['path'])
        require(path.resolve().is_relative_to(root) and path.stat().st_size<=4*1024*1024,'STORAGE_PATH_ESCAPE')
        raw=path.read_bytes();require(sha256(raw).hexdigest()==receipt['sha256'],'SAVED_PACKAGE_CHANGED')
        manifest=document(raw);files={};total=0
        require(len(manifest['source_hashes'])<=2000,'SOURCE_BYTES_LIMIT')
        for name,h in manifest['source_hashes'].items():
            path=root/'blobs'/h;require(path.resolve().is_relative_to(root),'STORAGE_PATH_ESCAPE')
            size=path.stat().st_size;total+=size;require(size<=32*1024*1024 and total<=128*1024*1024,'SOURCE_BYTES_LIMIT')
            files[name]=path.read_bytes();require(sha256(files[name]).hexdigest()==h,'SAVED_PACKAGE_CHANGED')
        return dict(files=files,**manifest)

    def capture(self,state,expected_decision_id=None):
        with self.lock:self._attempt+=1;attempt=self._attempt;self._current=None
        state=review_chain(state);base,base_id,decision,identities,needed=self._base(state)
        require(expected_decision_id is None or expected_decision_id==decision['decision_id'],'DECISION_BINDING_MISMATCH')
        audit=CaptureAudit(self.storage_root,state,self._now())
        try:
            return self._capture_admitted(state,base,base_id,decision,identities,needed,attempt,audit)
        except Exception as error:
            error.capture_id=audit.identifier
            with self.lock:
                if attempt==self._attempt:self._current=None
            try:audit.finish('FAILED',self._now(),reason=safe_reason(error))
            except Exception as persistence_error:
                persistence_error.capture_id=audit.identifier
                raise persistence_error from error
            raise

    def audit(self,capture_id,account_id):
        return read_capture(self.storage_root,capture_id,account_id)

    def _execution_targets(self,state,decision):
        return decision['target_quantities']

    def _capture_admitted(self,state,base,base_id,decision,identities,needed,attempt,audit):
        package=deepcopy(base);files=package['files'];pins=package['source_hashes'];namespace='generated/monthly/'+str(uuid4())+'/'
        def put(name,value,israw=False):
            path=namespace+name;require(path not in files,'GENERATED_PATH_CONFLICT')
            raw=value if israw else canonical(value);files[path]=raw;pins[path]=sha256(raw).hexdigest();return path
        receipts={};captures={};quotes={};proofs={};policy=active_entry_policy(state['ledger'])
        targets=self._execution_targets(state,decision)
        sell_only={sid for sid,q in state['ledger']['shares'].items() if q>0 and targets.get(sid,0)==0}
        for sid in sorted(needed):
            audit.stage='FETCH'
            ticker=identities['securities'][sid]['ticker']
            if ticker not in quotes:
                raw=self.fetch(ticker);captured=self._now()
                require(type(raw)is bytes and len(raw)<=4*1024*1024,'RAW_QUOTE_BYTES_REQUIRED');quotes[ticker]=(raw,captured)
            raw,captured=quotes[ticker]
            audit.raw(raw,sid,ticker,captured,self._now())
            key=str(len(receipts));rp=put(key+'.raw',raw,True)
            receipt=put(key+'.receipt',dict(security_id=sid,ticker=ticker,raw_path=rp,raw_sha256=pins[rp],captured_at=captured.isoformat()))
            receipts[sid]=receipt;captures[sid]=dict(captured_at=captured.isoformat(),source_hashes={rp:pins[rp],receipt:pins[receipt]})
            if policy is not None and sid not in sell_only:
                audit.stage='PULLBACK'
                checked=self._now();ref=decode_intraday_reference(raw,ticker=ticker,now=checked,captured_at=captured)
                result=self.pullback_cap_store.candidate(raw=raw,expected_sha256=pins[rp],security_id=sid,ticker=ticker,
                    session=ref['session'],session_open=ref['session_open'],session_close=ref['session_close'],
                    captured_at=captured.isoformat(),checked_at=checked.isoformat(),now=checked.isoformat(),
                    **{k:policy[k] for k in ('rebound_fraction','minimum_discount','maximum_age_seconds')})
                proofs[sid]=put(key+'.pullback.json',result['frozen_proof'])
        snapshot=dict(state=deepcopy(state),capital_decision=deepcopy(decision),identities=deepcopy(identities),
            base_files=deepcopy(base['files']),base_source_hashes=deepcopy(base['source_hashes']),
            base_documents=deepcopy(base['documents']),current_receipts=captures,quote_files={p:files[p] for r in captures.values() for p in r['source_hashes']})
        audit.stage='REVIEW'
        reviewed=self._review(snapshot,capture=True);review_id=self._identity(reviewed)
        require(set(reviewed['documents'])=={'unit_continuity','held_unit_continuity','account_review'},'MONTHLY_REVIEW_DOCUMENT_FIELDS')
        for path,raw in reviewed['files'].items():
            require(path not in files or files[path]==raw,'SOURCE_PATH_CONFLICT');files[path]=raw;pins[path]=reviewed['source_hashes'][path]
        package['documents'].update(reviewed['documents'],quote_receipts=receipts)
        if policy is not None:
            package['documents'].update(pullback_policy=put('pullback_policy.json',policy),pullback_proofs=proofs)
        audit.stage='VALIDATE'
        self._identity(package);self._validate(package,state)
        audit.stage='PUBLISH'
        with self.lock:
            require(attempt==self._attempt,'CAPTURE_SUPERSEDED')
            require(self._base(state)[1]==base_id and self._identity(self._review(snapshot))==review_id,'REGISTERED_SOURCE_CHANGED')
            receipt=self._publish(package,str(uuid4()))
            require(self._read_saved({'receipt':receipt})==package,'SAVED_PACKAGE_CHANGED')
            require(self._base(state)[1]==base_id and self._identity(self._review(snapshot))==review_id,'REGISTERED_SOURCE_CHANGED')
            require(attempt==self._attempt,'CAPTURE_SUPERSEDED')
            self._validate(package,state)
            audit.finish('CAPTURED',self._now(),receipt=receipt)
            self._current=dict(state=state,base_identity=base_id,review_identity=review_id,snapshot=snapshot,receipt=receipt,
                account_id=state['ledger']['account_id'],decision_id=decision['decision_id'],attempt=attempt)
        return dict(status='CAPTURED',capture_id=audit.identifier,account_id=state['ledger']['account_id'],decision_id=decision['decision_id'],attempt=attempt,
            source_authenticated=False,receipt=receipt)

    def resolve(self,account_id,decision_id):
        with self.lock:
            require(self._current is not None,'MONTHLY_CAPTURE_REQUIRED');saved=deepcopy(self._current)
            require((account_id,decision_id)==(saved['account_id'],saved['decision_id']),'CAPTURE_ACCOUNT_DECISION_MISMATCH')
            require(self._base(saved['state'])[1]==saved['base_identity']
                and self._identity(self._review(saved['snapshot']))==saved['review_identity'],'REGISTERED_SOURCE_CHANGED')
            package=self._read_saved(saved);self._identity(package);self._validate(package,saved['state'])
            require(self._current is not None and self._attempt==saved['attempt'],'CAPTURE_SUPERSEDED')
            return package
