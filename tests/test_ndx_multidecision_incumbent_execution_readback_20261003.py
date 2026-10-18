from pathlib import Path
import tempfile,unittest
from copy import deepcopy
from unittest.mock import patch
from contextlib import ExitStack
from scripts import ndx_multidecision_incumbent_execution_independent_readback_20261003 as r
from scripts import ndx_multidecision_incumbent_execution_20261003 as w
from test_ndx_multidecision_incumbent_execution_20261003 import physical_execution_sources

def setup(root):
 parent,bound=physical_execution_sources(root);out=root/'execution'
 with patch.object(w,'PARENT',parent),patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',out),patch.object(w,'resource'):rr=w.run(execute=True)
 pub=w.ref(out/'publication.json',w.hashfile(out/'publication.json'))
 return out,dict(result=(rr['path'],rr['sha256']),publication=(pub['path'],pub['sha256'])),bound

def contexts(root,out,bound,inputs):
 stack=ExitStack()
 for key,value in dict(PARENT=out,OUTPUT=root/'readback',BOUND=bound,INPUT_PATHS={k:v[0] for k,v in inputs.items()}).items():stack.enter_context(patch.object(r,key,value))
 return stack

def resign_result(out,bound,d):
 raw=r.enc(d);(out/'result.json').write_bytes(raw);rr=r.ref(out/'result.json',r.sha(raw));pub=r.decode((out/'publication.json').read_bytes());pub['result_reference']=rr;raw=r.enc(pub);(out/'publication.json').write_bytes(raw)
 return dict(result=(rr['path'],rr['sha256']),publication=(str((out/'publication.json').resolve()),r.sha(raw)))

class Tests(unittest.TestCase):
 def test_pending_before_io(self):
  with tempfile.TemporaryDirectory() as td, patch.object(r,'OUTPUT',Path(td)/'audit'), patch.object(r,'BOUND',{**r.BOUND,'result':(r.BOUND['result'][0],None)}),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'pending'):r.readback(execute=True)
 def test_full_physical16_literal_control_source_and_ledgers(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);out,bound,inputs=setup(root)
   with contexts(root,out,bound,inputs):
    rr=r.readback(execute=True)
    with self.assertRaisesRegex(ValueError,'retry'):r.readback(execute=True)
   report=r.decode(Path(rr['path']).read_bytes());self.assertEqual(len(report['rows']),16);self.assertEqual(sum(x['inspection'] is not None for x in report['rows']),16);self.assertFalse(report['control_engine_called']);self.assertFalse(report['weights_normalized'])
 def test_raw_cash_resigned_failure_durable_and_mapping_swapped_rejected(self):
  for cash in (True,False):
   with self.subTest(cash=cash),tempfile.TemporaryDirectory() as td:
    root=Path(td);out,bound,inputs=setup(root);d=r.decode((out/'result.json').read_bytes())
    if cash:
     row=d['rows'][0];raw=r.decode(Path(row['raw_reference']['path']).read_bytes());raw['result']['daily'][1]['cash_usd']+=1.;data=r.enc(raw);Path(row['raw_reference']['path']).write_bytes(data);row['raw_reference']['sha256']=r.sha(data)
     post=r.decode(Path(row['postcheck_reference']['path']).read_bytes());post['raw_reference']=deepcopy(row['raw_reference']);data=r.enc(post);Path(row['postcheck_reference']['path']).write_bytes(data);row['postcheck_reference']['sha256']=r.sha(data)
    else:d['candidate_mapping_preserved'][0]['tracks'][0]['candidate_input_reference']['json_pointer']='/inputs/rows/7/tracks/0'
    bad=resign_result(out,bound,d)
    with contexts(root,out,bad,inputs):
     with self.assertRaises(ValueError):r.readback(execute=True)
    if cash:self.assertTrue((root/'readback/failure.json').exists());self.assertEqual(r.decode((root/'readback/failure.json').read_bytes())['completed_track_count'],0)
 def test_blocked_control_never_uses_candidate_cash_or_calls_inspection(self):
  track=dict(track='CONTINUOUS',status='BLOCKED_ORIGINAL_CONTROL_INPUT',blocking_reasons=['MISSING_ORIGINAL_CONTROL_QUOTES'])
  row=dict(track_index=0,fx_mode=r.MODES[0],lane=r.LANES[0],track='CONTINUOUS',outcome='BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT',call_invoked=False,returned_call_count=0,started_reference={'path':'/synthetic/start','sha256':'a'*64},raw_reference=None,postcheck_reference={'path':'/synthetic/post','sha256':'b'*64},blocking_reasons=deepcopy(track['blocking_reasons']))
  start=dict(schema='MULTIDECISION_INCUMBENT_ACCOUNT_TRACK_STARTED_V1',track_index=0,coordinate=[r.MODES[0],r.LANES[0],'CONTINUOUS'],input_pointer='/inputs/rows/0/tracks/0',prepared_track=track,**r.FLAGS)
  post=dict(schema='MULTIDECISION_INCUMBENT_ACCOUNT_TRACK_POSTCHECK_V1',**deepcopy(row),**r.FLAGS);post['postcheck_reference']=None
  self.assertIsNone(r.inspect_slot(row=row,track=track,start=start,post=post,raw=None,inspection=None))
  row['returned_call_count']=False;post['returned_call_count']=False
  with self.assertRaises(ValueError):r.inspect_slot(row=row,track=track,start=start,post=post,raw=None,inspection=None)
 def test_after_publication_original_parent_inventory_and_own_started_drift(self):
  for parent in (True,False):
   with self.subTest(parent=parent),tempfile.TemporaryDirectory() as td:
    root=Path(td);out,bound,inputs=setup(root);real=r.saved
    def save(path,obj):
     rr=real(path,obj)
     if path.name=='independent_readback.json':
      if parent:(Path(inputs['inputs'][0]).parent/'unknown').write_bytes(b'x')
      else:(path.parent/'started.json').write_bytes(b'changed')
     return rr
    with contexts(root,out,bound,inputs),patch.object(r,'saved',side_effect=save):
     with self.assertRaises(ValueError):r.readback(execute=True)
    self.assertTrue((root/'readback/failure.json').exists())
if __name__=='__main__':unittest.main()
