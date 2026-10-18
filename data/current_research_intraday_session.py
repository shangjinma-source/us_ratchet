"""Read pinned scheduled sessions for intraday proposals; never infer market status."""
from copy import deepcopy
from datetime import date, datetime
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from data.current_research_successor_inputs import SuccessorInputLoader


def load_intraday_market_session(*, root, calendar_path, source_hashes, now):
    """Server-owned paths/pins only. Scheduled hours do not certify no trading halt."""
    def require(value, reason):
        if not value:
            raise ValueError(reason)
    require(isinstance(now, datetime) and now.tzinfo is not None, 'AWARE_NOW_REQUIRED')
    require(isinstance(source_hashes, dict) and calendar_path in source_hashes,
            'CALENDAR_NOT_PINNED')
    loader = SuccessorInputLoader(root=root)
    for path, digest in source_hashes.items():
        require(sha256(loader._path(path).read_bytes()).hexdigest() == digest,
                'CALENDAR_SOURCE_CHANGED')
    artifact = json.loads(loader._path(calendar_path).read_bytes())
    require(artifact.get('schema') == 'SCHEDULED_REGULAR_SESSIONS_V1', 'INVALID_CALENDAR_SCHEMA')
    evidence = artifact.get('source_hashes')
    require(isinstance(evidence, dict) and evidence and
            all(source_hashes.get(path) == digest for path, digest in evidence.items()),
            'CALENDAR_EVIDENCE_UNBOUND')
    days = artifact['calendar']
    sessions = artifact['sessions']
    require(isinstance(days, list) and days and days == sorted(set(days)) and
            all(date.fromisoformat(day).isoformat() == day for day in days), 'INVALID_CALENDAR_DOMAIN')
    by_day = {session['date']: session for session in sessions}
    require(len(by_day) == len(sessions) and set(by_day) == set(days), 'INVALID_SESSION_DOMAIN')
    zone = ZoneInfo('America/New_York')
    for day, session in by_day.items():
        require(session['timezone'] == 'America/New_York', 'INVALID_SESSION_ZONE')
        if 'source' in session:
            require(isinstance(session['source'], str) and session['source'] in source_hashes,
                    'SESSION_SOURCE_UNBOUND')
        if 'source_references' in session:
            references = session['source_references']
            require(isinstance(references, list) and references and
                    all(isinstance(reference, str) and reference in source_hashes for reference in references),
                    'SESSION_SOURCE_UNBOUND')
        opening = datetime.fromisoformat(session['open_at'])
        closing = datetime.fromisoformat(session['close_at'])
        require(all(value.tzinfo is not None and value.date().isoformat() == day and
                    value.astimezone(zone).date().isoformat() == day and
                    value.utcoffset() == value.astimezone(zone).utcoffset()
                    for value in (opening, closing)) and opening < closing,
                'INVALID_SESSION_TIMES')
    day = now.astimezone(zone).date().isoformat()
    require(day in by_day, 'CURRENT_SESSION_NOT_IN_CALENDAR')
    selected = deepcopy(by_day[day])
    require(datetime.fromisoformat(selected['open_at']) <= now < datetime.fromisoformat(selected['close_at']),
            'OUTSIDE_SCHEDULED_REGULAR_SESSION')
    selected['source_references'] = list(source_hashes)
    return dict(market_session=selected, source_hashes=deepcopy(source_hashes),
                local_source_bytes_verified=True, actual_market_open_certified=False)
