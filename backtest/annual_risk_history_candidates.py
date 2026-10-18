"""Price-only conditional candidates; no observation or completion timestamps."""
from datetime import date
from fractions import Fraction


def day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError('CANONICAL_DATE_REQUIRED')
    return value


def price(value):
    if isinstance(value, bool):
        raise ValueError('BOOLEAN_PRICE')
    result = Fraction(str(value))
    if result <= 0:
        raise ValueError('POSITIVE_PRICE_REQUIRED')
    return result


def snapshot_candidate(*, decision_date, session_dates, records, count=21):
    day(decision_date)
    if count not in (20, 21) or type(count) is not int:
        raise ValueError('DECLARED_WINDOW_REQUIRED')
    if session_dates != sorted(set(session_dates)):
        raise ValueError('ORDERED_UNIQUE_CALENDAR_REQUIRED')
    for value in session_dates:
        day(value)
    if decision_date not in session_dates:
        raise ValueError('DECISION_SESSION_REQUIRED')
    end = session_dates.index(decision_date) + 1
    expected = session_dates[max(0, end-count):end]
    output = []
    seen = set()
    for record in records:
        ticker = record['ticker']
        if ticker in seen:
            raise ValueError('DUPLICATE_DOMAIN_MEMBER')
        seen.add(ticker)
        start = day(record['ordinary_start'])
        spans = record['identity_spans']
        active = [s for s in spans if day(s['start']) <= decision_date <= day(s['end'])]
        if len(active) > 1:
            raise ValueError('AMBIGUOUS_DECISION_IDENTITY')
        sid = active[0]['security_id'] if active else None
        reasons = list(record.get('blockers', []))
        if sid is None:
            reasons.append('DECISION_IDENTITY_UNRESOLVED')
        closes = record['nominal_closes']
        missing = [d for d in expected if d < start or closes is None or closes.get(d) is None]
        if len(expected) != count or missing:
            reasons.append('INSUFFICIENT_ORDINARY_WINDOW')
        events = record['true_share_events']
        dates = [day(e['date']) for e in events]
        if dates != sorted(set(dates)):
            raise ValueError('ORDERED_UNIQUE_SHARE_EVENTS_REQUIRED')
        for event in events:
            price(event['ratio'])
        rows = None
        if not reasons:
            rows = []
            for session in expected:
                factor = Fraction(1)
                for event in events:
                    if session < event['date'] <= decision_date:
                        factor *= price(event['ratio'])
                identities = [s['security_id'] for s in spans if s['start'] <= session <= s['end']]
                if len(identities) != 1 or identities[0] is None:
                    reasons.append('WINDOW_IDENTITY_UNRESOLVED')
                    rows = None
                    break
                if identities[0] != sid:
                    link = record.get('cross_identity_link')
                    if (not isinstance(link, dict) or link.get('from_security_id') != identities[0]
                        or link.get('to_security_id') != sid or not link.get('source_reference')
                        or not session < day(link['effective_date']) <= decision_date
                        or not any(e['date'] == link['effective_date'] and
                                   price(e['ratio']) == price(link['share_ratio']) for e in events)):
                        reasons.append('CROSS_IDENTITY_LINK_UNBOUND')
                        rows = None
                        break
                rows.append(dict(date=session, close=str(price(closes[session])/factor),
                                 source_security_id=identities[0], true_share_divisor=str(factor)))
        output.append(dict(ticker=ticker, security_id=sid,
            status='BLOCKED' if reasons else 'CONDITIONAL_PRICE_CANDIDATE', reasons=reasons,
            missing_sessions=missing, closes=rows, unit_asof=decision_date,
            basis_id=f'conditional-decision-share:{sid}:{decision_date}',
            cross_identity_link=record.get('cross_identity_link'),
            source_reference=record['source_reference']))
    return dict(schema='ANNUAL_RISK_PRICE_CANDIDATE_V1', decision_date=decision_date,
        count=count, rows=output, executable=False, point_in_time_certified=False,
        availability='NO_HISTORICAL_OBSERVATION_TIMESTAMP; RESEARCH_AVAILABILITY_ASSUMPTION_NOT_YET_BOUND',
        price_rule='NOMINAL_CLOSE_DIVIDED_BY_TRUE_SHARE_EVENTS_AFTER_ROW_THROUGH_DECISION',
        total_return=False)
