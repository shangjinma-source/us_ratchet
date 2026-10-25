"""Internal end-of-period adapter; caller owns registration admission and lock.

No CLI or activation path. Use the approved base daily configuration: accepted
monthly archives are derived from completed Store operations by preflight.
This helper never generates monthly targets or continuation orders.
"""
from datetime import datetime, timezone

from backtest.current_quantity_v2_daily_evidence_providers import DailyEvidenceProviders
from backtest.registered_paper_settlement_runtime import finalize_registered_paper
from data.current_quantity_v2_difference_plan import require, stamp
from data.quantity_v2_simulation_account_binding import validate_account_binding
from scripts.run_current_quantity_v2_simulation import preflight, _fees


def run(*, config_path, config_sha256, account_id, expected_revision,
        evaluation_end, execute=False, clock=None, transports=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    checked = preflight(config_path=config_path, config_sha256=config_sha256,
                        session=evaluation_end)
    config = checked['config']; state = checked['state']
    validate_account_binding(bootstrap=dict(account_id=account_id,
        simulation_id=config['simulation_id']), simulation=state)
    require(checked['summary']['revision'] == expected_revision, 'STALE_SIMULATION_REVISION')
    closing = state['valuation']['registration']['calendar']['closes'][evaluation_end]
    require(stamp(clock()) >= stamp(closing), 'EVALUATION_END_NOT_CLOSED')
    if not execute:
        return dict(status='SETTLEMENT_PREFLIGHT_ONLY', revision=expected_revision,
                    evaluation_end=evaluation_end, new_decisions=0,
                    network_used=False, account_writes=False)
    from data.current_quantity_v2_completed_session_minutes import fetch_bytes
    from scripts.current_research_official_alert_capture import fetch_official_feed
    from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
    from data.current_quantity_v2_late_unit_review import BoundedLateUnitReview
    transport = transports or {}
    action_arguments = dict(rss_fetch=transport.get('rss', fetch_official_feed), clock=clock)
    if 'actions' in transport:
        action_arguments['fetch'] = transport['actions']
    sources = PaperActionEvidenceSources(**action_arguments)
    evidence = DailyEvidenceProviders(store=checked['store'], root=checked['root'],
        schedule_path=config['schedule_path'], schedule_sha256=config['schedule_sha256'],
        evidence_directory=checked['runtime']/'evidence',
        fee_provider=lambda current, day: _fees(config, checked['root'], current),
        origin_files_reader=checked['origins'], clock=clock,
        minute_fetch=transport.get('minutes', fetch_bytes),
        late_review=BoundedLateUnitReview(action_sources=sources, clock=clock))
    return finalize_registered_paper(store=checked['store'],
        simulation_id=config['simulation_id'], account_id=account_id,
        expected_revision=expected_revision, evaluation_end=evaluation_end,
        clock=clock, capture_arguments=evidence.capture_arguments,
        settlement_review=evidence.settlement_review, close_arguments=evidence.close_arguments)
