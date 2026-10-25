from copy import deepcopy
import unittest
import test_review_ma9_sma20_half as fixtures
from scripts.review_ma9_sma20_signals import review as signals
from scripts.review_ma9_sma20_half import review_targets

class IndependentMAReviewTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixtures.ReviewTests.setUpClass()
 def test_strict_signal_booleans(self):
  for field in ('on_sma9','on_sma20'):
   o=deepcopy(fixtures.ReviewTests.outcome);d=o['provider_audit'][0]['risk_overlay']['diagnostics']['A'];d[field]=int(d[field])
   with self.subTest(field=field),self.assertRaises(ValueError):signals(assembled=fixtures.ReviewTests.assembled,outcome=o,history_resolver=fixtures.ReviewTests.resolver)
 def test_float_targets_not_accepted_as_integers(self):
  for field in ('target_shares','monthly_ceiling','target_quantities'):
   o=deepcopy(fixtures.ReviewTests.outcome);row=o['provider_audit'][0];target=row['risk_overlay'] if field=='target_quantities' else row;target[field]['A']=float(target[field]['A'])
   with self.subTest(field=field),self.assertRaises(ValueError):fixtures.ReviewTests().check(o)
 def test_missing_order_and_fake_wait_rejected(self):
  for kind in ('orders','wait','date'):
   o=deepcopy(fixtures.ReviewTests.outcome);row=o['provider_audit'][0]
   if kind=='orders':row['orders']=[]
   elif kind=='wait':row['action']='WAIT_POST_ACTION_MARK'
   else:row['orders'][0]['active_date']=row['orders'][0]['decision_date']
   with self.subTest(kind=kind),self.assertRaises(ValueError):fixtures.ReviewTests().check(o)
 def test_bad_signal_evidence_blocks_and_nav_is_checked(self):
  def bad(**kwargs):
   x=fixtures.ReviewTests.resolver(**kwargs);x['histories']['A']['closes'][-1]['completed_at']='2099-01-01T00:00:00+00:00';return x
  with self.assertRaises(ValueError):signals(assembled=fixtures.ReviewTests.assembled,outcome=fixtures.ReviewTests.outcome,history_resolver=bad)
  o=deepcopy(fixtures.ReviewTests.outcome);o['daily_ledger'][0]['cash']='999'
  with self.assertRaises(ValueError):fixtures.ReviewTests().check(o)

 def test_incomplete_saved_arm_rejected_before_preparation(self):
  from tempfile import TemporaryDirectory
  from pathlib import Path
  from unittest.mock import patch
  import json
  from scripts import review_saved_ma9_sma20_half as saved
  with TemporaryDirectory() as folder:
   root=Path(folder)
   for name in saved.REVIEWER_PATHS:
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic')
   directory=root/saved.OUTPUT/('slippage5__'+saved.ARM);directory.mkdir(parents=True);(directory/'terminal.json').write_text(json.dumps({'status':'RUNNING'}))
   with patch.object(saved,'ROOT',root),patch.object(saved,'prepare_run') as prepare:
    with self.assertRaisesRegex(ValueError,'COMPLETED_ARM_REQUIRED'):saved.run('slippage5')
    prepare.assert_not_called()

if __name__=='__main__':unittest.main()
