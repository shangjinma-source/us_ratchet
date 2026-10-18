"""Read-only initial-cash intraday proposal. Never a DAY order or ledger plan."""
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json
import math
import re
from zoneinfo import ZoneInfo
from data.current_research_intraday_journal import IntradayObservationJournal
from data.current_research_intraday_review import review_intraday_session
from data.current_research_intraday_execution import TOP1_METHOD, TOP1_VERSION

SCHEMA = 'INTRADAY_INITIAL_CASH_BUY_PROPOSAL_V1'


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _time(value):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    _require(isinstance(value, datetime) and value.tzinfo is not None, 'AWARE_TIME_REQUIRED')
    return value


def _cash(value):
    _require(not isinstance(value, bool) and isinstance(value, (str, int, Fraction)), 'EXACT_CASH_REQUIRED')
    value = Fraction(str(value))
    _require(value >= 0, 'NEGATIVE_CASH')
    return value


def build_intraday_initial_buy_proposal(*, journal_root, session, event_path, expected_event_hashes,
        research_snapshot, available_cash, shares, reserved_cash, open_orders,
        account_id, account_revision, expected_revision, market_session, source_hashes, now, journal=None):
    """Server-owned paths/pins and snapshot only; reads saved evidence, never writes.

    Hashes establish local byte consistency, not source truth or trusted time.
    Acceptance deadline is NOT an order expiry or a fill-time constraint.
    """
    flags = dict(research_only=True, execution_blocked=True, adopted=False,
                 legacy_ledger_compatible=False, source_authenticated=False,
                 account_mutated=False, order_lifecycle='UNACTIVATED', schema=SCHEMA)
    try:
        now = _time(now)
        _require(market_session['date']==session and market_session['timezone']=='America/New_York', 'SESSION_BINDING_MISMATCH')
        opening=_time(market_session['open_at']); closing=_time(market_session['close_at'])
        _require(opening <= now < closing and opening.astimezone(ZoneInfo('America/New_York')).date().isoformat()==session and closing.astimezone(ZoneInfo('America/New_York')).date().isoformat()==session, 'OUTSIDE_DECLARED_REGULAR_SESSION')
        refs=market_session['source_references']
        _require(isinstance(refs,list) and refs and all(p in source_hashes and re.fullmatch('[0-9a-f]{64}',source_hashes[p]) for p in refs), 'SESSION_SOURCE_NOT_PINNED')
        _require(isinstance(account_id, str) and bool(account_id.strip()), 'ACCOUNT_ID_REQUIRED')
        _require(isinstance(account_revision, str) and bool(account_revision.strip())
                 and account_revision == expected_revision, 'ACCOUNT_REVISION_MISMATCH')
        _require(isinstance(shares, dict) and all(isinstance(s, str) and type(q) is int and q >= 0 for s,q in shares.items()), 'INVALID_SHARES')
        _require(not any(shares.values()) and _cash(reserved_cash) == 0
                 and isinstance(open_orders, list) and not open_orders, 'INITIAL_UNENCUMBERED_CASH_ONLY')
        snap = research_snapshot
        _require(snap.get('method') == TOP1_METHOD and snap.get('research_version') == TOP1_VERSION
                 and snap.get('research_only') is True and snap.get('execution_blocked') is True, 'TOP1_RESEARCH_REQUIRED')
        _require(re.fullmatch('[0-9a-f]{24}', snap['research_id']) is not None, 'INVALID_RESEARCH_ID')
        cash = _cash(available_cash); budget = snap['budget_identity_exact']
        _require(cash > 0 and cash == _cash(budget['entered_cash'])
                 and _cash(budget['fees']) == 0
                 and _cash(budget['stock_notional']) + _cash(budget['residual_cash']) == cash, 'BUDGET_BINDING_MISMATCH')
        display_budget = snap['budget']
        _require(type(display_budget) in (int, float) and math.isfinite(display_budget)
                 and display_budget == float(cash), 'DISPLAY_BUDGET_MISMATCH')
        _require(isinstance(expected_event_hashes, dict) and event_path in expected_event_hashes
                 and all(isinstance(h,str) and re.fullmatch('[0-9a-f]{64}',h) for h in expected_event_hashes.values()), 'EXPLICIT_EVENT_RECEIPT_REQUIRED')
        report = review_intraday_session(journal_root, session, expected_event_hashes=expected_event_hashes, journal=journal)
        _require(not report['missing_receipts'], 'MISSING_EXPECTED_EVENT_RECEIPT')
        records = [r for r in report['records'] if r['path'] == event_path]
        _require(len(records)==1 and not records[0]['issues'], 'OBSERVATION_REVIEW_FAILED')
        record = records[0]
        journal = IntradayObservationJournal(journal_root) if journal is None else journal
        event = journal.read_event(event_path, expected_sha256=expected_event_hashes[event_path])
        _require(event['research_id'] == snap['research_id'], 'RESEARCH_ID_MISMATCH')
        for key in ('research_version','method','as_of','budget_identity_exact','selected_security','stocks','sources'):
            _require(event['research_binding'].get(key) == snap.get(key), 'RESEARCH_BINDING_MISMATCH:'+key)
        selected = snap['selected_security']
        _require(selected['security_id'] == snap['selected_ranking_security_id'], 'SELECTED_SECURITY_MISMATCH')
        rows = record['observations']
        _require(len(rows)==1 and rows[0]['status']=='AVAILABLE' and rows[0].get('raw_replay_verified'), 'NO_AVAILABLE_REPLAYED_REFERENCE')
        row = rows[0]
        _require(row['ticker']==selected['ticker'], 'TICKER_MISMATCH')
        finished = _time(event['request_finished_at']); deadline = _time(row['refresh_by'])
        _require(_time(row['checked_at']) <= finished <= now < deadline <= closing
                 and now.astimezone(ZoneInfo('America/New_York')).date().isoformat()==session, 'REFERENCE_NOT_CURRENTLY_ACCEPTABLE')
        # Do not revive a superseded same-scope reference or a prior process boot.
        for other in report['records']:
            if other.get('event_id') == event['event_id']: continue
            _require(not other['issues'], 'SESSION_HAS_UNREVIEWABLE_EVIDENCE')
            saved = journal.read_event(other['path'], expected_sha256=other['event_sha256'])
            if _time(saved['request_finished_at']) < finished: continue
            supersedes = saved['process_boot_id'] != event['process_boot_id'] or (
                saved['research_id']==event['research_id'] and saved['observation_sequence']>event['observation_sequence'])
            _require(not supersedes, 'REFERENCE_SUPERSEDED')
        limit = Fraction(row['limit_price']); quantity = int(cash//limit)
        _require(limit>0 and limit*100 == int(limit*100), 'INVALID_CENT_CAP')
        causal = dict(schema=SCHEMA, research_snapshot=deepcopy(snap), account_id=account_id,
            account_revision=account_revision, expected_revision=expected_revision,
            available_cash=str(cash), shares=deepcopy(shares), reserved_cash=str(_cash(reserved_cash)), open_orders=[],
            session=session, market_session=deepcopy(market_session), source_hashes=deepcopy(source_hashes), proposal_created_at=now.isoformat(), proposed_at=now.isoformat(), reference_valid_until=deadline.isoformat(),
            event_path=event_path, event_sha256=expected_event_hashes[event_path],
            reviewed_event_hashes={r['path']:r['event_sha256'] for r in report['records']},
            observation=deepcopy(row), security=deepcopy(selected), quantity=quantity,
            limit_price=str(limit), fee_scope=dict(commission='0', other_fees='UNKNOWN_NOT_RESERVED'))
        identifier = sha256(json.dumps(causal,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        return dict(flags,status='READY',proposal_id=identifier,causal_inputs=causal,
            research_id=snap['research_id'],account_revision=account_revision,
            accept_before=deadline.isoformat(),reference_valid_until=deadline.isoformat(),
            proposal_created_at=now.isoformat(),market_session=deepcopy(market_session),proposed_at=now.isoformat(),security=deepcopy(selected),side='BUY',quantity=quantity,
            limit_price=str(limit),notional=str(quantity*limit),residual_cash=str(cash-quantity*limit),
            action='PROPOSE_BUY' if quantity else 'NO_AFFORDABLE_WHOLE_SHARE',time_in_force=None,
            limitations=['Acceptance deadline does not cancel an order; no order has been activated.',
                'Not compatible with the existing daily-close paper ledger; no fill or return is inferred.',
                'Local event hashes do not authenticate external source identity, units or timestamps.'])
    except (ValueError,KeyError,TypeError,ZeroDivisionError,OSError) as error:
        return dict(flags,status='BLOCKED',reason=str(error),proposal_id=None)
