"""Independent reader closure attacks on synthetic saved data, no true points."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from scripts import ndx_double_replacement_stream_independent_readback_20261008 as r
from backtest import ndx_double_replacement_compressed_raw_inspection_research as decoder
import test_ndx_double_replacement_stream_independent_readback_20261008 as fixtures

class Review(unittest.TestCase):
 def test_failed_existing_inspection_is_not_ignored(self):
  for filename in ('inspection.json','raw_byte_inspection.json'):
   with self.subTest(filename=filename),tempfile.TemporaryDirectory() as directory:
    root=Path(directory);factory=fixtures.StreamReadbackTests();registration,patches=factory.fixture(root,'postcheck')
    result=json.loads((patches['REQUEST']/'result.json').read_bytes());folder=root/'output/batches/000/000000000';envelope=json.loads((folder/'stream_result.json').read_bytes());reference=dict(path=str(folder/'stream_result.json'),sha256=r.filehash(folder/'stream_result.json'))
    with patch.multiple(r,**patches):envelope,files,state,failed=r.batch_evidence(reference,0,3*1024**2)
    path=folder/filename;path.write_bytes(r.encode(dict(schema='WRONG_ROLE',execution_authorized=True)))
    files[filename]=dict(path=str(path),sha256=r.filehash(path),byte_count=path.stat().st_size)
    domain=SimpleNamespace(task_page=lambda prepared,start,limit:dict(tasks=[dict(synthetic_id=i) for i in range(start,start+limit)]))
    def reject(**kwargs):raise ValueError('synthetic postcheck')
    with self.assertRaises((ValueError,KeyError)):
     r.inspect_batch(envelope,files,state,failed,descriptor=state['descriptor'],prepared={},domain=domain,inspector=SimpleNamespace(inspect_explicit_evaluations=reject),decoder=decoder,resource=dict(max_uncompressed_bytes=2**20,max_compressed_bytes=2**20),registration_ref=registration,started_ref=result['started_reference'],perform_arithmetic=True)
 def test_extra_registration_role_rejected_before_context(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);factory=fixtures.StreamReadbackTests();registration,patches=factory.fixture(root,'success',1)
   rp=Path(registration['path']);reg=json.loads(rp.read_bytes());extra=root/'extra';extra.write_bytes(b'unregistered');reg['input_references']['extra']=dict(path=str(extra),sha256=r.filehash(extra));rp.write_bytes(r.encode(reg));old=registration['sha256'];registration['sha256']=r.filehash(rp)
   resultpath=patches['REQUEST']/'result.json';result=json.loads(resultpath.read_bytes());result['registration_reference']=registration;result['source_hashes'][str(rp)]=registration['sha256'];result['source_hashes'][str(extra)]=r.filehash(extra);resultpath.write_bytes(r.encode(result));patches['REQUEST_RESULT_SHA']=r.filehash(resultpath)
   original=r.load_module
   def module(name,*args,**kwargs):
    value=original(name,*args,**kwargs)
    if name=='partition':value.context=lambda **kw:(_ for _ in ()).throw(AssertionError('invalid role set reached context'))
    return value
   with patch.object(r,'load_module',module),self.assertRaises(ValueError):factory.readback(registration,patches)

if __name__=='__main__':unittest.main()
