import os
import importlib.util,unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()/"tests"))
from copy import deepcopy
p=Path(os.environ.get('REENTRY_CANDIDATE_ROOT', '.'))/'core/reentry_buy_scope_v1.py';spec=importlib.util.spec_from_file_location('gate',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class GateTests(unittest.TestCase):
 def setUp(self):
  self.state=dict(schema='REENTRY_REFERENCE_V1',account_id='a',version=3,locks={'OLD':{'security_id':'OLD','current_security_id':'OLD'}})
  self.binding=dict(account_id='a',account_revision='r',target_id='t',proposal_id='p');self.targets={'NEW':10,'SELL':2};self.shares={'NEW':0,'SELL':7}
 def run_gate(self,proofs=(),**kw):return m.build_buy_scope_gate(reference_state=self.state,original_binding=self.binding,decision_session='2026-10-28',effective_targets=kw.get('targets',self.targets),actual_shares=self.shares,scope_proofs=list(proofs))
 def proof(self,ids,status):return dict(origin_security_id='OLD',reference_version=3,reference_state_sha256=m.digest(self.state),original_binding=deepcopy(self.binding),decision_session='2026-10-28',buy_security_ids=['NEW'],status=status,current_security_ids=ids,identity_evidence_sha256='a'*64)
 def test_missing_identity_waits_all_buys_preserves_sell(self):
  r=self.run_gate();self.assertEqual(r['execution_targets'],{'NEW':0,'SELL':2});self.assertEqual(r['original_sell_quantities'],{'SELL':5});self.assertEqual(r['buy_status']['NEW'],'WAIT_REFERENCE');self.assertFalse(r['executable'])
 def test_no_buy_no_reference_requirement(self):
  r=self.run_gate(targets={'NEW':0,'SELL':2});self.assertEqual(r['status'],'NO_NEW_BUY_GAP');self.assertEqual(r['original_sell_quantities'],{'SELL':5})
 def test_successor_not_old_sid_controls_block(self):
  p=self.proof(['NEW'],'INTERSECTS_BUY_SCOPE');p.update(price_status='LOCKED',price_evidence_sha256='b'*64,price_completed_through='2026-10-28');r=self.run_gate([p]);self.assertEqual(r['buy_status']['NEW'],'BLOCK_LOCKED');self.assertEqual(r['execution_targets']['SELL'],2)
  p['status']='DISJOINT_IDENTITY_CERTIFIED'
  with self.assertRaisesRegex(ValueError,'FALSE_DISJOINT'):self.run_gate([p])
 def test_certified_disjoint_does_not_require_price(self):
  r=self.run_gate([self.proof(['OTHER'],'DISJOINT_IDENTITY_CERTIFIED')]);self.assertEqual(r['buy_status']['NEW'],'ALLOW');self.assertFalse(r['lock_reviews'][0]['price_reviewed']);self.assertEqual(self.state['locks']['OLD']['current_security_id'],'OLD')
 def test_duplicate_and_stale_binding_rejected(self):
  p=self.proof(['OTHER'],'DISJOINT_IDENTITY_CERTIFIED')
  with self.assertRaisesRegex(ValueError,'DUPLICATE'):self.run_gate([p,p])
  for key,val in [('reference_version',4),('buy_security_ids',['DIFFERENT']),('original_binding',dict(self.binding,account_revision='changed'))]:
   bad=dict(p);bad[key]=val
   with self.assertRaisesRegex(ValueError,'BINDING'):self.run_gate([bad])
 def test_recovery_not_committed_and_price_future_rejected(self):
  p=self.proof(['NEW'],'INTERSECTS_BUY_SCOPE');p['price_status']='RECOVERED'
  with self.assertRaisesRegex(ValueError,'MUST_BE_COMMITTED'):self.run_gate([p])
  p.update(price_status='LOCKED',price_evidence_sha256='b'*64,price_completed_through='2026-10-29')
  with self.assertRaisesRegex(ValueError,'PRICE_EVIDENCE'):self.run_gate([p])
 def test_identity_known_price_missing_wait_only_and_no_new_sell(self):
  p=self.proof(['NEW'],'INTERSECTS_BUY_SCOPE');r=self.run_gate([p]);self.assertEqual(r['execution_targets']['NEW'],0);self.assertEqual(r['original_sell_quantities'],{'SELL':5});self.assertEqual(r['buy_status']['NEW'],'WAIT_REFERENCE')
  self.shares['NEW']=4;r=self.run_gate([p]);self.assertEqual(r['execution_targets']['NEW'],4);self.assertEqual(r['original_sell_quantities'],{'SELL':5})
 def test_filter_before_real_cash_allocation(self):
  import sys
  sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tests'))
  from test_news_risk_plan_v1 import fixture,NOW
  from data.strategy_account_preview import preview_scoped_account
  account,original,_=fixture(held={'A':4,'B':2,'C':3},targets={'A':8,'B':6,'C':1},cash='200')
  state=dict(schema='REENTRY_REFERENCE_V1',account_id=account['account_id'],version=1,locks={'A':{'security_id':'A'}})
  binding={k:original[k] for k in ('account_revision','target_id','proposal_id')};binding['account_id']=account['account_id']
  p=dict(origin_security_id='A',reference_version=1,reference_state_sha256=m.digest(state),original_binding=binding,decision_session='2026-10-28',buy_security_ids=['A','B'],status='INTERSECTS_BUY_SCOPE',current_security_ids=['A'],identity_evidence_sha256='a'*64,price_status='LOCKED',price_completed_through='2026-10-28',price_evidence_sha256='b'*64)
  gate=m.build_buy_scope_gate(reference_state=state,original_binding=binding,decision_session='2026-10-28',effective_targets=original['effective_target_quantities'],actual_shares=account['shares'],scope_proofs=[p])
  evidence=original['difference']['binding'];before=deepcopy((account,evidence,original))
  after=preview_scoped_account(state=account,legacy_shares=evidence['legacy_shares'],marks=evidence['marks'],limits=evidence['limits'],target_quantities=gate['execution_targets'],now=NOW,maximum_mark_age_seconds=evidence['maximum_mark_age_seconds'],fee_bps=evidence['fee_bps'])
  self.assertEqual([(o['security_id'],o['quantity']) for o in original['new_orders'] if o['side']=='BUY'],[('A',1),('B',1)])
  self.assertEqual([(o['security_id'],o['quantity']) for o in after['new_orders'] if o['side']=='BUY'],[('B',2)])
  self.assertEqual([o for o in after['new_orders'] if o['side']=='SELL'],[o for o in original['new_orders'] if o['side']=='SELL'])
  self.assertEqual((account,evidence,original),before)
if __name__=='__main__':unittest.main()
