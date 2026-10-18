from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import tempfile,unittest
from scripts import ndx_multidecision_target_scoring_inputs_20261003 as m
from test_ndx_multidecision_target_scoring_inputs_20261003 import fixture,alignment_core,target_core
class Review(unittest.TestCase):
 def test_original_roles_calendar_and_source_counts_fail_closed(self):
  docs,refs=fixture();before=deepcopy(docs);args=m.project_inputs(docs,refs);self.assertEqual(docs,before);self.assertEqual(len(args['nav_rows']),1101);self.assertEqual(len(args['fx_rows']),6975)
  for f in (lambda d:d['fx_readback']['table_rows'][0]['source_reference'].update(table_row_index=False),lambda d:d['nav_snapshot']['immutable_copies']['nav.csv'].update(sha256='0'*64),lambda d:d['history'].update(execution_authorized=0),lambda d:d['history']['requirements']['reference_calendar']['dates'].reverse()):
   bad=deepcopy(docs);f(bad)
   with self.assertRaises(ValueError):m.project_inputs(bad,refs)
 def test_alignment_drift_after_publication_fails_and_no_retry(self):
  docs,refs=fixture();original=m.save
  with tempfile.TemporaryDirectory() as tmp:
   def save(p,v,failure=False):
    out=original(p,v,failure)
    if p.name=='publication.json':(p.parent/'alignment.json').write_bytes(b'changed')
    return out
   with patch.object(m,'OUTPUT',Path(tmp)/'out'),patch.object(m,'load_inputs',return_value=(docs,refs,{},alignment_core,target_core)),patch.object(m,'guard'),patch.object(m,'save',side_effect=save),patch('shutil.disk_usage',return_value=type('D',(),{'free':10**12})()):
    with self.assertRaisesRegex(ValueError,'Final output drift'):m.run(execute=True)
    self.assertTrue((m.OUTPUT/'publication.json').exists());self.assertTrue((m.OUTPUT/'failure.json').exists())
    with self.assertRaisesRegex(ValueError,'Immutable'):m.run(execute=True)
if __name__=='__main__':unittest.main()
