from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from contextlib import ExitStack
from scripts import ndx_multidecision_account_execution_independent_readback_20261003 as r
from scripts import ndx_multidecision_account_execution_20261003 as w
from test_ndx_multidecision_account_execution_20261003 import physical

def setup(root):
 parent,bound=physical(root);out=root/'execution'
 with patch.object(w,'ROOT',root),patch.object(w,'PARENT',parent),patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',out),patch.object(w,'resource'):
  rr=w.run(execute=True)
 pub=w.ref(out/'publication.json',w.hashfile(out/'publication.json'))
 return out,dict(result=(rr['path'],rr['sha256']),publication=(pub['path'],pub['sha256'])),bound

def contexts(root,out,bound,inputs):
 stack=ExitStack()
 for key,value in dict(ROOT=root,PARENT=out,OUTPUT=root/'readback',BOUND=bound,INPUT_PATHS={k:v[0] for k,v in inputs.items()},PRODUCER=(str(w.SOURCE),w.LOADED),CORE=(str(r.ROOT/r.CORE[0]),r.CORE[1])).items():stack.enter_context(patch.object(r,key,value))
 return stack

class Tests(unittest.TestCase):
 def test_pending_before_io(self):
  with tempfile.TemporaryDirectory() as td, patch.object(r,'OUTPUT',Path(td)/'audit'), patch.object(r,'BOUND',{**r.BOUND,'result':(r.BOUND['result'][0],None)}),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'pending'):r.readback(execute=True)
 def test_full_physical16_source_and_independent_ledgers(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);out,bound,inputs=setup(root)
   with contexts(root,out,bound,inputs):
    rr=r.readback(execute=True)
    with self.assertRaisesRegex(ValueError,'retry'):r.readback(execute=True)
   report=r.decode(Path(rr['path']).read_bytes());self.assertEqual(len(report['rows']),16);self.assertEqual(sum(x['inspection'] is not None for x in report['rows']),8);self.assertFalse(report['account_engine_called'])
 def test_published_parent_extra_file_and_own_drift_fail_closed(self):
  for own in (False,True):
   with self.subTest(own=own),tempfile.TemporaryDirectory() as td:
    root=Path(td);out,bound,inputs=setup(root);real=r.saved
    def save(path,obj):
     rr=real(path,obj)
     if path.name=='independent_readback.json':
      if own:(path.parent/'started.json').write_bytes(b'changed')
      else:(out/'unexpected.txt').write_bytes(b'unknown')
     return rr
    with contexts(root,out,bound,inputs),patch.object(r,'saved',side_effect=save):
     with self.assertRaises(ValueError):r.readback(execute=True)
    self.assertTrue((root/'readback/failure.json').exists());self.assertTrue((root/'readback/independent_readback.json').exists())
if __name__=='__main__':unittest.main()
