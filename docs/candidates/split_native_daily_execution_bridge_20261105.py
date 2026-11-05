"""Native monthly daily target projection preserving the admitted provider class.

Lineage is a separate receipt: it is not inserted into the immutable training
closure. No deployment or source authentication is granted by this adapter.
"""
from copy import copy, deepcopy
from hashlib import sha256
from types import MethodType
from uuid import uuid4

from core.strategy_account_ledger import canonical, require
from core.strategy_account_difference import number
from docs.candidates.strategy_account_split_evidence_provider import StrategyAccountEvidenceProvider


class DailyExecutionBridge:
    def __init__(self, *, base_target, execution_provider, validate_sources, signal):
        require(getattr(execution_provider, '__func__', None) is StrategyAccountEvidenceProvider.execution,
                'DAILY_PROVIDER_INTERFACE_REQUIRED')
        self.provider = execution_provider.__self__
        self.base = deepcopy(base_target)
        self.signal = deepcopy(signal)
        self.validate_sources = validate_sources

    def __call__(self, state, effective, now):
        return self._execute(state, effective, now, projection=effective)

    def _execute(self, state, effective, now, *, projection, extra=None):
        self.validate_sources()
        require(type(effective) is dict and all(type(q) is int and q >= 0 for q in effective.values()),
                'DAILY_EFFECTIVE_QUANTITIES_INVALID')
        require(self.signal['effective_target_quantities'] == effective, 'DAILY_SIGNAL_TARGET_MISMATCH')
        base, before, expected = deepcopy(self.base), deepcopy(state), deepcopy(effective)
        projected = deepcopy(projection)
        lineage = dict(schema='DAILY_EXECUTION_PROJECTION_V1', base_target_id=base['target_id'],
            base_decision_id=base['payload']['decision']['decision_id'], account_revision=state['revision'],
            policy_id=self.signal['policy_id'], evidence_id=self.signal['evidence_id'],
            signal=deepcopy(self.signal), effective_target_quantities=expected)
        lineage.update(extra or {})
        raw = canonical(lineage)
        directory = self.provider.output / ('daily-native-' + uuid4().hex)
        directory.mkdir(parents=True, exist_ok=False)
        binding_path = directory / 'daily-binding.json'
        binding_path.write_bytes(raw)
        local = copy(self.provider)
        local.output = directory
        admitted_assemble = local._assemble  # Real subclass, including its closure/code gate.
        calls = []

        def project(view, verified_state, package, historical, *, target_quantities, execution_only):
            require(execution_only is True and target_quantities == base['payload']['target_quantities'],
                    'DAILY_BASE_QUANTITIES_CHANGED')
            require(verified_state == before, 'DAILY_ASSEMBLY_ACCOUNT_CHANGED')
            require({sid for sid, q in projected.items() if q} <= set(historical['metadata']),
                    'DAILY_EFFECTIVE_DOMAIN')
            quantities = {sid:q for sid,q in projected.items() if q}
            frozen_quantities = deepcopy(quantities)
            calls.append(True)
            result = admitted_assemble(verified_state, package, historical,
                target_quantities=quantities, execution_only=True)
            require(quantities == frozen_quantities, 'DAILY_PROVIDER_MUTATED_EFFECTIVE')
            return result

        local._assemble = MethodType(project, local)
        try:
            # The original execution verifies target hashes, account replay,
            # native split bindings and history before dispatching to project.
            result = local.execution(state, base, now)
            require(len(calls) == 1, 'DAILY_ADMITTED_ASSEMBLY_REQUIRED')
            require(state == before and base == self.base and effective == expected and projection == projected,
                    'DAILY_PROVIDER_MUTATED_INPUT')
            self.validate_sources()
            completed = sorted(directory.glob('*/complete.json'))
            require(len(completed) == 1, 'DAILY_CAPTURE_COMPLETION_REQUIRED')
            receipt = dict(schema='NATIVE_DAILY_EXECUTION_LINEAGE_COMPLETE_V1',
                binding_sha256=sha256(raw).hexdigest(),
                capture_completions={str(p.relative_to(directory)):sha256(p.read_bytes()).hexdigest()
                                     for p in completed},
                result_sha256=sha256(canonical(result)).hexdigest(),
                account_mutated=False, source_authenticated=False, production_activated=False)
            (directory/'complete.json').write_bytes(canonical(receipt))
            self.last_binding = dict(base_target_id=base['target_id'],
                base_decision_id=base['payload']['decision']['decision_id'],
                evidence_id=self.signal['evidence_id'], path=str(binding_path),
                sha256=sha256(raw).hexdigest(), completion_path=str(directory/'complete.json'))
            return result
        except BaseException:
            (directory/'failed.json').write_bytes(canonical(dict(status='FAILED_NOT_EXECUTABLE')))
            raise


class DailyMixedExecutionBridge(DailyExecutionBridge):
    zero_cash_only = True
    lineage_schema = 'DAILY_MIXED_SELL_ONLY_EXECUTION_V1'

    def __call__(self, state, effective, now, *, execution_quantities):
        require(type(effective) is dict and all(type(q) is int and q >= 0 for q in effective.values()),
                'DAILY_EFFECTIVE_QUANTITIES_INVALID')
        require(type(execution_quantities) is dict and set(execution_quantities) == set(effective),
                'DAILY_EXECUTION_DOMAIN')
        require(all(type(q) is int and q >= 0 for q in execution_quantities.values()),
                'DAILY_EXECUTION_QUANTITIES_INVALID')
        held = state['shares']
        require(execution_quantities == {sid:min(held.get(sid,0),q) for sid,q in effective.items()},
                'DAILY_SELL_ONLY_PROJECTION_REQUIRED')
        if self.zero_cash_only:
            require(number(state['available_cash']) == 0, 'DAILY_ZERO_CASH_ONLY')
        else:
            require(state['cash_confirmation_valid'], 'CASH_RECONFIRMATION_REQUIRED')
        return self._execute(state, effective, now, projection=execution_quantities,
            extra=dict(schema=self.lineage_schema, execution_quantities=deepcopy(execution_quantities),
                waiting_buys={sid:q-held.get(sid,0) for sid,q in effective.items() if q>held.get(sid,0)},
                projection_semantics='EXECUTION_SUBSET_NOT_STRATEGY_TARGET'))


class DailyBuyDataWaitExecutionBridge(DailyMixedExecutionBridge):
    zero_cash_only = False
    lineage_schema = 'DAILY_BUY_DATA_WAIT_SELL_EXECUTION_V1'
