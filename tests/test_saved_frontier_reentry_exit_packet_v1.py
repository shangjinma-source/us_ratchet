"""Real isolated SQLite stores; no production routing, accounts or network."""
import sys, unittest, sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
from contextlib import closing
sys.path.insert(0,str(Path(__file__).parent))
from test_saved_monthly_frontier_proposal import native_fixture
from test_monthly_cap_topup_packet import packet,DAYS
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.monthly_peak_exit_reentry_store_v1 import MonthlyPeakExitReentryStore
from data.saved_frontier_exit_packet_v1 import apply_frontier_exit_packet
from data.saved_frontier_reentry_exit_packet_v1 import apply_frontier_reentry_exit_packet,prepare_frontier_reentry_exit_packet
from unittest.mock import patch
H='a'*64

class ReentryExitPacketTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);folder=Path(self.temp.name)
  self.target=native_fixture();self.proposal=build_frontier_proposal(target=self.target);self.account=self.target['payload']['account_id']
  self.old=MonthlyPeakExitStore(folder/'old.sqlite');self.new=MonthlyPeakExitReentryStore(folder/'new.sqlite')
  self.new.activate_reference(account_id=self.account,activation_id=H,activation_at='2026-10-19T12:00:00Z',activation_session='2026-10-19',account_revision='r0',source_configuration_sha256=H)
 def case(self,prices=(100,105,110)):
  inputs=packet(self.target,{'A':list(prices),'B':[100,105,110]})
  inputs['base_target'].update(origin_reference=self.proposal['proposal_id'],quantities=self.proposal['payload']['proposed_target_quantities'])
  return dict(target=self.target,proposal=self.proposal,inputs=inputs,account_id=self.account,decision_date=DAYS[0],expected_previous_session=None)
 def extra(self):
  return dict(expected_reference_version=0,activation_id=H,session_contexts={d:dict(completed_at=d+'T20:00:00+00:00',holdings=dict(session_date=d,account_id=self.account,account_revision='r0',shares={'A':10,'B':10},unit_ids={'A':'nominal','B':'nominal'},evidence_sha256=H,event_boundary_sha256=H)) for d in DAYS})
 def rows(self):
  with closing(sqlite3.connect(self.new.path)) as c:
   tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
   return {t:list(c.execute('SELECT * FROM '+t+' ORDER BY rowid')) for t in tables}
 def test_prepare_is_read_only_and_apply_binds_same_observations(self):
  args=self.case((100,79,78));before=self.rows()
  with patch.object(self.new,'advance',side_effect=AssertionError('prepare must not write')):
   prepared=prepare_frontier_reentry_exit_packet(**args,risk_store=self.new)
  self.assertEqual(self.rows(),before);self.assertFalse(prepared['risk_committed']);self.assertFalse(prepared['risk_projection_performed']);self.assertIsNone(prepared['previous_risk']);self.assertEqual(prepared['final_session'],DAYS[-1]);self.assertEqual(prepared['final_unit_ids'],{'A':'nominal','B':'nominal'})
  r=apply_frontier_reentry_exit_packet(**args,risk_store=self.new,**self.extra(),expected_preparation_sha256=prepared['preparation_sha256']);self.assertEqual(r['reference_state']['locks']['A']['reference_price'],'79')
 def test_changed_precommit_preparation_rejected_before_transaction(self):
  args=self.case();prepared=prepare_frontier_reentry_exit_packet(**args,risk_store=self.new);before=self.rows()
  args['inputs']['histories']['A']['closes'][-1]['close']='111'
  with self.assertRaisesRegex(ValueError,'PRECOMMIT_PREPARATION_CHANGED'):apply_frontier_reentry_exit_packet(**args,risk_store=self.new,**self.extra(),expected_preparation_sha256=prepared['preparation_sha256'])
  self.assertEqual(self.rows(),before)
 def test_prepare_existing_same_session_does_not_replay_risk(self):
  args=self.case();r=apply_frontier_reentry_exit_packet(**args,risk_store=self.new,**self.extra());args['expected_previous_session']=DAYS[-1];before=self.rows()
  prepared=prepare_frontier_reentry_exit_packet(**args,risk_store=self.new);self.assertEqual(prepared['previous_risk'],r['state']);self.assertEqual(self.rows(),before);self.assertEqual(len(prepared['observations']),3)
 def test_no_lock_exact_old_risk_projection(self):
  args=self.case();before=deepcopy(args)
  old=apply_frontier_exit_packet(**args,risk_store=self.old)
  new=apply_frontier_reentry_exit_packet(**args,risk_store=self.new,**self.extra())
  self.assertEqual({k:v for k,v in new.items() if k!='reference_state'},old)
  self.assertEqual(new['reference_state']['locks'],{});self.assertEqual(self.new.read(self.account),self.old.read(self.account));self.assertEqual(args,before)
 def test_exit_intent_and_reference_same_transaction_without_fill(self):
  r=apply_frontier_reentry_exit_packet(**self.case((100,79,78)),risk_store=self.new,**self.extra())
  self.assertEqual(r['effective_target_quantities']['A'],0);lock=r['reference_state']['locks']['A'];self.assertEqual(lock['reference_price'],'79');self.assertEqual(lock['exit_session'],DAYS[1]);self.assertFalse(r['orders_created'])
 def test_exit_transaction_failure_rolls_back_all_tables(self):
  before=self.rows()
  def fail(connection):raise RuntimeError('injected atomic failure')
  self.new.before_commit=fail
  with self.assertRaisesRegex(RuntimeError,'atomic failure'):apply_frontier_reentry_exit_packet(**self.case((100,79,78)),risk_store=self.new,**self.extra())
  self.assertEqual(self.rows(),before);self.assertIsNone(self.new.read(self.account));self.assertEqual(self.new.read_reference(self.account)['locks'],{})
 def test_missing_exit_holdings_rolls_back_risk(self):
  extra=self.extra();extra['session_contexts'].pop(DAYS[1]);before=self.rows()
  with self.assertRaises(ValueError):apply_frontier_reentry_exit_packet(**self.case((100,79,78)),risk_store=self.new,**extra)
  self.assertEqual(self.rows(),before)
 def test_original_proposal_guard_precedes_write(self):
  args=self.case();args['proposal']=deepcopy(self.proposal);args['proposal']['proposal_id']='changed';before=self.rows()
  with self.assertRaisesRegex(ValueError,'FRONTIER_PROPOSAL_CHANGED'):apply_frontier_reentry_exit_packet(**args,risk_store=self.new,**self.extra())
  self.assertEqual(self.rows(),before)
if __name__=='__main__':unittest.main()
