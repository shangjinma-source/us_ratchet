"""Read-only journal-prefix evidence for an explicitly archived decision boundary.
This verifies ledger history, not broker completeness, price units or decision authority.
"""
from contextlib import closing
from datetime import datetime, date
from hashlib import sha256
import json
from core.strategy_account_ledger import create_account, apply_event, canonical, require


def aware(value):
    require(type(value) is str, 'SESSION_SNAPSHOT_TIME_REQUIRED')
    result = datetime.fromisoformat(value)
    require(result.utcoffset() is not None, 'SESSION_SNAPSHOT_AWARE_TIME_REQUIRED')
    return result


def account_session_snapshot(store, *, account_id, session_date, expected_latest_revision,
                             decision_evidence=None, decision_evidence_sha256=None,
                             security_ids=()):
    """Caller authenticates archived intent authority separately; never infer its time.

    decision_evidence is exact canonical bytes with schema, account_id, session_date,
    session_close_at, decision_at. Identity/unit evidence must be joined separately.
    """
    base = dict(schema='ACCOUNT_SESSION_PREFIX_EVIDENCE_V1', account_id=account_id,
                session_date=session_date, account_mutated=False, units_certified=False,
                broker_history_completeness_certified=False)
    def wait(reason, **fields):
        return dict(base, status='WAIT', reason=reason, **fields)
    require(date.fromisoformat(session_date).isoformat() == session_date, 'SESSION_SNAPSHOT_DATE')
    require(type(expected_latest_revision) is str and bool(expected_latest_revision), 'SESSION_SNAPSHOT_REVISION_REQUIRED')
    require(all(type(sid) is str and bool(sid) for sid in security_ids)
            and len(set(security_ids)) == len(security_ids), 'SESSION_SNAPSHOT_SECURITY_DOMAIN')
    if decision_evidence is None:
        return wait('WAIT_DECISION_BOUNDARY_UNPROVEN')
    require(type(decision_evidence) is bytes and sha256(decision_evidence).hexdigest() == decision_evidence_sha256, 'SESSION_SNAPSHOT_DECISION_HASH')
    evidence = json.loads(decision_evidence)
    require(canonical(evidence) == decision_evidence and set(evidence) == {'schema','account_id','session_date','session_close_at','decision_at'}
            and evidence['schema'] == 'ARCHIVED_ACCOUNT_DECISION_BOUNDARY_V1'
            and evidence['account_id'] == account_id and evidence['session_date'] == session_date, 'SESSION_SNAPSHOT_DECISION_BINDING')
    closed, cutoff = aware(evidence['session_close_at']), aware(evidence['decision_at'])
    current = store.clock()
    require(isinstance(current,datetime) and current.utcoffset() is not None, 'SESSION_SNAPSHOT_CLOCK_REQUIRED')
    require(closed <= cutoff <= current, 'SESSION_SNAPSHOT_BOUNDARY_ORDER')
    from zoneinfo import ZoneInfo
    require(closed.astimezone(ZoneInfo('America/New_York')).date().isoformat() == session_date, 'SESSION_SNAPSHOT_CLOSE_DATE')
    with closing(store._connect(True)) as connection:
        connection.execute('BEGIN')
        try:
            latest, _ = store._read(connection)
            require(latest['account_id'] == account_id, 'SESSION_SNAPSHOT_ACCOUNT')
            require(latest['revision'] == expected_latest_revision, 'SESSION_SNAPSHOT_STALE_REVISION')
            rows = list(connection.execute('SELECT ordinal,event_id,payload,received_at,revision FROM strategy_events ORDER BY ordinal'))
            prefix = create_account(account_id)
            selected, late = [], []
            for ordinal,event_id,payload,received_at,revision in rows:
                event = json.loads(payload); received = aware(received_at)
                if received <= cutoff:
                    prefix, _ = apply_event(prefix,event,expected_revision=prefix['revision'])
                    require(prefix['revision'] == revision, 'SESSION_SNAPSHOT_PREFIX_REVISION')
                    selected.append(dict(ordinal=ordinal,event_id=event_id,payload_sha256=sha256(payload.encode()).hexdigest(),received_at=received_at,revision=revision))
                elif event['kind'] in {'FILL','DIRECT_FILL'} and aware(event['executed_at']) <= cutoff:
                    late.append(dict(ordinal=ordinal,event_id=event_id,executed_at=event['executed_at'],received_at=received_at,payload_sha256=sha256(payload.encode()).hexdigest()))
            boundary = dict(account_id=account_id,session_date=session_date,decision_evidence_sha256=decision_evidence_sha256,
                            decision_at=evidence['decision_at'],session_close_at=evidence['session_close_at'],
                            prefix_revision=prefix['revision'],events=selected,late_fills=late)
            boundary_hash = sha256(canonical(boundary)).hexdigest()
            if late:
                return wait('WAIT_LATE_RECORDED_FILL_RECONCILIATION',event_boundary_sha256=boundary_hash,late_fills=late)
            if not selected:
                return wait('WAIT_ACCOUNT_PREFIX_UNPROVEN',event_boundary_sha256=boundary_hash)
            shares = dict(prefix['shares'])
            for sid in security_ids:shares.setdefault(sid,0)
            result = dict(base,status='JOURNAL_PREFIX_VERIFIED_UNITS_NOT_CERTIFIED',decision_at=evidence['decision_at'],
                          session_close_at=evidence['session_close_at'],account_revision=prefix['revision'],
                          latest_revision=latest['revision'],last_ordinal=selected[-1]['ordinal'],shares=shares,
                          events=selected,event_boundary_sha256=boundary_hash,decision_evidence_sha256=decision_evidence_sha256,
                          decision_authority_verified=False,limitation='Authenticated caller must bind original intent and calendar/units; no invented historical decision cutoff.')
            # Latest revision is a read-time concurrency check, not historical evidence.
            stable_evidence = {key: value for key, value in result.items() if key != 'latest_revision'}
            result['evidence_sha256'] = sha256(canonical(stable_evidence)).hexdigest()
            return result
        finally:
            connection.rollback()
