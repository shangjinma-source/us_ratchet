"""Reference-only increment tests; no actual build/publish/numeric work."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('wiring_v2',Path(__file__).resolve().parents[1]/'scripts/ndx_new_cutoff_identity_risk_wiring_v2_20260924.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.docs={k:json.loads((m.BASE/p).read_bytes()) for k,(p,h) in m.BOUND.items()}
 def test_exact19_and_other99_preserved_and_counts(self):
  result=m.assemble(self.docs);old=self.docs['original_wiring']
  self.assertEqual((result['candidate_security_count'],result['candidate_issuer_count'],result['bounded_source_missing_count'],result['dated_coordinate_risk_unassigned_count']),(21,20,79,1))
  self.assertTrue(result['original19_exact_proof']['exact']);self.assertIsNone(result['fit_column_count'])
  for before,after in zip(old['rows'],result['rows']):
   if before['ticker'] not in ('PCAR','CRWD'):self.assertEqual(before,after)
   self.assertEqual(before['channel_row_sha256'],after['channel_row_sha256'])
   self.assertEqual(before['independent_channel_detail'],after['independent_channel_detail'])
   self.assertEqual(before['original_windows'],after['original_windows'])
  self.assertTrue(all(result[k] is False for k in m.FALSE))
 def test_original_null_risk_and_crwd_late_window_preserved(self):
  r=m.assemble(self.docs);rows={x['ticker']:x for x in r['rows']};ext={x['ticker']:x for x in r['extended_provenance']}
  self.assertIsNone(ext['PCAR']['original_row']['risk_chain'])
  self.assertIsNone(rows['PCAR']['complete_original_evidence'][0]['complete_original_fact']['risk_chain'])
  self.assertEqual(rows['PCAR']['risk_chain'],'automotive');self.assertIsNone(rows['CPRT']['risk_chain'])
  self.assertFalse(ext['CRWD']['early_window_evidence_available'])
  self.assertEqual(r['conditional_candidates_with_saved_volume_unit_block'],['CRWD'])
  self.assertIn('SAVED_VOLUME_UNIT_RESTRICTION_RETAINED',rows['CRWD']['gaps'])
 def test_conflicting_crwd_fields_permissions_date_volume(self):
  for key,value in [('cusip','22788C104'),('security_class','CLASS_B_COMMON'),('memo_publication_date','2026-03-19'),('evidence_available_before_window_start',True),('volume_status','PASS')]:
   d=deepcopy(self.docs);d['crwd_identity'][key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):m.assemble(d)
 def test_pcar_judgment_not_oldfact_or_interval_proof(self):
  for key,value in [('conditional_assigned_risk_chain','industrial'),('new_window',{'first':'2026-03-20'}),('current_interval_verified',True),('cprt_classification_adjudicated',True)]:
   d=deepcopy(self.docs);d['pcar_adjudication'][key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):m.assemble(d)
 def test_numeric_hash_pointer_and_order_cannot_change(self):
  for attack in ('pointer','detail','order'):
   d=deepcopy(self.docs)
   if attack=='pointer':d['original_wiring']['rows'][0]['channel_reference']['json_pointer']='/rows/1'
   elif attack=='detail':d['audit']['details'][0]['liquidity_status']='PASS'
   else:d['channels']['rows'].reverse()
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(d)
 def test_no_mutation_of_input(self):
  before=m.canonical(self.docs);m.assemble(self.docs);self.assertEqual(m.canonical(self.docs),before)
 def test_existing_namespace_no_build_and_loaded_source_drift(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)/'wiring.json'),patch.object(m,'build') as build:
   with self.assertRaises(ValueError):m.publish()
   build.assert_not_called()
  with patch.object(m.Path,'read_bytes',return_value=b'drift'):
   with self.assertRaises(ValueError):m.guard({})
if __name__=='__main__':unittest.main()
