"""Pure prospective paper scheduling decisions; never dispatches or widens NY10."""
from datetime import datetime,time,timedelta
from zoneinfo import ZoneInfo
NY=ZoneInfo('America/New_York')


def planning_state(*,now,calendar,start_session,end_session,account_initialized):
    if not isinstance(now,datetime) or now.utcoffset() is None:raise ValueError('AWARE_TIME_REQUIRED')
    dates=calendar['calendar']
    if dates!=sorted(set(dates)) or start_session not in dates or end_session not in dates:raise ValueError('CALENDAR_COVERAGE_REQUIRED')
    local=now.astimezone(NY);day=local.date().isoformat()
    if not account_initialized and day>start_session:
        return dict(status='MISSED_REGISTERED_START_REVIEW_REQUIRED',dispatch=False,automatic_rebase=False)
    if day>end_session:return dict(status='TERMINAL_SETTLEMENT_REVIEW',dispatch=False)
    if day<start_session or day not in dates:return dict(status='WAITING_SESSION',dispatch=False)
    row=next(x for x in calendar['sessions'] if x['date']==day)
    opening=datetime.fromisoformat(row['open_at']);closing=datetime.fromisoformat(row['close_at'])
    start=datetime.combine(local.date(),time(10),NY);deadline=start+timedelta(minutes=1)
    if not opening<=start<closing:raise ValueError('DECISION_OUTSIDE_SESSION')
    if local<start:
        seconds=(start-local).total_seconds()
        return dict(status='WAITING_1000' if seconds<=120 else 'NOT_YET_PREWAKE',dispatch=False,wait_seconds=seconds,deadline=deadline.isoformat())
    if local>=deadline:
        return dict(status='MISSED_FIRST_WINDOW_REVIEW_REQUIRED' if not account_initialized else 'MISSED_DAILY_WINDOW_NO_NEW_DECISION',dispatch=False,automatic_rebase=False)
    return dict(status='ELIGIBLE_RUNTIME_MUST_REVALIDATE',dispatch=True,deadline=deadline.isoformat(),latest_prices_required=True)
