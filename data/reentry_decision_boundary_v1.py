"""Current server intent boundary archive; no history synthesis or account writes.

NOT an HTTP adapter. The builder must inject authenticate_current, which calls
its existing code/source gate after source review and before ANY risk commit.
It supplies SERVER_REVIEWED_REENTRY_INTENT_V1 plus source-authenticated observations and
unchanged account/target/proposal/risk-before snapshots as exact receipt_bytes/files.
The existing reader's post-commit daily archive is deliberately rejected. A caller-supplied trusted=True is never
accepted. Structural checks here do not replace that source authentication.
Configuration/release bytes and the root are fixed by the server builder.
"""
import base64
import json
from pathlib import Path
from hashlib import sha256
from datetime import datetime
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical, require

POLICY='SAVED_FRONTIER_CAP50_EXIT20_V1'
def hashed(raw): return sha256(raw).hexdigest()
def moment(value):
    result=datetime.fromisoformat(value) if isinstance(value,str) else value
    require(isinstance(result,datetime) and result.utcoffset() is not None,'BOUNDARY_AWARE_CLOCK')
    return result

def safe(path):
    require(not path.is_symlink() and all(not p.is_symlink() for p in path.parents),'BOUNDARY_SYMLINK')

class DecisionBoundaryArchive:
    def __init__(self, *, root, source_configuration_bytes, release_bytes, authenticate_current, clock):
        require(callable(authenticate_current) and callable(clock),'BOUNDARY_SERVER_CALLBACK_REQUIRED')
        require(type(source_configuration_bytes) is bytes and type(release_bytes) is bytes,'BOUNDARY_CONFIG_BYTES')
        self.root=Path(root).absolute();self.configuration=source_configuration_bytes
        self.release=release_bytes;self.authenticate_current=authenticate_current;self.clock=clock
        self.config=json.loads(self.configuration);self.policy=json.loads(self.release)
        require(self.policy.get('authorized') is True and self.policy.get('policy_id')==POLICY and self.policy.get('monthly_cap')=='1/2' and self.policy.get('exit_ratio')=='4/5' and self.policy.get('sma20_overlay') is False,'BOUNDARY_RELEASE_POLICY')
    def _check(self, receipt_raw, files, at):
        require(type(receipt_raw) is bytes and type(files) is dict and 0<len(files)<=2000 and all(type(k) is str and type(v) is bytes for k,v in files.items()),'BOUNDARY_EVIDENCE_BYTES')
        require(len(receipt_raw)+sum(map(len,files.values()))<=32*1024*1024,'BOUNDARY_EVIDENCE_BUDGET')
        r=json.loads(receipt_raw);pins=r.get('source_sha256')
        require(r.get('schema')=='SERVER_REVIEWED_REENTRY_INTENT_V1' and r.get('phase')=='PRECOMMIT' and r.get('risk_committed') is False and r.get('policy_id')==POLICY and isinstance(pins,dict) and set(pins)==set(files) and all(hashed(v)==pins[k] for k,v in files.items()),'BOUNDARY_SOURCE_RECEIPT')
        require(moment(r['valid_from'])<=at<moment(r['valid_until']),'BOUNDARY_SOURCE_EXPIRED')
        require(moment(self.policy['authorized_at'])<=at,'BOUNDARY_RELEASE_FUTURE')
        require(files['frontier/release.json']==self.release and r['release_sha256']==hashed(self.release),'BOUNDARY_RELEASE_CHANGED')
        calraw=files['frontier/calendar.json'];require(hashed(calraw)==self.config['calendar']['sha256'],'BOUNDARY_CALENDAR_PIN')
        calendar=json.loads(calraw);require(calendar['schema']=='FIXED_EXCHANGE_SESSIONS_V1' and calendar['exchange']=='NASDAQ','BOUNDARY_CALENDAR_SCHEMA')
        sessions=calendar['sessions'];dates=[x['date'] for x in sessions]
        require(dates==sorted(set(dates)),'BOUNDARY_CALENDAR_ORDER')
        account=json.loads(files['frontier/account.json']);target=json.loads(files['frontier/target.json']);proposal=json.loads(files['frontier/proposal.json'])
        require('frontier/risk-projection.json' not in files and 'frontier/risk-preview.json' not in files,'BOUNDARY_POSTCOMMIT_ARCHIVE_FORBIDDEN')
        observations=json.loads(files['frontier/precommit-observations.json'])
        require(type(observations) is list and bool(observations) and all(type(x) is dict for x in observations),'BOUNDARY_AUTHENTICATED_OBSERVATIONS_REQUIRED')
        observation_dates=[x['session_date'] for x in observations]
        require(observation_dates==sorted(set(observation_dates)),'BOUNDARY_OBSERVATION_ORDER')
        require(all(type(x.get('closes')) is dict and set(x['closes'])==set(x.get('unit_ids',{})) for x in observations),'BOUNDARY_OBSERVATION_UNITS')
        require(r.get('risk_before_sha256')==hashed(files['frontier/risk-before.json']),'BOUNDARY_RISK_BEFORE_BINDING')
        before=json.loads(files['frontier/risk-before.json'])
        require(before is None or before.get('account_id')==r['account_id'],'BOUNDARY_PREVIOUS_RISK_ACCOUNT')
        state=dict(observations[-1],account_id=r['account_id'])
        require(account['account_id']==r['account_id']==state['account_id'] and account['revision']==r['account_revision'] and target['target_id']==r['target_id'] and proposal['proposal_id']==r['proposal_id'],'BOUNDARY_INTENT_BINDING')
        require(target['payload']['account_id']==account['account_id'],'BOUNDARY_TARGET_ACCOUNT')
        completed=[x for x in sessions if moment(x['close'])<=at]
        require(completed and state['session_date']==completed[-1]['date'],'BOUNDARY_CURRENT_COMPLETED_SESSION_REQUIRED')
        row=completed[-1];require(moment(row['close']).astimezone(ZoneInfo('America/New_York')).date().isoformat()==row['date'],'BOUNDARY_SESSION_DATE')
        units=state['unit_ids'];require(type(units) is dict and units and all(type(k) is str and k and type(v) is str and v for k,v in units.items()),'BOUNDARY_UNITS')
        return r,row,units
    def archive_current(self):
        """The timestamp is taken here; no historical decision_at parameter exists."""
        first=self.authenticate_current()
        require(type(first) is dict and set(first)=={'receipt_bytes','files'},'BOUNDARY_SERVER_AUTH_RESULT')
        at=moment(self.clock());receipt,row,units=self._check(first['receipt_bytes'],first['files'],at)
        second=self.authenticate_current()
        require(second==first,'BOUNDARY_CONTEXT_CHANGED')
        end=moment(self.clock());require(at<=end,'BOUNDARY_CLOCK_REVERSED');self._check(first['receipt_bytes'],first['files'],end)
        boundary=canonical(dict(schema='ARCHIVED_ACCOUNT_DECISION_BOUNDARY_V1',account_id=receipt['account_id'],session_date=row['date'],session_close_at=row['close'],decision_at=at.isoformat()))
        envelope=dict(schema='SERVER_CURRENT_REENTRY_BOUNDARY_V1',boundary=base64.b64encode(boundary).decode(),source_configuration=base64.b64encode(self.configuration).decode(),receipt=base64.b64encode(first['receipt_bytes']).decode(),files={k:base64.b64encode(v).decode() for k,v in first['files'].items()},unit_ids=units,archived_at=end.isoformat(),historical_backfill=False,risk_committed=False,phase='PRECOMMIT')
        raw=canonical(envelope);digest=hashed(raw);safe(self.root);self.root.mkdir(parents=True,exist_ok=True);path=self.root/(digest+'.json');safe(path)
        try:
            with path.open('xb') as stream:stream.write(raw);stream.flush();__import__('os').fsync(stream.fileno())
        except FileExistsError:require(path.read_bytes()==raw,'BOUNDARY_EXISTING_BYTES_CHANGED')
        return dict(sha256=digest,account_id=receipt['account_id'],session_date=row['date'],account_revision=receipt['account_revision'],target_id=receipt['target_id'],proposal_id=receipt['proposal_id'],account_mutated=False)
    def read_verified(self, reference):
        if reference is None:return dict(status='WAIT',reason='WAIT_ORIGINAL_DECISION_BOUNDARY_MISSING')
        digest=reference.get('sha256');require(type(digest) is str and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'BOUNDARY_REFERENCE_HASH')
        path=self.root/(digest+'.json');safe(path)
        if not path.is_file():return dict(status='WAIT',reason='WAIT_ORIGINAL_DECISION_BOUNDARY_MISSING')
        require(path.stat().st_size<=48*1024*1024,'BOUNDARY_ARCHIVE_BUDGET');raw=path.read_bytes();require(hashed(raw)==digest,'BOUNDARY_ARCHIVE_CHANGED')
        envelope=json.loads(raw);require(canonical(envelope)==raw and envelope['schema']=='SERVER_CURRENT_REENTRY_BOUNDARY_V1' and envelope['historical_backfill'] is False and envelope.get('risk_committed') is False and envelope.get('phase')=='PRECOMMIT','BOUNDARY_ARCHIVE_SCHEMA')
        decode=lambda value:base64.b64decode(value,validate=True)
        require(decode(envelope['source_configuration'])==self.configuration,'BOUNDARY_SOURCE_CONFIGURATION_CHANGED')
        boundary=decode(envelope['boundary']);b=json.loads(boundary);require(canonical(b)==boundary,'BOUNDARY_CANONICAL')
        receipt,row,units=self._check(decode(envelope['receipt']),{k:decode(v) for k,v in envelope['files'].items()},moment(b['decision_at']))
        require(moment(b['decision_at'])<=moment(envelope['archived_at'])<=moment(self.clock()),'BOUNDARY_ARCHIVE_CLOCK')
        require(set(b)=={'schema','account_id','session_date','session_close_at','decision_at'} and b['schema']=='ARCHIVED_ACCOUNT_DECISION_BOUNDARY_V1' and b['account_id']==receipt['account_id'] and b['session_date']==row['date'] and b['session_close_at']==row['close'] and units==envelope['unit_ids'],'BOUNDARY_ARCHIVE_BINDING')
        for key in ('account_id','account_revision','target_id','proposal_id'):
            require(reference.get(key)==receipt[key],'BOUNDARY_REFERENCE_BINDING')
        require(reference.get('session_date')==b['session_date'],'BOUNDARY_REFERENCE_SESSION')
        return dict(status='SERVER_ARCHIVED_BOUNDARY_VERIFIED',decision_evidence=boundary,decision_evidence_sha256=hashed(boundary),unit_ids=units,account_revision=receipt['account_revision'],target_id=receipt['target_id'],proposal_id=receipt['proposal_id'],source_configuration_sha256=hashed(self.configuration),release_sha256=hashed(self.release),calendar_sha256=hashed(decode(envelope['files']['frontier/calendar.json'])),archive_sha256=digest,account_mutated=False,limitation='Authority depends on server builder authenticated callback at write time; hash is not protection from an attacker replacing both bytes and trusted reference.')
