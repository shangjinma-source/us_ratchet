"""Server-owned explicit capital admission. Importing this module mounts nothing."""
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from core.strategy_account_ledger import require
from core.strategy_capital_intent_journal import CapitalIntentJournal
from data.strategy_capital_service_v1 import CapitalContributionServiceV1
from data.strategy_account_rolling_router import RollingMonthlyRuntimeRouter
from data.strategy_account_release_activation import MonthlyReleaseActivation
from data.strategy_dynamic_source_gate import bind_dynamic_source_gate,DYNAMIC_SOURCE_PATHS
from scripts.register_quantity_v2_paper_protocol import safe_path
from api.strategy_capital_v1 import create_router

CAPITAL_SOURCES=DYNAMIC_SOURCE_PATHS|{
 'api/strategy_capital_server_v1.py','api/strategy_capital_v1.py',
 'core/strategy_capital_intent_journal.py','data/strategy_capital_service_v1.py',
 'data/strategy_account_rolling_router.py','data/strategy_account_release_activation.py',
 'data/strategy_account_active_release_store.py','data/strategy_account_ready_release.py',
 'scripts/prepare_real_monthly_release.py','scripts/register_quantity_v2_paper_protocol.py'}

def build_capital_service(*,root,configuration_path,configuration_sha256,clock=None,runtime_builder=None):
    # Clock and builder are server construction dependencies, never HTTP fields.
    root=Path(root).resolve();path=safe_path(root,configuration_path);raw=path.read_bytes()
    require(len(raw)<=1024*1024 and sha256(raw).hexdigest()==configuration_sha256,'CAPITAL_CONFIGURATION_CHANGED')
    config=json.loads(raw)
    require(set(config)=={'schema','source_pins','initial_snapshot','journal_path'}
            and config['schema']=='CAPITAL_SERVER_ADMISSION_V1','CAPITAL_CONFIGURATION_FIELDS')
    require(CAPITAL_SOURCES<=set(config['source_pins']),'CAPITAL_SOURCE_DOMAIN_REQUIRED')
    source_gate=bind_dynamic_source_gate(root=root,source_pins=config['source_pins'])
    def gate():
        require(path.read_bytes()==raw,'CAPITAL_CONFIGURATION_CHANGED');source_gate()
    initial=config['initial_snapshot']
    require(set(initial)=={'registry_path','registry_sha256','archive_path','archive_sha256'},'CAPITAL_SNAPSHOT_FIELDS')
    clock=clock or (lambda:datetime.now(timezone.utc))
    activation=MonthlyReleaseActivation(root=root,initial_snapshot=initial,validate_code=gate,clock=clock)
    options=dict(root=root,initial_snapshot=dict(initial,revision=0),snapshot_provider=activation.snapshot,clock=clock)
    if runtime_builder is not None:options['runtime_builder']=runtime_builder
    monthly=RollingMonthlyRuntimeRouter(**options)
    require(config['journal_path']=='data/strategy_account/capital_intents_v1.sqlite3','CAPITAL_DEDICATED_JOURNAL_REQUIRED')
    journal_path=safe_path(root,config['journal_path'])
    require(journal_path!=monthly.accounts.path and journal_path!=monthly.targets.path,'CAPITAL_STORAGE_COLLISION')
    gate()
    return CapitalContributionServiceV1(monthly=monthly,journal=CapitalIntentJournal(journal_path),validate_code=gate)

def create_capital_router(**options):
    return create_router(service=build_capital_service(**options))
