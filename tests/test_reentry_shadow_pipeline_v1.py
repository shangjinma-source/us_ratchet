"""Shadow orchestration tests. Snapshot/store are stubs here; cross-layer suite
separately exercises real journal, risk transaction and source files together.
Projection and cash allocation are real; no model, network or production DB.
"""
import sys,unittest,tempfile
from pathlib import Path
from unittest.mock import Mock,patch
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).parent))
from test_news_risk_plan_v1 import fixture,NOW
from data import reentry_shadow_pipeline_v1 as module

class ShadowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.directory=Path(self.tmp.name);account,preview,_=fixture(held={'A':0,'B':0,'C':3},targets={'A':4,'B':4,'C':1},cash='200')
  self.state=dict(schema='REENTRY_REFERENCE_V1',account_id=account['account_id'],version=1,locks={'A':dict(security_id='A')})
  self.risk=Mock(path=self.directory/'shadow/risk.sqlite');self.risk.read_reference.side_effect=lambda _:deepcopy(self.state);self.risk.advance.return_value={'effective_target_quantities':preview['effective_target_quantities']}
  self.account_store=Mock(path=self.directory/'account.sqlite')
  self.binding=dict(account_id=account['account_id'],account_revision=account['revision'],target_id=preview['target_id'],proposal_id=preview['proposal_id'])
  self.advance=dict(account_id=account['account_id'],expected_reference_version=1,observations=[dict(session_date='2026-10-27',closes={'A':'79'},unit_ids={'A':'u'})])
  self.authority=Mock(return_value=dict(advance=self.advance,decisions={'2026-10-27':dict(decision_evidence=b'fixture archived decision',unit_ids={'A':'u'})}))
  self.args=dict(root=Path.cwd(),shadow_directory=self.directory/'shadow',risk_store=self.risk,account_store=self.account_store,account=account,original_preview=preview,decision_session='2026-10-27',now=NOW,source_configurations={},authority_verifier=self.authority,binding_reader=lambda:deepcopy(self.binding),configuration_reader=lambda:'c'*64,clock_reader=lambda:NOW)
  self.snapshot=dict(status='JOURNAL_PREFIX_VERIFIED_UNITS_NOT_CERTIFIED',account_revision=account['revision'],shares={'A':0,'B':0,'C':3},evidence_sha256='a'*64,event_boundary_sha256='b'*64,session_close_at='2026-10-27T20:00:00Z')
 def run_case(self):
  with patch.object(module,'account_session_snapshot',return_value=self.snapshot):return module.run_shadow_pipeline(**self.args)
 def test_missing_authority_no_risk_write(self):
  self.args['authority_verifier']=None;r=self.run_case();self.assertEqual(r['reason'],'WAIT_DECISION_AUTHORITY_UNIMPLEMENTED');self.risk.advance.assert_not_called()
 def test_missing_final_authority_no_risk_write(self):
  self.args['binding_reader']=None;r=self.run_case();self.assertEqual(r['reason'],'WAIT_FINAL_BINDING_AUTHORITY_UNIMPLEMENTED');self.risk.advance.assert_not_called()
 def test_unknown_source_blocks_buys_not_sell(self):
  r=self.run_case();self.assertEqual(r['status'],'SHADOW_CHECKED');self.assertEqual(r['projection']['status'],'WAIT_BUY_REFERENCE');self.assertEqual([x['side'] for x in r['candidate_orders']],['SELL']);self.assertFalse(r['executable']);self.risk.advance.assert_called_once()
  self.assertEqual(r['candidate_orders'],[x for x in self.args['original_preview']['new_orders'] if x['side']=='SELL'])
 def test_source_failure_never_becomes_disjoint(self):
  self.args['source_configurations']={'A':{'path':'fixture','sha256':'a'*64}}
  with patch.object(module,'review_reference_interval',return_value={'status':'WAIT_REFERENCE_SOURCE','reason':'tampered'}):r=self.run_case()
  self.assertEqual([x['side'] for x in r['candidate_orders']],['SELL']);self.assertEqual(self.risk.advance.call_args.kwargs['recovery_evidence'],[])
 def test_late_fill_wait_precedes_atomic_write(self):
  self.snapshot={'status':'WAIT','reason':'WAIT_LATE_RECORDED_FILL_RECONCILIATION'};r=self.run_case();self.assertEqual(r['status'],'WAIT');self.risk.advance.assert_not_called()
 def test_final_changed_removes_all_candidate_orders(self):
  self.args['binding_reader']=Mock(side_effect=[self.binding,self.binding,dict(self.binding,account_revision='new')]);r=self.run_case();self.assertEqual(r['reason'],'PUBLICATION_ACCOUNT_TARGET_CHANGED');self.assertEqual(r['candidate_orders'],[])
 def test_new_risk_target_needs_fresh_original_preview(self):
  self.risk.advance.return_value={'effective_target_quantities':{'A':0,'B':4,'C':1}};r=self.run_case();self.assertEqual(r['reason'],'WAIT_FRESH_ORIGINAL_RISK_PREVIEW');self.assertEqual(r['candidate_orders'],[])
 def test_configuration_changed_removes_candidate_orders(self):
  self.args['configuration_reader']=Mock(side_effect=['c'*64,'d'*64]);r=self.run_case();self.assertEqual(r['reason'],'PUBLICATION_CONFIGURATION_CHANGED');self.assertEqual(r['candidate_orders'],[])
 def test_fresh_clock_expiry_removes_candidate_orders(self):
  self.args['clock_reader']=lambda:'2026-10-28T14:01:00+00:00';r=self.run_case();self.assertEqual(r['reason'],'PUBLICATION_EXPIRED_OR_FUTURE');self.assertEqual(r['candidate_orders'],[])
 def test_atomic_failure_not_hidden(self):
  self.risk.advance.side_effect=ValueError('atomic rollback')
  with self.assertRaisesRegex(ValueError,'atomic rollback'):self.run_case()
 def test_account_database_cannot_be_risk_database(self):
  self.account_store.path=self.risk.path
  with self.assertRaisesRegex(ValueError,'ACCOUNT_DATABASE_REFUSED'):self.run_case()
if __name__=='__main__':unittest.main()
