from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_multidecision_account_execution_independent_readback_20261003 as r
from test_ndx_multidecision_account_execution_readback_20261003 import setup,contexts

def write(path,obj):
 p=Path(path);p.write_bytes(r.enc(obj));return r.ref(p,r.hashfile(p))

class Review(unittest.TestCase):
 def test_self_signed_wrong_ledger_still_creates_one_failed_attempt(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);out,bound,inputs=setup(root)
   result=r.decode((out/'result.json').read_bytes());row=result['rows'][8];raw=r.decode(Path(row['raw_reference']['path']).read_bytes());raw['result']['daily'][-1]['cash_usd']+=1
   row['raw_reference']=write(row['raw_reference']['path'],raw)
   post=r.decode(Path(row['postcheck_reference']['path']).read_bytes());post['raw_reference']=row['raw_reference'];row['postcheck_reference']=write(row['postcheck_reference']['path'],post)
   rr=write(out/'result.json',result);pub=r.decode((out/'publication.json').read_bytes());pub['result_reference']=rr;pr=write(out/'publication.json',pub);bound=dict(result=(rr['path'],rr['sha256']),publication=(pr['path'],pr['sha256']))
   with contexts(root,out,bound,inputs):
    with self.assertRaises(ValueError):r.readback(execute=True)
    self.assertTrue((root/'readback/failure.json').exists(),'Numeric readback failure must be durable')
    with self.assertRaisesRegex(ValueError,'retry'):r.readback(execute=True)
   self.assertFalse((root/'readback/independent_readback.json').exists())
 def test_postreport_original_input_directory_drift_is_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);out,bound,inputs=setup(root);save=r.saved
   def saved(path,obj):
    rr=save(path,obj)
    if path.name=='independent_readback.json':(Path(inputs['inputs'][0]).parent/'unexpected').write_bytes(b'new')
    return rr
   with contexts(root,out,bound,inputs),patch.object(r,'saved',side_effect=saved):
    with self.assertRaises(ValueError):r.readback(execute=True)
   self.assertTrue((root/'readback/failure.json').exists())

if __name__=='__main__':unittest.main()
