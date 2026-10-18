import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_single_replacement_execution_independent_readback_20261003 as m
from scripts import ndx_single_replacement_shard_worker_20261003 as worker
from test_ndx_single_replacement_execution_independent_readback_20261003 import physical

class Tests(unittest.TestCase):
 def test_saved_technical_stop_preserves_success_prefix_and_rest_denominator(self):
  with tempfile.TemporaryDirectory() as tmp,physical(Path(tmp)) as c:
   first=m.ref(m.REQUEST_PATH,m.REQUEST_SHA)
   with patch.object(worker,'OUTPUT',m.PARENT),patch.object(worker,'load_common',return_value=c),patch.object(worker,'resource'),patch.object(c['evaluator'],'evaluate_one',side_effect=KeyboardInterrupt('synthetic original error')):
    stopped=worker.run(execute=True,max_shards=1,prior_result_reference=first)
   with patch.object(m,'REQUEST_PATH',Path(stopped['path'])),patch.object(m,'REQUEST_SHA',stopped['sha256']):r=m.readback(execute=True)
   report=json.loads(Path(r['path']).read_bytes());p=report['partition']
   self.assertEqual(p['terminal_count'],513);self.assertEqual(p['undispatched_count'],47)
   self.assertEqual(p['outcome_counts']['EVALUATION_EXCEPTION'],1)
   self.assertEqual(sum(v['inspection']['arithmetic_checked_count']for v in report['shards']),512)
   self.assertFalse(report['full_domain_evaluated'])

 def test_each_prior_request_must_not_claim_full_domain_after512_of560(self):
  with tempfile.TemporaryDirectory() as tmp,physical(Path(tmp)) as c:
   first=m.ref(m.REQUEST_PATH,m.REQUEST_SHA)
   with patch.object(worker,'OUTPUT',m.PARENT),patch.object(worker,'load_common',return_value=c),patch.object(worker,'resource'):
    second=worker.run(execute=True,max_shards=1,prior_result_reference=first)
   p=Path(first['path']);v=json.loads(p.read_bytes());v['full_queue_completed']=True;p.write_bytes(m.enc(v));changed=m.ref(p,m.sha(p.read_bytes()))
   p2=Path(second['path']);v2=json.loads(p2.read_bytes());v2['prior_request_references']=[changed]
   sp=Path(v2['started_reference']['path']);sv=json.loads(sp.read_bytes());sv['prior_result_reference']=changed;sp.write_bytes(m.enc(sv));sr=m.ref(sp,m.sha(sp.read_bytes()));v2['started_reference']=sr;v2['saved_references'][0]=sr;p2.write_bytes(m.enc(v2))
   with patch.object(m,'REQUEST_PATH',p2),patch.object(m,'REQUEST_SHA',m.sha(p2.read_bytes())),self.assertRaises(ValueError):m.readback(execute=True)

 def test_post_report_parent_extra_failure_is_durable_no_retry(self):
  with tempfile.TemporaryDirectory() as tmp,physical(Path(tmp)):
   original=m.save
   def save(name,value):
    r=original(name,value)
    if name=='independent_readback.json':(m.PARENT/'request-0000'/'unexpected.bin').write_bytes(b'extra')
    return r
   with patch.object(m,'save',save),self.assertRaises(ValueError):m.readback(execute=True)
   self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertTrue((m.OUTPUT/'independent_readback.json').exists())
   with self.assertRaises(ValueError):m.readback(execute=True)

 def test_registered_denominator_and_source_roles_cannot_be_resigned(self):
  for attack in ('denominator','role'):
   with self.subTest(attack=attack),tempfile.TemporaryDirectory() as tmp,physical(Path(tmp)):
    p=m.REQUEST_PATH;v=json.loads(p.read_bytes())
    if attack=='denominator':v['partition']['undispatched_count']=47
    else:v['input_references']['reader']=copy.deepcopy(v['input_references']['audit'])
    p.write_bytes(m.enc(v))
    with patch.object(m,'REQUEST_SHA',m.sha(p.read_bytes())),self.assertRaises(ValueError):m.readback(execute=True)

if __name__=='__main__':unittest.main()
