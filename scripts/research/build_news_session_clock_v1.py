"""Build an isolated historical regular-session clock from saved schedule reviews."""
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]


def event_execution(sessions, available_at):
    available = datetime.fromisoformat(available_at.replace('Z', '+00:00'))
    if available.utcoffset() is None:
        raise ValueError('TIMEZONE_REQUIRED')
    for index, row in enumerate(sessions):
        if datetime.fromisoformat(row['close']) > available:
            if index + 1 == len(sessions):
                return None
            return dict(decision_date=row['date'], decision_close=row['close'],
                        execution_date=sessions[index + 1]['date'],
                        execution_open=sessions[index + 1]['open'])
    return None


def build(root=ROOT):
    sources = {}
    def read(path, expected=None):
        raw = (root/path).read_bytes()
        digest = sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('SOURCE_CHANGED:' + path)
        sources[path] = digest
        return raw
    early_path = 'tmp/independent_calendar_review_20261026/calendar_review.json'
    later_path = 'tmp/old_window_official_calendar_20261026/review.json'
    early = json.loads(read(early_path))
    later = json.loads(read(later_path))
    for source in early['sources']:
        read('tmp/independent_calendar_review_20261026/' + source['key'] + '.bin', source['sha256'])
    for path, digest in later['source_hashes'].items():
        read(path, digest)
    holidays = set(early['full_holidays']) | set(later['full_holidays'])
    early_closes = set(early['early_close_sessions_retained']) | set(later['early_closes_retained'])
    rows = []
    day, end = date(2020, 12, 31), date(2026, 7, 30)
    eastern = ZoneInfo('America/New_York')
    while day <= end:
        label = day.isoformat()
        if day.weekday() < 5 and label not in holidays:
            close_hour = 13 if label in early_closes else 16
            rows.append(dict(date=label, open=datetime.combine(day, time(9, 30), eastern)
                .astimezone(timezone.utc).isoformat(), close=datetime.combine(day, time(close_hour), eastern)
                .astimezone(timezone.utc).isoformat(), early_close=label in early_closes))
        day += timedelta(days=1)
    comparisons = []
    for directory in ('recent_continuous_baseline_20261026_v7', 'old_continuous_baseline_20261026_v9'):
        path = 'tmp/' + directory + '/execution_inputs.json'
        document = json.loads(read(path))
        expected = (document['prepared'] if 'prepared' in document else document)['session_dates']
        actual = [row['date'] for row in rows if expected[0] <= row['date'] <= expected[-1]]
        if expected != actual:
            raise ValueError('FROZEN_SESSION_DATES_DIFFER:' + directory)
        comparisons.append(dict(window=directory, matched_sessions=len(actual)))
    return dict(schema='NEWS_RESEARCH_REGULAR_SESSION_CLOCK_V1', sessions=rows,
        session_closes={row['date']: row['close'] for row in rows}, source_hashes=sources,
        date_comparisons=comparisons, timezone='America/New_York',
        limitations=['Historical research clock; no production calendar mutation.',
            'Saved official published dates and known special closure, not every emergency notice.',
            'Scheduled regular hours do not prove a security was tradable or a fill occurred.',
            'Only 2020-12-31 through 2026-07-30. No extrapolation beyond this interval.'])


if __name__ == '__main__':
    result = build()
    examples = {value: event_execution(result['sessions'], value) for value in
        ('2026-01-30T21:10:41Z', '2023-07-03T17:00:00Z', '2023-07-03T16:59:59Z')}
    result['timing_examples'] = examples
    destination = ROOT/'tmp/news_session_clock_20261027/clock.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(sessions=len(result['sessions']), comparisons=result['date_comparisons'], examples=examples)))
