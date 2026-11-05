"""Isolated shared runtime. Synthetic evidence permitted only in disposable tests.

No production reader, route activation, authenticated broker evidence or model IO.
"""
from copy import deepcopy
from hashlib import sha256
from threading import RLock
from uuid import uuid4
from core.strategy_account_ledger import canonical, require
from core.strategy_account_difference import timestamp
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from docs.candidates.strategy_split_daily_execution_bridge import DailyExecutionBridge
from docs.candidates.strategy_split_frontier_preview_service import SavedFrontierPreviewService


class SplitRuntime:
    def __init__(self, *, monthly, provider, risk_store, signal_builder, clock, frontier_view=None):
        require(type(monthly.accounts) is SplitStrategyAccountStore and type(risk_store) is MonthlyPeakExitStore,
                'SPLIT_RUNTIME_STORE_TYPES')
        self.monthly=monthly;self.accounts=monthly.accounts;self.targets=monthly.targets
        self.provider=provider;self.risk=risk_store;self.signal_builder=signal_builder;self.clock=clock
        if frontier_view is not None:
            from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView
            require(type(frontier_view) is SavedFrontierMonthlyView and frontier_view.monthly is monthly,
                    'RUNTIME_FRONTIER_VIEW_BINDING')
        self.frontier_view=frontier_view
        self.lock=RLock();self.generation=uuid4().hex;self.jobs={}
        # These are the same bound runtime, not cached copies of an older service.
        self.daily_observer=self;self.ui=self;self.ai=self

    def _state(self):
        account=self.accounts.read();target=self.targets.current()
        require(account is not None and target is not None,'RUNTIME_ACCOUNT_TARGET_REQUIRED')
        if self.frontier_view is not None:
            view=self.frontier_view.current()
            require(view is not None and view['target_id']==target['target_id'] and view['payload']==target['payload'],
                    'RUNTIME_FRONTIER_TARGET_CHANGED')
            target=view
        risk=self.risk.read(account['account_id'])
        require(risk is not None,'RUNTIME_PERSISTED_RISK_REQUIRED')
        return dict(account=account,target=target,risk=risk,generation=self.generation)

    def context(self):
        with self.lock:return deepcopy(self._state())

    def preview(self):
        with self.lock:
            snapshot=self._state();account,target,risk=(snapshot[k] for k in ('account','target','risk'))
            signal=self.signal_builder(deepcopy(snapshot),self.clock())
            if self.frontier_view is not None:
                require(signal.get('proposal_id')==target['proposal_id'],'RUNTIME_SIGNAL_PROPOSAL_MISMATCH')
            baseline=target.get('risk_monthly_targets',target['payload']['target_quantities'])
            require(set(baseline)<=set(risk['peaks']),'RUNTIME_TARGET_REQUIRES_RISK_HISTORY')
            expected={s:0 if s in risk['exited'] else baseline.get(s,0) for s in set(account['shares'])|set(baseline)}
            require(signal['effective_target_quantities']==expected,'RUNTIME_SIGNAL_IGNORES_PERSISTED_EXIT')
            execution=DailyExecutionBridge(base_target=target,execution_provider=self.provider.execution,
                                           validate_sources=self.monthly.selection._pins,signal=signal)
            observer=SavedFrontierPreviewService(account_store=self.accounts,target_store=self.targets,
                signal_verifier=lambda *args:deepcopy(signal),execution_provider=execution,
                policy_id=signal['policy_id'],clock=self.clock,fee_bps='0',maximum_mark_age_seconds=120,
                monthly_quantities=baseline)
            result=observer.preview()
            require(self._state()==snapshot,'RUNTIME_CHANGED_DURING_PREVIEW')
            # The daily gate does not return its signal deadline. Preserve the
            # actual verified signal's bounds explicitly; HOLD has no quotes.
            quote_deadlines={sid:value['reference_valid_until']
                             for sid,value in result['reference_quotes'].items()}
            deadline=min([timestamp(signal['valid_until'])]+
                         [timestamp(value) for value in quote_deadlines.values()])
            return dict(result, runtime_binding=sha256(canonical(snapshot)).hexdigest(),
                        account_revision=account['revision'],target_id=target['target_id'],generation=self.generation,
                        ai_validity=dict(valid_from=signal['valid_from'],valid_until=deadline.isoformat(),
                                         signal_valid_until=signal['valid_until'],quote_valid_until=quote_deadlines))

    def append(self,event,*,expected_revision):
        with self.lock:return self.accounts.append(event,expected_revision=expected_revision)

    def start_ai(self):
        with self.lock:
            snapshot=self._state();preview=self.preview()
            require(self._state()==snapshot,'AI_INPUT_CHANGED')
            validity=deepcopy(preview['ai_validity']);started=self.clock()
            require(timestamp(validity['valid_from'])<=started<timestamp(validity['valid_until']),
                    'AI_PREVIEW_EXPIRED')
            job=uuid4().hex;self.jobs[job]=dict(binding=sha256(canonical(snapshot)).hexdigest(),
                                              validity=validity,started_at=started.isoformat())
            return dict(job_id=job,context=deepcopy(snapshot),preview=deepcopy(preview))

    def complete_ai(self,job_id,opinion):
        with self.lock:
            expected=self.jobs.pop(job_id,None)
            require(expected is not None and expected['binding']==sha256(canonical(self._state())).hexdigest(),
                    'AI_ACCOUNT_TARGET_RISK_GENERATION_CHANGED')
            current=self.clock()
            require(timestamp(expected['started_at'])<=current<timestamp(expected['validity']['valid_until']),
                    'AI_QUOTE_OR_SIGNAL_EXPIRED')
            return dict(status='BOUND_REVIEW_ONLY',opinion=deepcopy(opinion),runtime_binding=expected['binding'],
                        validity=deepcopy(expected['validity']),
                        orders_created=False,production_activated=False)
