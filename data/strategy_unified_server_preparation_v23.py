"""Opt-in monthly supplementation for the deployed cap/exit policy."""
from copy import copy, deepcopy
from pathlib import Path
from fastapi import APIRouter
from fastapi.routing import APIRoute

from core.strategy_account_ledger import require
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v22 import (
    build_unified_server_preparation_v22, CapExitDailyService)
from data.strategy_monthly_supplement_reader import MonthlySupplementReader, EXTRA_SOURCES
from data.monthly_cap_exit_reader_v2 import MonthlyCapExitReaderV2
from data.strategy_observed_daily_admission_v1 import ObservedDailyAdmission
from api.strategy_daily_preview_v4 import create_router

SOURCES = EXTRA_SOURCES | {'data/strategy_unified_server_preparation_v23.py',
    'data/monthly_cap_exit_reader_v2.py'}


def build_unified_server_preparation_v23(*, root, configuration_path, configuration_sha256, clock=None):
    root = Path(root).resolve()
    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, config = _read(root, reference)
    require(set(config) == {'schema', 'base_v22', 'supplement_authorization', 'source_pins'} and
        config['schema'] == 'MONTHLY_SUPPLEMENT_UNIFIED_PREPARATION_V23', 'V23_CONFIGURATION')
    require(set(config['source_pins']) == SOURCES, 'V23_SOURCE_SCOPE')
    authorization_raw, authorization = _read(root, config['supplement_authorization'])
    executing = Path(__file__).resolve().parents[1]
    def validate():
        require(_read(root, reference)[0] == raw and
            _read(root, config['supplement_authorization'])[0] == authorization_raw, 'V23_CONFIG_CHANGED')
        for name, digest in config['source_pins'].items():
            require(_read_digest(root/name, 32*1024*1024) == digest and
                _read_digest(executing/name, 32*1024*1024) == digest, 'V23_SOURCE_CHANGED')
    validate()
    prepared = build_unified_server_preparation_v22(root=root,
        configuration_path=config['base_v22']['path'],
        configuration_sha256=config['base_v22']['sha256'], clock=clock)
    old = prepared['observed_daily']; daily = copy(old.service.service)
    previous = daily.reader
    source_reader = copy(previous.source_reader)
    packet = source_reader.packet_reader
    _, old_authorization = _read(root, packet.review_reference)
    before = deepcopy(old_authorization); after = deepcopy(authorization)
    before.pop('code_pins'); after.pop('code_pins')
    supplement = after.pop('monthly_supplement', None)
    require(before == after and supplement and supplement.get('authorized') is True,
        'V23_EXISTING_AUTHORITY_CHANGED')
    old_pins = {row['path']: row['sha256'] for row in old_authorization['code_pins']}
    new_pins = {row['path']: row['sha256'] for row in authorization['code_pins']}
    require(len(new_pins) == len(authorization['code_pins']) and
        all(new_pins.get(name) == digest for name, digest in old_pins.items()) and
        all(new_pins.get(name) == digest for name, digest in config['source_pins'].items()),
        'V23_AUTHORITY_CODE_CHANGED')
    def gate():
        prepared['validate_code']()
        validate()
    monthly = prepared['monthly']
    source_reader.packet_reader = MonthlySupplementReader(root=root,
        configuration_path=packet.reference['path'], configuration_sha256=packet.reference['sha256'],
        archive_root=packet.archive_root, release_path=packet.release_path,
        trusted_release_sha256=packet.release_sha,
        review_configuration_path=config['supplement_authorization']['path'],
        review_configuration_sha256=config['supplement_authorization']['sha256'],
        clock=packet.clock, account_reader=monthly.accounts.read, target_reader=monthly.current,
        risk_store=previous.risk_store)
    reader = MonthlyCapExitReaderV2(source_reader=source_reader, risk_store=previous.risk_store,
        source_archive_root=previous.source_archive_root, output_archive_root=previous.output_archive_root,
        release_bytes=previous.release_bytes, validate_release=gate)
    daily.reader = reader; daily.validate_code = gate
    service = CapExitDailyService(daily, reader, gate)
    observed = ObservedDailyAdmission(service=service, monthly=monthly, journal=old.journal,
        clock=old.clock, validate_sources=gate,
        policy_references=dict(base=old.policy_references, supplement=config['supplement_authorization']))
    matches = [route for route in prepared['router'].routes if isinstance(route, APIRoute)
        and route.path == '/api/strategy-daily-v3/preview' and route.methods == {'POST'}]
    require(len(matches) == 1, 'V23_DAILY_ROUTE_REQUIRED')
    router = APIRouter()
    router.routes.extend(route for route in prepared['router'].routes if route is not matches[0])
    router.include_router(create_router(service=observed))
    gate()
    return dict(prepared, router=router, observed_daily=observed, validate_code=gate)
