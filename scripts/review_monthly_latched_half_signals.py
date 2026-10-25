"""Recompute saved SMA diagnostics from supplied historical evidence, without trading."""
from copy import deepcopy
from datetime import date, datetime
from fractions import Fraction
from zoneinfo import ZoneInfo


def review(*, assembled, outcome, history_resolver):
    def require(ok, reason):
        if not ok:
            raise ValueError(reason)

    def stamp(value):
        result = datetime.fromisoformat(value)
        require(result.utcoffset() is not None, 'SIGNAL_AWARE_TIME_REQUIRED')
        return result

    days = assembled['session_dates'][:-1]
    records = outcome['provider_audit']
    require(len(days) == len(records), 'SIGNAL_AUDIT_COVERAGE')
    checked = 0
    waiting = 0
    for day, record in zip(days, records):
        require(record['status'] == 'READY', 'SIGNAL_NONREADY_AUDIT')
        if record.get('action') == 'WAIT_POST_ACTION_MARK':
            waiting += 1
            continue  # Waiting legality is checked by the separate action reviewer.
        ceiling = record['monthly_ceiling']
        month = record['target_decision_date']
        evidence = history_resolver(decision_date=day, target_quantities=deepcopy(ceiling),
                                    monthly_decision_date=month, count=20)
        base = evidence['base_target']
        saved = record['risk_overlay']
        require(bool(base.get('origin_reference')) and all(type(q) is int and q >= 0
                for q in ceiling.values()), 'SIGNAL_TARGET_REFERENCE')
        require(base == saved['base_target'] and base['quantities'] == ceiling
                and base['monthly_decision_date'] == month, 'SIGNAL_TARGET_BINDING')
        require(saved['signal_date'] == day and saved['observed_at'] == evidence['observed_at'],
                'SIGNAL_TIME_BINDING')
        observed = stamp(evidence['observed_at'])
        zone = ZoneInfo('America/New_York')
        require(observed.astimezone(zone).date().isoformat() == day, 'SIGNAL_OBSERVATION_DATE')
        calendar = evidence['session_dates']
        require(calendar == sorted(set(calendar)) and day in calendar, 'SIGNAL_CALENDAR')
        require(all(date.fromisoformat(value).isoformat() == value for value in calendar), 'SIGNAL_CALENDAR_DATE')
        require(month in calendar and month <= day, 'SIGNAL_MONTH')
        closes = evidence['session_close_times']
        require(bool(closes['review_reference']), 'SIGNAL_CALENDAR_REFERENCE')
        current_close = stamp(closes['closes'][day])
        require(current_close <= observed and current_close.astimezone(zone).date().isoformat() == day,
                'SIGNAL_CURRENT_SESSION_INCOMPLETE')
        positive = {sid for sid, quantity in ceiling.items() if quantity}
        require(positive == set(evidence['histories']) == set(base['price_units'])
                == set(saved['diagnostics']), 'SIGNAL_DOMAIN')
        if not positive:
            continue
        position = calendar.index(day)
        require(position >= 19, 'SIGNAL_WARMUP')
        expected_dates = calendar[position - 19:position + 1]
        for sid in sorted(positive):
            history = evidence['histories'][sid]
            units = history['units']
            require(units['schema'] == 'REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1'
                    and units['unit_asof'] == day and units['currency'] == 'USD'
                    and bool(units['basis_id']) and units['basis_id'] == base['price_units'][sid]
                    and bool(units['review_reference']) and bool(history['source_reference']), 'SIGNAL_UNITS')
            rows = history['closes']
            require([row['date'] for row in rows] == expected_dates, 'SIGNAL_EXACT_WINDOW')
            values = []
            previous = None
            for row in rows:
                completed = stamp(row['completed_at'])
                scheduled = stamp(closes['closes'][row['date']])
                require(scheduled <= completed <= observed
                        and completed.astimezone(zone).date().isoformat() == row['date']
                        and scheduled.astimezone(zone).date().isoformat() == row['date']
                        and (previous is None or completed > previous), 'SIGNAL_COMPLETION_TIME')
                require(type(row['close']) is not bool, 'SIGNAL_BOOLEAN_PRICE')
                value = Fraction(str(row['close']))
                require(value > 0, 'SIGNAL_PRICE')
                values.append(value)
                previous = completed
            last = values[-1]
            average = sum(values, Fraction(0)) / 20
            diagnostic = saved['diagnostics'][sid]
            require(last == Fraction(str(assembled['close_prices'][sid][day])), 'SIGNAL_NOMINAL_CLOSE')
            require(Fraction(diagnostic['close']) == last and Fraction(diagnostic['sma20']) == average
                    and type(diagnostic['on']) is bool and diagnostic['on'] == (last > average)
                    and diagnostic['monthly_ceiling'] == ceiling[sid], 'SIGNAL_DIAGNOSTIC_MISMATCH')
            checked += 1
    return dict(status='SMA20_DIAGNOSTICS_RECOMPUTED_FROM_SUPPLIED_HISTORY', security_sessions=checked,
                wait_sessions=waiting, waiting_legality_verified=False, source_authenticity_certified=False,
                point_in_time_membership_certified=False, independent_out_of_sample=False)
