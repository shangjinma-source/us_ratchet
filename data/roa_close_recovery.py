"""Read-only late-fill close replay. No journal writes or inferred executions."""
from copy import deepcopy
from datetime import datetime
from threading import RLock
from core.strategy_account_ledger import replay, require
from data.roa_execution_lifecycle import RoaExecutionLifecycle, digest


def instant(value):
    result=datetime.fromisoformat(value)
    require(result.utcoffset() is not None,'AWARE_RECOVERY_TIME_REQUIRED')
    return result


def holdings_at(account, at):
    """Trusted store.read state; full replay also rejects unsupported share actions."""
    rebuilt=replay(account['account_id'],[r['payload'] for r in account['events']])
    require(rebuilt==account,'RECOVERY_ACCOUNT_REPLAY_MISMATCH')
    held=deepcopy(account['shares'])
    fills=[]
    for ordinal,row in enumerate(account['events']):
        payload=row['payload']
        if payload['kind'] not in ('FILL','DIRECT_FILL'):continue
        if payload['kind']=='FILL':
            order=account['orders'][payload['order_id']]
            sid,side=order['security_id'],order['side']
        else:sid,side=payload['security_id'],payload['side']
        fills.append((instant(payload['executed_at']),ordinal,sid,side,payload['quantity']))
    for executed,ordinal,sid,side,quantity in sorted(fills,reverse=True):
        if executed<=instant(at):continue
        held[sid]=held.get(sid,0)+(-quantity if side=='BUY' else quantity)
        require(held[sid]>=0,'RECOVERY_EXECUTION_ORDER_INCONSISTENT')
    return {sid:q for sid,q in held.items() if q}


class MemoryLifecycle(RoaExecutionLifecycle):
    def __init__(self,state):self.state=deepcopy(state);self.lock=RLock()
    def read(self):return deepcopy(self.state)
    def _save(self,state):
        self.state=deepcopy(state);self.state['version']+=1;return self.read()


def recover_closes(*, checkpoint, current_lifecycle, account, sessions, calendar, now):
    """Return reviewable replacement; caller must compare-and-swap bound versions.

    checkpoint is a trusted saved PRE-observation lifecycle, not fabricated from
    today's peaks. sessions are contiguous authoritative completed closes carrying
    validated nominal prices. No materialized OPEN after checkpoint is supported.
    """
    for key in ('account_id','strategy_epoch','contract_sha256'):
        require(checkpoint[key]==current_lifecycle[key],'RECOVERY_SCOPE_MISMATCH')
    require(account['account_id']==checkpoint['account_id'],'RECOVERY_ACCOUNT_SCOPE')
    require(bool(sessions),'RECOVERY_SESSIONS_REQUIRED')
    for row in account['events']:
        if row['payload']['kind'] in ('FILL','DIRECT_FILL'):
            require(instant(row['payload']['executed_at'])<=instant(now),'RECOVERY_FUTURE_EXECUTION')
    original={e['event_id']:e for e in checkpoint['events']}
    for event in current_lifecycle['events']:
        if event.get('materialized_revision'):
            require(event['event_id'] in original and event==original[event['event_id']],
                    'RECOVERY_CROSSES_MATERIALIZED_OPEN')
    for event_id,event in original.items():
        current=next((e for e in current_lifecycle['events'] if e['event_id']==event_id),None)
        require(current is not None,'RECOVERY_EVENT_REMOVED')
        # completed_sids is observational and will be replayed, all other fields frozen.
        require({k:v for k,v in current.items() if k!='completed_sids'}==
                {k:v for k,v in event.items() if k!='completed_sids'},'RECOVERY_EVENT_CHANGED')
    state=deepcopy(checkpoint)
    state['events']+= [deepcopy(e) for e in current_lifecycle['events'] if e['event_id'] not in original]
    for event in state['events']:
        if event['event_id'] not in original:event.pop('completed_sids',None)
    lifecycle=MemoryLifecycle(state);observations=[];previous=checkpoint.get('last_close')
    for item in sessions:
        day=item['session'];times=calendar(day)
        require(previous is None or times['previous_session']==previous,'RECOVERY_CLOSE_GAP')
        require(instant(times['close_at'])<=instant(now),'RECOVERY_FUTURE_CLOSE')
        if previous is None:
            require(all(e['session']>=day for e in checkpoint['events']),'RECOVERY_CHECKPOINT_TOO_LATE')
        shares=holdings_at(account,times['close_at'])
        require(set(shares)<=set(item['prices']),'RECOVERY_CLOSE_PRICES_MISSING')
        lifecycle.close_observation(session=day,shares=shares,closing_prices=item['prices'])
        observations.append(dict(session=day,shares=shares,price_digest=digest(item['prices'])))
        previous=day
    require(previous>=(current_lifecycle.get('last_close') or previous),'RECOVERY_CANNOT_ROLL_BACK')
    return dict(status='RECOVERY_PROPOSAL_NOT_APPLIED',account_revision=account['revision'],
        prior_lifecycle_digest=digest(current_lifecycle),checkpoint_digest=digest(checkpoint),
        recovered_state=lifecycle.read(),observations=observations,
        limitation='Trusted calendar and nominal close evidence required; no account/cash writes; CAS and source revalidation required before apply.')

class TrustedCloseRecovery:
    """Server-owned wrapper, deliberately no HTTP route or client path arguments.

    price_reader(session, shares) returns prices and source_hashes for verified
    nominal closes. calendar_sessions is the trusted complete session sequence.
    A single call replaces the existing maintenance close-observation call.
    """
    def __init__(self, *, account_store, lifecycle, directory, evidence_root,
                 calendar, calendar_sessions, price_reader, clock):
        from pathlib import Path
        self.store=account_store;self.lifecycle=lifecycle
        self.directory=Path(directory).resolve();self.root=Path(evidence_root).resolve()
        self.calendar=calendar;self.sessions=list(calendar_sessions)
        require(self.sessions==sorted(set(self.sessions)),'RECOVERY_CALENDAR_INVALID')
        self.price_reader=price_reader;self.clock=clock

    def _write(self,path,document):
        import json
        require(not path.is_symlink() and not path.with_suffix('.new').is_symlink(),'RECOVERY_SYMLINK')
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.new')
        temporary.write_text(json.dumps({'document':document,'sha256':digest(document)},sort_keys=True),encoding='utf8')
        temporary.replace(path)

    def _read(self,path):
        import json
        require(not path.is_symlink(),'RECOVERY_SYMLINK')
        envelope=json.loads(path.read_text(encoding='utf8'))
        require(digest(envelope['document'])==envelope['sha256'],'RECOVERY_CHECKPOINT_HASH')
        return envelope['document']

    def _verify_prices(self,capture):
        from hashlib import sha256
        require(bool(capture.get('source_hashes')),'RECOVERY_PRICE_EVIDENCE_REQUIRED')
        for name,expected in capture['source_hashes'].items():
            path=(self.root/name).resolve()
            require(path.is_relative_to(self.root) and not path.is_symlink(),'RECOVERY_EVIDENCE_PATH')
            require(sha256(path.read_bytes()).hexdigest()==expected,'RECOVERY_PRICE_SOURCE_CHANGED')

    def observe(self,session):
        from contextlib import closing
        require(session in self.sessions,'RECOVERY_UNKNOWN_SESSION')
        now=self.clock().isoformat()
        require(instant(self.calendar(session)['close_at'])<=instant(now),'RECOVERY_FUTURE_CLOSE')
        checkpoint_path=self.directory/(session+'.checkpoint.json')
        audit_path=self.directory/(session+'.recovery.json')
        # SQLite RESERVED lock excludes concurrent journal appends across processes.
        # Lifecycle lock is shared with the one authoritative in-process service.
        with self.lifecycle.lock, closing(self.store._connect(False)) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                account=self.store._read(connection)[0];current=self.lifecycle.read()
                if audit_path.exists():
                    audit=self._read(audit_path)
                    if audit['account_revision']==account['revision'] and audit['applied_state_digest']==digest(current):
                        return dict(status='UNCHANGED',account_revision=account['revision'],state=current)
                    if current.get('last_close')==session and holdings_at(account,self.calendar(session)['close_at'])==current.get('close_shares',{}):
                        return dict(status='UNCHANGED_CLOSE_HOLDINGS',account_revision=account['revision'],state=current)
                if not checkpoint_path.exists():
                    require((current.get('last_close') or '')<session,'RECOVERY_CHECKPOINT_UNAVAILABLE')
                    self._write(checkpoint_path,dict(checkpoint=current,account_revision=account['revision'],created_at=now))
                saved=self._read(checkpoint_path);checkpoint=saved['checkpoint']
            finally:connection.rollback()
        # Network/source work does not hold journal write reservation.
        start=checkpoint.get('last_close')
        days=[d for d in self.sessions if (start is None and d==session or start is not None and start<d<=session)]
        captures=[];rows=[]
        for day in days:
            shares=holdings_at(account,self.calendar(day)['close_at'])
            capture=self.price_reader(day,shares);self._verify_prices(capture)
            captures.append(capture);rows.append(dict(session=day,prices=capture['prices']))
        proposal=recover_closes(checkpoint=checkpoint,current_lifecycle=current,account=account,
            sessions=rows,calendar=self.calendar,now=now)
        # A late fill earlier than this checkpoint needs an earlier saved checkpoint.
        if start is not None:
            previous_shares=holdings_at(account,self.calendar(start)['close_at'])
            require(previous_shares==checkpoint.get('close_shares',{}),'RECOVERY_EARLIER_CHECKPOINT_REQUIRED')
        with self.lifecycle.lock, closing(self.store._connect(False)) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                latest=self.store._read(connection)[0]
                require(latest['revision']==proposal['account_revision'],'RECOVERY_ACCOUNT_CHANGED')
                require(digest(self.lifecycle.read())==proposal['prior_lifecycle_digest'],'RECOVERY_LIFECYCLE_CHANGED')
                for capture in captures:self._verify_prices(capture)
                replacement=proposal['recovered_state'];replacement['version']=current['version']
                intended=deepcopy(replacement);intended['version']+=1
                audit=dict(account_revision=latest['revision'],prior_lifecycle_digest=digest(current),
                    applied_state_digest=digest(intended),checkpoint_digest=digest(checkpoint),
                    observations=proposal['observations'],evidence=[c['source_hashes'] for c in captures])
                # Write-ahead evidence remains valid if process stops before/after replace.
                self._write(audit_path,audit)
                applied=self.lifecycle._save(replacement)
                require(digest(applied)==audit['applied_state_digest'],'RECOVERY_APPLY_MISMATCH')
                return dict(status='RECOVERED',account_revision=latest['revision'],state=applied)
            finally:connection.rollback()
