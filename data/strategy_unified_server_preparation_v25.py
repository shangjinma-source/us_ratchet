"""Explicit candidate deployment for completed-close initial monthly risk epochs."""
from copy import copy, deepcopy
from pathlib import Path
from fastapi import APIRouter
from fastapi.routing import APIRoute
from core.strategy_account_ledger import require
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v24 import build_unified_server_preparation_v24
from data.strategy_unified_server_preparation_v22 import CapExitDailyService
from data.strategy_observed_daily_admission_v1 import ObservedDailyAdmission
from data.monthly_cap_exit_reader_v4 import MonthlyCapExitReaderV4
from data.strategy_monthly_supplement_reader_v2 import MonthlySupplementReaderV2, EXTRA_SOURCES
from data.strategy_monthly_risk_history_v2 import MonthlyRiskHistoryV2
from data.strategy_daily_first_window_v7 import SOURCES as RISK_SOURCES
from api.strategy_daily_preview_v4 import create_router

SOURCES = EXTRA_SOURCES | RISK_SOURCES | {
    'data/monthly_risk_epoch.py', 'data/monthly_cap_exit_reader_v4.py',
    'data/strategy_monthly_risk_capture_v2.py', 'data/strategy_monthly_risk_history_v2.py',
    'data/strategy_unified_server_preparation_v25.py'}


def build_unified_server_preparation_v25(*, root, configuration_path, configuration_sha256, clock=None):
    root = Path(root).resolve()
    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, config = _read(root, reference)
    require(set(config) == {'schema','base_v24','source_pins','initial_risk_epoch','supplement_authorization'} and
            config['schema']=='COMPLETED_SELECTION_CLOSE_PREPARATION_V25', 'V25_CONFIGURATION')
    authority = config['initial_risk_epoch']
    require(set(authority)=={'authorized','archive_root'} and
            authority['authorized'] is True, 'V25_RISK_COLLECTION_AUTHORITY')
    require(set(config['source_pins'])==SOURCES, 'V25_SOURCE_SCOPE')
    new_raw, authorization = _read(root, config['supplement_authorization'])
    executing = Path(__file__).resolve().parents[1]
    def validate():
        require(_read(root, reference)[0] == raw, 'V25_CONFIG_CHANGED')
        require(_read(root, config['supplement_authorization'])[0] == new_raw,
                'V25_AUTHORIZATION_CHANGED')
        for name, digest in config['source_pins'].items():
            require(_read_digest(root/name,32*1024*1024)==digest and
                    _read_digest(executing/name,32*1024*1024)==digest, 'V25_SOURCE_CHANGED')
    def local(name):
        path = Path(authority[name])
        require(not path.is_absolute() and '..' not in path.parts and bool(path.parts), 'V25_LOCAL_PATH')
        resolved = root/path
        require(resolved.resolve().is_relative_to(root) and resolved.resolve()!=root, 'V25_LOCAL_PATH')
        return resolved
    validate()
    prepared = build_unified_server_preparation_v24(root=root,
        configuration_path=config['base_v24']['path'], configuration_sha256=config['base_v24']['sha256'], clock=clock)
    def gate():
        prepared['validate_code'](); validate()
    old = prepared['observed_daily']; daily = copy(old.service.service)
    previous = daily.reader
    monthly = prepared['monthly']
    source_reader = copy(previous.source_reader)
    packet = source_reader.packet_reader
    _, old_authorization = _read(root, packet.review_reference)
    before, after = deepcopy(old_authorization), deepcopy(authorization)
    old_pins, new_pins = before.pop('code_pins'), after.pop('code_pins')
    require(before == after, 'V25_EXISTING_AUTHORITY_CHANGED')
    pins = {row['path']:row['sha256'] for row in new_pins}
    require(len(pins) == len(new_pins) and
        all(pins.get(row['path']) == row['sha256'] for row in old_pins) and
        all(pins.get(name) == digest for name,digest in config['source_pins'].items()),
        'V25_AUTHORITY_CODE_CHANGED')
    source_reader.packet_reader = MonthlySupplementReaderV2(root=root,
        configuration_path=packet.reference['path'], configuration_sha256=packet.reference['sha256'],
        archive_root=packet.archive_root, release_path=packet.release_path,
        trusted_release_sha256=packet.release_sha,
        review_configuration_path=config['supplement_authorization']['path'],
        review_configuration_sha256=config['supplement_authorization']['sha256'], clock=packet.clock,
        account_reader=monthly.accounts.read, target_reader=monthly.current,
        risk_store=previous.risk_store, fetch_daily=packet.fetch_daily, fetch_official=packet.fetch_official)
    old_history = previous.risk_history
    history = MonthlyRiskHistoryV2(root=root, source=old_history.source,
        directory=old_history.directory/'completed-close-v2',
        source_pins=[dict(path=name,sha256=config['source_pins'][name]) for name in sorted(RISK_SOURCES)],
        account_reader=monthly.accounts.read, target_reader=monthly.current,
        risk_store=previous.risk_store, clock=packet.clock, validate=gate,
        fetch_daily=packet.fetch_daily, fetch_official=packet.fetch_official)
    reader = MonthlyCapExitReaderV4(source_reader=source_reader, risk_store=previous.risk_store,
        source_archive_root=previous.source_archive_root, output_archive_root=local('archive_root'),
        release_bytes=previous.release_bytes, validate_release=gate, risk_history=history)
    daily.reader=reader; daily.validate_code=gate
    observed=ObservedDailyAdmission(service=CapExitDailyService(daily,reader,gate), monthly=monthly,
        journal=old.journal, clock=old.clock, validate_sources=gate,
        policy_references=dict(base=old.policy_references,initial_risk_epoch=reference))
    matches=[route for route in prepared['router'].routes if isinstance(route,APIRoute)
        and route.path=='/api/strategy-daily-v3/preview' and route.methods=={'POST'}]
    require(len(matches)==1,'V25_DAILY_ROUTE_REQUIRED')
    router=APIRouter()
    router.routes.extend(route for route in prepared['router'].routes if route is not matches[0])
    router.include_router(create_router(service=observed)); gate()
    return dict(prepared,router=router,observed_daily=observed,validate_code=gate)
