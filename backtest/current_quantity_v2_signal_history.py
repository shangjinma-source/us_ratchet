"""Resolve explicitly reviewed decision-unit signal histories without IO.

The caller authenticates source hashes and constructs decision-specific units.
This module never infers split ratios, joins security identities or certifies
the supplied calendar. Missing decision snapshots remain errors.
"""
from copy import deepcopy
from datetime import date


def build_signal_history_resolver(*, session_dates, session_close_times, snapshots):
    """Freeze inputs; each snapshot declares observation time and SID histories.

    snapshots[decision_date] contains observed_at, review_reference, histories.
    A history uses risk_overlays' units/source_reference/closes schema and may
    contain a longer warmup series. Only exact completed window dates are read.
    """
    calendar = deepcopy(session_dates)
    if calendar != sorted(set(calendar)):
        raise ValueError('ORDERED_UNIQUE_CALENDAR_REQUIRED')
    if any(date.fromisoformat(day).isoformat() != day for day in calendar):
        raise ValueError('CANONICAL_CALENDAR_REQUIRED')
    schedule = deepcopy(session_close_times)
    stored = deepcopy(snapshots)

    def resolve(*, decision_date, target_quantities, monthly_decision_date, count):
        if type(count) is not int or count not in (20, 21):
            raise ValueError('DECLARED_OVERLAY_WINDOW_REQUIRED')
        if decision_date not in calendar:
            raise ValueError('DECISION_NOT_IN_CALENDAR')
        if any(type(q) is not int or q < 0 for q in target_quantities.values()):
            raise ValueError('WHOLE_NONNEGATIVE_TARGET_REQUIRED')
        snapshot = stored[decision_date]
        if not snapshot.get('review_reference'):
            raise ValueError('REVIEWED_DECISION_SNAPSHOT_REQUIRED')
        past = calendar[:calendar.index(decision_date) + 1]
        positive = {sid: q for sid, q in target_quantities.items() if q}
        if positive and len(past) < count:
            raise ValueError('INSUFFICIENT_COMPLETED_HISTORY')
        expected = past[-count:] if positive else [decision_date]
        histories, units = {}, {}
        for sid in positive:
            source = snapshot['histories'][sid]
            # Ignore later observations, but never fill a missing session with
            # an earlier date. Duplicate past rows are ambiguous, so reject.
            past_rows = [row for row in source['closes'] if row['date'] <= decision_date]
            by_date = {row['date']: row for row in past_rows}
            if len(by_date) != len(past_rows):
                raise ValueError('DUPLICATE_HISTORY_DATE')
            history = {key: deepcopy(value) for key, value in source.items() if key != 'closes'}
            history['closes'] = [deepcopy(by_date[day]) for day in expected]
            histories[sid] = history
            units[sid] = history['units']['basis_id']
        return dict(observed_at=snapshot['observed_at'], session_dates=past,
                    session_close_times=dict(review_reference=schedule['review_reference'],
                        closes={day: schedule['closes'][day] for day in expected}),
                    histories=histories,
                    base_target=dict(quantities=deepcopy(target_quantities), price_units=units,
                        origin_reference=snapshot['review_reference'],
                        monthly_decision_date=monthly_decision_date))

    return resolve
