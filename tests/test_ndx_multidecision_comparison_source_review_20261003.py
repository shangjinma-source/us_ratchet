from pathlib import Path
from copy import deepcopy
import tempfile,unittest
from unittest.mock import patch
from test_ndx_multidecision_path_comparison_source_adapter_20261003 import a,physical


class Review(unittest.TestCase):
 def test_matching_self_claimed_counts_must_equal_all_original_rows(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bound=physical(root);saved={};project=a.project_inputs
   def capture(**kwargs):saved.update(deepcopy(kwargs));return project(**kwargs)
   with patch.object(a,'BOUND',bound),patch.object(a,'project_inputs',side_effect=capture):a.read_inputs()
   for boolean in (True,False):
    bad=deepcopy(saved);docs=bad['documents']
    if boolean:docs['control_execution']['returned_call_count']=True
    else:
     docs['control_execution']['counts']={'ACCOUNT_RETURNED_PENDING_INDEPENDENT_READBACK':15}
     docs['control_audit']['counts']=deepcopy(docs['control_execution']['counts'])
    with self.subTest(boolean=boolean),self.assertRaises(ValueError):project(**bad)

 def test_full_source_projection_passes_independent_inspection_and_guard(self):
  from backtest.ndx_multidecision_path_comparison_research import compare_multidecision_paths
  from backtest.ndx_multidecision_path_comparison_inspection_research import inspect_multidecision_comparison
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bound=physical(root)
   with patch.object(a,'BOUND',bound):c=a.read_inputs()
   result=compare_multidecision_paths(**c['kwargs'])
   report=inspect_multidecision_comparison(saved_comparison=result,**c['kwargs'])
   self.assertEqual(report['track_count'],16)
   self.assertIsNone(c['kwargs']['candidate_slots'][0]['result'])
   self.assertIsInstance(c['kwargs']['candidate_slots'][0]['blocking_reasons_preserved'][0],dict)
   (Path(bound['candidate_audit'][0]).parent/'extra').write_bytes(b'x')
   with self.assertRaisesRegex(ValueError,'namespace'):a.guard(c['source_hashes'],c['source_inventories'])

 def test_original_control_audit_no_engine_claim_is_strict(self):
  for value in (True,0):
   with self.subTest(value=value),tempfile.TemporaryDirectory() as td:
    root=Path(td);bound=physical(root);p=Path(bound['control_audit'][0]);doc=a.decode(p.read_bytes());doc['control_engine_called']=value;raw=a.enc(doc);p.write_bytes(raw);bound['control_audit']=(str(p),a.sha(raw))
    with patch.object(a,'BOUND',bound),self.assertRaisesRegex(ValueError,'authority'):a.read_inputs()


if __name__=='__main__':unittest.main()
