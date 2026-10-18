"""Read-only pinned-byte adapter. Calendar/identity/unit admissions are conditional,
not external-source authenticity or complete corporate-action certification.
"""
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from data.current_research_saved_quote import read_saved_quote
from data.current_research_intraday_performance import compute_intraday_paper_performance, _time, ledger_observation_floor
from data.current_research_intraday_continuation_ledger import review_continuation_ledger


def review_saved_intraday_performance(state, *, root, sources, source_hashes,
                                      calendar_path, session_date, now):
    """Server-owned sources by SID: ticker, expected_security_type, entry,
    relative_directory, continuity{status,from_date,to_date,source_references},
    reviewed_at. Calendar: REVIEWED_OFFICIAL_SESSION_CALENDAR with pinned refs.
    Missing/invalid evidence returns INCOMPLETE; never substitutes another day.
    Only current state at a close after all recorded events is supported.
    """
    state = review_continuation_ledger(state)
    baseline = compute_intraday_paper_performance(state, now=now)
    try:
        def require(ok, message):
            if not ok: raise ValueError(message)
        root = Path(root).resolve()
        def read(name):
            require(isinstance(name,str) and '\\' not in name, 'INVALID_SOURCE_PATH')
            path = Path(name)
            require(not path.is_absolute() and not path.drive and '..' not in path.parts, 'SOURCE_OUTSIDE_ROOT')
            full = (root/path).resolve()
            require(full.is_relative_to(root) and full.stat().st_size <= 32*1024*1024, 'SOURCE_OUTSIDE_ROOT_OR_TOO_LARGE')
            raw = full.read_bytes()
            require(hashlib.sha256(raw).hexdigest() == source_hashes[name], 'SOURCE_HASH_MISMATCH')
            return raw
        require(isinstance(source_hashes,dict) and bool(source_hashes), 'SOURCE_PINS_REQUIRED')
        for name in source_hashes: read(name)
        def refs(items):
            require(isinstance(items,list) and bool(items) and all(isinstance(x,str) and x in source_hashes for x in items), 'EVIDENCE_UNPINNED')
        calendar = json.loads(read(calendar_path))
        require(calendar.get('status') == 'REVIEWED_OFFICIAL_SESSION_CALENDAR', 'CALENDAR_NOT_REVIEWED')
        refs(calendar['source_references'])
        session = calendar['sessions'][session_date]
        opening, close = (_time(session[k]) for k in ('open_at','close_at'))
        ny = ZoneInfo('America/New_York')
        require(session.get('timezone') == 'America/New_York' and opening < close <= _time(now)
                and all(t.astimezone(ny).date().isoformat() == session_date for t in (opening,close)), 'SESSION_NOT_COMPLETED')
        require(ledger_observation_floor(state) <= close, 'CURRENT_STATE_AFTER_CLOSE')
        security = state['acceptance']['proposal']['security']
        start = _time(state['acceptance']['accepted_at']).astimezone(ny).date().isoformat()
        marks = {}
        for sid, quantity in state['shares'].items():
            if not quantity: continue
            row = sources[sid]
            require(sid == security['security_id'] and row['ticker'] == security['ticker'], 'SECURITY_IDENTITY_MISMATCH')
            declaration = row['continuity']
            require(declaration.get('status') == 'NO_UNPROCESSED_ACTIONS'
                    and declaration.get('from_date') == start and declaration.get('to_date') == session_date
                    and declaration.get('price_basis') == 'NOMINAL_PER_CURRENT_SHARE', 'UNIT_CONTINUITY_UNAVAILABLE')
            refs(declaration['source_references'])
            decoded = read_saved_quote(root=root,ticker=row['ticker'],expected_security_type=row['expected_security_type'],
                entry=row['entry'],relative_directory=row['relative_directory'],decision_date=session_date,
                decision_session_close_at=session['close_at'])
            require(all(source_hashes.get(k) == v for k,v in decoded['source_hashes'].items()), 'QUOTE_PINS_NOT_ADMITTED')
            require(close <= _time(decoded['received_at']) <= _time(row['reviewed_at']) <= _time(now), 'CAPTURE_OR_REVIEW_TIME_INVALID')
            require(not any(start <= e['session'] <= session_date for e in decoded['event_details']), 'EXPOSED_ACTION_UNSUPPORTED')
            marks[sid] = dict(security_id=sid,price=decoded['ohlc']['close'],observed_at=session['close_at'],
                received_at=decoded['received_at'],price_basis='NOMINAL_PER_CURRENT_SHARE',
                unit_continuity='NO_UNPROCESSED_ACTIONS',source_references=list(decoded['source_hashes']))
        result = compute_intraday_paper_performance(state,now=now,marks=marks,source_hashes=source_hashes,
            valuation_kind='COMPLETED_SESSION_CLOSE')
        result.update(source_bytes_verified=True,source_hashes=dict(source_hashes),valuation_session=session_date,
            valuation_at=close.isoformat(),source_authenticated=False,complete_corporate_actions_verified=False)
        result['limitations'].append('Nominal-unit continuity is a pinned conditional admission, not action-completeness certification.')
        return result
    except (OSError,KeyError,TypeError,ValueError,ArithmeticError) as exc:
        baseline.update(status='INCOMPLETE',equity=None,total_return=None,net_pnl=None,performance_available=False,
                        issues=[dict(reason=str(exc))])
        return baseline
