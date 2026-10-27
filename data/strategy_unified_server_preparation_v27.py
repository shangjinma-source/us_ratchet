"""Explicit frontier release composition; construction never activates or migrates targets."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter
from fastapi.routing import APIRoute
from core.strategy_account_ledger import require
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_daily_session_capture import reject_links, stamp
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v26 import build_unified_server_preparation_v26
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView, SavedFrontierProposalStore
from data.saved_frontier_rolling_admission_v1 import SavedFrontierRollingAdmissionV1
from data.strategy_observed_frontier_daily_admission_v1 import ObservedFrontierDailyAdmission
from data.strategy_frontier_target_charts_v1 import StrategyFrontierTargetChartsV1
from data.strategy_frontier_latest_display_charts_v1 import FrontierLatestDisplayChartsV1
from data.saved_frontier_first_window_v1 import SOURCES as FIRST_WINDOW_SOURCES
from api.strategy_frontier_daily_preview_v1 import create_router as daily_router
from api.strategy_frontier_monthly_target_v1 import create_router as monthly_router
from api.strategy_frontier_latest_display_charts_v1 import create_router as display_router

POLICY_ID = 'SAVED_FRONTIER_CAP50_EXIT20_V1'
SOURCES = {'data/saved_frontier_source_review_v1.py', 'data/strategy_unified_server_preparation_v27.py', 'data/saved_frontier_preview_service_v1.py', 'data/saved_frontier_monthly_view_v1.py', 'api/strategy_frontier_daily_preview_v1.py', 'data/strategy_frontier_latest_display_charts_v1.py', 'data/strategy_frontier_target_charts_v1.py', 'data/strategy_observed_frontier_daily_admission_v1.py', 'web/index.html', 'data/saved_frontier_supplement_request_v1.py', 'api/strategy_frontier_monthly_target_v1.py', 'data/saved_frontier_daily_composition_v1.py', 'data/saved_frontier_supplement_prepare_v1.py', 'data/saved_frontier_first_window_v1.py', 'web/strategy_daily_mount.js', 'data/saved_frontier_security_domain_v1.py', 'data/saved_frontier_zero_cash_preview_v1.py', 'core/saved_monthly_frontier_proposal.py', 'data/saved_frontier_capture_review_v1.py', 'data/saved_frontier_buy_data_wait_preview_v1.py', 'web/strategy_monthly_target_charts.js', 'api/strategy_frontier_latest_display_charts_v1.py', 'data/saved_frontier_source_reader_v1.py', 'data/saved_frontier_live_reader_v1.py', 'api/strategy_server_mount_v6.py', 'data/saved_frontier_exit_packet_v1.py', 'web/strategy_daily_controller.js'}

SOURCES |= {'web/strategy_target_recovery_v1.js', 'api/news_desk_v1.py',
            'web/news.html', 'web/news.js', 'data/news_refresh_service.py',
            'data/news_desk.py', 'data/news_issuer_source.py',
            'data/news_evidence_groups.py', 'data/news_observation_history.py',
            'data/news_sandisk_capture.py', 'data/news_sandisk_parser.py'}
SOURCES |= FIRST_WINDOW_SOURCES | {'data/saved_frontier_rolling_admission_v1.py'}
SOURCES |= {
    'data/saved_frontier_current_migration_v1.py',
    'data/strategy_followup_frontier_source_v1.py',
    'data/strategy_advice_followup_plan_v3.py',
    'data/strategy_followup_close_review_v2.py',
    'data/strategy_followup_price_basis_v2.py',
    'data/strategy_followup_cap_source_v2.py',
    'data/strategy_followup_supplement_authorization_v1.py',
    'scripts/queue_current_daily_followups_v3.py',
    'scripts/audit_current_daily_followup_sources_v4.py',
    'scripts/review_saved_daily_followups_v4.py',
    'scripts/archive_saved_daily_followups_v4.py',
    'scripts/run_current_daily_followups_v2.py',
    'scripts/run_local_current_followups_v1.ps1',
    'data/strategy_advice_followup_plan_v1.py',
    'data/strategy_advice_followup_plan_v2.py',
    'data/strategy_followup_queue_v1.py',
    'data/strategy_followup_result_store_v1.py',
    'data/strategy_followup_capture_groups_v1.py',
    'data/strategy_followup_execution_binding_v1.py',
    'data/strategy_followup_authorization_v1.py',
    'data/strategy_followup_cap_source_v1.py',
    'data/strategy_followup_cap_replay_v1.py',
    'data/strategy_followup_close_review_v1.py',
    'data/strategy_followup_price_basis_v1.py',
    'scripts/audit_legacy_daily_followup_sources_v2.py',
    'scripts/capture_daily_followup_groups_v1.py',
}

def build_unified_server_preparation_v27(*, root, configuration_path, configuration_sha256, clock=None):
    root = Path(root).resolve()
    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, config = _read(root, reference)
    require(set(config) == {'schema', 'base_v26', 'release', 'source_pins', 'proposal_database',
                           'capture_root', 'archive_root', 'display_root'}
            and config['schema'] == 'SAVED_FRONTIER_UNIFIED_PREPARATION_V27', 'V27_CONFIGURATION')
    require(set(config['source_pins']) == SOURCES, 'V27_SOURCE_SCOPE')
    release_raw, release = _read(root, config['release'])
    require(release.get('authorized') is True and release.get('policy_id') == POLICY_ID
            and release.get('monthly_cap') == '1/2' and release.get('exit_ratio') == '4/5'
            and release.get('sma20_overlay') is False, 'V27_POLICY_RELEASE_REQUIRED')
    executing = Path(__file__).resolve().parents[1]
    current_time = clock or (lambda: datetime.now(timezone.utc))

    def validate():
        require(stamp(release['authorized_at']) <= stamp(current_time()), 'V27_RELEASE_NOT_YET_AUTHORIZED')
        require(_read(root, reference)[0] == raw and _read(root, config['release'])[0] == release_raw,
                'V27_CONFIGURATION_CHANGED')
        for name, digest in config['source_pins'].items():
            require(_read_digest(root/name, 32*1024*1024) == digest
                    and _read_digest(executing/name, 32*1024*1024) == digest, 'V27_SOURCE_CHANGED')

    def local(name):
        path = Path(config[name])
        require(not path.is_absolute() and '..' not in path.parts and bool(path.parts), 'V27_LOCAL_PATH')
        candidate = root/path
        reject_links(candidate)
        require(candidate.resolve().is_relative_to(root/'data/strategy_account')
                and candidate.resolve() != root/'data/strategy_account', 'V27_STORAGE_SCOPE')
        return candidate

    validate()
    prepared = build_unified_server_preparation_v26(root=root,
        configuration_path=config['base_v26']['path'], configuration_sha256=config['base_v26']['sha256'], clock=clock)
    def gate():
        prepared['validate_code']()
        validate()
    monthly = prepared['monthly']
    old = prepared['observed_daily']
    prior = old.service.service
    previous_reader = prior.reader
    packet = previous_reader.source_reader.packet_reader
    source_raw, source_configuration = _read(root, packet.reference)
    def sources_gate():
        gate()
        require(_read(root, packet.reference)[0] == source_raw, 'V27_SOURCE_CONFIGURATION_CHANGED')
    proposals = SavedFrontierProposalStore(local('proposal_database'))
    storage_paths = [local(name).resolve() for name in
                     ('proposal_database', 'capture_root', 'archive_root', 'display_root')]
    require(len(set(storage_paths)) == len(storage_paths), 'V27_STORAGE_COLLISION')
    require(proposals.path.resolve() not in {monthly.accounts.path.resolve(), monthly.targets.path.resolve(),
            previous_reader.risk_store.path.resolve()}, 'V27_DATABASE_COLLISION')
    view = SavedFrontierMonthlyView(monthly=monthly, proposals=proposals, validate_sources=sources_gate)
    from data.saved_frontier_live_reader_v1 import SavedFrontierLiveReader
    reader = SavedFrontierLiveReader(root=root, monthly_view=view,
        risk_store=previous_reader.risk_store, source_configuration=deepcopy(source_configuration),
        source_pins=deepcopy(config['source_pins']), capture_root=local('capture_root'),
        archive_root=local('archive_root'), release_bytes=release_raw, clock=old.clock,
        validate_sources=sources_gate, fetch_daily=packet.fetch_daily, fetch_official=packet.fetch_official)
    daily = SavedFrontierRollingAdmissionV1(monthly=monthly, monthly_view=view,
        reader=reader, clock=old.clock, validate_code=sources_gate,
        policy_execution_enabled=True, policy_id=POLICY_ID)
    references = deepcopy(old.policy_references)
    references['frontier_release'] = deepcopy(config['release'])
    references['frontier_preparation'] = reference
    observed = ObservedFrontierDailyAdmission(service=daily, monthly=view, journal=old.journal,
        clock=old.clock, validate_sources=sources_gate, policy_references=references)
    charts = StrategyFrontierTargetChartsV1(root=root, target_service=view)
    display = FrontierLatestDisplayChartsV1(view=view, validate_sources=sources_gate,
        output_root=local('display_root'), clock=old.clock)
    replacements = {
        ('/api/strategy-account/target', 'GET'),
        ('/api/strategy-account/target/generate', 'POST'),
        ('/api/strategy-account/target/preview', 'POST'),
        ('/api/strategy-account/target/bars', 'GET'),
        ('/api/strategy-daily-v3/preview', 'POST'),
        ('/api/strategy-display/latest-bars', 'GET')}
    router = APIRouter()
    counts = dict.fromkeys(replacements, 0)
    for route in prepared['router'].routes:
        keys = [key for key in replacements if isinstance(route, APIRoute)
                and route.path == key[0] and route.methods == {key[1]}]
        if keys:
            counts[keys[0]] += 1
        else:
            router.routes.append(route)
    require(all(count == 1 for count in counts.values()), 'V27_REPLACEMENT_ROUTE_REQUIRED')
    from fastapi.responses import FileResponse

    @router.get('/static/strategy_target_recovery_v1.js')
    def target_recovery_script():
        validate()
        return FileResponse(root/'web/strategy_target_recovery_v1.js', media_type='application/javascript',
                            headers={'Cache-Control': 'no-store'})

    router.include_router(monthly_router(service=view, charts=charts))
    router.include_router(daily_router(service=observed))
    router.include_router(display_router(service=display))
    from api.news_desk_v1 import create_router as news_router
    router.include_router(news_router(root, validate=validate))
    sources_gate()
    return dict(prepared, router=router, monthly=monthly, frontier_monthly=view,
        observed_daily=observed, frontier_reader=reader, latest_display=display,
        validate_code=sources_gate, proposal_migration_performed=False)
