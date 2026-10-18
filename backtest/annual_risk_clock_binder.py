"""Bind a declared daily research clock, never historical vendor receipt evidence."""
from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from backtest.annual_risk_history_candidates import day, price
from backtest.current_quantity_v2_risk_overlays import UNIT_SCHEMA

BASIS = 'ASSUMED_CLOSE_AVAILABLE_FOR_NEXT_OPEN_RESEARCH'


def bind_snapshot(*, candidate, schedule, expected_identities, assumption, review_reference):
    if assumption.get('timestamp_basis') != BASIS or not review_reference:
        raise ValueError('FIXED_AVAILABILITY_ASSUMPTION_REQUIRED')
    if candidate.get('schema') != 'ANNUAL_RISK_PRICE_CANDIDATE_V1' or candidate['count'] != 21:
        raise ValueError('REVIEWED_21_PRICE_CANDIDATE_REQUIRED')
    calendar = schedule['session_dates']
    if calendar != sorted(set(calendar)) or set(calendar) != set(schedule['closes']):
        raise ValueError('EXACT_OFFICIAL_CALENDAR_REQUIRED')
    clocks = {}
    for session in calendar:
        day(session)
        stamp = datetime.fromisoformat(schedule['closes'][session])
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError('AWARE_OFFICIAL_CLOSE_REQUIRED')
        ny = stamp.astimezone(ZoneInfo('America/New_York'))
        if ny.date().isoformat() != session or stamp.utcoffset() != ny.utcoffset():
            raise ValueError('OFFICIAL_CLOSE_DATE_OFFSET_MISMATCH')
        clocks[session] = stamp
    decision = day(candidate['decision_date'])
    if decision not in calendar or calendar.index(decision) < 20:
        raise ValueError('OFFICIAL_WINDOW_INCOMPLETE')
    expected = calendar[calendar.index(decision)-20:calendar.index(decision)+1]
    rows = candidate['rows']
    tickers = [row['ticker'] for row in rows]
    if len(tickers) != len(set(tickers)) or set(tickers) != set(expected_identities):
        raise ValueError('EXACT_OBSERVED_DOMAIN_REQUIRED')
    histories, blocked, used = {}, [], set()
    for row in rows:
        sid = row['security_id']
        if sid != expected_identities[row['ticker']]:
            raise ValueError('DECISION_IDENTITY_MISMATCH')
        if sid is not None:
            if sid in used:
                raise ValueError('DUPLICATE_SECURITY_ID')
            used.add(sid)
        if row['status'] == 'BLOCKED':
            if row['closes'] is not None or not row['reasons']:
                raise ValueError('INVALID_BLOCKED_ROW')
            blocked.append(deepcopy(row))
            continue
        if row['status'] != 'CONDITIONAL_PRICE_CANDIDATE' or sid is None or row['reasons']:
            raise ValueError('INVALID_READY_ROW')
        if row['unit_asof'] != decision or not row['basis_id'] or not row['source_reference']:
            raise ValueError('DECISION_UNIT_MISMATCH')
        if [item['date'] for item in row['closes']] != expected:
            raise ValueError('EXACT_OFFICIAL_WINDOW_REQUIRED')
        prices = []
        for item in row['closes']:
            session = item['date']
            if item['source_security_id'] != sid:
                link = row.get('cross_identity_link')
                if (not isinstance(link,dict) or link.get('from_security_id') != item['source_security_id']
                    or link.get('to_security_id') != sid or not link.get('source_reference')
                    or not session < day(link['effective_date']) <= decision):
                    raise ValueError('CROSS_IDENTITY_LINK_UNBOUND')
            prices.append(dict(date=session,close=str(price(item['close'])),
                completed_at=schedule['closes'][session],timestamp_basis=BASIS))
        histories[sid] = dict(units=dict(schema=UNIT_SCHEMA,unit_asof=decision,currency='USD',
            basis_id=row['basis_id'],review_reference=review_reference),
            source_reference=row['source_reference'],closes=prices,
            timestamp_basis=BASIS,cross_identity_link=deepcopy(row.get('cross_identity_link')))
    observed = clocks[decision] + timedelta(minutes=1)
    if observed.astimezone(ZoneInfo('America/New_York')).date().isoformat() != decision:
        raise ValueError('ASSUMED_OBSERVATION_OUTSIDE_SESSION_DATE')
    return dict(observed_at=observed.isoformat(),review_reference=review_reference,
        histories=histories,blocked_rows=blocked,timestamp_basis=BASIS,
        historical_receipt_verified=False,point_in_time_certified=False,
        selection_eligibility='UNMODIFIED_253_SESSION_SELECTION_GUARD_REQUIRED',
        full_domain_executable=False,production_adopted=False)
