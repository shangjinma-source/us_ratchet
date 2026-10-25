"""Explicit capital contribution orchestration, isolated from ordinary cash saves."""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256

from core.strategy_account_ledger import canonical, require
from core.strategy_account_difference import number
from backtest.continuous_guided_account_decision import VERSION, REQUIRED_PINS
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_continuous32_target_service import StrategyContinuous32TargetService as StrategyAccountTargetService, MINIMUM_RUNTIME_PATHS
from data.strategy_account_monthly_release import validate_account_identity_coverage


class ProfiledCapitalContributionService:
    def __init__(self, *, monthly, journal, validate_code):
        self.monthly, self.journal, self.validate_code = monthly, journal, validate_code

    def _snapshot(self):
        self.validate_code()
        state,target=self.monthly.accounts.read(),self.monthly.current()
        require(state is not None and target is not None,"CAPITAL_ACCOUNT_AND_TARGET_REQUIRED")
        require(target["payload"]["account_id"]==state["account_id"],"TARGET_ACCOUNT_MISMATCH")
        require(target["payload"]["target_month"]==self.monthly._month(),"CAPITAL_CURRENT_MONTH_TARGET_REQUIRED")
        runtime,configuration=self.monthly._for_target(target)
        validate_account_identity_coverage(self.monthly.root,configuration,state)
        require(type(runtime.selection) is StrategyAccountTargetService,'CAPITAL_EXPLICIT_CONTINUOUS32_RUNTIME_REQUIRED')
        runtime.selection._pins()
        return state,target,runtime

    def _profile(self,runtime):
        provider=runtime.execution_provider
        require(getattr(provider,"__func__",None) is StrategyAccountEvidenceProvider.execution,
                "CAPITAL_REAL_PROVIDER_REQUIRED")
        _,history=provider.__self__.training()
        budget=history["max_objective_evaluations"]
        require(type(budget) is int and budget>0,"CAPITAL_ADMITTED_BUDGET_REQUIRED")
        return dict(method_version=VERSION,selector_profile=PROFILE_ID,continuous_iterations=32,max_objective_evaluations=budget,
                    source_pins={p:runtime.selection.pins[p] for p in REQUIRED_PINS})

    def record(self, *, event_id, contribution_amount, expected_revision, previous_target_id):
        with self.monthly.snapshot_operation():
            state,target,_=self._snapshot()
            require(state["revision"]==expected_revision and target["target_id"]==previous_target_id,
                    "CAPITAL_STALE_SNAPSHOT")
            rows=[r["payload"] for r in state["events"] if r["payload"]["kind"]=="CASH_CONFIRM"]
            require(bool(rows),"CAPITAL_BALANCE_CONFIRMATION_REQUIRED")
            confirmation=rows[-1]
            intent=dict(event_id=event_id,contribution_amount=str(number(contribution_amount)),
                account_id=state["account_id"],account_revision=expected_revision,
                previous_target_id=previous_target_id,available_balance=state["available_cash"],
                balance_confirmation_reference=dict(event_id=confirmation["event_id"],
                    payload_sha256=sha256(canonical(confirmation)).hexdigest()))
            self.journal.record(intent,account_state=state,previous_target=target)
            self.validate_code()
            return dict(status="INTENT_RECORDED",event_id=event_id,contribution_amount=intent["contribution_amount"],
                        confirmed_available_balance=intent["available_balance"],account_mutated=False)

    def status(self, *, event_id):
        with self.monthly.snapshot_operation():
            self.validate_code()
            result=self.journal.reconcile(event_id,target_store=self.monthly.targets)
            self.validate_code()
            return result

    def _publish(self,event_id,state,target,runtime):
        candidate=self.journal.publication_candidate(event_id,account_state=state,previous_target=target)
        require(candidate["profile"]==self._profile(runtime),"CAPITAL_ADMISSION_CHANGED")
        # Reuse original freshness and immutable training checks; no fresh
        # market request and no new selection are allowed during recovery.
        runtime.selection._fresh(candidate["decision"],runtime.selection._now())
        training,_=runtime.execution_provider.__self__.training()
        closure=candidate["decision"]["payload"]["input_binding"]["source_hashes"]
        require(all(closure.get(name)==digest for name,digest in training["source_hashes"].items()),
                "CAPITAL_PREPARED_SOURCE_CHANGED")
        self.validate_code();runtime.selection._pins()
        # Account SQLite is locked only for final validation/publication. This
        # does not make journal and target commits one transaction.
        with closing(self.monthly.accounts._connect(False)) as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                current,_=self.monthly.accounts._read(con)
                require(current==state,"ACCOUNT_CHANGED_DURING_CAPITAL_PUBLICATION")
                require(self.monthly.current()==target,"TARGET_CHANGED_DURING_CAPITAL_PUBLICATION")
                require(target["payload"]["target_month"]==self.monthly._month(),"CAPITAL_MONTH_CHANGED")
                self.validate_code();runtime.selection._pins()
                runtime.selection._fresh(candidate["decision"],runtime.selection._now())
                payload=dict(schema="REAL_STRATEGY_MONTHLY_TARGET_V1",account_id=state["account_id"],
                    target_month=target["payload"]["target_month"],created_at=self.monthly.clock().isoformat(),
                    request=candidate["request"],previous_target_id=target["target_id"],
                    decision=candidate["decision"],target_quantities=candidate["decision"]["payload"]["target_quantities"],
                    runtime_pins=deepcopy(runtime.selection.pins))
                self.monthly.targets.append(payload)
            finally:
                con.rollback()
        return self.journal.reconcile(event_id,target_store=self.monthly.targets)

    def configure(self, *, event_id):
        with self.monthly.snapshot_operation():
            self.validate_code()
            status=self.journal.reconcile(event_id,target_store=self.monthly.targets)
            if status["status"]=="CONSUMED_BY_PUBLISHED_TARGET":return status
            require(status["status"] in {"INTENT_RECORDED","PREPARED_PUBLISH_ONLY"},"CAPITAL_RECOVERY_REQUIRED")
            state,target,runtime=self._snapshot()
            if status["status"]=="PREPARED_PUBLISH_ONLY":
                return self._publish(event_id,state,target,runtime)
            profile=self._profile(runtime)
            claim=self.journal.claim_selection_once(event_id,account_state=state,previous_target=target)
            require(claim["may_start_selection"],"CAPITAL_RECOVERY_REQUIRED")
            captures=[]
            def evidence_provider(snapshot):
                evidence=deepcopy(runtime.selection.provider(snapshot))
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

    def recover_publication(self, *, event_id):
        """Never invoke a selector, even when no candidate was prepared."""
        with self.monthly.snapshot_operation():
            self.validate_code()
            status=self.journal.reconcile(event_id,target_store=self.monthly.targets)
            if status["status"]=="CONSUMED_BY_PUBLISHED_TARGET":return status
            require(status["status"]=="PREPARED_PUBLISH_ONLY","CAPITAL_PREPARED_RECOVERY_REQUIRED")
            state,target,runtime=self._snapshot()
            return self._publish(event_id,state,target,runtime)
