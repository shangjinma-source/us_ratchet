"""Independent snapshot bridge boundaries; temporary sources only."""
import copy
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from test_ndx_first_persisted_candidate_calendar_research import fixture, m
from test_ndx_first_persisted_candidate_calendar_20261003 import file_fixture, w


class Tests(unittest.TestCase):
 def test_permanent_claims_and_role_swaps(self):
  args=fixture();before=copy.deepcopy(args)
  result=m.prepare_first_persisted_candidate_evidence(**args)
  self.assertEqual(args,before)
  self.assertEqual(result['original_source_claims_preserved'],args['capture']['document']['source_hashes'])
  self.assertFalse(any(m.is_live_cache(p) for p in result['source_hash_claims']))
  self.assertFalse(result['full_transitive_source_closure_reverified'])
  for mode in ('ticker','namespace','preserved','audit_live'):
   a=fixture();c=a['capture'];d=c['document']
   if mode=='ticker':
    d['input_references']['current_QQQ'],d['input_references']['current_SPY']=d['input_references']['current_SPY'],d['input_references']['current_QQQ']
   elif mode=='namespace':d['captured_artifacts']['QQQ']['path']='C:/research/other/QQQ.csv'
   elif mode=='preserved':c['readback']['capture_original_source_hashes_preserved'].pop(next(iter(d['source_hashes'])))
   else:c['readback']['source_hashes'].update({'C:/research/data/cache/DIA.csv':'a'*64})
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.prepare_first_persisted_candidate_evidence(**a)

 def test_all_live_roles_rejected_before_read(self):
  for path in ('E:/Git/us_ratchet/data/cache/DIA.csv','C:/other/data/cache/QQQ.csv','C:\\other\\DATA\\CACHE\\spy.csv'):
   with self.subTest(path=path),patch.object(Path,'read_bytes',side_effect=AssertionError('Live read forbidden')):
    with self.assertRaises(ValueError):w.no_live({path:'a'*64})

 def test_snapshot_drift_after_publication_preserves_failure(self):
  with tempfile.TemporaryDirectory() as td:
   bindings=file_fixture(Path(td));snapshot=Path(td)/'sources/QQQ.csv';save=w.save
   def altered(path,value,**kwargs):
    out=save(path,value,**kwargs)
    if path.name=='publication.json':snapshot.write_bytes(snapshot.read_bytes()+b'\n')
    return out
   with ExitStack() as stack:
    for key,value in bindings.items():stack.enter_context(patch.object(w,key,value))
    stack.enter_context(patch.object(w,'now',return_value='2026-10-02T20:02:00+00:00'))
    stack.enter_context(patch.object(w,'save',side_effect=altered))
    with self.assertRaisesRegex(ValueError,'Source drift'):w.run(execute=True)
    self.assertTrue((bindings['OUTPUT']/'failure.json').exists())
    self.assertTrue((bindings['OUTPUT']/'publication.json').exists())
    with self.assertRaises(ValueError):w.run(execute=True)


if __name__=='__main__':unittest.main()
