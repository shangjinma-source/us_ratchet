"""Independent stream source adversarial IO tests; inert synthetic economics only."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from scripts import ndx_double_replacement_stream_worker_20261008 as w
from backtest import ndx_double_replacement_stream_request_research as stream
import test_ndx_double_replacement_stream_worker_20261008 as fixture_module

class Review(unittest.TestCase):
 def test_final_inventory_rejects_link_even_if_same_bytes(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);fixture=fixture_module.StreamWorkerTests();registration,constants=fixture.fixture(root)
   result=json.loads(Path(fixture.execute(registration,constants)['path']).read_bytes());raw=root/'output/batches/000/000000000/raw_return.json.gz'
   original=Path.is_symlink
   with patch.object(Path,'is_symlink',lambda p:p==raw or original(p)):
    with self.assertRaises(ValueError):w.verify_stream_manifest(Path(result['manifest_reference']['path']),stream,result['context'],result['manifest_reference'],root/'output')
 def test_uncalled_terminal_inventory_rechecked_after_result(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);fixture=fixture_module.StreamWorkerTests();registration,constants=fixture.fixture(root);verify=w.verify_stream_manifest;counter=[0]
   def gate(envelope,output,*,phase='batch',remaining_batches=None):
    if phase=='batch':raise MemoryError('synthetic predispatch stop')
   def mutated(*args,**kwargs):
    counter[0]+=1
    if counter[0]==2:(root/'output/batches/000/000000000/raw_return.json.gz').write_bytes(b'unindexed raw')
    return verify(*args,**kwargs)
   with patch.multiple(w,**constants),patch.object(w,'resource_gate',gate),patch.object(w,'verify_stream_manifest',mutated):
    with self.assertRaises(ValueError):w.execute(registration_path=registration['path'],registration_sha256=registration['sha256'],execute=True)
   failure=json.loads((root/'output/requests/request-000000/failure.json').read_bytes())
   self.assertEqual(failure['counts']['unresolved_dispatch_or_raw'],512)
   self.assertEqual(failure['counts']['undispatched'],1)
 def test_full_manifest_append_then_raise_is_unknown_not_undispatched(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);fixture=fixture_module.StreamWorkerTests();registration,constants=fixture.fixture(root);append=w.append_durable
   def interrupted(handle,line):append(handle,line);raise OSError('after durable line')
   with patch.object(w,'append_durable',interrupted),self.assertRaises(OSError):fixture.execute(registration,constants)
   failure=json.loads((root/'output/requests/request-000000/failure.json').read_bytes())
   self.assertEqual(failure['indexed_record_count'],0);self.assertEqual(failure['counts']['unresolved_dispatch_or_raw'],512);self.assertEqual(failure['counts']['undispatched'],1)
   self.assertTrue((root/'output/requests/request-000000/batch_manifest.jsonl').read_bytes().endswith(b'\n'))
 def test_resource_reserve_phase_arithmetic(self):
  envelope=dict(max_uncompressed_bytes=1,max_compressed_bytes=1,memory_bytes=7,disk_bytes=11,initial_capacity_bytes=101,per_remaining_batch_capacity_bytes=31)
  def available(pointer):pointer._obj.available=5*1024**3+7;return 1
  for phase,remaining,wanted in [('initial',None,101),('remaining',2,62),('remaining',0,11),('batch',None,11)]:
   for delta,passes in [(0,True),(-1,False)]:
    with self.subTest(phase=phase,remaining=remaining,delta=delta),patch.object(w.ctypes.windll.kernel32,'GlobalMemoryStatusEx',available),patch.object(w.shutil,'disk_usage',return_value=SimpleNamespace(free=5*1024**3+wanted+delta)):
     if passes:w.resource_gate(envelope,Path.cwd(),phase=phase,remaining_batches=remaining)
     else:
      with self.assertRaisesRegex(ValueError,'DISK'):w.resource_gate(envelope,Path.cwd(),phase=phase,remaining_batches=remaining)
if __name__=='__main__':unittest.main()
