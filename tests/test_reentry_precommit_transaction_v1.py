"""PRECOMMIT -> archive -> real journal snapshot -> one atomic risk commit.
All market/source authority is synthetic and server-owned, never live evidence.
"""
import sys,json,sqlite3,tempfile,unittest
from pathlib import Path
from datetime import datetime
from hashlib import sha256
from contextlib import closing
sys.path.insert(0,str(Path(__file__).parent))
from test_saved_monthly_frontier_proposal import native_fixture
from test_monthly_cap_topup_packet import packet,DAYS
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from core.strategy_account_store import StrategyAccountStore
from core.strategy_account_ledger import canonical
from data.monthly_peak_exit_reentry_store_v1 import MonthlyPeakExitReentryStore
from data.saved_frontier_reentry_exit_packet_v1 import prepare_frontier_reentry_exit_packet,apply_frontier_reentry_exit_packet
from data.reentry_decision_boundary_v1 import DecisionBoundaryArchive
from data.strategy_account_session_snapshot_v1 import account_session_snapshot
H='a'*64
def hash_bytes(raw):return sha256(raw).hexdigest()
class PrecommitTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.target=native_fixture();self.proposal=build_frontier_proposal(target=self.target);self.aid=self.target['payload']['account_id']
  self.now=datetime.fromisoformat('2026-10-19T19:00:00+00:00');self.account=StrategyAccountStore(self.root/'account.sqlite',clock=lambda:self.now);self.state=self.account.initialize(self.aid,operation_id='init')
  for event in [dict(kind='CASH_CONFIRM',amount='10000',cash_basis='TOTAL_UNINVESTED'),dict(kind='DIRECT_FILL',security_id='A',side='BUY',quantity=10,price='100',fees='0',executed_at=self.now.isoformat())]:
   self.state,_=self.account.append(dict(event,event_id=str(len(self.state['events']))),expected_revision=self.state['revision'])
  self.risk=MonthlyPeakExitReentryStore(self.root/'risk.sqlite');self.risk.activate_reference(account_id=self.aid,activation_id=H,activation_at='2026-10-19T19:30:00Z',activation_session='2026-10-19',account_revision=self.state['revision'],source_configuration_sha256=H)
  self.contexts={};self.current_args=None
  self.calendar=canonical(dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=[dict(date=d,open=d+'T13:30:00Z',close=d+'T20:00:00Z') for d in DAYS]))
  self.release=canonical(dict(authorized=True,authorized_at='2026-10-19T12:00:00Z',policy_id='SAVED_FRONTIER_CAP50_EXIT20_V1',monthly_cap='1/2',exit_ratio='4/5',sma20_overlay=False))
  self.archive=DecisionBoundaryArchive(root=self.root/'intent',source_configuration_bytes=canonical(dict(calendar={'sha256':hash_bytes(self.calendar)})),release_bytes=self.release,authenticate_current=self.authenticate,clock=lambda:self.now)
 def rows(self):
  with closing(sqlite3.connect(self.risk.path)) as c:
   return {r[0]:list(c.execute('SELECT * FROM '+r[0]+' ORDER BY rowid')) for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()}
 def setup_day(self,index):
  day=DAYS[index];self.now=datetime.fromisoformat(day+'T21:00:00+00:00')
  inputs=packet(self.target,{'A':[100,79,78],'B':[100,100,100]});inputs.update(signal_date=day,observed_at=self.now.isoformat(),session_dates=DAYS[:index+1]);inputs['session_close_times']['closes']={d:d+'T20:00:00+00:00' for d in DAYS[:index+1]}
  for history in inputs['histories'].values():history['closes']=history['closes'][:index+1];history['units']['unit_asof']=day
  inputs['base_target'].update(origin_reference=self.proposal['proposal_id'],quantities=self.proposal['payload']['proposed_target_quantities'])
  old=self.risk.read(self.aid)
  self.current_args=dict(target=self.target,proposal=self.proposal,inputs=inputs,account_id=self.aid,decision_date=DAYS[0],expected_previous_session=old['session_date'] if old else None)
 def authenticate(self):
  before=self.rows();prepared=prepare_frontier_reentry_exit_packet(**self.current_args,risk_store=self.risk);self.assertEqual(self.rows(),before)
  self.assertEqual(self.account.read(),self.state)
  files={'frontier/release.json':self.release,'frontier/calendar.json':self.calendar,'frontier/account.json':canonical(self.state),'frontier/target.json':canonical(self.target),'frontier/proposal.json':canonical(self.proposal),'frontier/risk-before.json':canonical(prepared['previous_risk']),'frontier/precommit-observations.json':canonical(prepared['observations']),'frontier/preparation.json':canonical(prepared)}
  receipt=dict(schema='SERVER_REVIEWED_REENTRY_INTENT_V1',phase='PRECOMMIT',risk_committed=False,risk_before_sha256=hash_bytes(files['frontier/risk-before.json']),policy_id='SAVED_FRONTIER_CAP50_EXIT20_V1',account_id=self.aid,account_revision=self.state['revision'],target_id=self.target['target_id'],proposal_id=self.proposal['proposal_id'],valid_from=self.now.isoformat(),valid_until=prepared['final_session']+'T22:00:00Z',release_sha256=hash_bytes(self.release),source_sha256={k:hash_bytes(v) for k,v in files.items()})
  return dict(receipt_bytes=canonical(receipt),files=files)
 def stage(self,index):
  self.setup_day(index);before=self.rows();prepared=prepare_frontier_reentry_exit_packet(**self.current_args,risk_store=self.risk)
  ref=self.archive.archive_current();self.assertEqual(self.rows(),before)
  verified=self.archive.read_verified(ref);b=json.loads(verified['decision_evidence'])
  snapshot=account_session_snapshot(self.account,account_id=self.aid,session_date=b['session_date'],expected_latest_revision=self.state['revision'],decision_evidence=verified['decision_evidence'],decision_evidence_sha256=verified['decision_evidence_sha256'],security_ids=['A','B'])
  self.assertIn('shares',snapshot);self.assertEqual(snapshot['account_revision'],self.state['revision'])
  self.contexts[b['session_date']]=dict(completed_at=b['session_close_at'],holdings=dict(snapshot,unit_ids=verified['unit_ids']))
  return prepared,ref
 def commit(self,prepared):
  return apply_frontier_reentry_exit_packet(**self.current_args,risk_store=self.risk,expected_preparation_sha256=prepared['preparation_sha256'],expected_reference_version=self.risk.read_reference(self.aid)['version'],activation_id=H,session_contexts=self.contexts)
 def test_same_account_precommit_archive_snapshot_unique_transaction(self):
  before=(self.root/'account.sqlite').read_bytes();p,_=self.stage(0);self.commit(p);p,ref=self.stage(1)
  calls=[];self.risk.before_commit=lambda connection:calls.append(1)
  r=self.commit(p);self.assertEqual(calls,[1]);self.assertEqual(r['reference_state']['locks']['A']['reference_price'],'79');self.assertEqual(r['reference_state']['locks']['A']['held_quantity_at_exit'],10)
  self.assertEqual((self.root/'account.sqlite').read_bytes(),before);self.assertEqual(self.archive.read_verified(ref)['status'],'SERVER_ARCHIVED_BOUNDARY_VERIFIED')
 def test_archive_survives_atomic_failure_retry_does_not_lose_lock(self):
  p,_=self.stage(0);self.commit(p);p,ref=self.stage(1);before=self.rows()
  def fail(connection):raise RuntimeError('atomic rollback')
  self.risk.before_commit=fail
  with self.assertRaisesRegex(RuntimeError,'atomic rollback'):self.commit(p)
  self.assertEqual(self.rows(),before);self.assertEqual(self.archive.read_verified(ref)['status'],'SERVER_ARCHIVED_BOUNDARY_VERIFIED')
  self.risk.before_commit=None;r=self.commit(p);self.assertEqual(list(r['reference_state']['locks']),['A']);self.assertEqual(r['reference_state']['locks']['A']['reference_price'],'79')
 def test_prepared_input_changed_after_archive_refuses_commit(self):
  p,_=self.stage(0);self.commit(p);p,_=self.stage(1);before=self.rows()
  self.current_args['inputs']['histories']['A']['closes'][-1]['close']='78'
  with self.assertRaisesRegex(ValueError,'PRECOMMIT_PREPARATION_CHANGED'):self.commit(p)
  self.assertEqual(self.rows(),before)
if __name__=='__main__':unittest.main()
