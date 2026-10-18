from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from fractions import Fraction
import tempfile,unittest
from backtest import ndx_multidecision_scoring_history_inspection_v2_research as c
from scripts import ndx_multidecision_scoring_history_independent_readback_v2_20261003 as r
from test_ndx_scoring_history_readback_v2_20261003 import compound,bind_event,saved_case
class Review(unittest.TestCase):
 def test_original_numeric_expectation_survives_both_reference_variants(self):
  a,d=saved_case();reference=compound();reference['additional_execution_raw_reference']=dict(path='extra.raw',sha256='a'*64);bind_event(a,d,reference);before=deepcopy((a,d))
  self.assertEqual(c.inspect_scoring_history_channel(saved_channel=d,**a)['window_count'],78);self.assertEqual((a,d),before)
  self.assertTrue(all(Fraction(x['split_only_return_exact'])==0 for x in d['return_rows']))
  d['quote_rows'][0]['nominal_close_exact']='1';d['quote_rows_sha256']=c.digest(d['quote_rows']);d['content_sha256']=c.digest({k:v for k,v in d.items()if k!='content_sha256'})
  with self.assertRaises(ValueError):c.inspect_scoring_history_channel(saved_channel=d,**a)
 def test_no_generic_object_or_role_substitution(self):
  for f in (lambda x:x.update(event_index=False),lambda x:x.update(event_index=1.0),lambda x:x.update(parent=deepcopy(x['original_raw_reference'])),lambda x:x.update(additional_execution_raw_reference=False),lambda x:x['original_raw_reference'].update(json_pointer='/x'),lambda x:x['parent'].update(sha256='0'*64)):
   value=compound();f(value)
   with self.assertRaises(ValueError):c.event_reference(value)
 def test_previous_failure_whole_bytes_count_and_namespace(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);old=root/'old';old.mkdir();prior={};index=r.ref(root/'index','a'*64);pub=r.ref(root/'pub','b'*64)
   def put(role,p,obj):
    b=obj if isinstance(obj,bytes) else r.encoded(obj);p.write_bytes(b);prior[role]=(str(p),r.sha(b))
   put('reader',root/'reader',b'not executable');put('inspector',root/'core',b'not executable')
   put('started',old/'started.json',dict(schema='MULTIDECISION_SCORING_HISTORY_READBACK_STARTED_V1',reader_sha256=prior['reader'][1],retry_allowed=False,index_reference=index,publication_reference=pub))
   failure=dict(completed_channel_count=6,remaining_channel_count=71,error='Reference',error_type='ValueError',retry_allowed=False,status='FAILED_DO_NOT_CONSUME');put('failure',old/'failure.json',failure)
   with patch.object(r,'PREVIOUS_ATTEMPT',prior):
    self.assertEqual(len(r.previous_evidence({},index,pub)),4)
    failure['completed_channel_count']=6.0;put('failure',old/'failure.json',failure)
    with self.assertRaises(ValueError):r.previous_evidence({},index,pub)
    failure['completed_channel_count']=6;put('failure',old/'failure.json',failure);(old/'unexpected').write_bytes(b'')
    with self.assertRaises(ValueError):r.previous_evidence({},index,pub)
if __name__=='__main__':unittest.main()
