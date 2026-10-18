from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_multidecision_nav_reference_metrics_20261003 as w
from test_ndx_multidecision_nav_reference_metrics_20261003 import physical

class Review(unittest.TestCase):
 def test_private_reference_only_and_binary64_free_window_metrics(self):
  from backtest import ndx_multidecision_reference_metrics_research as shared
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bound=physical(root,missing=True)
   with patch.object(w,'ROOT',root),patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',root/'out'),patch.object(w,'resource'),patch.object(shared,'reference_metrics',side_effect=AssertionError('stale shared implementation')),patch.object(shared,'account_twr_metrics',side_effect=AssertionError('no account calculations')):
    rr=w.run(execute=True)
   d=w.decode(Path(rr['path']).read_bytes());m=d['metrics']['modes']
   self.assertIsNone(m[w.MODES[0]]['metrics']);self.assertEqual(len(m[w.MODES[0]]['observations']),120)
   self.assertEqual(m[w.MODES[1]]['metrics']['interval_count'],119)
   self.assertEqual(m[w.MODES[1]]['metrics']['maximum_drawdown'],{'numerator':'1','denominator':'2'})
   self.assertFalse(d['formal_comparison_passed']);self.assertFalse(d['subscription_redemption_modeled'])
 def test_final_parent_extra_file_and_return_preservation(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bound=physical(root);real=w.save
   def save(name,obj,emergency=False):
    rr=real(name,obj,emergency)
    if name=='publication.json':(Path(bound['account_inputs'][0]).parent/'unbound.json').write_bytes(b'{}')
    return rr
   with patch.object(w,'ROOT',root),patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',root/'out'),patch.object(w,'resource'),patch.object(w,'save',side_effect=save):
    with self.assertRaisesRegex(ValueError,'Exact original parent namespace'):w.run(execute=True)
    with self.assertRaisesRegex(ValueError,'Create only'):w.run(execute=True)
   self.assertTrue((root/'out/failure.json').exists());self.assertTrue((root/'out/publication.json').exists())
   raw=w.decode((root/'out/raw_result.json').read_bytes());self.assertTrue(raw['returned']);self.assertEqual(raw['returned_call_count'],1)

if __name__=='__main__':unittest.main()
