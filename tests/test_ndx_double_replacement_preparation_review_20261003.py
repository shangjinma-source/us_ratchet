import json,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from test_ndx_double_replacement_preparation_20261003 import physical
from scripts import ndx_double_replacement_preparation_20261003 as m

class Tests(unittest.TestCase):
 def test_interleaved_main_rows_and_no_old_account_read(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);bound,refs=physical(root)
   inputs=m.decode(Path(refs['inputs']['path']).read_bytes());main=inputs['rows'][:40];controls=inputs['rows'][40:]
   inputs['rows']=[x for pair in zip(main[:24],controls) for x in pair]+main[24:]
   def replace(role,body):
    path=Path(refs[role]['path']);raw=m.enc(body);path.write_bytes(raw);refs[role]['sha256']=m.sha(raw);bound[role]=(str(path),m.sha(raw))
   replace('inputs',inputs)
   pub=m.decode(Path(refs['input_publication']['path']).read_bytes());pub['input_reference']=refs['inputs'];replace('input_publication',pub)
   policy=m.decode(Path(refs['policy']['path']).read_bytes());policy['original_inputs_reference']=refs['inputs']
   policy['original_row_references']=[dict(scenario_id=row['scenario_id'],reference={**refs['inputs'],'json_pointer':f'/rows/{i}'}) for i,row in enumerate(inputs['rows']) if row['branch_role']=='MAIN_LANE'];replace('policy',policy)
   actual_read=Path.read_bytes
   def guarded(path):
    if path==m.ROOT/m.ACCOUNT_CLAIM[0]:raise AssertionError('Old account must not be reread')
    return actual_read(path)
   with patch.object(m,'BOUND',bound),patch.object(m,'OUTPUT',root/'out'),patch.object(m,'resource'),patch.object(Path,'read_bytes',guarded):
    result=m.run(execute=True)
   doc=m.decode(Path(result['path']).read_bytes());cases=doc['preparation']['document']['cases']
   self.assertEqual([x['identity']['input_reference']['json_pointer'] for x in cases],['/rows/'+str(i) for i in list(range(0,48,2))+list(range(48,64))])
   self.assertEqual(len(doc['consumed_authenticated_sources']),14)
   self.assertEqual(len(doc['declared_parent_sources']),5)

 def test_self_signed_role_and_false_zero_are_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   bound,refs=physical(Path(tmp))
   with patch.object(m,'BOUND',bound):docs,r,*_=m.load_inputs()
   for attack in ('falsezero','math','risk','policyself','parent','copy'):
    bad=deepcopy(docs)
    if attack=='falsezero':bad['policy']['execution_authorized']=0
    elif attack=='math':bad['policy']['budget_math_reference']['sha256']='0'*64
    elif attack=='risk':bad['policy']['risk_policy']['parameter_override_allowed']=0
    elif attack=='policyself':bad['policy']['action_policy']['action_contract_reference']=r['policy']
    elif attack=='parent':bad['input_publication']['source_hashes']={}
    else:bad['inputs']['rows'][0]['original_scenario']={'wrong':True}
    with self.subTest(attack=attack),self.assertRaises(ValueError):m.project(bad,r)

 def test_last_output_or_parent_drift_retains_raw_and_forbids_retry(self):
  for attack in ('output','parent'):
   with self.subTest(attack=attack),tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);bound,refs=physical(root);save=m.save
    def mutate(name,value,emergency=False):
     result=save(name,value,emergency)
     if name=='publication.json':
      if attack=='output':(root/'out'/'raw_preparation.json').write_bytes(b'changed')
      else:(Path(refs['scenarios']['path']).parent/'failure.json').write_bytes(b'{}')
     return result
    with patch.object(m,'BOUND',bound),patch.object(m,'OUTPUT',root/'out'),patch.object(m,'resource'),patch.object(m,'save',side_effect=mutate):
     with self.assertRaises(ValueError):m.run(execute=True)
     self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertTrue((m.OUTPUT/'raw_preparation.json').exists())
     with self.assertRaisesRegex(ValueError,'No overwrite'):m.run(execute=True)

if __name__=='__main__':unittest.main()
