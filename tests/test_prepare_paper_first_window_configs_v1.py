from copy import deepcopy
from unittest import TestCase
from scripts.prepare_paper_first_window_configs_v1 import configuration_rows,MISSING,REUSABLE
class ConfigRowsTests(TestCase):
 def setUp(self):
  self.template=dict(schema='PAPER_FIRST_WINDOW_SOURCE_PREPARATION_V1',release_sha256=None,security_id='A',fixed={'unchanged':True})
  self.candidates=[dict(security_id='A',ticker='AAA'),dict(security_id='B',ticker='BBB')]
  self.report=dict(candidate_count_matches=True,candidate_count=2,source_errors=[],calendar_errors=[],parent_errors=[],baseline_errors=[],securities=[dict(r,identity_ok=True,saved_unit_baseline={'byte_closure_verified':True},preparation_class=MISSING if r['security_id']=='A' else REUSABLE) for r in self.candidates])
 def test_only_missing_config_and_no_template_mutation(self):
  import json
  before=deepcopy(self.template);rows,reuse=configuration_rows(self.template,self.report,self.candidates)
  self.assertEqual(self.template,before);self.assertEqual(len(rows),1);self.assertEqual(len(reuse),1)
  self.assertEqual(json.loads(rows[0]['raw']),self.template)
 def test_duplicate_or_wrong_identity_rejected(self):
  for kind in ('duplicate','identity','unreviewed','errors'):
   with self.subTest(kind=kind):
    report=deepcopy(self.report)
    if kind=='duplicate':report['securities'][1]=deepcopy(report['securities'][0])
    if kind=='identity':report['securities'][0]['ticker']='WRONG'
    if kind=='unreviewed':report['securities'][0]['saved_unit_baseline']['byte_closure_verified']=False
    if kind=='errors':report['source_errors']=['bad']
    with self.assertRaises(ValueError):configuration_rows(self.template,report,self.candidates)
 def test_release_authority_rejected(self):
  self.template['release_sha256']='a'*64
  with self.assertRaises(ValueError):configuration_rows(self.template,self.report,self.candidates)
