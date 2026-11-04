"""Offline scheduled-call context from verified issuer bodies; not a news trigger.

Initial supported format is Moderna's issuer-distributed earnings-call notice.
Unrecognized, changed or conflicting notices require review, never a guessed date.
This module is not mounted in the production news/model pipeline yet.
"""
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

from core.news_investment_review_v1 import moment, require
from data.news_investment_sources_v1 import recover


TITLE = re.compile(
    r'Moderna to Report (First|Second|Third|Fourth) Quarter (\d{4}) '
    r'Financial Results on (Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), '
    r'([A-Z][a-z]+ \d{1,2}, \d{4})')
CALL = re.compile(
    r'will host a live conference call and webcast at (\d{1,2}):(\d{2}) '
    r'(a\.m\.|p\.m\.) ET on '
    r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), '
    r'([A-Z][a-z]+ \d{1,2}, \d{4}) to report its '
    r'(first|second|third|fourth) quarter (\d{4}) financial results')


def build_scheduled_earnings(snapshot, cache, positions):
    """Recover current receipts without replacing the seven-day news gate.

    The timestamp denotes the announced call, not first earnings publication.
    Calendar coverage is limited to supplied notices; absence is not reassurance.
    """
    now = moment(snapshot['generated_at'])
    require(len(snapshot['events']) <= 250, 'SCHEDULE_INPUT_LIMIT')
    identities = {p['security_id'] for p in positions if p['ticker'] == 'MRNA'}
    candidates, coverage = [], []
    for event in snapshot['events']:
        if event.get('tickers') != ['MRNA'] or not re.search(
                r'financial results|earnings', event.get('title', ''), re.I):
            continue
        row = dict(event_id=event.get('id'), status='REJECTED')
        try:
            require(len(identities) == 1, 'SCHEDULE_IDENTITY_REQUIRED')
            require(event.get('content_kind') == 'ISSUER_RELEASE_BODY',
                    'SCHEDULE_ISSUER_BODY_REQUIRED')
            published, observed = moment(event['published_at']), moment(event['collected_at'])
            require(published <= observed <= now, 'SCHEDULE_SOURCE_TIME_INVALID')
            require(now-observed <= timedelta(hours=24), 'SCHEDULE_REFRESH_REQUIRED')
            require(now-published <= timedelta(days=90), 'SCHEDULE_NOTICE_TOO_OLD')
            body, raw_digest = recover(event, snapshot['source_receipts'], cache)
            require(not re.search(r'cancel(?:led|ed|lation)|postpon|reschedul',
                                  event['title']+' '+body, re.I), 'SCHEDULE_CHANGE_REQUIRES_REVIEW')
            title = TITLE.fullmatch(event['title'])
            calls = list(CALL.finditer(body))
            require(title is not None and len(calls) == 1, 'SCHEDULE_FORMAT_REQUIRES_REVIEW')
            call = calls[0]
            hour, minute = int(call[1]), int(call[2])
            require(1 <= hour <= 12 and 0 <= minute < 60, 'SCHEDULE_CLOCK_INVALID')
            require((title[1].lower(), title[2], title[3], title[4]) ==
                    (call[6], call[7], call[4], call[5]), 'SCHEDULE_TITLE_BODY_CONFLICT')
            day = datetime.strptime(call[5], '%B %d, %Y')
            require(day.strftime('%A') == call[4], 'SCHEDULE_WEEKDAY_CONFLICT')
            local = day.replace(hour=hour % 12 + (12 if call[3] == 'p.m.' else 0),
                                minute=minute, tzinfo=ZoneInfo('America/New_York'))
            # Reject ambiguous or nonexistent local clocks rather than choose a fold.
            require(local.utcoffset() == local.replace(fold=1).utcoffset() and
                    local.astimezone(timezone.utc).astimezone(local.tzinfo) == local,
                    'SCHEDULE_AMBIGUOUS_LOCAL_TIME')
            scheduled = local.astimezone(timezone.utc)
            require(now < scheduled <= now+timedelta(days=30), 'SCHEDULE_OUTSIDE_FUTURE_WINDOW')
            candidates.append(dict(
                role='SCHEDULED_EVENT', event_kind='EARNINGS_CALL',
                security_id=next(iter(identities)), ticker='MRNA',
                reporting_period=f'{title[2]}-{title[1].upper()}-QUARTER',
                scheduled_at=scheduled.isoformat(), time_zone='America/New_York',
                timestamp_scope='ANNOUNCED_CALL_NOT_FIRST_REPORT_PUBLICATION',
                published_at=event['published_at'], observed_at=event['collected_at'],
                source_id=event['id'], url=event['url'], title=event['title'],
                source_quote=call[0], text_sha256=event['content_sha256'], raw_sha256=raw_digest,
                eligible_as_new_trigger=False, may_refresh_event_window=False,
                executable=False, automatic_trade_action=None))
            row['status'] = 'VERIFIED_SCHEDULE_NOTICE'
        except (ValueError, KeyError, TypeError, OSError) as error:
            row['reason'] = str(error)[:160]
        coverage.append(row)
    # No latest-wins rule: a later conflicting notice might be a correction.
    periods = {}
    for item in candidates:
        periods.setdefault(item['reporting_period'], set()).add(item['scheduled_at'])
    conflict = any(len(times) > 1 for times in periods.values()) or any(
        row['status'] == 'REJECTED' and row.get('reason') not in
        {'SCHEDULE_OUTSIDE_FUTURE_WINDOW', 'SCHEDULE_NOTICE_TOO_OLD',
         'SCHEDULE_ISSUER_BODY_REQUIRED'} for row in coverage)
    return dict(schema='SCHEDULED_EARNINGS_CONTEXT_V1',
                status='REVIEW_REQUIRED' if conflict else 'CONTEXT_ONLY',
                events=[] if conflict else candidates, coverage=coverage,
                calendar_coverage_complete=False, changes_strategy=False)
