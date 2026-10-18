from pathlib import Path
from copy import deepcopy
import tempfile,unittest
from unittest.mock import patch
from test_ndx_multidecision_path_comparison_independent_readback_20261003 import r,p,setup,configured


class Review(unittest.TestCase):
 def test_independent_full_pipeline_and_post_arithmetic_failure_facts(self):
  from scripts import ndx_multidecision_path_comparison_source_adapter_20261003 as adapter
  from backtest import ndx_multidecision_path_comparison_research as producer
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bound,out,h,ph=setup(root);save=r.saved
   def drift(path,obj):
    rr=save(path,obj)
    if path.name=='independent_readback.json':(out/'alien').write_bytes(b'new')
    return rr
   with configured(root,bound,out,h,ph),patch.object(adapter,'project_inputs',side_effect=AssertionError('adapter')),patch.object(producer,'compare_multidecision_paths',side_effect=AssertionError('producer')),patch.object(r,'saved',side_effect=drift):
    with self.assertRaisesRegex(ValueError,'namespace'):r.readback(execute=True)
    with self.assertRaisesRegex(ValueError,'retry'):r.readback(execute=True)
   report=r.decode((root/'readback/independent_readback.json').read_bytes());failure=r.decode((root/'readback/failure.json').read_bytes())
   self.assertEqual(report['inspection']['track_count'],16)
   self.assertEqual(failure['status'],'FAILED_NO_RETRY');self.assertIs(failure['arithmetic_inspection_completed'],True)

 def test_self_signed_all_four_source_maps_cannot_omit_numerical_dependency(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bound,out,h,ph=setup(root)
   docs={name:r.decode((out/name).read_bytes()) for name in ('started.json','raw_result.json','comparison.json','publication.json')}
   source=str((r.ROOT/'backtest/ndx_cash_fork_reference_window_research.py').resolve())
   for doc in docs.values():del doc['source_hashes'][source]
   def store(name):
    raw=r.enc(docs[name]);(out/name).write_bytes(raw);return r.ref(out/name,r.sha(raw))
   start=store('started.json');docs['raw_result.json']['started_reference']=start;raw=store('raw_result.json')
   docs['comparison.json']['raw_reference']=raw;comparison=store('comparison.json')
   docs['publication.json'].update(started_reference=start,raw_reference=raw,comparison_reference=comparison);pub=store('publication.json')
   with configured(root,bound,out,comparison['sha256'],pub['sha256']):
    with self.assertRaisesRegex(ValueError,'producer source union'):r.readback(execute=True)
   self.assertFalse((root/'readback').exists())


if __name__=='__main__':unittest.main()
