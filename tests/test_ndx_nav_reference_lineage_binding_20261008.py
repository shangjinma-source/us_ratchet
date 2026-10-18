import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from backtest import ndx_history_failed_lineage_guard_20261008 as helper
from scripts import ndx_multidecision_nav_reference_metrics_20261003 as producer
from scripts import ndx_multidecision_nav_reference_metrics_independent_readback_20261003 as reader

class Tests(unittest.TestCase):
 def test_diagnostic_guard_does_not_authorize_success_loading(self):
  sources={**helper.PINS,str(helper.AUDIT):helper.AUDIT_SHA}
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);refs={}
   for role,name in [('alignment','alignment.json'),('account_inputs','inputs.json')]:
    parent=root/role;parent.mkdir()
    for filename in ('started.json',name,'publication.json'):(parent/filename).write_bytes(b'{}')
    refs[role]={'path':str(parent/name)}
   producer.guard(sources,refs);reader.guard(sources,{})
   for module in (producer,reader):
    self.assertEqual(module.lineage_members(sources),frozenset(helper.PINS))
    for path,digest in helper.PINS.items():
     with self.assertRaises(ValueError):module.load(dict(path=path,sha256=digest),{})
    with patch.object(module,'LINEAGE_SHA','0'*64),self.assertRaises(ValueError):module.lineage_members(sources)
   unrelated=root/'unrelated';unrelated.mkdir();p=unrelated/'data.json';p.write_bytes(b'{}');p.with_name('failure.json').write_bytes(b'{}')
   bad={str(p):producer.sha(b'{}')}
   with self.assertRaises(ValueError):producer.guard(bad,refs)
   with self.assertRaises(ValueError):reader.guard(bad,{})
  self.assertEqual(reader.PRODUCER_SHA,producer.LOADED)

 def test_pending_actual_inputs_reject_before_io(self):
  for module in (producer,reader):
   bound=dict(module.BOUND);path,_=bound['account_inputs'];bound['account_inputs']=(path,None)
   with patch.object(module,'BOUND',bound),patch.object(module,'load',side_effect=AssertionError('Unexpected input IO')):
    with self.assertRaisesRegex(ValueError,'pending'):module.load_inputs()

if __name__=='__main__':unittest.main()
