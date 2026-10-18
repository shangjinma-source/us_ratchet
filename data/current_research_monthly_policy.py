"""Pure explicit-month routing; never searches or manufactures a calendar."""
from datetime import date
import re


def route_monthly_research_policy(*, decision_date, active_date, calendar, current_target_month):
    """The caller authenticates session calendar and persisted target month.

    A RESELECT result labels the proposed target month; the caller persists it
    only after a new selection succeeds. Routing itself changes no state.
    """
    def require(ok, reason):
        if not ok:
            raise ValueError(reason)

    def day(value):
        require(type(value) is str and date.fromisoformat(value).isoformat() == value,
                'INVALID_CANONICAL_SESSION_DATE')
        return value

    decision, active = day(decision_date), day(active_date)
    require(isinstance(calendar, list) and len(calendar) >= 2, 'EXPLICIT_SESSION_CALENDAR_REQUIRED')
    sessions = [day(value) for value in calendar]
    require(sessions == sorted(set(sessions)), 'CALENDAR_MUST_BE_UNIQUE_AND_ORDERED')
    require(decision in sessions, 'DECISION_NOT_IN_CALENDAR')
    index = sessions.index(decision)
    require(index + 1 < len(sessions) and sessions[index + 1] == active,
            'ACTIVE_NOT_ADJACENT_IN_SUPPLIED_CALENDAR')
    require(type(current_target_month) is str and re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', current_target_month),
            'EXPLICIT_TARGET_MONTH_REQUIRED')
    require(date.fromisoformat(current_target_month + '-01').strftime('%Y-%m') == current_target_month,
            'INVALID_TARGET_MONTH')
    target_month = active[:7]
    require(current_target_month <= target_month, 'TARGET_MONTH_IS_IN_FUTURE')
    if current_target_month == target_month:
        action, reason = 'ROLL', 'TARGET_MONTH_ALREADY_SELECTED'
    else:
        action = 'RESELECT'
        reason = 'MONTH_BOUNDARY_RESELECT' if decision[:7] != target_month else 'MISSED_MONTH_BOUNDARY_CATCH_UP'
    return dict(action=action, target_month=target_month, current_target_month=current_target_month,
                decision_date=decision, active_date=active, reason=reason,
                research_only=True, execution_blocked=True, search_calls=0, state_changed=False,
                calendar_completeness_verified=False,
                calendar_scope='ADJACENCY_IN_CALLER_SUPPLIED_CALENDAR_ONLY',
                target_month_commit_rule='PERSIST_NEW_TARGET_MONTH_ONLY_AFTER_SUCCESSFUL_RESELECT')
