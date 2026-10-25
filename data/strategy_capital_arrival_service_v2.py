"""Single-input arrived capital: durable intent + idempotent atomic ledger update.
Two databases are not an atomic commit. The fixed ledger event is the cash authority;
recovery never computes a second increment or restores a stale balance.
"""
from hashlib import sha256
from copy import deepcopy
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from data.strategy_continuous32_target_service import StrategyContinuous32TargetService as StrategyAccountTargetService, MINIMUM_RUNTIME_PATHS
from core.strategy_account_ledger import canonical,require
from core.strategy_account_difference import number
from data.strategy_profiled_capital_service import ProfiledCapitalContributionService

class CapitalArrivalServiceV2(ProfiledCapitalContributionService):
    def __init__(self,*,monthly,journal,validate_code,capture_provider_builder=None):
        super().__init__(monthly=monthly,journal=journal,validate_code=validate_code)
        from data.strategy_capital_capture_provider_v2 import capital_capture_provider
        self.capture_provider_builder=capture_provider_builder or capital_capture_provider

    def _before_claim(self,state,target,runtime,evidence):
        from data.strategy_account_target_inputs import build_target_inputs
        self.validate_code();runtime.selection._pins()
        require(self.monthly.accounts.read()==state and self.monthly.current()==target,'CAPITAL_SNAPSHOT_CHANGED')
        at=self.monthly.clock()
        build_target_inputs(state=state,now=at.isoformat(),maximum_mark_age_seconds=runtime.selection.age,**{k:v for k,v in evidence.items() if k!='limits'})
        store=self.monthly.targets
        if hasattr(store,'calendar_path'):
            from scripts.register_quantity_v2_paper_protocol import safe_path
            path=safe_path(store.root,store.calendar_path)
            with path.open('rb') as stream:raw=stream.read(1024*1024+1)
            require(len(raw)<=1024*1024 and sha256(raw).hexdigest()==store.calendar_sha256,'PUBLICATION_CALENDAR_CHANGED')
            calendar=json.loads(raw);require(calendar['schema']=='FIXED_EXCHANGE_SESSIONS_V1' and calendar['exchange']=='NASDAQ','PUBLICATION_CALENDAR_SCHEMA')
            day=at.astimezone(ZoneInfo('America/New_York')).date().isoformat()
            sessions=[row for row in calendar['sessions'] if row['date']==day]
            require(len(sessions)==1 and datetime.fromisoformat(sessions[0]['open'])<=at<datetime.fromisoformat(sessions[0]['close']),'PUBLICATION_OUTSIDE_SESSION')
        require(target['payload']['target_month']==self.monthly._month(),'CAPITAL_MONTH_CHANGED')

    def _publish(self,event_id,state,target,runtime):
        result=super()._publish(event_id,state,target,runtime)
        current=self.monthly.accounts.read()
        return dict(result,event_id=event_id,credited=True,account_revision=current['revision'],confirmed_available_balance=current['available_cash'])

    def _credit(self,event_id):
        request=self.journal.arrival(event_id)
        if request is None:return None,False
        state=self.monthly.accounts.read()
        rows=[r['payload'] for r in state['events'] if r['payload']['event_id']==request['cash_event']['event_id']]
        require(not rows or rows==[request['cash_event']],'CAPITAL_CREDIT_EVENT_CONFLICT')
        return request,bool(rows)

    def status(self,*,event_id):
        with self.monthly.snapshot_operation():
            self.validate_code();request,credited=self._credit(event_id)
            result=self.journal.reconcile(event_id,target_store=self.monthly.targets)
            if result['status']=='NOT_FOUND' and request:result=dict(status='CASH_RECORDED' if credited else 'ARRIVAL_RECORDED')
            self.validate_code()
            state=self.monthly.accounts.read()
            return dict(result,event_id=event_id,credited=credited,account_revision=state['revision'],confirmed_available_balance=state['available_cash'],contribution_amount=request['contribution_amount'] if request else None)

    def arrive(self,*,event_id,contribution_amount,expected_revision,previous_target_id):
        require(type(event_id) is str and 0<len(event_id)<=128,'CAPITAL_EVENT_ID')
        amount=number(contribution_amount);require(amount>0,'CAPITAL_AMOUNTS_INVALID')
        with self.monthly.snapshot_operation():
            self.validate_code()
            request,credited=self._credit(event_id)
            require(self.journal.reconcile(event_id,target_store=self.monthly.targets)['status']!='WITHDRAWN','CAPITAL_INTENT_WITHDRAWN')
            if request:
                require(request['contribution_amount']==str(amount) and request['expected_revision']==expected_revision and request['previous_target_id']==previous_target_id,'CAPITAL_EVENT_CONFLICT')
                state=self.monthly.accounts.read();target=self.monthly.current()
            else:
                state,target,_=self._snapshot()
                require(state['revision']==expected_revision and target['target_id']==previous_target_id,'CAPITAL_STALE_SNAPSHOT')
                require(state['cash_confirmation_valid'],'CAPITAL_BALANCE_CONFIRMATION_REQUIRED')
                require(number(state['available_cash'])>=0,'CAPITAL_AMOUNTS_INVALID')
                cash_event=dict(event_id='capital-arrival:'+sha256(event_id.encode()).hexdigest(),kind='CASH_CONFIRM',amount=str(number(state['available_cash'])+amount),cash_basis='AVAILABLE_AFTER_RESERVATIONS')
                request=dict(event_id=event_id,account_id=state['account_id'],expected_revision=expected_revision,previous_target_id=previous_target_id,contribution_amount=str(amount),base_available_cash=state['available_cash'],cash_event=cash_event)
                self.journal.save_arrival(request)
            require(state['account_id']==request['account_id'] and target['target_id']==previous_target_id,'CAPITAL_STALE_SNAPSHOT')
            if not credited:
                self.validate_code()
                self.monthly.accounts.append(request['cash_event'],expected_revision=expected_revision)
            # Cash is now authoritative even if record/configuration subsequently fails.
            state=self.monthly.accounts.read()
            if state['last_cash_confirmation_event']!=request['cash_event']['event_id']:
                return dict(status='CREDITED_REVIEW_REQUIRED',event_id=event_id,credited=True,reason='ACCOUNT_CHANGED_AFTER_CAPITAL_CREDIT')
            existing=self.journal.intent(event_id)
            if existing is None:
                self.record(event_id=event_id,contribution_amount=str(amount),expected_revision=state['revision'],previous_target_id=previous_target_id)
            return self.status(event_id=event_id)

    def withdraw(self,*,event_id,reason='FUNDS_NOT_RECEIVED'):
        with self.monthly.snapshot_operation():
            self.validate_code()
            require(not self._credit(event_id)[1],'CAPITAL_CREDIT_CANNOT_WITHDRAW')
            result=self.journal.withdraw(event_id,target_store=self.monthly.targets,reason=reason,checked_at=self.monthly.clock().isoformat())
            self.validate_code();return result

    def configure(self, *, event_id):
        require(self._credit(event_id)[1],'CAPITAL_ARRIVAL_NOT_CREDITED')
        with self.monthly.snapshot_operation():
            self.validate_code()
            status=self.journal.reconcile(event_id,target_store=self.monthly.targets)
            if status["status"]=="CONSUMED_BY_PUBLISHED_TARGET":return self.status(event_id=event_id)
            require(status["status"] in {"INTENT_RECORDED","PREPARED_PUBLISH_ONLY"},"CAPITAL_RECOVERY_REQUIRED")
            state,target,runtime=self._snapshot()
            if status["status"]=="PREPARED_PUBLISH_ONLY":
                return self._publish(event_id,state,target,runtime)
            profile=self._profile(runtime)
            captures=[]
            require(not self.journal.source_directory(event_id).exists(),'CAPITAL_SOURCE_STORAGE_RECOVERY_REQUIRED')
            admitted_capture=self.capture_provider_builder(runtime)
            def capture_evidence(snapshot):
                require(target["payload"]["target_month"]==self.monthly._month(),"CAPITAL_MONTH_CHANGED")
                evidence=deepcopy(admitted_capture(snapshot))
                # Retain the exact explicit source augmentation performed by
                # the continuous selector, so prepared evidence is recoverable.
                package=evidence['source_package']
                for name in MINIMUM_RUNTIME_PATHS:
                    raw=(runtime.selection.root/name).read_bytes();digest=runtime.selection.pins[name]
                    require(sha256(raw).hexdigest()==digest,'CONTINUOUS32_SOURCE_CHANGED')
                    require(name not in package['source_hashes'] or package['source_hashes'][name]==digest,'CONTINUOUS32_SOURCE_CONFLICT')
                    require(name not in package['files'] or package['files'][name]==raw,'CONTINUOUS32_SOURCE_CONFLICT')
                    package['files'][name]=raw;package['source_hashes'][name]=digest
                require(not captures,"CAPITAL_MULTIPLE_SOURCE_CAPTURES")
                captures.append(deepcopy(evidence["source_package"]["files"]))
                return evidence
            evidence=capture_evidence(state)
            self.validate_code();runtime.selection._pins()
            require(self.monthly.accounts.read()==state and self.monthly.current()==target,'CAPITAL_SNAPSHOT_CHANGED')
            self.journal.seal_sources(event_id,evidence['source_package']['files'],evidence['source_package']['source_hashes'])
            self._before_claim(state,target,runtime,evidence)
            claim=self.journal.claim_selection_once(event_id,account_state=state,previous_target=target)
            require(claim['may_start_selection'],'CAPITAL_RECOVERY_REQUIRED')
            def evidence_provider(snapshot):
                require(snapshot==state,'CAPITAL_SNAPSHOT_CHANGED')
                return deepcopy(evidence)
            # Use the actual selector implementation without mutating a cached
            # runtime or forging a provider bound method.
            selector=StrategyAccountTargetService(store=self.monthly.accounts,evidence_provider=evidence_provider,
                runtime_root=runtime.selection.root,runtime_pins=runtime.selection.pins,
                maximum_mark_age_seconds=runtime.selection.age,execution_fee_bps=runtime.selection.fees,
                clock=self.monthly.clock)
            selected=selector.select()
            require(selected["status"]=="READY",selected.get("reason","CAPITAL_SELECTION_FAILED"))
            decision,_,snapshot=selector.current
            require(snapshot==state and self.monthly.accounts.read()==state
                    and self.monthly.current()==target,"CAPITAL_SNAPSHOT_CHANGED")
            require(len(captures)==1,"CAPITAL_SOURCE_CAPTURE_REQUIRED")
            self.validate_code();runtime.selection._pins()
            self.journal.prepare(event_id,decision=decision,source_files=captures[0],profile=profile,
                                 account_state=state,previous_target=target)
            return self._publish(event_id,state,target,runtime)

    def recover_publication(self,*,event_id):
        require(self._credit(event_id)[1],'CAPITAL_ARRIVAL_NOT_CREDITED')
        result=super().recover_publication(event_id=event_id)
        return dict(result,event_id=event_id,credited=True)

