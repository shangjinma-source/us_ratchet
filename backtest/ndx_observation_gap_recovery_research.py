"""Pure gap classification; never append a calendar or authorize a decision."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo('America/New_York')
MAX_SOURCE_SESSIONS = 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def session(value):
    require(type(value) is str, 'Canonical date string required')
    parsed = date.fromisoformat(value)
    require(parsed.isoformat() == value and parsed.weekday() < 5, 'Canonical weekday date required')
    return parsed


def timing(day):
    close = datetime.combine(day,time(16),NEW_YORK)
    following = day+timedelta(days=1)
    while following.weekday() >= 5:
        following += timedelta(days=1)
    deadline = datetime.combine(following,time(9,30),NEW_YORK)
    return close.astimezone(timezone.utc),deadline.astimezone(timezone.utc)


def classify_gap_recovery(*, last_sealed_session, common_source_sessions, observed_at_utc, prospective_start_date):
    """Conservative regular-close / next-weekday-open classification only.

    All earlier pending rows are missed observations, never retroactive timely
    evidence. Only the latest completed row can be a timeliness candidate.
    Real clock, source completeness, old-prefix identity, lineage and eligibility
    must be authenticated by a separate future adapter; this function grants none.
    """
    last = session(last_sealed_session); start = session(prospective_start_date)
    require(type(observed_at_utc) is str, 'Explicit aware timestamp required')
    observed = datetime.fromisoformat(observed_at_utc)
    require(observed.tzinfo is not None and observed.utcoffset() == timedelta(0), 'UTC timestamp required')
    require(observed >= timing(last)[0], 'Clock precedes sealed close')
    require(type(common_source_sessions) is list and len(common_source_sessions) <= MAX_SOURCE_SESSIONS
            and all(type(value) is str for value in common_source_sessions)
            and common_source_sessions == sorted(set(common_source_sessions)), 'Bounded unique ascending source sessions required')
    dates = [session(value) for value in common_source_sessions]
    require(all(day > last for day in dates), 'Only unsealed source dates may be supplied')
    completed = [day for day in dates if timing(day)[0] <= observed]
    excluded = [day.isoformat() for day in dates if timing(day)[0] > observed]
    pending = []; candidate = None
    for index,day in enumerate(completed):
        close,deadline = timing(day)
        is_latest = index == len(completed)-1
        timely = observed < deadline
        is_candidate = is_latest and timely and day >= start
        record = {'session':day.isoformat(),'conservative_close_utc':close.isoformat(),
            'conservative_seal_deadline_utc':deadline.isoformat(),
            'recorded_at_utc':observed.isoformat(),
            'classification':('TIMELY_LATEST_ROW_REQUIRES_NEW_LINEAGE_REVIEW' if is_candidate else
                'EARLIER_PENDING_ROW_NOT_TIMELY_EVIDENCE' if not is_latest else
                'BEFORE_PROSPECTIVE_START' if day < start else 'LATEST_ROW_SEAL_DEADLINE_MISSED'),
            'decision_eligible':False,'first_observed_at_historical_close_claimed':False}
        pending.append(record)
        if is_candidate:
            candidate = dict(record)
    return {'schema':'OBSERVATION_GAP_RECOVERY_CLASSIFICATION_V1','last_sealed_session':last_sealed_session,
        'prospective_start_date':prospective_start_date,'observed_at_utc':observed.isoformat(),
        'pending_classifications':pending,'excluded_not_completed_sessions':excluded,
        'timeliness_candidate':candidate,'missed_or_ineligible_row_count':len(pending)-int(candidate is not None),
        'requires_versioned_lineage_and_consumer_review':True,
        'canonical_calendar_append_allowed':False,'candidate_seal_allowed':False,
        'cohort_registration_allowed':False,'retrospective_backfill_allowed':False,
        'system_clock_verified':False,'source_calendar_completeness_verified':False,
        'old_sealed_prefix_verified':False,'exchange_holidays_and_early_closes_verified':False,
        'point_in_time_verified':False,'promotion_allowed':False,'live_mutation_allowed':False,
        'scope':'PURE_CALLER_SUPPLIED_GAP_CLASSIFICATION_NOT_AN_OBSERVATION_LEDGER'}
