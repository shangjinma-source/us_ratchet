"""Boundary archive integration using an isolated real account journal.
The source-authentication callback is an explicitly synthetic server fixture.
"""
import json,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from core.strategy_account_store import StrategyAccountStore
from core.strategy_account_ledger import canonical
from data.reentry_decision_boundary_v1 import DecisionBoundaryArchive
from data.strategy_account_session_snapshot_v1 import account_session_snapshot

def digest(raw):return sha256(raw).hexdigest()
class BoundaryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.now=datetime(2026,10,28,19,tzinfo=timezone.utc);self.store=StrategyAccountStore(self.root/'account.sqlite',clock=lambda:self.now)
  self.state=self.store.initialize('synthetic',operation_id='init')
  self.append('CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED')
  self.append('DIRECT_FILL',security_id='A',side='BUY',quantity=4,price='100',fees='0',executed_at=self.now.isoformat())
  self.now=datetime(2026,10,29,14,tzinfo=timezone.utc)
  self.release=canonical(dict(authorized=True,authorized_at='2026-10-28T12:00:00Z',policy_id='SAVED_FRONTIER_CAP50_EXIT20_V1',monthly_cap='1/2',exit_ratio='4/5',sma20_overlay=False))
  calendar=canonical(dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=[dict(date=d,open=d+'T13:30:00Z',close=d+'T20:00:00Z') for d in ['2026-10-28','2026-10-29']]))
  self.config=canonical(dict(calendar=dict(path='calendar.json',sha256=digest(calendar))))
  self.files={'frontier/release.json':self.release,'frontier/calendar.json':calendar,'frontier/account.json':canonical(self.state),'frontier/target.json':canonical(dict(target_id='target',payload=dict(account_id='synthetic'))),'frontier/proposal.json':canonical(dict(proposal_id='proposal')),'frontier/risk-before.json':canonical(None),'frontier/precommit-observations.json':canonical([dict(session_date='2026-10-28',decision_date='2026-10-28',closes={'A':'100'},unit_ids={'A':'unitA'})])}
  self.receipt=dict(schema='SERVER_REVIEWED_REENTRY_INTENT_V1',phase='PRECOMMIT',risk_committed=False,risk_before_sha256=digest(canonical(None)),policy_id='SAVED_FRONTIER_CAP50_EXIT20_V1',account_id='synthetic',account_revision=self.state['revision'],target_id='target',proposal_id='proposal',valid_from='2026-10-29T13:59:00Z',valid_until='2026-10-29T20:00:00Z',release_sha256=digest(self.release))
  self.calls=0
  def authenticate():
   self.calls+=1
   # No boolean from client: fixture owns actual journal and exact evidence bytes.
   self.assertEqual(self.store.read(),self.state)
   return dict(receipt_bytes=canonical(dict(self.receipt,source_sha256={k:digest(v) for k,v in self.files.items()})),files=deepcopy(self.files))
  self.archive=DecisionBoundaryArchive(root=self.root/'archive',source_configuration_bytes=self.config,release_bytes=self.release,authenticate_current=authenticate,clock=lambda:self.now)
 def append(self,kind,**kwargs):self.state,_=self.store.append(dict(kind=kind,event_id='e'+str(len(self.state['events'])),**kwargs),expected_revision=self.state['revision'])
 def test_current_decision_separate_from_close_real_snapshot_no_account_write(self):
  before=(self.root/'account.sqlite').read_bytes();ref=self.archive.archive_current();verified=self.archive.read_verified(ref)
  b=json.loads(verified['decision_evidence']);self.assertEqual(b['decision_at'],'2026-10-29T14:00:00+00:00');self.assertEqual(b['session_close_at'],'2026-10-28T20:00:00Z')
  snapshot=account_session_snapshot(self.store,account_id='synthetic',session_date=b['session_date'],expected_latest_revision=self.state['revision'],decision_evidence=verified['decision_evidence'],decision_evidence_sha256=verified['decision_evidence_sha256'],security_ids=['A'])
  self.assertEqual(snapshot['shares'],{'A':4});self.assertEqual(verified['unit_ids'],{'A':'unitA'});self.assertEqual(verified['observation']['closes'],{'A':'100'});self.assertEqual(self.calls,2);self.assertEqual((self.root/'account.sqlite').read_bytes(),before)
  self.assertEqual(self.archive.archive_current(),ref)
 def test_missing_intent_not_backfilled(self):
  self.assertEqual(self.archive.read_verified(None)['reason'],'WAIT_ORIGINAL_DECISION_BOUNDARY_MISSING');self.assertEqual(self.calls,0)
  self.assertFalse((self.root/'archive').exists())
 def test_boolean_not_authority_and_changed_context_rejected(self):
  self.archive.authenticate_current=lambda:dict(trusted=True)
  with self.assertRaisesRegex(ValueError,'AUTH_RESULT'):self.archive.archive_current()
  counter=[0]
  def changing():
   counter[0]+=1
   return dict(receipt_bytes=canonical(dict(self.receipt,source_sha256={k:digest(v) for k,v in self.files.items()})),files=deepcopy(self.files)) if counter[0]==1 else dict(trusted=True)
  self.archive.authenticate_current=changing
  with self.assertRaisesRegex(ValueError,'CONTEXT_CHANGED'):self.archive.archive_current()
  self.assertFalse((self.root/'archive').exists())
 def test_tamper_and_cross_target_reference_rejected(self):
  ref=self.archive.archive_current();wrong=dict(ref,target_id='other')
  with self.assertRaisesRegex(ValueError,'REFERENCE_BINDING'):self.archive.read_verified(wrong)
  path=self.root/'archive'/(ref['sha256']+'.json');path.write_bytes(path.read_bytes()+b' ')
  with self.assertRaisesRegex(ValueError,'ARCHIVE_CHANGED'):self.archive.read_verified(ref)
 def test_config_and_expiry_and_old_session_rejected(self):
  self.receipt['valid_until']='2026-10-29T13:59:59Z'
  with self.assertRaisesRegex(ValueError,'EXPIRED'):self.archive.archive_current()
  self.receipt['valid_until']='2026-10-29T20:00:00Z';self.files['frontier/precommit-observations.json']=canonical([dict(session_date='2026-10-27',decision_date='2026-10-27',closes={'A':'100'},unit_ids={'A':'unitA'})])
  with self.assertRaisesRegex(ValueError,'CURRENT_COMPLETED'):self.archive.archive_current()
 def test_old_committed_archive_and_postcommit_material_rejected(self):
  self.receipt['schema']='SERVER_REVIEWED_DAILY_EVIDENCE_V1'
  with self.assertRaisesRegex(ValueError,'SOURCE_RECEIPT'):self.archive.archive_current()
  self.receipt['schema']='SERVER_REVIEWED_REENTRY_INTENT_V1';self.receipt['risk_committed']=True
  with self.assertRaisesRegex(ValueError,'SOURCE_RECEIPT'):self.archive.archive_current()
  self.receipt['risk_committed']=False;self.files['frontier/risk-projection.json']=b'{}'
  with self.assertRaisesRegex(ValueError,'POSTCOMMIT_ARCHIVE_FORBIDDEN'):self.archive.archive_current()
  del self.files['frontier/risk-projection.json'];self.files['frontier/risk-before.json']=canonical({'changed':'state'})
  with self.assertRaisesRegex(ValueError,'RISK_BEFORE_BINDING'):self.archive.archive_current()
  self.assertFalse((self.root/'archive').exists())
 def test_later_recorded_execution_before_archived_decision_waits(self):
  ref=self.archive.archive_current();verified=self.archive.read_verified(ref)
  self.now=datetime(2026,10,29,15,tzinfo=timezone.utc)
  self.append('DIRECT_FILL',security_id='A',side='SELL',quantity=1,price='100',fees='0',executed_at='2026-10-29T13:59:00Z')
  result=account_session_snapshot(self.store,account_id='synthetic',session_date=ref['session_date'],expected_latest_revision=self.state['revision'],decision_evidence=verified['decision_evidence'],decision_evidence_sha256=verified['decision_evidence_sha256'],security_ids=['A'])
  self.assertEqual(result['reason'],'WAIT_LATE_RECORDED_FILL_RECONCILIATION')
if __name__=='__main__':unittest.main()
