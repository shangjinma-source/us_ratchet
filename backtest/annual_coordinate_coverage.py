"""Read-only coverage diagnostics; never use future coverage to shrink a domain."""
from datetime import date
from fractions import Fraction


def audit_coordinate_coverage(*, rows, calendars):
    tickers = [row['ticker'] for row in rows]
    if len(tickers) != len(set(tickers)):
        raise ValueError('DUPLICATE_TICKER')
    identities = [row['current_security_id'] for row in rows if row.get('current_security_id')]
    if len(identities) != len(set(identities)):
        raise ValueError('DUPLICATE_SECURITY')
    reports = []
    for calendar in calendars:
        sessions = calendar['sessions']
        if not sessions or sessions != sorted(set(sessions)):
            raise ValueError('INVALID_CALENDAR')
        if any(date.fromisoformat(day).isoformat() != day for day in sessions):
            raise ValueError('INVALID_DATE')
        if any(date.fromisoformat(day).year != calendar['year'] for day in sessions):
            raise ValueError('YEAR_MISMATCH')
        securities = []
        for row in rows:
            if not row.get('current_security_id'):
                securities.append(dict(security_id=None, ticker=row['ticker'],
                                       status='IDENTITY_UNRESOLVED', missing_sessions=None,
                                       source_status=row['status']))
                continue
            prices = row.get('nominal_ohlc')
            if prices is None:
                securities.append(dict(security_id=row['current_security_id'], ticker=row['ticker'],
                                       status='COORDINATES_BLOCKED', missing_sessions=None,
                                       source_status=row['status']))
                continue
            def valid_price(day):
                try:
                    values = prices[day]['ohlc']
                    raw = [values[key] for key in ('open', 'high', 'low', 'close')]
                    if any(isinstance(value, bool) for value in raw):
                        return False
                    op, hi, lo, close = [Fraction(str(value)) for value in raw]
                    return 0 < lo <= min(op, close) <= max(op, close) <= hi
                except (KeyError, TypeError, ValueError, ZeroDivisionError):
                    return False
            missing = [day for day in sessions if not valid_price(day)]
            invalid = [day for day in missing if day in prices]
            securities.append(dict(security_id=row['current_security_id'], ticker=row['ticker'],
                                   status='MISSING_SESSIONS' if missing else 'SUPPLIED_CALENDAR_COVERED',
                                   missing_sessions=missing, missing_count=len(missing),
                                   invalid_present_sessions=invalid,
                                   source_status=row['status']))
        reports.append(dict(year=calendar['year'], first=sessions[0], last=sessions[-1],
                            expected_sessions=len(sessions), securities=securities))
    return dict(years=reports, domain_count=len(rows), domain_filtered=False,
                usage='DIAGNOSTIC_ONLY_NOT_SELECTION_OR_EXECUTION_ADMISSION',
                calendar_authenticated=False, ipo_classification_inferred=False,
                note='Missing whole dates and missing OHLC rows are equally absent. '
                     'Eligibility uses predecision information separately; never exclude '
                     'securities using future annual coverage. Covered rows still require '
                     'identity, price-coordinate and corporate-action admission.')
