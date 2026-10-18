import json,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from test_ndx_single_replacement_domain_research import fixture
from scripts import ndx_single_replacement_preparation_20261003 as m

def physical(root):
 bound={};docs={};refs={}
 def add(role,name,body=None,raw=None):
  p=root/name;p.parent.mkdir(parents=True,exist_ok=True);b=raw if raw is not None else m.enc(body);p.write_bytes(b)
  bound[role]=(str(p),m.sha(b));refs[role]=dict(path=str(p),sha256=m.sha(b));docs[role]=body;return refs[role]
 original=fixture()['original_rows'][0]['input_row']
 originals=[dict(i=i,label='中文原证据') for i in range(40)]
 add('inventory','inventory/inventory.json',dict(rows=originals));add('inventory_publication','inventory/publication.json',dict(schema='CONDITIONAL_CASH_INVENTORY_V2_PUBLICATION_RECEIPT_V1',status='SOURCE_LOCKED_INVENTORY_ONLY_NOT_FORK_READY',fork_executed=False,inventory_reference=refs['inventory']))
 add('scenarios','scenarios/scenarios.json',dict(rows=originals))
 for role in ('core','risk_semantics'):
  path,h=m.BOUND[role];add(role,role+'.py',raw=(m.ROOT/path).read_bytes())
 for role in ('input_producer','historical_input_readback_note','historical_topup_audit_note','historical_topup_reader'):add(role,role+'.txt',raw=b'Synthetic historical role only')
 rows=[]
 for i in range(40):
  r=deepcopy(original);r['scenario_id']='case'+str(i);r['original_inventory_row']=r['original_scenario']=originals[i]
  r['scenario_reference']={**refs['scenarios'],'json_pointer':f'/rows/{i}'};r['inventory_row_reference']={**refs['inventory'],'json_pointer':f'/rows/{i}'};rows.append(r)
 source={refs[k]['path']:refs[k]['sha256'] for k in ('inventory','inventory_publication','scenarios','input_producer')};source[str(m.ROOT/m.ACCOUNT_CLAIM[0])]=m.ACCOUNT_CLAIM[1]
 inp=dict(schema='REMAINING_STANDARD_CASH_INPUTS_V1',scenario_count=64,rows=rows+[dict(branch_role='CONTROL') for _ in range(24)],source_hashes=source,**dict.fromkeys(m.PARENT_FLAGS,False))
 add('inputs','inputs/inputs.json',inp);add('input_publication','inputs/publication.json',dict(schema='REMAINING_STANDARD_CASH_INPUTS_PUBLICATION_V1',status='INPUTS_ONLY_NOT_EXECUTED',input_reference=refs['inputs'],source_hashes=source,**dict.fromkeys(m.PARENT_FLAGS,False)))
 p=dict(schema='SINGLE_REPLACEMENT_CASH_ACTION_POLICY_REGISTRATION_V1',status='ECONOMIC_DOMAIN_POLICY_FIXED_BEFORE_NEW_PREPARATION_NOT_EXECUTION_PERMISSION',original_inputs_reference=refs['inputs'],domain_core_reference=refs['core'],
  action_policy={**fixture()['action_contract']},risk_policy=dict(original_parameters=original['risk_parameters']),original_row_references=[dict(scenario_id=r['scenario_id'],reference={**refs['inputs'],'json_pointer':f'/rows/{i}'}) for i,r in enumerate(rows)],
  **dict.fromkeys(('source_preparation_authorized','evaluation_authorized','execution_authorized','point_in_time_verified','future_independent_oos','quantity_caps_computed','risk_evaluated'),False))
 p['action_policy'].pop('domain_core_reference');p['action_policy'].pop('action_contract_reference');p['action_policy']['expected_scenario_ids']=[r['scenario_id'] for r in rows]
 add('policy','policy.json',p)
 return bound,refs

class Tests(unittest.TestCase):
 def test_unmocked_physical40_private_core_unicode_and_direct_scope(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);bound,refs=physical(root)
   with patch.object(m,'BOUND',bound),patch.object(m,'OUTPUT',root/'out'),patch.object(m,'resource'):
    result=m.run(execute=True)
    out=json.loads(Path(result['path']).read_bytes())
    self.assertEqual(out['preparation']['document']['scenario_count'],40)
    self.assertNotIn(str(m.ROOT/m.ACCOUNT_CLAIM[0]),out['consumed_authenticated_sources'])
    self.assertIn(str(m.ROOT/m.ACCOUNT_CLAIM[0]),out['declared_parent_sources'])
    self.assertIs(out['full_transitive_source_closure_reverified'],False)
    with self.assertRaises(ValueError):m.run(execute=True)

 def test_bad_source_copy_rejected_and_pending_before_read(self):
  with tempfile.TemporaryDirectory() as tmp:
   bound,refs=physical(Path(tmp))
   with patch.object(m,'BOUND',bound):
    d,r,s,rows,c,core=m.load_inputs();d['inputs']['rows'][0]['original_inventory_row']={'wrong':True}
    with self.assertRaises(ValueError):m.project(d,r)
   bound['policy']=(bound['policy'][0],None)
   with patch.object(m,'BOUND',bound),patch.object(Path,'read_bytes',side_effect=AssertionError('No IO')):
    with self.assertRaises(ValueError):m.load_inputs()

 def test_returned_before_guard_failure_and_interrupt_preserved(self):
  for mode in ('drift','interrupt','none'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);bound,refs=physical(root)
    with patch.object(m,'BOUND',bound),patch.object(m,'OUTPUT',root/'out'),patch.object(m,'resource'):
     context=m.load_inputs();core=context[-1];original=core.prepare_single_replacement_domain
     def call(*args):
      if mode=='interrupt':raise KeyboardInterrupt('original')
      if mode=='none':return None
      value=original(*args);Path(refs['policy']['path']).write_bytes(b'drift');return value
     core.prepare_single_replacement_domain=call
     with patch.object(m,'load_inputs',return_value=context),self.assertRaises(BaseException):m.run(execute=True)
     raw=json.loads((m.OUTPUT/'raw_preparation.json').read_bytes());self.assertIs(raw['returned'],mode!='interrupt')
     if mode=='drift':self.assertEqual(raw['result']['document']['scenario_count'],40)
     self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertFalse((m.OUTPUT/'publication.json').exists())

if __name__=='__main__':unittest.main()
