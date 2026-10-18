import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from backtest import ndx_history_failed_lineage_guard_20261008 as h
from scripts import ndx_multidecision_incumbent_execution_20261003 as producer
from scripts import ndx_multidecision_incumbent_execution_independent_readback_20261003 as reader

from scripts import ndx_multidecision_incumbent_inputs_20261003 as inputs_producer
from scripts import ndx_multidecision_incumbent_inputs_independent_readback_20261003 as inputs_reader

class Tests(unittest.TestCase):
 def test_guard_fixed_lineage_and_success_loader_separation(self):
  sources={**h.PINS,str(h.AUDIT):h.AUDIT_SHA}
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);inputs=root/'inputs';inputs.mkdir();execution=root/'execution';execution.mkdir()
   for name in ('started.json','inputs.json','publication.json'):(inputs/name).write_bytes(b'{}')
   with patch.object(producer,'PARENT',inputs),patch.object(reader,'PARENT',execution),patch.object(reader,'INPUT_PATHS',{'inputs':str(inputs/'inputs.json')}):
    producer.guard(sources);reader.guard(sources,set());inputs_producer.guard(sources,{});inputs_reader.guard(sources,{})
    for module in (producer,reader,inputs_producer,inputs_reader):
     self.assertEqual(module.lineage_members(sources),frozenset(h.PINS))
     for path,digest in h.PINS.items():
      with self.assertRaises(ValueError):module.load(dict(path=path,sha256=digest),{})
     with patch.object(module,'LINEAGE_SHA','0'*64),self.assertRaises(ValueError):module.lineage_members(sources)
    unrelated=root/'unrelated';unrelated.mkdir();p=unrelated/'data.json';p.write_bytes(b'{}');p.with_name('failure.json').write_bytes(b'{}');bad={str(p):producer.sha(b'{}')}
    with self.assertRaises(ValueError):producer.guard(bad)
    with self.assertRaises(ValueError):reader.guard(bad,set())
    with self.assertRaises(ValueError):inputs_producer.guard(bad,{})
    with self.assertRaises(ValueError):inputs_reader.guard(bad,{})
  self.assertEqual(reader.PRODUCER[1],producer.LOADED)
  self.assertEqual(inputs_reader.PRODUCER_SHA,inputs_producer.LOADED)

if __name__=='__main__':unittest.main()
