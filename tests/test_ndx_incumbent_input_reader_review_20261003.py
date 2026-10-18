from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_multidecision_incumbent_inputs_independent_readback_20261003 as r
from test_ndx_multidecision_incumbent_inputs_independent_readback_20261003 import sample,resign

class Review(unittest.TestCase):
 def test_resigned_parent_authority_schema_and_original_order(self):
  for attack in ('schema','authority','count','order'):
   x=sample();c=x['candidate']['document']['inputs']
   if attack=='schema':x['candidate']['document']['schema']='FOREIGN'
   elif attack=='authority':c['execution_authorized']=0
   elif attack=='count':c['coordinate_count']=48.0
   else:x['original']['document']['original_control_order']=list(reversed(r.TICKERS))
   c['content_sha256']=r.sha(r.enc({k:v for k,v in c.items() if k!='content_sha256'}));resign(x)
   with self.subTest(attack=attack),self.assertRaises(ValueError):r.inspect_inputs(**x)
 def test_coordinated_underflow_does_not_turn_positive_nominal_into_zero(self):
  x=sample();ch=x['original']['document']['rows'][4]['channel'];day=x['candidate']['document']['inputs']['rows'][0]['tracks'][0]['stateful_input']['calendar'][0];idx=next(i for i,q in enumerate(ch['quote_rows']) if q['session']==day)
  ch['quote_rows'][idx]['nominal_open_exact']='1e-400';ch['quote_rows_sha256']=r.sha(r.enc(ch['quote_rows']));x['saved']['source_slots'][4]['original_row_preserved']=x['original']['document']['rows'][4]
  for lane in x['saved']['rows']:
   for track in lane['tracks']:track['engine_binding']['keyword_arguments']['opens']['data'][0][4]=0.
  resign(x)
  with self.assertRaisesRegex(ValueError,'positive nominal'):r.inspect_inputs(**x)
 def test_started_output_drift_keeps_failure_and_prevents_retry(self):
  from test_ndx_multidecision_incumbent_inputs_20261003 import physical,w
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bound=physical(root);parent=root/'producer'
   with patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',parent),patch.object(w,'resource'):ir=w.run(execute=True)
   save=r.save;out=root/'readback'
   def write(name,value,emergency=False):
    rr=save(name,value,emergency)
    if name=='independent_readback.json':(out/'started.json').write_bytes(b'{}')
    return rr
   with patch.object(r,'BOUND',bound),patch.object(r,'PARENT',parent),patch.object(r,'OUTPUT',out),patch.object(r,'INPUTS_SHA',ir['sha256']),patch.object(r,'PUBLICATION_SHA',r.hashfile(parent/'publication.json')),patch.object(r,'resource'),patch.object(r,'save',side_effect=write):
    with self.assertRaisesRegex(ValueError,'output drift'):r.readback(execute=True)
    with self.assertRaisesRegex(ValueError,'no retry'):r.readback(execute=True)
   self.assertTrue((out/'failure.json').exists())

if __name__=='__main__':unittest.main()
