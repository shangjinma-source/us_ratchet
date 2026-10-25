"""Explicit deployment of risk-history continuation after actual liquidation."""
from copy import copy
from pathlib import Path
from fastapi import APIRouter
from fastapi.routing import APIRoute
from core.strategy_account_ledger import require
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v23 import build_unified_server_preparation_v23
from data.strategy_unified_server_preparation_v22 import CapExitDailyService
from data.strategy_observed_daily_admission_v1 import ObservedDailyAdmission
from data.strategy_daily_first_window_v5 import SOURCES as REVIEW_SOURCES
from data.strategy_monthly_risk_history_v1 import MonthlyRiskHistory
from data.monthly_cap_exit_reader_v3 import MonthlyCapExitReaderV3
from api.strategy_daily_preview_v4 import create_router

SOURCES = REVIEW_SOURCES | {
    'data/strategy_monthly_risk_capture_v1.py', 'data/strategy_monthly_supplement_capture.py',
    'data/strategy_monthly_risk_history_v1.py', 'data/monthly_cap_exit_reader_v3.py',
    'data/strategy_unified_server_preparation_v24.py'}


def build_unified_server_preparation_v24(*, root, configuration_path, configuration_sha256, clock=None):
    root = Path(root).resolve()
    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, config = _read(root, reference)
    require(set(config) == {'schema','base_v23','source_pins','risk_history_capture'} and
            config['schema']=='RISK_HISTORY_CONTINUATION_PREPARATION_V24', 'V24_CONFIGURATION')
    authority = config['risk_history_capture']
    require(set(authority)=={'authorized','capture_root','archive_root'} and
            authority['authorized'] is True, 'V24_RISK_COLLECTION_AUTHORITY')
    require(set(config['source_pins'])==SOURCES, 'V24_SOURCE_SCOPE')
    executing = Path(__file__).resolve().parents[1]
    def validate():
        require(_read(root, reference)[0] == raw, 'V24_CONFIG_CHANGED')
        for name, digest in config['source_pins'].items():
            require(_read_digest(root/name,32*1024*1024)==digest and
                    _read_digest(executing/name,32*1024*1024)==digest, 'V24_SOURCE_CHANGED')
    def local(name):
        path = Path(authority[name])
        require(not path.is_absolute() and '..' not in path.parts and bool(path.parts), 'V24_LOCAL_PATH')
        resolved = root/path
        require(resolved.resolve().is_relative_to(root) and resolved.resolve()!=root, 'V24_LOCAL_PATH')
        return resolved
    validate()
    prepared = build_unified_server_preparation_v23(root=root,
        configuration_path=config['base_v23']['path'], configuration_sha256=config['base_v23']['sha256'], clock=clock)
    def gate():
        prepared['validate_code'](); validate()
    old = prepared['observed_daily']; daily = copy(old.service.service)
    previous = daily.reader
    packet = previous.source_reader.packet_reader
    _, source = _read(root, packet.reference)
    monthly = prepared['monthly']
    history = MonthlyRiskHistory(root=root, source=source, directory=local('capture_root'),
        source_pins=[dict(path=name,sha256=config['source_pins'][name]) for name in sorted(REVIEW_SOURCES)],
        account_reader=monthly.accounts.read, target_reader=monthly.current,
        risk_store=previous.risk_store, clock=packet.clock, validate=gate,
        fetch_daily=packet.fetch_daily, fetch_official=packet.fetch_official)
    reader = MonthlyCapExitReaderV3(source_reader=previous.source_reader, risk_store=previous.risk_store,
        source_archive_root=previous.source_archive_root, output_archive_root=local('archive_root'),
        release_bytes=previous.release_bytes, validate_release=gate, risk_history=history)
    daily.reader=reader; daily.validate_code=gate
    observed=ObservedDailyAdmission(service=CapExitDailyService(daily,reader,gate), monthly=monthly,
        journal=old.journal, clock=old.clock, validate_sources=gate,
        policy_references=dict(base=old.policy_references,risk_history=reference))
    matches=[route for route in prepared['router'].routes if isinstance(route,APIRoute)
        and route.path=='/api/strategy-daily-v3/preview' and route.methods=={'POST'}]
    require(len(matches)==1,'V24_DAILY_ROUTE_REQUIRED')
    router=APIRouter()
    router.routes.extend(route for route in prepared['router'].routes if route is not matches[0])
    router.include_router(create_router(service=observed)); gate()
    return dict(prepared,router=router,observed_daily=observed,validate_code=gate)
