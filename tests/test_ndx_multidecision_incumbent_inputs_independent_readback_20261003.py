import unittest,tempfile
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from scripts import ndx_multidecision_incumbent_inputs_independent_readback_20261003 as r
from test_ndx_multidecision_incumbent_inputs_research import fixture,m


def sample():
 a=fixture();s=m.prepare_incumbent_account_inputs(**a)
 return dict(saved=s,candidate={k:v for k,v in a['candidate_evidence'].items() if k!='references'},original={k:v for k,v in a['original_eight_evidence'].items() if k!='references'},candidate_refs=a['candidate_evidence']['references'],original_refs=a['original_eight_evidence']['references'])
def resign(x):x['saved']['content_sha256']=r.sha(r.enc({k:v for k,v in x['saved'].items() if k!='content_sha256'}))

class Tests(unittest.TestCase):
 def test_complete_independent_projection(self):
  x=sample();before=r.enc(x);out=r.inspect_inputs(**x);self.assertEqual(out['track_count'],16);self.assertEqual(out['control_security_count'],8);self.assertEqual(r.enc(x),before)
 def test_re_signed_wrong_value_identity_flow_and_missing(self):
  for attack in ('price','TSM','flow','missing','weight','source'):
   x=sample();t=x['saved']['rows'][0]['tracks'][0]
   if attack=='price':t['engine_binding']['keyword_arguments']['opens']['data'][0][4]+=1
   elif attack=='TSM':x['saved']['source_slots'][4]['candidate_universe_member_claimed']=True
   elif attack=='flow':t['engine_binding']['keyword_arguments']['external_flows']=[{'amount_usd':1000}]
   elif attack=='missing':t['candidate_blocking_reasons_preserved']=[]
   elif attack=='weight':t['engine_binding']['keyword_arguments']['schedule'][0]['targets']['CONTROL:TSM']['target_weight']=.5
   else:x['saved']['source_hashes'].pop(next(iter(x['saved']['source_hashes'])))
   resign(x)
   with self.assertRaises(ValueError):r.inspect_inputs(**x)
 def test_pending_no_io(self):
  with patch.object(r,'INPUTS_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'pending'):r.load_inputs()
 def test_physical_full_chain_and_final_drift_no_retry(self):
  from test_ndx_multidecision_incumbent_inputs_20261003 import physical,w
  for damage in (False,True):
   with tempfile.TemporaryDirectory() as td:
    root=Path(td);bound=physical(root);parent=root/'publisher'
    with patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',parent):ir=w.run(execute=True)
    original=r.save
    def save(name,value,emergency=False):
     rr=original(name,value,emergency)
     if damage and name=='independent_readback.json':(root/'original'/'unexpected').write_bytes(b'x')
     return rr
    with patch.object(r,'BOUND',bound),patch.object(r,'PARENT',parent),patch.object(r,'OUTPUT',root/'reader'),patch.object(r,'INPUTS_SHA',ir['sha256']),patch.object(r,'PUBLICATION_SHA',r.hashfile(parent/'publication.json')),patch.object(r,'save',side_effect=save):
     if damage:
      with self.assertRaisesRegex(ValueError,'inventory drift'):r.readback(execute=True)
      self.assertTrue((r.OUTPUT/'failure.json').exists())
     else:
      rr=r.readback(execute=True);self.assertEqual(r.decode(Path(rr['path']).read_bytes())['inspection']['track_count'],16)
      with self.assertRaisesRegex(ValueError,'no retry'):r.readback(execute=True)

if __name__=='__main__':unittest.main()
