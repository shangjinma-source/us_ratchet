"""Candidate dated member domain, reference-session dates only; no OHLC or returns."""
import calendar
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'tmp/qqq_20201231_anchor_20261025'


def build_domain():
    sources = {}
    def read(path):
        data = path.read_bytes()
        sources[path.relative_to(ROOT).as_posix()] = hashlib.sha256(data).hexdigest()
        return json.loads(data)
    anchor = read(DIRECTORY / 'holdings_identity_comparison.json')
    events = read(DIRECTORY / 'recent_member_event_review.json')['records']
    reference_dates = {}
    for ticker in ('AAPL', 'META', 'EBAY'):
        data = read(ROOT / f'tmp/free_history_price_probe_20261025_v1/{ticker}.response')
        stamps = data['chart']['result'][0]['timestamp']
        days = [datetime.fromtimestamp(value, timezone.utc).date().isoformat() for value in stamps]
        if days != sorted(set(days)):
            raise ValueError('Duplicate or unsorted reference dates:' + ticker)
        reference_dates[ticker] = set(days)
    union = set.union(*reference_dates.values())
    intersection = set.intersection(*reference_dates.values())
    # Do not silently resolve disputed dates by removing them.
    differences = {ticker: sorted(union - days) for ticker, days in reference_dates.items()}
    relevant_differences = sorted(day for day in union - intersection if '2019-01-01' <= day <= '2023-12-31')
    if relevant_differences:
        raise ValueError('Reference calendars disagree in research/warmup range:' + str(relevant_differences))
    sessions = sorted(intersection)
    members = [row['candidate_ticker'] for row in anchor['rows']]
    if len(members) != 102 or len(set(members)) != 102:
        raise ValueError('Anchor requires all 102 distinct securities')
    members = set(members)
    events = sorted(events, key=lambda event: event['official_effective_date'])
    decisions = []
    applied = []
    pending = list(events)
    # December 2020 is the launch decision for January 2021; December 2023
    # is retained as a boundary observation, without extending the return period.
    for year, month in [(2020, 12)] + [(y, m) for y in range(2021, 2024) for m in range(1, 13)]:
        prefix = f'{year}-{month:02d}'
        month_sessions = [day for day in sessions if day.startswith(prefix)]
        if not month_sessions:
            raise ValueError('No reference sessions:' + prefix)
        decision = max(month_sessions)
        while pending and pending[0]['official_effective_date'] <= decision:
            event = pending.pop(0)
            removed, added = set(event['official_removed']), set(event['official_added'])
            if not removed <= members or added & members:
                raise ValueError('Invalid forward transition:' + str(event))
            members = (members - removed) | added
            applied.append(event)
        training = [day for day in sessions if day <= decision][-253:]
        unavailable = [event['source_url'] for event in applied
                       if not event['notice_publication_date'] or event['notice_publication_date'] > decision]
        blockers = []
        if len(training) != 253:
            blockers.append('INSUFFICIENT_REFERENCE_SESSION_PREHISTORY')
        if unavailable:
            blockers.append('APPLIED_EVENT_NOT_KNOWN_BY_DECISION')
        decisions.append(dict(decision_cutoff=decision, calendar_month_end=f'{prefix}-{calendar.monthrange(year, month)[1]:02d}',
            full_members=sorted(members), member_count=len(members), training_dates=training,
            training_date_count=len(training), training_start=training[0] if training else None,
            event_sources_known_by_decision=not unavailable, unavailable_event_sources=unavailable,
            date_membership_blockers=blockers, event_source_references=[event['source_url'] for event in applied],
            price_coverage_checked=False, security_specific_253_price_history_checked=False,
            role='JANUARY_2021_LAUNCH' if year == 2020 else ('TERMINAL_BOUNDARY_ONLY' if (year, month) == (2023, 12) else 'IN_SCOPE_DECISION')))
    return dict(status='CANDIDATE_DOMAIN_NOT_PRICE_ADMITTED', calendar_basis='THREE_SAVED_US_EQUITY_TIMESTAMP_SERIES_AGREE_NOT_OFFICIAL_CALENDAR',
        reference_calendar_differences=differences, relevant_reference_differences=relevant_differences,
        source_hashes=sources, decisions=decisions, unconsumed_events=pending,
        ceg_notice_analysis={'effective':'2022-02-02','notice':'2022-02-03','first_affected_month_end':'2022-02-28',
            'monthly_decision_blocked':False,'reason':'Notice is available before the first affected monthly decision.'},
        limitations=['Anchor is fund holdings, independently matched to community; index completeness still conditional.',
          '253 dates do not prove 253 valid quotes per member or pre-IPO eligibility.',
          'Calendar uses observed timestamps; not an official exchange calendar certification.',
          'SEC anchor publication timing is not used to claim contemporaneous strategy availability; it is ex-post corroboration.',
          'Verified community event queue does not independently prove absence of omitted events.'])


if __name__ == '__main__':
    output = build_domain()
    (DIRECTORY / 'monthly_member_domain_v1.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps({'decisions':len(output['decisions']), 'date_blocked_decisions':[row['decision_cutoff'] for row in output['decisions'] if row['date_membership_blockers']],
                      'member_counts':sorted(set(row['member_count'] for row in output['decisions'])), 'remaining_events':len(output['unconsumed_events'])}))
