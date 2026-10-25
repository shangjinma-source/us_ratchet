"""Keep current advice archives and policy references readable by follow-up jobs."""
from copy import copy, deepcopy
from pathlib import Path
from fastapi import APIRouter
from fastapi.routing import APIRoute
from core.strategy_account_ledger import require
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v25 import build_unified_server_preparation_v25
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_unified_server_preparation_v22 import CapExitDailyService
from data.strategy_observed_daily_admission_v1 import ObservedDailyAdmission
from api.strategy_daily_preview_v4 import create_router

SOURCES = {'data/strategy_unified_server_preparation_v26.py'}


def build_unified_server_preparation_v26(*, root, configuration_path, configuration_sha256, clock=None):
    root = Path(root).resolve()
    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, config = _read(root, reference)
    require(set(config) == {'schema','base_v25','source_pins','archive_root'} and
        config['schema'] == 'FOLLOWUP_COMPATIBLE_EPOCH_PREPARATION_V26', 'V26_CONFIGURATION')
    require(set(config['source_pins']) == SOURCES, 'V26_SOURCE_SCOPE')
    archive = root/config['archive_root']
    require(not Path(config['archive_root']).is_absolute() and
        '..' not in Path(config['archive_root']).parts and
        archive.resolve().is_relative_to(root/'data/strategy_account') and
        archive.resolve() != root/'data/strategy_account', 'V26_ACCOUNT_ARCHIVE_SCOPE')
    def validate():
        require(_read(root, reference)[0] == raw, 'V26_CONFIGURATION_CHANGED')
        for name, digest in config['source_pins'].items():
            require(_read_digest(root/name, 32*1024*1024) == digest and
                _read_digest(Path(__file__).resolve().parents[1]/name, 32*1024*1024) == digest,
                'V26_SOURCE_CHANGED')
    validate()
    prepared = build_unified_server_preparation_v25(root=root,
        configuration_path=config['base_v25']['path'],configuration_sha256=config['base_v25']['sha256'],clock=clock)
    def gate():
        prepared['validate_code'](); validate()
    old = prepared['observed_daily']
    daily = copy(old.service.service)
    reader = copy(daily.reader)
    reader.output_archive_root = archive
    daily.reader = reader
    daily.validate_code = gate
    packet = reader.source_reader.packet_reader
    _, authorization = _read(root, packet.review_reference)
    references = deepcopy(old.policy_references)
    # Prefer the actual current reader, not an obsolete nested base authorization.
    references['evidence_references'] = dict(
        configuration_path=packet.reference['path'],configuration_sha256=packet.reference['sha256'],
        review_configuration_path=packet.review_reference['path'],
        review_configuration_sha256=packet.review_reference['sha256'],
        trusted_release_sha256=authorization['release']['sha256'])
    references['followup_compatibility'] = reference
    observed = ObservedDailyAdmission(service=CapExitDailyService(daily,reader,gate),
        monthly=prepared['monthly'],journal=old.journal,clock=old.clock,
        validate_sources=gate,policy_references=references)
    matches = [route for route in prepared['router'].routes if isinstance(route,APIRoute)
        and route.path == '/api/strategy-daily-v3/preview' and route.methods == {'POST'}]
    require(len(matches) == 1, 'V26_DAILY_ROUTE_REQUIRED')
    router = APIRouter()
    router.routes.extend(route for route in prepared['router'].routes if route is not matches[0])
    router.include_router(create_router(service=observed));gate()
    return dict(prepared,router=router,observed_daily=observed,validate_code=gate)
