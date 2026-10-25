"""Preserve capital intents during the explicit original-to-continuous32 upgrade."""
from hashlib import sha256
from pathlib import Path

from core.strategy_account_ledger import require
from core.strategy_capital_intent_journal import CapitalIntentJournal
from core.strategy_profiled_capital_intent_journal import ProfiledCapitalIntentJournal
from data.strategy_capital_service_v1 import CapitalContributionServiceV1
from data.strategy_account_target_service import StrategyAccountTargetService
from data.strategy_continuous32_target_service import StrategyContinuous32TargetService
from api.strategy_profiled_capital_composition import (
    SOURCES as PROFILED_SOURCES, build_capital_service,
)
from api.strategy_capital_v1 import create_router
from scripts.register_quantity_v2_paper_protocol import safe_path

SOURCES = PROFILED_SOURCES | {
    "api/strategy_capital_transition_composition.py",
    "data/strategy_capital_service_v1.py",
    "data/strategy_account_target_service.py",
}


class TransitionCapitalService:
    def __init__(self, *, monthly, validate_code, source_pins):
        require(SOURCES <= set(source_pins), "CAPITAL_TRANSITION_SOURCE_SCOPE_REQUIRED")
        self.monthly, self.validate_code = monthly, validate_code
        self.pins = dict(source_pins)
        self.original_journal = CapitalIntentJournal(
            Path(monthly.root) / "data/strategy_account/capital_intents_v1.sqlite3")
        self.profiled_journal = ProfiledCapitalIntentJournal(
            Path(monthly.root) / "data/strategy_account/profiled_capital_intents_v1.sqlite3")
        self.original = CapitalContributionServiceV1(
            monthly=monthly, journal=self.original_journal, validate_code=self._gate)
        self._gate()

    def _gate(self):
        self.validate_code()
        for name in SOURCES:
            expected = self.pins[name]
            require(sha256(safe_path(self.monthly.root, name).read_bytes()).hexdigest() == expected
                    and sha256((Path(__file__).resolve().parents[1] / name).read_bytes()).hexdigest()
                    == expected, "CAPITAL_TRANSITION_SOURCE_CHANGED")

    def _owner(self, event_id):
        original = self.original_journal.intent(event_id)
        profiled = self.profiled_journal.intent(event_id)
        require(not (original is not None and profiled is not None),
                "CAPITAL_EVENT_EXISTS_IN_BOTH_JOURNALS")
        if original is not None:
            return "original"
        if profiled is not None:
            return "profiled"
        return None

    def _current_profile(self):
        target = self.monthly.current()
        require(target is not None, "CAPITAL_ACCOUNT_AND_TARGET_REQUIRED")
        runtime, _ = self.monthly._for_target(target)
        if type(runtime.selection) is StrategyAccountTargetService:
            return "original"
        require(type(runtime.selection) is StrategyContinuous32TargetService,
                "CAPITAL_TRANSITION_UNKNOWN_SELECTOR")
        return "profiled"

    def _invoke(self, method, fields):
        with self.monthly.snapshot_operation():
            self._gate()
            # A recorded event always retains its original journal and semantics,
            # including after a newer target is published.
            owner = self._owner(fields["event_id"])
            selected = owner or self._current_profile()
            service = self.original if selected == "original" else build_capital_service(
                monthly=self.monthly, validate_code=self._gate, source_pins=self.pins)
            if method != "status":
                status = service.status(event_id=fields["event_id"])
                if status["status"] != "CONSUMED_BY_PUBLISHED_TARGET":
                    require(selected == self._current_profile(),
                            "CAPITAL_PENDING_EVENT_REQUIRES_ORIGINAL_TARGET")
            result = getattr(service, method)(**fields)
            self._gate()
            return result

    def record(self, **fields):
        return self._invoke("record", fields)

    def configure(self, **fields):
        return self._invoke("configure", fields)

    def recover_publication(self, **fields):
        return self._invoke("recover_publication", fields)

    def status(self, **fields):
        return self._invoke("status", fields)


def create_transition_capital_router(**options):
    return create_router(service=TransitionCapitalService(**options))
