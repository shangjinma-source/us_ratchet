import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backtest import ndx_single_replacement_journal_research as journal
from scripts import ndx_single_replacement_shard_worker_20261003 as m
from test_ndx_single_replacement_execution_registration_research import fixture_plan


def context():
    domain=m.private('domain');evaluator=m.private('evaluator',domain);registration=m.private('registration')
    a=fixture_plan();a['shard_size']=2;plan=registration.build_execution_registration(**a)
    return dict(evaluator=evaluator,journal=journal,plan=plan,validated=evaluator.validate_prepared(a['prepared']),sources={},dirs={},small_sources={},refs={})


class Tests(unittest.TestCase):
    def test_explicit_anchored_resume_never_reevaluates_prefix(self):
        c=context();calls=[];evaluate=c['evaluator'].evaluate_one
        def counted(row,task):calls.append(task['global_ordinal']);return evaluate(row,task)
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)/'output'),patch.object(m,'load_common',return_value=c),patch.object(m,'resource'),patch.object(c['evaluator'],'evaluate_one',counted):
            first=m.run(execute=True,max_shards=1)
            with self.assertRaises(ValueError):m.run(execute=True,max_shards=1)
            second=m.run(execute=True,max_shards=1,prior_result_reference=first)
            self.assertEqual(calls,[0,1,2,3]);out=json.loads(m.read(second));self.assertEqual(out['partition']['terminal_count'],4)
            self.assertEqual(out['partition']['undispatched_count'],556)
            with self.assertRaises(ValueError):m.run(execute=True,max_shards=1,prior_result_reference=first)

    def test_resource_stop_records_complete_undispatched_domain(self):
        c=context()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)/'output'),patch.object(m,'load_common',return_value=c):
            def storage(path,additional=0):
                if Path(path)==m.OUTPUT and (m.OUTPUT/'request-0000'/'started.json').exists():raise ValueError('RESOURCE_STOP_BEFORE_DISPATCH')
            with patch.object(m,'resource',storage),self.assertRaises(ValueError):m.run(execute=True,max_shards=1)
            failure=json.loads((m.OUTPUT/'request-0000'/'failure.json').read_bytes())
            self.assertEqual(failure['partition']['undispatched_count'],560)
            self.assertIsNone(failure['current_descriptor']);self.assertFalse(any(m.OUTPUT.glob('shard-*')))

    def test_private_real_two_points_and_durable_order(self):
        c=context()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'resource'):
            folder=Path(tmp)/'shard';r=m.process_shard(c,c['plan']['document']['shards'][0],folder)
            result=json.loads(m.read(r));self.assertEqual(result['status'],'COMPLETE_PENDING_INDEPENDENT_READBACK')
            rows=[json.loads(line)['body'] for line in (folder/'journal.jsonl').read_bytes().splitlines()]
            self.assertEqual([r['stage'] for r in rows],['START','RAW_RETURNED','POSTCHECK']*2)
            self.assertEqual(rows[1]['payload']['result']['cash_after_usd'],'4999/40')
            with self.assertRaises(FileExistsError):m.process_shard(c,c['plan']['document']['shards'][0],folder)

    def test_interrupt_none_and_hostile_repr_preserve_raw(self):
        class Bad:
            def __repr__(self):raise KeyboardInterrupt('repr')
        for mode in ('interrupt','none','repr'):
            c=context();seen=[]
            with tempfile.TemporaryDirectory() as tmp,patch.object(m,'resource'):
                folder=Path(tmp)/'shard'
                def evaluate(row,task):
                    seen.append(task['global_ordinal'])
                    self.assertTrue((folder/'journal.jsonl').read_bytes().endswith(b'\n'))
                    if mode=='interrupt':raise KeyboardInterrupt('saved interrupt')
                    return None if mode=='none' else Bad()
                with patch.object(c['evaluator'],'evaluate_one',evaluate):r=m.process_shard(c,c['plan']['document']['shards'][0],folder)
                result=json.loads(m.read(r));self.assertEqual(result['status'],'STOPPED_NO_RETRY');self.assertEqual(seen,[0])
                scan=result['inspection'];self.assertEqual(scan['undispatched_ordinals'],[1])
                self.assertEqual(scan['terminal_rows'][0]['outcome'],'EVALUATION_EXCEPTION' if mode=='interrupt' else 'VALIDATION_FAILURE')
                self.assertTrue((folder/'failure.json').exists())

    def test_partial_each_record_conservative_and_success_forgery(self):
        tasks=[dict(task_id='a'*64,global_ordinal=0),dict(task_id='b'*64,global_ordinal=1)]
        lines=[];previous='0'*64
        for seq,(stage,payload) in enumerate([('START',dict(task=tasks[0],dispatch_may_have_occurred=True)),('RAW_RETURNED',dict(call_invoked=True,call_count=1,returned=True,result_preserved_as_json=True,result=None)),('POSTCHECK',dict(outcome='VALIDATION_FAILURE'))]):
            r=journal.make_record(context_sha256='c'*64,sequence=seq,previous_sha256=previous,global_ordinal=0,task_id='a'*64,stage=stage,payload=payload);previous=r['record_sha256'];lines.append(journal.encode(r)+b'\n')
        for n in range(3):
            raw=b''.join(lines[:n])+lines[n][:8]
            scan=journal.inspect_journal(raw,context_sha256='c'*64,ordered_tasks=tasks)
            self.assertEqual(scan['unresolved_ordinal'],0);self.assertEqual(scan['undispatched_ordinals'],[1])
        value=json.loads(lines[2]);value['body']['payload']['outcome']='FEASIBLE';value['record_sha256']=journal.sha(journal.encode(value['body']))
        with self.assertRaises(ValueError):journal.inspect_journal(b''.join(lines[:2])+journal.encode(value)+b'\n',context_sha256='c'*64,ordered_tasks=tasks)


if __name__=='__main__':unittest.main()
