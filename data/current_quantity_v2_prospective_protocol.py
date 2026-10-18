"""Pure structural gates for proposed V2 prospective records; no scheduler or IO."""
from datetime import datetime, date
from zoneinfo import ZoneInfo

METHOD = 'EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def stamp(value):
    value = datetime.fromisoformat(value)
    require(value.tzinfo is not None and value.utcoffset() is not None, 'AWARE_TIME_REQUIRED')
    return value


def validate_protocol(protocol):
    require(protocol['schema'] == 'MONTHLY_QUANTITY_V2_PROSPECTIVE_CANDIDATE_V1', 'PROTOCOL_SCHEMA')
    require(protocol['status'] == 'PROPOSED_NOT_ACTIVATED_NOT_OOS_STARTED', 'NOT_AN_ACTIVATION')
    require(protocol['selection'] == dict(method=METHOD, completed_closes=253,
        scenario_count=12, sessions_per_scenario=21, objective_budget=8192,
        fixed_seed='fresh-quantity-20261014-v1', frequency='ONCE_PER_TARGET_MONTH'), 'METHOD_DRIFT')
    require(all(protocol['activation'][key] is None for key in
        ('registered_at', 'start_decision_date', 'start_active_session', 'initial_capital', 'account_id')), 'BACKDATED_START')
    require(protocol['activation']['account_writes_authorized'] is False, 'ACCOUNT_AUTHORITY')
    require(protocol['forward_record']['started'] is False and protocol['forward_record']['completed'] is False,
            'FALSE_FORWARD_HISTORY')
    costs = protocol['costs_and_comparator']
    require(costs['commission_bps'] == '0' and costs['minimum_commission'] == '0',
            'CONFIRMED_COMMISSION_DRIFT')
    require(costs['other_fees'] == 'UNKNOWN_NOT_RESERVED; record actual known charges, never claim fully net',
            'UNKNOWN_FEES_MUST_REMAIN_EXPLICIT')
    return dict(status='VALID_CANDIDATE_ONLY', sources_verified=False, activated=False)


def validate_decision_record(record):
    """Validate declared timing/shape, not calendar authenticity or source bytes.

    Source receipt times and completion time are explicit; publication dates alone
    cannot substitute for receipt timestamps. External cash flows are never sizes.
    """
    require(record['method'] == METHOD, 'METHOD_MISMATCH')
    days = record['training_sessions']
    require(len(days) == 253 and days == sorted(set(days)), 'TRAINING_SESSION_SHAPE')
    for day in days: date.fromisoformat(day)
    require(days[-1] == record['decision_date'], 'DECISION_WINDOW_MISMATCH')
    require(record['scenario_start_dates'] == days[::21][:-1] and
            record['scenario_end_dates'] == days[21::21], 'SCENARIO_BOUNDARIES')
    close, decided, active = map(stamp, (record['completed_close_at'], record['decision_recorded_at'], record['active_open_at']))
    require(close <= decided < active, 'DECISION_TIME_ORDER')
    require(close.astimezone(ZoneInfo('America/New_York')).date().isoformat() == record['decision_date'], 'CLOSE_DATE_MISMATCH')
    require(record['source_received_at'] and all(close <= stamp(t) <= decided
            for t in record['source_received_at']), 'SOURCE_RECEIPT_TIME_ORDER')
    require(record['target_month'] == active.astimezone(ZoneInfo('America/New_York')).date().isoformat()[:7] and
            record['target_month'] not in record['previous_target_months'], 'MONTH_DUPLICATE_OR_MISMATCH')
    require(record['source_hashes'] and record['full_domain_manifest_hash'], 'MISSING_SOURCE_BINDING')
    require(record['external_cash_flows'] == [], 'NEW_EXTERNAL_FLOW_REQUIRES_SEPARATE_SERIES')
    return dict(status='STRUCTURALLY_VALID_DECISION_RECORD', source_bytes_verified=False,
                calendar_verified=False, execution_authorized=False)
