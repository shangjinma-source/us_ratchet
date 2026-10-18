from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import test_ndx_registered_scoring_queue_worker_20261003 as author
from backtest import ndx_registered_scoring_journal_research as journal

m=author.m


class Review(unittest.TestCase):
    def configure(self,root,context):
        stack=ExitStack();self.addCleanup(stack.close)
        for name,value in [('OUTPUT',root/'out'),('FRESH_CLI',True)]:stack.enter_context(patch.object(m,name,value))
        for name in ('code_guard','common_guard','space'):stack.enter_context(patch.object(m,name,return_value=None))
        stack.enter_context(patch.object(m,'environment',return_value={}))
        stack.enter_context(patch.object(m,'job_arguments',return_value={}))
        stack.enter_context(patch.dict(m._COMMON,{'review':context},clear=True))

    def test_stopped_shard_terminal_is_not_lost_due_to_failure_marker(self):
        with TemporaryDirectory() as td:
            c=author.fixture();self.configure(Path(td),c)
            def failure(**kwargs):raise ArithmeticError('retained original')
            c['modules']['rolling'].fit_causal_scoring_windows=failure
            reference=m.run_batch(execute=True,common='review')
            result=m.loads(Path(reference['path']).read_bytes())
            self.assertEqual(result['status'],'STOPPED')
            self.assertEqual(result['completed_new_job_count'],0)
            self.assertEqual(result['unresolved_task_ids'],[])
            self.assertEqual(result['undispatched_new_task_ids'],[])
            self.assertEqual(result['current_shard_terminal_tasks'][-1]['status'],'NUMERICAL_EXCEPTION')
            with self.assertRaises(ValueError):m.run_shard(0,common='review',execute=True,completed_reference=result['unresolved_shard_reference'])

    def test_explicit_completed_reference_still_requires_correct_scope(self):
        with TemporaryDirectory() as td:
            c=author.fixture();self.configure(Path(td),c)
            reference=m.run_shard(0,common='review',execute=True)
            path=Path(reference['path']);original=m.loads(path.read_bytes())
            for field,value in [('whole_queue_completed',True),('logical_job_count',0),('schema','FOREIGN_RESULT'),('point_in_time_verified',0)]:
                changed=deepcopy(original);changed[field]=value;raw=m.enc(changed);path.write_bytes(raw)
                with self.subTest(field=field),self.assertRaises(ValueError):m.run_shard(0,common='review',execute=True,completed_reference=m.ref(path,m.sha(raw)))
            path.write_bytes(m.enc(original))

    def test_partial_journal_never_manufactures_a_return_or_retries(self):
        records=[];previous=journal.ZERO
        for stage,payload in [('TASK_STARTED',{}),('INPUTS',{}),('FIT_DISPATCH',{})]:
            row=journal.make_record(sequence=len(records),previous_hash=previous,context_sha256='c'*64,task_id='a'*64,task_position=0,stage=stage,payload=payload);records.append(row);previous=row['record_sha256']
        raw=b''.join(journal.encode(row)+b'\n' for row in records)+b'{"partial_raw"'
        out=journal.inspect_journal(raw,context_sha256='c'*64,ordered_task_ids=['a'*64,'b'*64])
        self.assertEqual(out['unresolved_task_ids'],['a'*64]);self.assertEqual(out['undispatched_task_ids'],['b'*64])
        self.assertNotIn('fit_returned',out['tasks'][0]);self.assertFalse(out['bytes_truncated']);self.assertFalse(out['automatic_retry_allowed'])

    def test_nonpass_inspection_is_retained_and_success_claim_rejected(self):
        with TemporaryDirectory() as td:
            c=author.fixture();self.configure(Path(td),c)
            c['modules']['inspector'].inspect_fitted_scoring_windows=lambda **kw:{'status':'REJECTED','detail':'saved original report'}
            reference=m.run_batch(execute=True,common='review')
            result=m.loads(Path(reference['path']).read_bytes())
            self.assertEqual(result['status'],'STOPPED')
            self.assertEqual(result['current_shard_terminal_tasks'][-1]['status'],'VALIDATION_FAILURE')
            path=m.OUTPUT/'shards/0000/journal.jsonl';rows=[m.loads(line) for line in path.read_bytes().splitlines()]
            self.assertEqual(rows[-2]['payload']['inspection']['status'],'REJECTED')
            rows[-1]['payload']['outcome']=m.SUCCESS
            rows[-1]['record_sha256']=journal.digest({k:v for k,v in rows[-1].items() if k!='record_sha256'})
            raw=b''.join(journal.encode(row)+b'\n' for row in rows)
            with self.assertRaises(ValueError):journal.inspect_journal(raw,context_sha256=result['context_sha256'],ordered_task_ids=c['queue']['shards'][0]['job_ids'])


if __name__=='__main__':unittest.main()
