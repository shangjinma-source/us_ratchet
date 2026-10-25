"""Initial monthly risk epoch from source-admitted calendar, not training history."""
from datetime import datetime
from core.strategy_account_ledger import require


def validate_monthly_epoch(*, decision_date, target_month, session_dates):
    """Allow this month or its immediately preceding trading close only.

    The server must additionally bind the epoch to selection or saved risk state.
    This calendar boundary is not independent policy authorization.
    """
    require(session_dates == sorted(set(session_dates)) and decision_date in session_dates,
            'RISK_EPOCH_CALENDAR')
    preceding = [day for day in session_dates if day[:7] < target_month]
    require(decision_date[:7] == target_month or
            (preceding and decision_date == preceding[-1]), 'RISK_EPOCH_MONTH_BOUNDARY')


def initial_completed_risk_session(*, inputs, target, now):
    created_text = inputs['base_target']['monthly_target_created_at']
    require(created_text == target['payload']['created_at'], 'RISK_CREATION_BINDING')
    created = datetime.fromisoformat(created_text)
    require(created.tzinfo is not None and now.tzinfo is not None and created <= now,
            'RISK_CREATION_TIME')
    dates = inputs['session_dates']
    require(dates == sorted(set(dates)) and bool(dates), 'RISK_CALENDAR_ORDER')
    closes = inputs['session_close_times']['closes']
    stamps = [datetime.fromisoformat(closes[day]) for day in dates]
    require(all(stamp.tzinfo is not None for stamp in stamps) and
            stamps == sorted(set(stamps)), 'RISK_CLOSE_TIME_ORDER')
    completed_now = [day for day, stamp in zip(dates, stamps) if stamp <= now]
    require(completed_now and completed_now[-1] == inputs['signal_date'],
            'LATEST_COMPLETED_SIGNAL_REQUIRED')
    completed_at_selection = [day for day, stamp in zip(dates, stamps) if stamp <= created]
    require(bool(completed_at_selection), 'RISK_SELECTION_CLOSE_REQUIRED')
    return completed_at_selection[-1]
