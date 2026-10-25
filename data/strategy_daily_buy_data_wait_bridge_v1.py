"""Sell-only subset after missing buy data; signal and monthly target stay intact."""
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4
from core.strategy_account_ledger import canonical, require
from core.strategy_account_difference import number
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider


class DailyBuyDataWaitExecutionBridge:
    def __init__(self, *, base_target, execution_provider, validate_sources, signal):
        self.base = deepcopy(base_target)
        require(getattr(execution_provider, "__func__", None) is StrategyAccountEvidenceProvider.execution,
                "DAILY_PROVIDER_INTERFACE_REQUIRED")
        self.provider = execution_provider.__self__
        self.validate_sources = validate_sources
        self.signal = deepcopy(signal)

    def __call__(self, state, effective, now, *, execution_quantities):
        self.validate_sources()
        require(type(effective) is dict and all(type(q) is int and q >= 0 for q in effective.values()),
                "DAILY_EFFECTIVE_QUANTITIES_INVALID")
        base, before, expected = deepcopy(self.base), deepcopy(state), deepcopy(effective)
        provider, signal = self.provider, self.signal
        projection = deepcopy(execution_quantities)
        require(type(projection) is dict and set(projection) == set(effective), "DAILY_EXECUTION_DOMAIN")
        require(all(type(q) is int and q >= 0 for q in projection.values()), "DAILY_EXECUTION_QUANTITIES_INVALID")
        held = state["shares"]
        require(projection == {sid: min(held.get(sid, 0), q) for sid, q in effective.items()}, "DAILY_SELL_ONLY_PROJECTION_REQUIRED")
        require(state["cash_confirmation_valid"], "CASH_RECONFIRMATION_REQUIRED")
        require(signal["effective_target_quantities"] == effective, "DAILY_SIGNAL_TARGET_MISMATCH")
        lineage = dict(schema="DAILY_BUY_DATA_WAIT_SELL_EXECUTION_V1", base_target_id=base["target_id"],
                       base_decision_id=base["payload"]["decision"]["decision_id"],
                       account_revision=state["revision"], policy_id=signal["policy_id"],
                       evidence_id=signal["evidence_id"], signal=signal,
                       effective_target_quantities=expected, execution_quantities=projection,
                       waiting_buys={sid: q-held.get(sid, 0) for sid, q in effective.items() if q>held.get(sid, 0)},
                       projection_semantics="EXECUTION_SUBSET_NOT_STRATEGY_TARGET")
        raw = canonical(lineage)
        evidence_directory = provider.output / ("daily-" + uuid4().hex)
        evidence_directory.mkdir(parents=True, exist_ok=False)
        binding_path = evidence_directory / "daily-binding.json"
        with binding_path.open("xb") as stream:
            stream.write(raw)

        class ExecutionView:
            output = evidence_directory
            def __getattr__(self, name):
                return getattr(provider, name)

            def _assemble(self, verified_state, package, historical, *, target_quantities, execution_only):
                require(target_quantities == base["payload"]["target_quantities"], "DAILY_BASE_QUANTITIES_CHANGED")
                require({sid for sid, q in projection.items() if q} <= set(historical["metadata"]), "DAILY_EFFECTIVE_DOMAIN")
                package = deepcopy(package)
                name = str(binding_path)
                require(name not in package["files"], "DAILY_BINDING_PATH_COLLISION")
                package["files"][name] = raw
                package["source_hashes"][name] = sha256(raw).hexdigest()
                package["documents"]["daily_execution_binding"] = name
                quantities = {sid: q for sid, q in projection.items() if q}
                before_quantities = deepcopy(quantities)
                result = StrategyAccountEvidenceProvider._assemble(self, verified_state, package, historical,
                    target_quantities=quantities,
                    execution_only=execution_only)
                require(quantities == before_quantities, "DAILY_PROVIDER_MUTATED_EFFECTIVE")
                return result

        evidence = StrategyAccountEvidenceProvider.execution(ExecutionView(), state, base, now)
        require(state == before and base == self.base and effective == expected and execution_quantities == projection, "DAILY_PROVIDER_MUTATED_INPUT")
        self.validate_sources()
        self.last_binding = dict(base_target_id=base["target_id"],
                                 base_decision_id=base["payload"]["decision"]["decision_id"],
                                 evidence_id=signal["evidence_id"], path=str(binding_path),
                                 sha256=sha256(raw).hexdigest())
        return evidence
