"""Pure prospective membership supplement consumer; no sealed universe mutation.

Publication timestamps are source assertions, not historical capture certificates.
Same-day effectiveness requires an explicit aware boundary supplied by the caller.
"""
from datetime import datetime, date
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')


def aware(value):
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('AWARE_TIMESTAMP_REQUIRED')
    return result


def evaluate_membership_event(event, *, decision_at, effective_at=None):
    cutoff = aware(decision_at)
    if not event.get('source_references'):
        raise ValueError('MEMBERSHIP_SOURCE_REFERENCES_REQUIRED')
    base = dict(event_id=event['event_id'], decision_at=cutoff.isoformat(),
                add=list(event['add']), remove=list(event['remove']),
                historically_authenticated=event.get('available_at_historically_authenticated') is True)
    publication = event.get('source_reported_published_at')
    if publication is None:
        return dict(base, status='UNKNOWN_PUBLICATION_TIME', apply=False)
    published = aware(publication)
    if cutoff < published:
        return dict(base, status='NOT_YET_KNOWN', apply=False)
    effective_day = date.fromisoformat(event['effective_date'])
    local_day = cutoff.astimezone(NY).date()
    if local_day < effective_day:
        return dict(base, status='KNOWN_NOT_EFFECTIVE', apply=False)
    if effective_at is not None:
        boundary = aware(effective_at)
        if boundary.astimezone(NY).date() != effective_day:
            raise ValueError('EFFECTIVE_BOUNDARY_DATE_MISMATCH')
        if cutoff < boundary:
            return dict(base, status='KNOWN_NOT_EFFECTIVE', apply=False)
    elif local_day == effective_day:
        return dict(base, status='UNKNOWN_INTRADAY_EFFECTIVE_BOUNDARY', apply=False)
    # A prior date's BEFORE_MARKET_OPEN event is effective on a later date;
    # no midnight publication or fabricated session-open timestamp is inferred.
    if event.get('effective_phase') != 'BEFORE_MARKET_OPEN':
        raise ValueError('UNSUPPORTED_EFFECTIVE_PHASE')
    return dict(base, status='KNOWN_AND_EFFECTIVE', apply=True)


def propose_membership_update(members, events, *, decision_at, effective_boundaries=None):
    result = set(members)
    audit = []
    seen = set()
    for event in sorted(events, key=lambda row: (row['effective_date'], row['event_id'])):
        if event['event_id'] in seen:
            raise ValueError('DUPLICATE_MEMBERSHIP_EVENT')
        seen.add(event['event_id'])
        row = evaluate_membership_event(event, decision_at=decision_at,
            effective_at=(effective_boundaries or {}).get(event['event_id']))
        audit.append(row)
        if row['apply']:
            if not set(row['remove']) <= result or set(row['add']) & result:
                raise ValueError('MEMBERSHIP_ANCHOR_CONFLICT')
            result.difference_update(row['remove'])
            result.update(row['add'])
    return dict(members=sorted(result), events=audit,
                complete_pit_universe_certified=False, proposal_only=True)
