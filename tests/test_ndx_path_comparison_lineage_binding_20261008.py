import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from backtest import ndx_history_failed_lineage_guard_20261008 as h
from scripts import ndx_multidecision_path_comparison_source_adapter_20261003 as adapter
from scripts import ndx_multidecision_path_comparison_20261003 as producer
from scripts import ndx_multidecision_path_comparison_independent_readback_20261003 as reader

class Tests(unittest.TestCase):
 def test_diagnostic_guard_not_success_role(self):
  sources={**h.PINS,str(h.AUDIT):h.AUDIT_SHA}
  for module in (adapter,reader):
   module.guard(sources,{})
   for path,digest in h.PINS.items():
    with self.assertRaises(ValueError):module.load(dict(path=path,sha256=digest),{})
   with patch.object(module,'LINEAGE_SHA','0'*64),self.assertRaises(ValueError):module.guard(sources,{})
   with tempfile.TemporaryDirectory() as directory:
    p=Path(directory)/'data.json';p.write_bytes(b'{}');p.with_name('failure.json').write_bytes(b'{}')
    with self.assertRaises(ValueError):module.guard({str(p):module.sha(b'{}')},{})
  self.assertEqual(producer.ADAPTER[1],adapter.LOADED)
  self.assertEqual(reader.ADAPTER[1],adapter.LOADED)
  self.assertEqual(reader.PRODUCER[1],producer.LOADED)

if __name__=='__main__':unittest.main()
