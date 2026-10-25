"""Versioned frontier request domain; preserves frozen production source files."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from core.strategy_account_ledger import canonical, require
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
from data.strategy_daily_session_capture import reject_links

def prepare_supplement_request(*, root, state, target, identity_reference,
                               calendar_reference, unit_source_paths, source_pins,
                               security_ids, decision_date, now,
                               monthly_quantities=None, extra_security_ids=()):
    """Build a stable request from server records, never browser ticker/price input."""
    from zoneinfo import ZoneInfo
    from data.saved_frontier_security_domain_v1 import plan_security_domain
    from data.strategy_daily_rolling_parent_v3 import pinned
    from data.strategy_daily_session_capture import stamp
    domain = plan_security_domain(root=root, state=state, target=target,
        identity_reference=identity_reference, source_paths=unit_source_paths,
        monthly_quantities=monthly_quantities, extra_security_ids=extra_security_ids)
    wanted = set(security_ids)
    require(bool(wanted) and wanted <= set(domain['securities']), 'SUPPLEMENT_REQUEST_DOMAIN')
    calendar = json.loads(pinned(root, calendar_reference, maximum=8*1024*1024))
    require(calendar['schema'] == 'FIXED_EXCHANGE_SESSIONS_V1' and
        calendar['exchange'] == 'NASDAQ', 'SUPPLEMENT_CALENDAR_SCHEMA')
    sessions = calendar['sessions']; dates = [row['date'] for row in sessions]
    require(dates == sorted(set(dates)), 'SUPPLEMENT_CALENDAR_DATES')
    current = stamp(now); today = current.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    if today not in dates:
        return dict(status='WAIT_SUPPLEMENT_SESSION', request=None)
    index = dates.index(today); session = sessions[index]
    if not stamp(session['open']) <= current < stamp(session['close']):
        return dict(status='WAIT_SUPPLEMENT_SESSION', request=None)
    from data.monthly_risk_epoch import validate_monthly_epoch
    validate_monthly_epoch(decision_date=decision_date, target_month=target['payload']['target_month'], session_dates=dates)
    require(index >= 20 and decision_date in dates and dates.index(decision_date) < index, 'SUPPLEMENT_MONTHLY_WINDOW')
    unresolved = sorted(sid for sid in wanted if domain['securities'][sid]['unit_baseline'] is None)
    if unresolved:
        return dict(status='WAIT_UNIT_BASELINE', request=None, unresolved=unresolved)
    start = min(index-20, dates.index(decision_date))
    binding = dict(account_id=state['account_id'], account_revision=state['revision'],
        target_id=target['target_id'], session=today)
    request = dict(account_id=state['account_id'], state_revision=state['revision'],
        window_start=sessions[start]['open'], observed_floor=session['open'],
        securities={sid: {'ticker': domain['securities'][sid]['ticker']} for sid in sorted(wanted)},
        current_target_quantities={sid: (target['payload']['target_quantities']
                                        if monthly_quantities is None else monthly_quantities).get(sid, 0)
                                   for sid in sorted(wanted)})
    configurations = {sid: dict(schema='SAVED_FRONTIER_FIRST_WINDOW_V1', security_id=sid,
        monthly_decision_date=decision_date, identity=identity_reference, calendar=calendar_reference,
        unit_source_paths=unit_source_paths, source_pins=source_pins) for sid in sorted(wanted)}
    return dict(status='SUPPLEMENT_REQUEST_PREPARED', binding=binding, request=request,
        configurations=configurations, domain=domain, policy_approved=False)
