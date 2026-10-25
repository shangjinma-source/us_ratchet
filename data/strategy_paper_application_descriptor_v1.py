"""Prospective paper application admission/planning, never registration or writes.

Trusted approval hashes belong to a server-side review configuration. Supplying
a descriptor, or a WEB/fixture release, cannot create a book or accept an order.
"""
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from zoneinfo import ZoneInfo

SCOPE = 'ISOLATED_CURRENT_STRATEGY_PAPER_DECISIONS_AND_MODELED_SETTLEMENT_V1'
SCHEMA = 'CURRENT_STRATEGY_PAPER_APPLICATION_DESCRIPTOR_V1'
LEDGER_SCHEMA = 'CURRENT_STRATEGY_PROSPECTIVE_PAPER_BOOK_V1'
NY = ZoneInfo('America/New_York')


def require(value, reason):
    if not value: raise ValueError(reason)


def stamp(value):
    value = datetime.fromisoformat(value) if type(value) is str else value
    require(isinstance(value, datetime) and value.utcoffset() is not None, 'PAPER_AWARE_TIME_REQUIRED')
    return value.astimezone(timezone.utc)


def document(raw, digest):
    require(type(raw) is bytes and 0 < len(raw) <= 4*1024*1024 and
            type(digest) is str and re.fullmatch('[a-f0-9]{64}', digest) and
            sha256(raw).hexdigest() == digest, 'PAPER_DESCRIPTOR_HASH')
    value = json.loads(raw)
    require(type(value) is dict, 'PAPER_DOCUMENT_REQUIRED')
    return value


def sessions(calendar_bytes, calendar_sha256):
    calendar = document(calendar_bytes, calendar_sha256)
    require(calendar.get('schema') == 'FIXED_EXCHANGE_SESSIONS_V1' and
            calendar.get('exchange') == 'NASDAQ', 'PAPER_CALENDAR_SCOPE')
    rows = calendar.get('sessions')
    require(type(rows) is list and 0 < len(rows) <= 4000, 'PAPER_CALENDAR_DOMAIN')
    result = []; previous = None
    for row in rows:
        opened, closed = stamp(row['open']), stamp(row['close'])
        local = opened.astimezone(NY)
        require(local.date().isoformat() == row['date'] and
                closed.astimezone(NY).date() == local.date() and
                local.time() == time(9,30) and opened < closed and
                (previous is None or previous < opened), 'PAPER_CALENDAR_SESSION')
        start = datetime.combine(local.date(), time(10), NY).astimezone(timezone.utc)
        end = start + timedelta(minutes=1)
        require(opened < start < end < closed, 'PAPER_CALENDAR_DECISION_WINDOW')
        result.append(dict(date=row['date'], open=opened.isoformat(), close=closed.isoformat(),
                           decision_at=start.isoformat(), decision_until=end.isoformat()))
        previous = closed
    return result


def plan_future_start(*, calendar_bytes, calendar_sha256, now, terminal_date):
    """Choose only a genuinely future window; does not register this selection."""
    current = stamp(now)
    rows = sessions(calendar_bytes, calendar_sha256)
    eligible = [r for r in rows if stamp(r['decision_at']) > current and r['date'] <= terminal_date]
    require(eligible, 'PAPER_FUTURE_WINDOW_UNAVAILABLE')
    terminal = [r for r in rows if r['date'] == terminal_date]
    require(len(terminal) == 1 and terminal_date >= eligible[0]['date'], 'PAPER_TERMINAL_SESSION_REQUIRED')
    return dict(schema='PROSPECTIVE_PAPER_WINDOW_PLAN_V1', planned_at=current.isoformat(),
        calendar_sha256=calendar_sha256, first_session=eligible[0], terminal_session=terminal[0],
        registered=False, initialized=False, task_activation_allowed=False)


def classify_window(*, plan, calendar_bytes, now, initialized=False):
    """Phase only: caller must separately validate registration and ledger replay."""
    require(type(initialized) is bool, 'PAPER_INITIALIZED_FLAG')
    rows = sessions(calendar_bytes, plan['calendar_sha256'])
    require(plan['first_session'] in rows and plan['terminal_session'] in rows,
            'PAPER_PLAN_CALENDAR_BINDING')
    first, terminal, current = plan['first_session'], plan['terminal_session'], stamp(now)
    require(current >= stamp(plan['planned_at']), 'PAPER_PLAN_CLOCK_ROLLBACK')
    common = dict(orders_allowed=False, registration_required=True)
    if not initialized:
        if current < stamp(first['decision_at']): status='WAIT_REGISTERED_START'
        elif current < stamp(first['decision_until']): status='FIRST_DECISION_WINDOW'
        else: status='MISSED_REGISTERED_START'
    elif current >= stamp(terminal['close']):
        status='TERMINAL_SETTLEMENT_ONLY'
    else:
        day = current.astimezone(NY).date().isoformat()
        row = next((r for r in rows if r['date'] == day and first['date'] <= day <= terminal['date']), None)
        if row and stamp(row['decision_at']) <= current < stamp(row['decision_until']): status='DAILY_DECISION_WINDOW'
        elif row and current >= stamp(row['close']): status='CLOSED_SESSION_SETTLEMENT_ONLY'
        else: status='NO_NEW_DECISION'
    return dict(common, status=status)


def validate_descriptor(*, descriptor_bytes, trusted_descriptor_sha256, approval_bytes,
                        trusted_approval_sha256, calendar_bytes, code_bytes, source_bytes, now):
    """Validate a separately approved candidate; no execution capability returned."""
    app = document(descriptor_bytes, trusted_descriptor_sha256)
    approval = document(approval_bytes, trusted_approval_sha256)
    require(approval.get('schema') == 'PAPER_APPLICATION_REVIEW_V1' and approval.get('scope') == SCOPE and
            approval.get('descriptor_sha256') == trusted_descriptor_sha256 and approval.get('approved') is True,
            'PAPER_INDEPENDENT_APPROVAL_REQUIRED')
    current = stamp(now)
    require(stamp(approval['reviewed_at']) <= current and
            approval.get('review_role') == 'IMPLEMENTATION_REVIEW_OF_USER_AUTHORIZED_PAPER_SCOPE' and
            type(approval.get('authorization_basis')) is str and approval['authorization_basis'].strip(),
            'PAPER_APPROVAL_TIME_OR_ROLE')
    require(set(app) == {'schema','scope','account_id','simulation_id','genesis','ledger_schema',
            'storage','code_sha256','source_sha256','source_admission','calendar_sha256',
            'policy','plan','activation'}, 'PAPER_DESCRIPTOR_FIELDS')
    require(app['schema'] == SCHEMA and app['scope'] == SCOPE and app['activation'] is False and
            app['ledger_schema'] == LEDGER_SCHEMA, 'PAPER_PROSPECTIVE_SCOPE_REQUIRED')
    for key, prefix in [('account_id','paper-current:'),('simulation_id','paper-study:')]:
        require(type(app[key]) is str and re.fullmatch(prefix+'[a-z0-9][a-z0-9-]{7,63}',app[key]),
                'PAPER_ISOLATED_ID_REQUIRED')
    require(app['genesis'] == dict(currency='USD',cash='20000',shares={},orders={},external_cash_events_allowed=False),
            'PAPER_ZERO_HISTORY_GENESIS_REQUIRED')
    root = 'data/current_strategy_paper/'+app['simulation_id'].split(':')[1]
    expected = dict(ledger=root+'/book.sqlite3',targets=root+'/targets.sqlite3',caps=root+'/caps.sqlite3',
                    evidence=root+'/evidence',registration=root+'/registration.json')
    require(app['storage'] == expected, 'PAPER_STORAGE_NAMESPACE_REQUIRED')
    for field, supplied in [('code_sha256',code_bytes),('source_sha256',source_bytes)]:
        pins = app[field]
        require(type(pins) is dict and 0 < len(pins) <= 2000 and set(pins) == set(supplied), 'PAPER_CLOSURE_DOMAIN')
        for name,digest in pins.items():
            require(type(name) is str and '\\' not in name and ':' not in name and
                    not PurePosixPath(name).is_absolute() and all(v not in ('','.','..') for v in name.split('/')),
                    'PAPER_CLOSURE_PATH')
            require(type(supplied[name]) is bytes and sha256(supplied[name]).hexdigest() == digest,
                    'PAPER_CLOSURE_CHANGED')
        require(sum(map(len,supplied.values())) <= 128*1024*1024, 'PAPER_CLOSURE_BUDGET')
    require('data/strategy_paper_application_descriptor_v1.py' in app['code_sha256'], 'PAPER_DESCRIPTOR_CODE_PIN_REQUIRED')
    executing_root = Path(__file__).resolve().parents[1]
    for name, raw in code_bytes.items():
        target = executing_root/name
        require(all(not p.is_symlink() and not (p.exists() and getattr(p.lstat(),'st_file_attributes',0)&0x400)
                    for p in (target,*target.parents)) and target.is_file() and
                target.stat().st_size == len(raw) and target.read_bytes() == raw,
                'PAPER_EXECUTING_CODE_CHANGED')
    require(app['source_admission'] == dict(scope='PAPER_CURRENT_STRATEGY_SOURCE_REVIEW_V1',
                source_authenticated=False,coverage_complete=False,missing_evidence='WAIT_NO_ORDERS'),
                'PAPER_SOURCE_ADMISSION_SCOPE')
    policy = app['policy']
    require(set(policy) == {'selector_profile','continuous_iterations','daily_rule','entry_rule','fill_model',
                'fee_bps','unfilled_sale_proceeds_available','terminal_settlement'}, 'PAPER_POLICY_FIELDS')
    from data.strategy_continuous32_target_decision import PROFILE_ID
    require(policy['selector_profile'] == PROFILE_ID and type(policy['continuous_iterations']) is int and
            policy['continuous_iterations'] == 32 and policy['daily_rule'] == 'SMA20_STRICT_ABOVE_FULL_ELSE_FLOOR_MONTHLY_HALF' and
            policy['entry_rule'] == 'CURRENT_HALT_AWARE_PULLBACK_AND_SELL_V1' and
            policy['fill_model'] == 'STRICT_CROSS_FULL_FILL_AT_LIMIT' and
            type(policy['fee_bps']) is str and 0 <= Fraction(policy['fee_bps']) <= 10000 and
            policy['unfilled_sale_proceeds_available'] is False and
            policy['terminal_settlement'] == 'AT_OR_AFTER_FINAL_CLOSE_NO_NEW_ORDERS_RECOVERY_REMAINS_AVAILABLE',
            'PAPER_POLICY_MISMATCH')
    plan = app['plan']
    rebuilt = plan_future_start(calendar_bytes=calendar_bytes,calendar_sha256=app['calendar_sha256'],
        now=plan['planned_at'],terminal_date=plan['terminal_session']['date'])
    require(plan == rebuilt and stamp(plan['planned_at']) <= stamp(approval['reviewed_at']) <
            stamp(plan['first_session']['decision_at']), 'PAPER_FUTURE_PLAN_BINDING')
    phase = classify_window(plan=plan,calendar_bytes=calendar_bytes,now=current)
    return dict(status='DESCRIPTOR_REVIEWED_NOT_REGISTERED',descriptor_sha256=trusted_descriptor_sha256,
        approval_sha256=trusted_approval_sha256,application=deepcopy(app),phase=phase,
        future_start_still_available=current < stamp(plan['first_session']['decision_at']),
        registration_allowed=False, execution_integration_verified=False,
        orders_allowed=False,book_creation_allowed=False,real_account_writes=False,task_activation_allowed=False)
