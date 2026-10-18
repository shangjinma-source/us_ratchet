"""Calendar-year slices of one continuous account; no trading or source IO."""
from datetime import date
from fractions import Fraction


def calendar_year_metrics(*, opening_date, opening_equity, daily_ledger,
                          expected_sessions, report_through):
    """Require every supplied session, preserving prior-year equity as basis.

    The caller owns calendar provenance. This validates coverage against that
    calendar, not whether the calendar or underlying prices are authentic.
    External flows need a separate return method and are deliberately rejected.
    """
    def day(value):
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError('NON_CANONICAL_DATE')
        return parsed

    def amount(value):
        if isinstance(value, bool):
            raise ValueError('BOOLEAN_AMOUNT')
        return Fraction(str(value))

    start, cutoff = day(opening_date), day(report_through)
    capital = amount(opening_equity)
    if capital <= 0 or cutoff <= start:
        raise ValueError('INVALID_OPENING_STATE')
    if not expected_sessions or expected_sessions != sorted(set(expected_sessions)):
        raise ValueError('INVALID_CALENDAR_ORDER')
    for session in expected_sessions:
        day(session)
    if expected_sessions[0] <= opening_date or expected_sessions[-1] > report_through:
        raise ValueError('CALENDAR_OUTSIDE_REPORT')
    if [row['date'] for row in daily_ledger] != expected_sessions:
        raise ValueError('INCOMPLETE_OR_DUPLICATED_LEDGER')
    years = []
    previous_date, previous_equity = opening_date, capital
    for year in sorted({day(session).year for session in expected_sessions}):
        rows = [row for row in daily_ledger if day(row['date']).year == year]
        basis_date, basis = previous_date, previous_equity
        if basis <= 0:
            raise ValueError('NONPOSITIVE_YEAR_OPENING_EQUITY')
        peak, worst = basis, Fraction(0)
        for row in rows:
            equity = amount(row['equity'])
            if equity < 0:
                raise ValueError('NEGATIVE_EQUITY')
            if amount(row.get('external_flow', '0')) != 0:
                raise ValueError('EXTERNAL_FLOW_REQUIRES_SEPARATE_RETURN_METHOD')
            peak = max(peak, equity)
            worst = max(worst, 1 - equity / peak)
            previous_date, previous_equity = row['date'], equity
        # A list of supplied dates cannot establish the exchange calendar's
        # first/last sessions or missing days. A later requested cutoff also
        # cannot extend the actual observation window into a full year/YTD.
        scope = ('PARTIAL_YEAR_ON_SUPPLIED_CALENDAR'
                 if day(basis_date).year == year
                 else 'UNVERIFIED_CALENDAR_YEAR_SLICE')
        elapsed = (day(previous_date) - day(basis_date)).days
        cumulative = previous_equity / basis - 1
        years.append(dict(year=year, scope=scope, basis_date=basis_date,
                          full_year_coverage_verified=False,
                          year_to_date_coverage_verified=False,
                          first_session=rows[0]['date'], last_session=previous_date,
                          sessions=len(rows), opening_equity=str(basis),
                          closing_equity=str(previous_equity),
                          cumulative_return=str(cumulative),
                          elapsed_day_annualized_return=float(1+cumulative)**(365/elapsed)-1,
                          maximum_within_year_close_drawdown=str(worst)))
    return dict(years=years, continuous_account=True, calendar_authenticated=False,
                requested_report_through=report_through,
                last_observed_session=expected_sessions[-1],
                capital_reset_each_year=False, external_flows_supported=False,
                drawdown_scope='WITHIN_YEAR_WITH_PRIOR_YEAR_CLOSE_PEAK; NOT_FULL_PATH_DRAWDOWN')
