"""Explicit cap50/exit20 deployment builder; no activation on import."""
from copy import copy
from hashlib import sha256
import json
from pathlib import Path
from fastapi import APIRouter
from fastapi.routing import APIRoute

from core.strategy_account_ledger import require
from data.monthly_cap_exit_reader import MonthlyCapExitReader
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.monthly_cap_target_view import capped_target_view
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v21 import build_unified_server_preparation_v21
from data.strategy_observed_daily_admission_v1 import ObservedDailyAdmission
from api.strategy_daily_preview_v4 import create_router

SOURCES = {'data/strategy_unified_server_preparation_v22.py', 'data/monthly_cap_exit_reader.py',
    'data/monthly_cap_exit_packet.py', 'data/monthly_cap_target_view.py',
    'data/monthly_peak_exit_history.py', 'data/monthly_peak_exit_store.py',
    'core/monthly_peak_exit.py', 'core/monthly_risk_sizing.py'}


class CapExitDailyService:
    def __init__(self, service, reader, validate):
        self.service, self.reader, self.validate = service, reader, validate
        self.monthly = service.monthly

    def preview(self, *, expected_revision, target_id):
        with self.monthly.snapshot_operation():
            self.validate()
            result = self.service.preview(expected_revision=expected_revision, target_id=target_id)
            projection = self.reader.last_projection
            result['policy_id'] = 'MONTHLY_CAP50_EXIT20'
            result['risk_monthly_targets'] = capped_target_view(self.monthly.current())['target_quantities']
            if projection is not None:
                result['signal_explanations'] = projection['signal_explanations']
                result['risk_signal_date'] = projection['signal_date']
            self.validate()
            return result


def build_unified_server_preparation_v22(*, root, configuration_path, configuration_sha256, clock=None):
    root = Path(root).resolve()
    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, config = _read(root, reference)
    require(config['schema'] == 'CAP50_EXIT20_UNIFIED_PREPARATION_V22', 'V22_CONFIGURATION_SCHEMA')
    require(set(config['source_pins']) == SOURCES, 'V22_SOURCE_SCOPE')
    release_raw, release = _read(root, config['release'])
    require(release['policy_id'] == 'MONTHLY_CAP50_EXIT20' and release['authorized'] is True
        and release['monthly_cap'] == '1/2' and release['exit_ratio'] == '4/5'
        and release['sma20_overlay'] is False, 'V22_POLICY_RELEASE_REQUIRED')
    executing = Path(__file__).resolve().parents[1]
    def validate():
        require(_read(root, reference)[0] == raw and _read(root, config['release'])[0] == release_raw,
                'V22_CONFIGURATION_CHANGED')
        for name, digest in config['source_pins'].items():
            require(_read_digest(root/name, 32*1024*1024) == digest and
                    _read_digest(executing/name, 32*1024*1024) == digest, 'V22_SOURCE_CHANGED')
    validate()
    prepared = build_unified_server_preparation_v21(root=root,
        configuration_path=config['base_v21']['path'],
        configuration_sha256=config['base_v21']['sha256'], clock=clock)
    def gate():
        prepared['validate_code']()
        validate()
    def local(name):
        path = Path(config[name])
        require(not path.is_absolute() and '..' not in path.parts, 'V22_LOCAL_PATH')
        candidate = root/path
        require(candidate.resolve().is_relative_to(root) and candidate.resolve() != root, 'V22_LOCAL_PATH')
        return candidate
    old = prepared['observed_daily']
    previous = old.service.service  # V21 display wrapper -> V20 daily service
    reader = MonthlyCapExitReader(source_reader=previous.reader,
        risk_store=MonthlyPeakExitStore(local('risk_database')),
        source_archive_root=old.service.archive_root,
        output_archive_root=local('archive_root'), release_bytes=release_raw, validate_release=gate)
    daily = copy(previous)
    daily.reader, daily.policy_id, daily.validate_code = reader, 'MONTHLY_CAP50_EXIT20', gate
    service = CapExitDailyService(daily, reader, gate)
    observed = ObservedDailyAdmission(service=service, monthly=prepared['monthly'],
        journal=old.journal, clock=old.clock, validate_sources=gate,
        policy_references=dict(base=old.policy_references, cap_exit_release=config['release']))
    matches = [route for route in prepared['router'].routes if isinstance(route, APIRoute)
               and route.path == '/api/strategy-daily-v3/preview' and route.methods == {'POST'}]
    require(len(matches) == 1, 'V22_DAILY_ROUTE_REQUIRED')
    router = APIRouter()
    router.routes.extend(route for route in prepared['router'].routes if route is not matches[0])
    router.include_router(create_router(service=observed))
    gate()
    return dict(prepared, router=router, observed_daily=observed, validate_code=gate)
