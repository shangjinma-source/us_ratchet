"""Read the same pinned calendar as the active daily reader; never infer sessions."""
from datetime import timedelta
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from data.news_event_sources_v1 import moment


def window(*, reader, discovered_at):
    reader.validate()
    from data.saved_frontier_live_reader_v1 import pinned
    reference = reader.source['calendar']
    raw = pinned(reader.root, reference, maximum=8*1024*1024)
    document = json.loads(raw)
    if document.get('schema') != 'FIXED_EXCHANGE_SESSIONS_V1' or document.get('exchange') != 'NASDAQ':
        raise ValueError('EVENT_CALENDAR_SCHEMA')
    rows = document['sessions']
    dates = [row['date'] for row in rows]
    if not dates or dates != sorted(set(dates)):
        raise ValueError('EVENT_CALENDAR_DOMAIN')
    observed = moment(discovered_at)
    zone = ZoneInfo('America/New_York')
    if not dates[0] <= observed.astimezone(zone).date().isoformat() <= dates[-1]:
        raise ValueError('EVENT_CALENDAR_COVERAGE_MISSING')
    for row in rows:
        opening, closing = moment(row['open']), moment(row['close'])
        if not opening < closing or any(value.astimezone(zone).date().isoformat() != row['date'] for value in (opening, closing)):
            raise ValueError('EVENT_CALENDAR_SESSION_INVALID')
    for row in rows:
        opening, closing = moment(row['open']), moment(row['close'])
        if closing <= observed:
            continue
        eligible = max(opening, observed)
        if eligible-observed > timedelta(days=7):
            raise ValueError('EVENT_FIRST_OPEN_OUTSIDE_BOUND')
        return dict(not_before=eligible.isoformat(), valid_until=min(eligible+timedelta(minutes=10), closing).isoformat(),
                    session=row['date'], calendar_reference=reference, calendar_sha256=sha256(raw).hexdigest(),
                    scope='Scheduled session only; actual READY, quotes and risk remain mandatory.')
    raise ValueError('EVENT_NEXT_SESSION_UNKNOWN')
