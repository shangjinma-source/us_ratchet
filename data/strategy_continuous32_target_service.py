"""Server-owned target lifecycle. No HTTP wiring or client clock/decision inputs.

The explicit pin set is a deployment-review boundary, not a claim that Python's
entire transitive import/runtime closure has been proven. Providers must verify
their external source evidence. This layer never writes the account.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath
from threading import RLock
from backtest.continuous_guided_account_decision import REQUIRED_PINS
from data.strategy_account_target_service import MINIMUM_RUNTIME_PATHS as ORIGINAL_RUNTIME_PATHS
from core.strategy_account_ledger import canonical
from data.strategy_account_preview import preview_scoped_account
from data.strategy_continuous32_target_decision import decide_target, validate_result, PROFILE_ID, VERSION
from data.strategy_account_target_inputs import require, stamp

MINIMUM_RUNTIME_PATHS=ORIGINAL_RUNTIME_PATHS|set(REQUIRED_PINS)|{
    'data/strategy_continuous32_target_service.py','data/strategy_continuous32_target_decision.py',
    'data/strategy_account_target_service.py','data/strategy_account_target_decision.py',
    'data/strategy_account_target_inputs.py','data/strategy_account_preview.py',
    'core/strategy_account_ledger.py','core/strategy_account_store.py','core/strategy_account_difference.py',
    'data/current_quantity_v2_monthly_training.py','scripts/return_priority_current_rebased_training.py',
}


class StrategyContinuous32TargetService:
    def __init__(self,*,store,evidence_provider,runtime_root,runtime_pins,
                 maximum_mark_age_seconds,execution_fee_bps,clock=None):
        self.store=store;self.provider=evidence_provider;self.root=Path(runtime_root).resolve()
        self.pins=deepcopy(runtime_pins);self.age=maximum_mark_age_seconds;self.fees=execution_fee_bps
        self.clock=clock or (lambda:datetime.now(timezone.utc));self.lock=RLock();self.current=None
        require(type(self.pins)is dict and MINIMUM_RUNTIME_PATHS<=set(self.pins),'EXPLICIT_RUNTIME_PIN_SCOPE_REQUIRED')
        require(type(self.age)is int and self.age>0,'EXPLICIT_FRESHNESS_REQUIRED')

    def _pins(self):
        require(len(self.pins)<=2000,'RUNTIME_PIN_BUDGET')
        for name,expected in self.pins.items():
            require(type(name)is str and '\\' not in name and ':' not in name and not PurePosixPath(name).is_absolute()
                    and all(part not in ('','.','..') for part in name.split('/')),'UNSAFE_RUNTIME_PATH')
            path=self.root/name
            require(not any(p.is_symlink() for p in [path,*path.parents] if p!=self.root.parent),'RUNTIME_SYMLINK_REFUSED')
            require(path.is_file() and path.stat().st_size<=32*1024*1024 and sha256(path.read_bytes()).hexdigest()==expected,'RUNTIME_SOURCE_CHANGED')
            if name in MINIMUM_RUNTIME_PATHS:
                executing=Path(__file__).resolve().parents[1]/name
                require(sha256(executing.read_bytes()).hexdigest()==expected,'EXECUTING_RUNTIME_SOURCE_CHANGED')

    def _now(self):
        value=self.clock()
        require(isinstance(value,datetime) and value.tzinfo is not None and value.utcoffset() is not None,'AWARE_SERVER_CLOCK_REQUIRED')
        return value

    def _account(self,initial):
        current=self.store.read()
        require(current is not None and current['account_id']==initial['account_id'] and current['revision']==initial['revision'],'ACCOUNT_CHANGED_DURING_TARGET')
        return current

    def _fresh(self,decision,at):
        binding=decision['payload']['input_binding']
        require(at>=stamp(binding['valuation_at']),'SERVER_CLOCK_ROLLBACK')
        for mark in binding['marks'].values():
            require(0<=(at-stamp(mark['observed_at'])).total_seconds()<=self.age,'REQUOTE_REQUIRED')

    def generate(self):
        """Compatibility interface: selection and immediate difference preview."""
        return self._generate(selection_only=False)

    def select(self):
        """Select and retain a decision; execution limits are requested separately."""
        return self._generate(selection_only=True)

    def _generate(self, *, selection_only):
        """Provider(state) returns input source package/document paths and limits only."""
        with self.lock:
            self.current=None
            try:
                self._pins();state=self.store.read();require(state is not None,'ACCOUNT_NOT_INITIALIZED')
                require(state['cash_confirmation_valid'] and state['execution_ready'],'CASH_RECONFIRMATION_REQUIRED')
                started=self._now();evidence=self.provider(deepcopy(state))
                fields={'source_package','manifest_path','marks_path','unit_review_path'}
                allowed = (fields, fields|{'limits'}) if selection_only else (fields|{'limits'},)
                require(type(evidence)is dict and set(evidence) in allowed,'TARGET_PROVIDER_FIELDS')
                evidence=deepcopy(evidence)
                package=evidence['source_package']
                for name in MINIMUM_RUNTIME_PATHS:
                    raw=(self.root/name).read_bytes()
                    require(sha256(raw).hexdigest()==self.pins[name], 'CONTINUOUS32_SOURCE_CHANGED')
                    require(name not in package['source_hashes'] or package['source_hashes'][name]==self.pins[name], 'CONTINUOUS32_SOURCE_CONFLICT')
                    require(name not in package['files'] or package['files'][name]==raw, 'CONTINUOUS32_SOURCE_CONFLICT')
                    package['files'][name]=raw;package['source_hashes'][name]=self.pins[name]
                self._pins();self._account(state);valuation=self._now();require(valuation>=started,'SERVER_CLOCK_ROLLBACK')
                decision=decide_target(state=state,now=valuation.isoformat(),maximum_mark_age_seconds=self.age,
                    **{k:deepcopy(v) for k,v in evidence.items() if k!='limits'})
                self._pins();self._account(state);finished=self._now();self._fresh(decision,finished)
                if decision['status']!='TARGET_READY':return dict(status='SEARCH_INCOMPLETE',execution_blocked=True)
                self.current=(deepcopy(decision),deepcopy(evidence.get('limits')),deepcopy(state))
                if selection_only:
                    return dict(status='READY',decision_id=decision['decision_id'],selector_profile=PROFILE_ID,account_revision=state['revision'],
                        orders_created=False,account_mutated=False,execution_previewed=False)
                return self._preview()
            except ValueError as error:
                self.current=None
                reason=str(error)
                if reason in {'STALE_OR_FUTURE_MARK','STALE_OR_FUTURE_MARKS'}:reason='REQUOTE_REQUIRED'
                if not reason.replace('_','').isalnum() or len(reason)>100:reason='TARGET_UNAVAILABLE'
                return dict(status='REQUOTE_REQUIRED' if reason=='REQUOTE_REQUIRED' else 'BLOCKED',reason=reason,execution_blocked=True)
            except Exception:
                self.current=None
                return dict(status='BLOCKED',reason='TARGET_UNAVAILABLE',execution_blocked=True)

    def _preview(self):
        require(self.current is not None,'NO_CURRENT_TARGET')
        decision,limits,original=self.current
        self._pins();state=self._account(original);at=self._now();self._fresh(decision,at)
        target=decision['payload']['target_quantities']
        needed=set(target)|{sid for sid,q in state['shares'].items() if q}|{o['security_id'] for o in state['orders'].values() if o['status']=='OPEN'}
        require(type(limits)is dict,'EXECUTION_LIMITS_REQUIRED')
        require(needed<=set(limits),'EXECUTION_LIMIT_DOMAIN_MISMATCH')
        difference=preview_target(decision=decision,state=state,limits={sid:limits[sid] for sid in needed},now=at.isoformat(),
            maximum_mark_age_seconds=self.age,execution_fee_bps=self.fees,legacy_shares={})
        self._pins();self._account(original);self._fresh(decision,self._now())
        return dict(status='READY',decision_id=decision['decision_id'],selector_profile=PROFILE_ID,account_revision=state['revision'],
            difference=difference,orders_created=False,account_mutated=False,
            runtime_pin_scope=sorted(self.pins),runtime_transitive_closure_certified=False)

    def preview(self):
        """No client-supplied decision or timestamp; recompute from retained binding."""
        with self.lock:
            try:return self._preview()
            except Exception as error:
                self.current=None
                reason=str(error) if isinstance(error,ValueError) and str(error).replace('_','').isalnum() and len(str(error))<=100 else 'TARGET_UNAVAILABLE'
                return dict(status='REQUOTE_REQUIRED' if reason in {'REQUOTE_REQUIRED','STALE_OR_FUTURE_MARK'} else 'BLOCKED',reason=reason,execution_blocked=True)


def preview_target(*,decision,state,limits,now,maximum_mark_age_seconds,execution_fee_bps,legacy_shares):
    payload=decision['payload'];binding=payload['input_binding']
    require(sha256(canonical(payload)).hexdigest()==decision['decision_id'],'TARGET_DECISION_CHANGED')
    require(sha256(canonical(binding)).hexdigest()==payload['input_id'],'TARGET_INPUT_CHANGED')
    require(binding.get('selector_profile')==PROFILE_ID and binding.get('selection_method')==VERSION
            and binding.get('continuous_iterations')==32,'CONTINUOUS32_PROFILE_CHANGED')
    require(decision['status']=='TARGET_READY','TARGET_NOT_READY')
    target=validate_result(payload['search_result'],binding['search_arguments'])
    require(target==payload['target_quantities'],'TARGET_QUANTITIES_CHANGED')
    require(state['account_id']==binding['account_id'] and state['revision']==binding['account_revision'],'STALE_ACCOUNT_TARGET')
    needed=set(target)|{sid for sid,q in state['shares'].items() if q}|{o['security_id'] for o in state['orders'].values() if o['status']=='OPEN'}
    require(set(limits)==needed,'EXECUTION_LIMIT_DOMAIN_MISMATCH')
    return preview_scoped_account(state=state,legacy_shares=legacy_shares,
        marks={sid:deepcopy(binding['marks'][sid]) for sid in needed},limits=limits,
        target_quantities=target,now=now,maximum_mark_age_seconds=maximum_mark_age_seconds,
        fee_bps=execution_fee_bps)
