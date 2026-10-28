import importlib.util,json,sqlite3,tempfile,unittest,os
from pathlib import Path
from unittest.mock import patch
candidate=os.environ.get('NEWS_PROPOSAL_CACHE_CANDIDATE')
if candidate:
 spec=importlib.util.spec_from_file_location('candidate',candidate);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
else:
 import data.saved_frontier_monthly_view_v1 as m
class Tests(unittest.TestCase):
 def setUp(self):m._expected_proposal_bytes.cache_clear()
 def test_full_key_changed_nested_and_return_not_aliased(self):
  with patch.object(m,'build_frontier_proposal',side_effect=lambda *,target:dict(proposal_id=str(target['nested']['q']))) as build:
   a={'nested':{'q':1}};first=m._expected_proposal_bytes(m.canonical(a));self.assertEqual(first,m._expected_proposal_bytes(m.canonical(a)));self.assertEqual(build.call_count,1)
   a['nested']['q']=2;self.assertNotEqual(first,m._expected_proposal_bytes(m.canonical(a)));self.assertEqual(build.call_count,2)
 def test_database_tamper_still_rejected_after_hit(self):
  with tempfile.TemporaryDirectory() as d,patch.object(m,'build_frontier_proposal',return_value={'proposal_id':'fixed'}) as build:
   store=m.SavedFrontierProposalStore(Path(d)/'p.sqlite3');target={'target_id':'target'};store.bind(target)
   one=store.read(target);one['proposal_id']='caller mutation';self.assertEqual(store.read(target)['proposal_id'],'fixed')
   with sqlite3.connect(store.path) as c:c.execute('update frontier_proposals set document=?',(b'{"proposal_id":"tampered"}',))
   c.close()
   with self.assertRaisesRegex(ValueError,'FRONTIER_PROPOSAL_CHANGED'):store.read(target)
 def test_exception_not_cached_and_bounded(self):
  with patch.object(m,'build_frontier_proposal',side_effect=ValueError('bad')) as b:
   for _ in range(2):
    with self.assertRaises(ValueError):m._expected_proposal_bytes(b'{}')
   self.assertEqual(b.call_count,2)
  with patch.object(m,'build_frontier_proposal',return_value={}):
   for i in range(8):m._expected_proposal_bytes(m.canonical({'q':i}))
   self.assertEqual(m._expected_proposal_bytes.cache_info().currsize,1)
if __name__=='__main__':unittest.main()
