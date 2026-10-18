import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from backtest import ndx_history_failed_lineage_guard_20261008 as h
from scripts import ndx_multidecision_account_inputs_20261003 as producer
from scripts import ndx_multidecision_account_inputs_independent_readback_20261003 as reader

class Tests(unittest.TestCase):
 def test_fixed_diagnostic_guard_never_success_loader(self):
  sources={**h.PINS,str(h.AUDIT):h.AUDIT_SHA}
  for module in (producer,reader):
   with self.subTest(module=module.__name__):
    module.guard(sources)
    self.assertEqual(module.lineage_members(sources),frozenset(h.PINS))
    for path,digest in h.PINS.items():
     with self.assertRaises(ValueError):module.load(dict(path=path,sha256=digest),{})
    with patch.object(module,'LINEAGE_SHA','0'*64),self.assertRaises(ValueError):module.guard(sources)
  self.assertEqual(reader.PRODUCER_SHA,producer.LOADED)
 def test_other_failed_parent_stays_rejected(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'data.json';path.write_bytes(b'{}');path.with_name('failure.json').write_bytes(b'{}')
   for module in (producer,reader):
    with self.subTest(module=module.__name__),self.assertRaises(ValueError):module.guard({str(path):module.sha(b'{}')})

if __name__=='__main__':unittest.main()
