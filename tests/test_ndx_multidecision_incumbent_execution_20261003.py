import unittest,tempfile,sys
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from scripts import ndx_multidecision_incumbent_execution_20261003 as e
from test_ndx_multidecision_incumbent_inputs_20261003 import physical,w
from scripts import ndx_multidecision_incumbent_inputs_independent_readback_20261003 as audit


def physical_execution_sources(root):
 bound=physical(root);parent=root/'prepared'
 with patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',parent):ir=w.run(execute=True)
 with patch.object(audit,'BOUND',bound),patch.object(audit,'PARENT',parent),patch.object(audit,'OUTPUT',root/'audit'),patch.object(audit,'INPUTS_SHA',ir['sha256']),patch.object(audit,'PUBLICATION_SHA',audit.hashfile(parent/'publication.json')):ar=audit.readback(execute=True)
 refs=dict(inputs=ir,publication=e.ref(parent/'publication.json',e.hashfile(parent/'publication.json')),readback=ar,reader=e.ref(audit.SOURCE,e.hashfile(audit.SOURCE)))
 return parent,{k:(r['path'],r['sha256']) for k,r in refs.items()}

class Tests(unittest.TestCase):
 def test_physical_full16_private_controls_without_global_mutation(self):
  from backtest import ndx_dynamic_whole_lot_repair_path as old
  original=old._risk_snapshot;before=set(sys.modules)
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);parent,bound=physical_execution_sources(root)
   with patch.object(e,'BOUND',bound),patch.object(e,'PARENT',parent),patch.object(e,'OUTPUT',root/'execution'):
    ref=e.run(execute=True);r=e.decode(Path(ref['path']).read_bytes());self.assertEqual(r['account_call_count'],16);self.assertEqual(r['returned_call_count'],16);self.assertIsNone(r['failure'])
    for row in r['rows']:
     raw=e.decode(Path(row['raw_reference']['path']).read_bytes());self.assertFalse(raw['result']['risk_is_order_gate']);self.assertFalse(raw['result']['weights_normalized']);started=e.decode(Path(row['started_reference']['path']).read_bytes());self.assertEqual([d['session'] for d in raw['result']['daily']],started['prepared_track']['engine_binding']['keyword_arguments']['closes']['index'])
    with self.assertRaisesRegex(ValueError,'Exclusive'):e.run(execute=True)
  self.assertIs(old._risk_snapshot,original);self.assertFalse(any(name.startswith('_private_account_') for name in set(sys.modules)-before))
 def test_pending_before_io(self):
  b=deepcopy(e.BOUND);b['inputs']=(b['inputs'][0],None)
  with patch.object(e,'BOUND',b),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'pending'):e.load_inputs()
 def test_return_none_preserved_then_full_partition_stops(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);parent,bound=physical_execution_sources(root)
   with patch.object(e,'BOUND',bound),patch.object(e,'PARENT',parent),patch.object(e,'OUTPUT',root/'execution'):
    c=e.load_inputs();c['engines']['CONTINUOUS']=lambda **kw:None
    with patch.object(e,'load_inputs',return_value=c):
     with self.assertRaisesRegex(ValueError,'technical failure'):e.run(execute=True)
    r=e.decode((e.OUTPUT/'result.json').read_bytes());self.assertEqual(len(r['rows']),16);self.assertEqual(r['rows'][0]['outcome'],'VALIDATION_FAILURE');self.assertEqual(r['counts']['UNDISPATCHED'],15)
    raw=e.decode(Path(r['rows'][0]['raw_reference']['path']).read_bytes());self.assertTrue(raw['returned']);self.assertIsNone(raw['result']);self.assertTrue((e.OUTPUT/'failure.json').exists())
 def test_exception_is_not_zero_return_or_risk_failure(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);parent,bound=physical_execution_sources(root)
   with patch.object(e,'BOUND',bound),patch.object(e,'PARENT',parent),patch.object(e,'OUTPUT',root/'execution'):
    c=e.load_inputs()
    def fail(**kw):raise ArithmeticError('synthetic failure')
    c['engines']['CONTINUOUS']=fail
    with patch.object(e,'load_inputs',return_value=c):
     with self.assertRaises(ValueError):e.run(execute=True)
    r=e.decode((e.OUTPUT/'result.json').read_bytes());self.assertEqual(r['rows'][0]['outcome'],'NUMERICAL_EXCEPTION');raw=e.decode(Path(r['rows'][0]['raw_reference']['path']).read_bytes());self.assertFalse(raw['returned']);self.assertEqual(raw['returned_call_count'],0)

if __name__=='__main__':unittest.main()
