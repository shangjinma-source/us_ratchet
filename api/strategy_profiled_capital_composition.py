"""Attach explicit continuous32 capital service to an already admitted shared router."""
from pathlib import Path
from hashlib import sha256
from scripts.register_quantity_v2_paper_protocol import safe_path
from contextlib import closing
from core.strategy_account_ledger import require
from core.strategy_capital_intent_journal import CapitalIntentJournal
from core.strategy_profiled_capital_intent_journal import ProfiledCapitalIntentJournal
from data.strategy_profiled_capital_service import ProfiledCapitalContributionService
from data.strategy_profiled_rolling_router import ProfiledRollingMonthlyRuntimeRouter
from api.strategy_capital_v1 import create_router

SOURCES={'core/strategy_profiled_capital_intent_journal.py','data/strategy_profiled_capital_service.py',
 'api/strategy_profiled_capital_composition.py','core/strategy_capital_intent_journal.py',
 'api/strategy_capital_v1.py'}

def build_capital_service(*,monthly,validate_code,source_pins):
    require(isinstance(monthly,ProfiledRollingMonthlyRuntimeRouter),'PROFILED_SHARED_RUNTIME_REQUIRED')
    require(callable(validate_code),'PROFILED_CAPITAL_GATE_REQUIRED')
    require(type(source_pins)is dict and SOURCES<=set(source_pins),'PROFILED_CAPITAL_PINS_REQUIRED')
    pins=dict(source_pins)
    root=Path(monthly.root);legacy=CapitalIntentJournal(root/'data/strategy_account/capital_intents_v1.sqlite3')
    def gate():
        validate_code()
        for name in SOURCES:
            require(sha256(safe_path(root,name).read_bytes()).hexdigest()==pins[name] and sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest()==pins[name],'PROFILED_CAPITAL_SOURCE_CHANGED')
        # Never abandon unresolved legacy intents. No mutation/migration is done.
        if legacy.path.exists():
            with closing(legacy._connect()) as con:
                events=[r[0] for r in con.execute('SELECT event_id FROM intents LIMIT 1001')]
            require(len(events)<=1000,'CAPITAL_LEGACY_EVENT_BUDGET')
            require(all(legacy.reconcile(event,target_store=monthly.targets)['status']=='CONSUMED_BY_PUBLISHED_TARGET'
                        for event in events),'CAPITAL_LEGACY_PENDING_REVIEW_REQUIRED')
        validate_code()
    gate()
    journal=ProfiledCapitalIntentJournal(root/'data/strategy_account/profiled_capital_intents_v1.sqlite3')
    return ProfiledCapitalContributionService(monthly=monthly,journal=journal,validate_code=gate)

def create_profiled_capital_router(*,monthly,validate_code,source_pins):
    return create_router(service=build_capital_service(monthly=monthly,validate_code=validate_code,source_pins=source_pins))
