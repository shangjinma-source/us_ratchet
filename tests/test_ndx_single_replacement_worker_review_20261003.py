import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_single_replacement_shard_worker_20261003 as w
from backtest import ndx_single_replacement_journal_research as j
from test_ndx_single_replacement_shard_worker_20261003 import context

class Tests(unittest.TestCase):
 def test_second_interrupt_preserves_success_prefix_exact_partition_and_no_resume(self):
  c=context();real=c['evaluator'].evaluate_one;seen=[]
  def evaluate(row,task):
   seen.append(task['global_ordinal'])
   if task['global_ordinal']==1:raise KeyboardInterrupt('after one complete result')
   return real(row,task)
  with tempfile.TemporaryDirectory()as tmp,patch.object(w,'OUTPUT',Path(tmp)/'out'),patch.object(w,'load_common',return_value=c),patch.object(w,'resource'),patch.object(c['evaluator'],'evaluate_one',evaluate):
   rr=w.run(execute=True,max_shards=2);result=json.loads(w.read(rr));self.assertEqual(seen,[0,1]);self.assertEqual(result['status'],'STOPPED_NO_RETRY')
   p=result['partition'];self.assertEqual(p['terminal_count'],2);self.assertEqual(p['outcome_counts']['EVALUATION_EXCEPTION'],1);self.assertEqual(p['undispatched_count'],558);self.assertEqual(p['full_integer_count'],560);self.assertFalse(result['full_queue_completed'])
   lines=[json.loads(x)['body']for x in (w.OUTPUT/'shard-0000/journal.jsonl').read_bytes().splitlines()]
   self.assertEqual(lines[4]['stage'],'RAW_EXCEPTION');self.assertEqual(lines[4]['payload']['error']['type'],'KeyboardInterrupt');self.assertEqual(lines[1]['payload']['result']['cash_after_usd'],'4999/40')
   with self.assertRaises(ValueError):w.run(execute=True,max_shards=1,prior_result_reference=rr)
   self.assertEqual(seen,[0,1])

 def test_return_followed_by_code_drift_retains_original_raw_then_validation_stop(self):
  c=context();real=c['evaluator'].evaluate_one;returned=[]
  with tempfile.TemporaryDirectory()as tmp:
   source=Path(tmp)/'small.py';source.write_bytes(b'original');c['small_sources']={str(source):w.sha(b'original')}
   def evaluate(row,task):
    result=real(row,task);returned.append(copy.deepcopy(result));source.write_bytes(b'drift');return result
   with patch.object(w,'resource'),patch.object(c['evaluator'],'evaluate_one',evaluate):
    rr=w.process_shard(c,c['plan']['document']['shards'][0],Path(tmp)/'shard')
   result=json.loads(w.read(rr));self.assertEqual(result['status'],'STOPPED_NO_RETRY');self.assertEqual(len(returned),1)
   rows=[json.loads(x)['body']for x in (Path(tmp)/'shard/journal.jsonl').read_bytes().splitlines()]
   self.assertEqual(rows[1]['payload']['result'],returned[0]);self.assertTrue(rows[1]['payload']['returned']);self.assertEqual(rows[2]['payload']['outcome'],'VALIDATION_FAILURE');self.assertEqual(result['inspection']['undispatched_ordinals'],[1])

 def test_complete_resume_rejects_started_bool_authority_and_extra_partial_attempt(self):
  for fault in ('authority','orphan'):
   c=context()
   with tempfile.TemporaryDirectory()as tmp,patch.object(w,'OUTPUT',Path(tmp)/'out'),patch.object(w,'load_common',return_value=c),patch.object(w,'resource'):
    rr=w.run(execute=True,max_shards=1)
    if fault=='orphan':(w.OUTPUT/'shard-0001').mkdir()
    else:
     batch=json.loads(w.read(rr));sr=batch['completed_shard_references'][0];shard=json.loads(w.read(sr));start=json.loads(w.read(shard['started_reference']));start['point_in_time_verified']=0
     def rewrite(ref,obj):
      raw=w.enc(obj);Path(ref['path']).write_bytes(raw);ref['sha256']=w.sha(raw)
     rewrite(shard['started_reference'],start);rewrite(sr,shard);batch['saved_references'][1]=sr;rewrite(rr,batch)
    with patch.object(c['evaluator'],'evaluate_one',side_effect=AssertionError('dispatch forbidden')),self.assertRaises(ValueError):w.run(execute=True,max_shards=1,prior_result_reference=rr)

 def test_late_prior_journal_or_request_drift_blocks_new_success(self):
  for target in ('journal','request'):
   c=context();real=c['evaluator'].evaluate_one
   with tempfile.TemporaryDirectory()as tmp,patch.object(w,'OUTPUT',Path(tmp)/'out'),patch.object(w,'load_common',return_value=c),patch.object(w,'resource'):
    first=w.run(execute=True,max_shards=1);seen=[]
    old=w.OUTPUT/('shard-0000/journal.jsonl'if target=='journal'else'request-0000/result.json')
    def evaluate(row,task):
     seen.append(task['global_ordinal'])
     if len(seen)==1:
      with old.open('ab')as stream:stream.write(b'\n')
     return real(row,task)
    with patch.object(c['evaluator'],'evaluate_one',evaluate),self.assertRaises(ValueError):w.run(execute=True,max_shards=1,prior_result_reference=first)
    self.assertEqual(seen,[2,3])
    self.assertTrue((w.OUTPUT/'request-0001/failure.json').exists())
    self.assertTrue((w.OUTPUT/'shard-0001/journal.jsonl').exists())

 def test_start_full_signed_plan_and_dispatch_fact_cannot_be_resigned(self):
  c=context();task=c['evaluator'].project_validated_task(c['validated'],0)
  for fault in ('quantity','holdings','permissions','dispatch'):
   payload=dict(task=copy.deepcopy(task),dispatch_may_have_occurred=True)
   if fault=='quantity':payload['task']['identity']['buy_quantity']+=1
   elif fault=='holdings':payload['task']['proposed_holdings']['C']+=1
   elif fault=='permissions':payload['task']['source_bytes_authenticated']=0
   else:payload['dispatch_may_have_occurred']=1
   row=j.make_record(context_sha256='b'*64,sequence=0,previous_sha256='0'*64,global_ordinal=0,task_id=task['task_id'],stage='START',payload=payload)
   with self.subTest(fault=fault),self.assertRaises(ValueError):j.inspect_journal(j.encode(row)+b'\n',context_sha256='b'*64,ordered_tasks=[task])

 def test_returned_call_cannot_be_relabelled_exception_in_journal(self):
  task=dict(global_ordinal=0,task_id='a'*64);previous='0'*64;lines=[]
  events=[('START',{'task':task,'dispatch_may_have_occurred':True}),('RAW_RETURNED',dict(call_invoked=True,call_count=1,returned=True,result_preserved_as_json=True,result=None,error=None)),('POSTCHECK',dict(outcome='EVALUATION_EXCEPTION'))]
  for sequence,(stage,payload)in enumerate(events):
   row=j.make_record(context_sha256='b'*64,sequence=sequence,previous_sha256=previous,global_ordinal=0,task_id=task['task_id'],stage=stage,payload=payload);previous=row['record_sha256'];lines.append(j.encode(row)+b'\n')
  with self.assertRaises(ValueError):j.inspect_journal(b''.join(lines),context_sha256='b'*64,ordered_tasks=[task])

if __name__=='__main__':unittest.main()
