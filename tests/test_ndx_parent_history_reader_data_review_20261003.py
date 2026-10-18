"""Independent compact-history boundary counterexamples; no saved observations."""
import copy,importlib.util,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_prospective_observation_parent_history_independent_readback_20261003 as m
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('compact_fixture',ROOT/'tests/test_ndx_prospective_observation_parent_history_independent_readback_20261003.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
class Review(unittest.TestCase):
 def test_full_prior_late_month_first_preserved_no_raw_embedded(self):
  args=f.fixture(True);before=copy.deepcopy(args);out=m.inspect(*args)
  self.assertEqual(out['typed_row_count'],67);self.assertEqual(out['first_actual_observed_session_by_month']['2026-10'],'2026-10-02');self.assertEqual(args,before)
  self.assertEqual(args[0]['observations'][0],args[2]['document']['observations'][0])
  self.assertFalse(any(k in args[0]['observations'][-1]for k in ('payload','receipt','audit','rows','base64')))
  for mode in ('omit','month','last','attempt','reader','v1'):
   h,g,p,o=f.fixture(True)
   if mode=='omit':p['document']['known_typed_rows'].pop(0)
   elif mode=='month':p['document']['first_actual_observed_session_by_month']['2026-10']='2026-10-05'
   elif mode=='last':p['document']['last_accounted_session']='2026-10-01'
   elif mode=='attempt':p['document']['parent_attempt_inventory'][0]['status']='FAILED'
   elif mode=='reader':p['readback']['reader_sha256']='0'*64
   else:o['audit']['schema']='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1'
   with self.subTest(mode=mode),self.assertRaises((ValueError,KeyError)):m.inspect(h,g,p,o)
 def test_claims_roles_and_capture_cannot_be_replaced(self):
  for mode in ('capture','role','receipt','conflict','dropaudit','bool'):
   h,g,p,o=f.fixture(True)
   if mode=='capture':o['payload']['full_original_sources_preserved']['QQQ']['sources']['reference']={'path':'unbound','sha256':'a'*64}
   elif mode=='role':g['baseline_references']={'QQQ':copy.deepcopy(g['baseline_references']['SPY']),'SPY':copy.deepcopy(g['baseline_references']['QQQ'])}
   elif mode=='receipt':o['receipt']['source_hashes']=dict(o['receipt']['source_hashes'],extra='b'*64)
   elif mode=='conflict':o['receipt']['source_hashes'][g['reference']['path']]='f'*64;o['payload']['source_hashes'][g['reference']['path']]='f'*64
   elif mode=='dropaudit':o['audit']['source_hashes'].pop(o['payload_reference']['path'])
   else:o['audit']['counts']['parent_gap_count']=5.0
   with self.subTest(mode=mode),self.assertRaises((ValueError,KeyError)):m.inspect(h,g,p,o)
 def test_pending_no_reads_and_no_producer_calls(self):
  with patch.dict(m.BOUND, {'history': (m.BOUND['history'][0], None)}), patch.object(Path,'read_bytes',side_effect=AssertionError('actual IO')),patch.object(Path,'exists',side_effect=AssertionError('actual IO')):
   with self.assertRaisesRegex(ValueError,'Pending'):m.readback(execute=True)
  import ast
  tree=ast.parse(Path(m.__file__).read_text())
  for n in ast.walk(tree):
   if isinstance(n,ast.Call):self.assertNotIn(ast.unparse(n.func),('exec','eval','append_observation_history','producer.append_observation_history'))
if __name__=='__main__':unittest.main()
