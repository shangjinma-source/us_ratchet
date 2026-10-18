"""Conservative post-action interval proposals, never whole-channel admission."""
from datetime import date

SUPPORTED = {
    'EXC': ('2022-02-02', None, 'PARENT_CONTINUES_AFTER_SPINOFF'),
    'HON': ('2026-06-29', '438516205', 'POST_REVERSE_SPLIT_NEW_CUSIP'),
    'LRCX': ('2024-10-03', '512807306', 'POST_FORWARD_SPLIT_NEW_CUSIP'),
    'WDC': ('2025-02-24', '958102105', 'PARENT_EX_DISTRIBUTION_NOT_WDCVV'),
}


def day(value):
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise ValueError('Exact ISO session required')
    return value


def propose_interval(*, ticker, calendar, returned_events, official_boundary, completed_before):
    """All dates/events are supplied observations; function does not authenticate them."""
    if ticker not in SUPPORTED: raise ValueError('No supported official post-action boundary')
    floor, cusip, role = SUPPORTED[ticker]
    if official_boundary != dict(ticker=ticker, first_post_action_session=floor, post_action_cusip=cusip, role=role):
        raise ValueError('Exact official boundary coordinate required')
    completed_before = day(completed_before)
    if type(calendar) is not list or not calendar or calendar != sorted(set(day(d) for d in calendar)):
        raise ValueError('Unique ordered explicit caller calendar required')
    if calendar[0] < floor or calendar[-1] >= completed_before:
        raise ValueError('Caller calendar crosses action floor or incomplete receipt day')
    if type(returned_events) is not list: raise ValueError('Complete observed event list required')
    event_days = [day(e['session']) for e in returned_events]
    if len(event_days) != len(set(event_days)): raise ValueError('Duplicate returned action date')
    if any(d > floor for d in event_days):
        raise ValueError('Later returned action requires another explicit boundary; no silent dropping')
    if floor not in event_days: raise ValueError('Expected action is absent from captured channel')
    return dict(schema='POST_ACTION_CONDITIONAL_INTERVAL_PROPOSAL_V1', ticker=ticker,
        first_post_action_session=floor, post_action_cusip=cusip, boundary_role=role, calendar=list(calendar),
        completed_before=completed_before, returned_events=returned_events,
        excluded_pre_boundary_history_still_blocked=True, first_requested_session_return_allowed=False,
        returns_require_two_adjacent_in_segment_sessions=True, provider_dates_are_exchange_calendar=False,
        raw_events_deleted=False, quote_reconstruction_performed=False, simple_split_whole_channel_admitted=False,
        no_returned_later_event_proves_complete_actions=False, provider_price_identity_bound=False,
        post_action_cusip_assigned_to_pre_boundary_history=False, point_in_time_verified=False,
        promotion_allowed=False, input_artifact_binding_verified=False)
