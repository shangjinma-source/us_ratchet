from pathlib import Path
from copy import deepcopy
import tempfile,unittest
from unittest.mock import patch
from contextlib import ExitStack
from scripts import ndx_multidecision_path_comparison_independent_readback_20261003 as r
from scripts import ndx_multidecision_path_comparison_20261003 as p
from test_ndx_multidecision_path_comparison_source_adapter_20261003 import physical

def setup(root):
 bound=physical(root/'sources');out=root/'published'
 with patch.object(p,'BOUND',bound),patch.object(p,'OUTPUT',out),patch.object(p,'ADAPTER',r.ADAPTER):rr=p.run(execute=True)
 return bound,out,rr['sha256'],r.sha((out/'publication.json').read_bytes())
def configured(root,bound,out,h,ph):
 return patch.multiple(r,BOUND=bound,PARENT=out,OUTPUT=root/'readback',COMPARISON_SHA=h,PUBLICATION_SHA=ph,PRODUCER=(str(p.SOURCE),p.LOADED))
class Tests(unittest.TestCase):
 def test_pending_before_any_io(self):
  with patch.object(r,'COMPARISON_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('read')),patch.object(Path,'exists',side_effect=AssertionError('exists')):
   with self.assertRaisesRegex(ValueError,'pending'):r.readback(execute=True)
 def test_real_source_reconstruction_and_independent_arithmetic(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bound,out,h,ph=setup(root)
   with configured(root,bound,out,h,ph):
    rr=r.readback(execute=True)
    with self.assertRaisesRegex(ValueError,'retry'):r.readback(execute=True)
   report=r.decode(Path(rr['path']).read_bytes());self.assertEqual(report['status'],'PASS');self.assertFalse(report['adapter_called']);self.assertFalse(report['comparator_called'])
 def test_resigned_metric_tamper_durable_failure_and_no_retry(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bound,out,h,ph=setup(root);doc=r.decode((out/'comparison.json').read_bytes());raw=r.decode((out/'raw_result.json').read_bytes());pub=r.decode((out/'publication.json').read_bytes())
   doc['comparison']['rows'][8]['candidate']['metrics']['annualized_return_diagnostic_decimal']='123';raw['result']=deepcopy(doc['comparison']);b=r.enc(raw);(out/'raw_result.json').write_bytes(b);rawref=r.ref(out/'raw_result.json',r.sha(b));doc['raw_reference']=rawref;pub['raw_reference']=rawref;b=r.enc(doc);(out/'comparison.json').write_bytes(b);h=r.sha(b);pub['comparison_reference']=r.ref(out/'comparison.json',h);b=r.enc(pub);(out/'publication.json').write_bytes(b);ph=r.sha(b)
   with configured(root,bound,out,h,ph):
    with self.assertRaises(ValueError):r.readback(execute=True)
    with self.assertRaisesRegex(ValueError,'retry'):r.readback(execute=True)
   self.assertTrue((root/'readback/started.json').exists());self.assertTrue((root/'readback/failure.json').exists());self.assertIs(r.decode((root/'readback/failure.json').read_bytes())['arithmetic_inspection_completed'],False)
 def test_published_parent_or_own_drift_preserves_failed_report(self):
  for own in (False,True):
   with self.subTest(own=own),tempfile.TemporaryDirectory() as td:
    root=Path(td);bound,out,h,ph=setup(root);save=r.saved
    def changed(path,value):
     rr=save(path,value)
     if path.name=='independent_readback.json':
      if own:(path.parent/'started.json').write_bytes(b'changed')
      else:(out/'unexpected').write_bytes(b'unknown')
     return rr
    with configured(root,bound,out,h,ph),patch.object(r,'saved',side_effect=changed):
     with self.assertRaises(ValueError):r.readback(execute=True)
    self.assertTrue((root/'readback/failure.json').exists());failure=r.decode((root/'readback/failure.json').read_bytes());self.assertIs(failure['arithmetic_inspection_completed'],True);self.assertEqual(failure['status'],'FAILED_NO_RETRY')
if __name__=='__main__':unittest.main()
