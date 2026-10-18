"""Independent lifecycle checks over real synthetic sources; never actual research."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_single_replacement_signed_paths_20261003 as m
from test_ndx_single_replacement_signed_paths_20261003 import physical

class Tests(unittest.TestCase):
 def test_paired_eof_hash_failure_precedes_every_account_call(self):
  with tempfile.TemporaryDirectory()as t,physical(Path(t))as registration:
   original_read=m.read_paired;original_call=m.preserve_call;account_calls=[]
   def changed(c):
    p=Path(c['refs']['paired']['path']);p.write_bytes(p.read_bytes()+b' ')
    return original_read(c)  # real stream parser must reach EOF then reject hash
   def counted(path,function,kwargs):
    if Path(path).name=='raw_result.json':account_calls.append(str(path))
    return original_call(path,function,kwargs)
   with patch.object(m,'read_paired',changed),patch.object(m,'preserve_call',counted),self.assertRaises(ValueError):m.run(registration_reference=registration,execute=True)
   self.assertEqual(account_calls,[]);self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertFalse((m.OUTPUT/'raw_requests.json').exists());self.assertFalse((m.OUTPUT/'scenario-00').exists())
 def test_unserializable_true_return_and_broken_repr_are_durable(self):
  class Returned:
   def __repr__(self):raise RuntimeError('repr itself failed')
  with tempfile.TemporaryDirectory()as t:
   path=Path(t)/'raw_result.json'
   raw,ref=m.preserve_call(path,lambda:Returned(),{})
   self.assertEqual(json.loads(path.read_bytes()),raw);self.assertEqual(m.filehash(path),ref['sha256'])
   self.assertIs(raw['returned'],True);self.assertIs(raw['call_invoked'],True);self.assertEqual(raw['call_count'],1);self.assertIsNone(raw['error']);self.assertIsNone(raw['result']);self.assertIs(raw['result_preserved_as_json'],False)
   self.assertEqual(raw['result_type'],'Returned');self.assertEqual(raw['representation_error']['type'],'RuntimeError');self.assertEqual(raw['serialization_error']['type'],'TypeError');self.assertIsNone(raw['representation'])
 def test_second_account_exception_keeps_first_and_all_remaining(self):
  with tempfile.TemporaryDirectory()as t,physical(Path(t))as registration:
   private=m.private;calls=[]
   def wrap(role,raw):
    module=private(role,raw)
    if role=='account':
     original=module.account_path
     def account(**kwargs):
      calls.append(kwargs['initial']['session'])
      if len(calls)==2:raise RuntimeError('second-account deliberate failure')
      return original(**kwargs)
     module.account_path=account
    return module
   with patch.object(m,'private',wrap),self.assertRaises(RuntimeError):m.run(registration_reference=registration,execute=True)
   result=json.loads((m.OUTPUT/'result.json').read_bytes());self.assertEqual(len(calls),2);self.assertEqual(len(result['rows']),40)
   self.assertEqual(result['outcome_counts']['ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK'],1);self.assertEqual(result['outcome_counts']['ACCOUNT_EXCEPTION'],1);self.assertEqual(result['outcome_counts']['UNDISPATCHED'],38)
   first=result['rows'][0];self.assertEqual(json.loads(Path(first['inspection_reference']['path']).read_bytes())['status'],'PASS')
   failed=json.loads(Path(result['rows'][1]['raw_reference']['path']).read_bytes());self.assertFalse(failed['returned']);self.assertEqual(failed['error']['message'],'second-account deliberate failure')
   self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertFalse((m.OUTPUT/'publication.json').exists());self.assertTrue(all(r['account_call_invoked']is False for r in result['rows'][2:]));self.assertFalse(result['controls_executed'])
   with self.assertRaises(ValueError):m.run(registration_reference=registration,execute=True)
   self.assertEqual(len(calls),2)
 def test_full_mixed_partition_real_source_and_accounts_not_fake_cash(self):
  with tempfile.TemporaryDirectory()as t,physical(Path(t),blocked=True)as registration:
   refs=m.run(registration_reference=registration,execute=True);result=json.loads(Path(refs['result']['path']).read_bytes())
   self.assertEqual(len(result['rows']),40);self.assertEqual(result['outcome_counts']['NO_FEASIBLE'],1);self.assertEqual(result['outcome_counts']['BLOCKED_TEMPLATE_PRICE_GAP'],1);self.assertEqual(result['outcome_counts']['ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK'],38)
   for i,status in ((0,'BLOCKED_TEMPLATE_PRICE_GAP'),(1,'NO_FEASIBLE')):
    row=result['rows'][i];request=json.loads(Path(row['request_reference']['path']).read_bytes())['prepared_request']
    self.assertEqual(row['outcome'],status);self.assertIsNone(request['accounting_request']);self.assertFalse(row['account_call_invoked']);self.assertNotIn('raw_reference',row);self.assertIsNone(request['reused_candidate_path_reference']);self.assertFalse((m.OUTPUT/f'scenario-{i:02d}'/'started.json').exists())
   self.assertFalse(result['controls_executed']);self.assertFalse(result['independent_source_readback_passed']);self.assertFalse(result['point_in_time_verified'])
if __name__=='__main__':unittest.main()
