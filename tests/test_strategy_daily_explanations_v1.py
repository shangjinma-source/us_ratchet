import json
import tempfile
import unittest
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from data.strategy_daily_explanations_v1 import explain_preview
from data.strategy_daily_rebound_archive import archive_rebound_evidence
from test_current_quantity_v2_risk_overlays import fixture

class ExplanationTests(unittest.TestCase):
 def case(self, root):
  inputs=fixture({'A':[100]*20,'B':[100]*19+[110]},quantities={'A':13,'B':52})
  files={'inputs':json.dumps(inputs).encode()}
  receipt=dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1',account_revision='rev',target_id='target',
    normalized_inputs_path='inputs',source_sha256={k:sha256(v).hexdigest() for k,v in files.items()})
  archive=archive_rebound_evidence(root=root,receipt_bytes=json.dumps(receipt).encode(),files=files)
  return dict(status='READY',account_revision='rev',target_id='target',evidence_archive=archive,
    effective_target_quantities={'A':6,'B':52},new_orders=[dict(security_id='A',side='SELL',quantity=8)],reference_quotes={})
 def explain(self, result, root):
  return explain_preview(result,archive_root=root,policy_id='SMA20_HALF_OFF_RESEARCH')
 def test_explanation_leaves_orders_unchanged_and_equality_halves_monthly(self):
  with tempfile.TemporaryDirectory() as root:
   result=self.case(root);before=deepcopy(result);answer=self.explain(result,root)
   self.assertEqual(result,before)
   notes=answer.pop('signal_explanations');self.assertEqual(answer,result)
   self.assertFalse(notes['A']['above_sma20']);self.assertEqual(notes['A']['effective_target'],6)
   self.assertTrue(notes['B']['above_sma20']);self.assertEqual(notes['B']['effective_target'],52)
 def test_mismatched_targets_binding_and_policy_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   result=self.case(root)
   for key,value,error in [('target_id','other','BINDING'),('account_revision','other','BINDING'),('effective_target_quantities',{'A':7,'B':52},'TARGET')]:
    with self.subTest(key=key):
     changed=deepcopy(result);changed[key]=value
     with self.assertRaisesRegex(ValueError,error):self.explain(changed,root)
   with self.assertRaisesRegex(ValueError,'POLICY'):
    explain_preview(result,archive_root=root,policy_id='another')
 def test_missing_complete_or_changed_source_rejected(self):
  for broken in ('complete','source'):
   with self.subTest(broken=broken),tempfile.TemporaryDirectory() as root:
    result=self.case(root);folder=Path(result['evidence_archive']['receipt_path']).parent
    if broken=='complete':(folder/'complete.json').unlink()
    else:next((folder/'sources').iterdir()).write_bytes(b'changed')
    with self.assertRaises((ValueError,OSError)):self.explain(result,root)
 def test_wait_does_not_read_old_archive(self):
  result=dict(status='WAIT',evidence_archive={'receipt_path':'must-not-read'})
  self.assertEqual(self.explain(result,'missing'),result)
