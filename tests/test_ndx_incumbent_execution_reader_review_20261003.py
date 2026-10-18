from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from test_ndx_multidecision_incumbent_execution_readback_20261003 import r,setup,contexts,resign_result


class Review(unittest.TestCase):
 def test_full_readback_never_calls_public_control_or_candidate_engine(self):
  from backtest import ndx_incumbent_flow_split_control_research as control
  from backtest import ndx_dynamic_fractional_flow_split_research_v2 as fraction
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);out,bound,inputs=setup(root)
   with contexts(root,out,bound,inputs),patch.object(control,'simulate_incumbent_flow_split_control',side_effect=AssertionError('control called')),patch.object(fraction,'simulate_dynamic_fractional_flow_split_research',side_effect=AssertionError('candidate called')):
    rr=r.readback(execute=True)
   report=r.decode(Path(rr['path']).read_bytes())
   self.assertEqual(len(report['rows']),16)
   self.assertTrue(all(x['inspection']['status']=='PASS' for x in report['rows']))
   self.assertFalse(report['control_engine_called']);self.assertFalse(report['candidate_engine_called'])

 def test_self_signed_helper_omission_and_slot_authority_rejected(self):
  for omitted in (True,False):
   with self.subTest(omitted=omitted),tempfile.TemporaryDirectory() as td:
    root=Path(td);out,bound,inputs=setup(root);d=r.decode((out/'result.json').read_bytes())
    if omitted:
     path=str((r.ROOT/'backtest/ndx_dynamic_fractional_flow_split_research.py').resolve())
     del d['source_hashes'][path]
     pub=r.decode((out/'publication.json').read_bytes());pub['source_hashes']=deepcopy(d['source_hashes']);(out/'publication.json').write_bytes(r.enc(pub))
    else:
     row=d['rows'][1];raw=r.decode(Path(row['raw_reference']['path']).read_bytes());raw['actual_orders_executed']=0
     data=r.enc(raw);Path(row['raw_reference']['path']).write_bytes(data);row['raw_reference']['sha256']=r.sha(data)
     post=r.decode(Path(row['postcheck_reference']['path']).read_bytes());post['raw_reference']=deepcopy(row['raw_reference']);data=r.enc(post);Path(row['postcheck_reference']['path']).write_bytes(data);row['postcheck_reference']['sha256']=r.sha(data)
    bad=resign_result(out,bound,d)
    with contexts(root,out,bad,inputs):
     with self.assertRaisesRegex(ValueError,'source union' if omitted else 'authority False'):r.readback(execute=True)
     if not omitted:
      failure=r.decode((r.OUTPUT/'failure.json').read_bytes());self.assertEqual(failure['completed_track_count'],1)
      self.assertEqual(len(failure['completed_track_inspections']),1)
      with self.assertRaisesRegex(ValueError,'retry'):r.readback(execute=True)


if __name__=='__main__':unittest.main()
