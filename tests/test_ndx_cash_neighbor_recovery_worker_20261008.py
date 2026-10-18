import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from scripts import ndx_cash_neighbor_recovery_worker_20261008 as w
from backtest import ndx_cash_neighbor_recovery_partition_research as pure

class Tests(unittest.TestCase):
    def fixture(self):
        segment=dict(original_task_start=163,original_task_stop=164,task_ids=['a'*64],original_descriptor=dict(global_task_start=259193,global_task_stop=259357,shard=dict(start=46000,stop=46164,path='frozen.tasks',sha256='b'*64)))
        tasks=[None]*163+[dict(task_id='a'*64)]
        return segment,tasks
    def run_one(self,folder,*,evaluate,inspect,gate=None):
        segment,tasks=self.fixture()
        adapter=SimpleNamespace(evaluation_arguments=lambda p,t:dict(value=1),inspect_return=inspect)
        with patch.object(w,'resource_gate',gate or (lambda *a:None)):
            return w.process_segment(folder=folder,segment=segment,tasks=tasks,prepared={},registration_sha='c'*64,pure=pure,adapter=adapter,evaluate=evaluate,verify=lambda:None,input_bytes=10)
    def test_low_disk_and_ram_prevent_call(self):
        for disk,ram in ((w.MIN_DISK-1,w.MIN_RAM+999999),(w.MIN_DISK+999999,w.MIN_RAM-1)):
            calls=[]
            def gate(*args):return w.resource_gate(Path('.'),10,disk_free=disk,memory_free=ram)
            original=w.resource_gate
            def actual_gate(*args):return original(Path('.'),10,disk_free=disk,memory_free=ram)
            with tempfile.TemporaryDirectory() as tmp:
                _,report=self.run_one(Path(tmp)/'segment',evaluate=lambda **kw:calls.append(kw),inspect=lambda *a:dict(outcome='FEASIBLE'),gate=actual_gate)
                self.assertEqual(calls,[]);self.assertEqual(report['inspection']['undispatched_task_ids'],['a'*64]);self.assertIsNone(report['inspection']['active'])
    def test_raw_saved_before_failed_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'segment'
            def check(*args):
                self.assertIn(b'RAW_RETURNED',(folder/'journal.jsonl').read_bytes())
                raise ValueError('synthetic validation')
            _,report=self.run_one(folder,evaluate=lambda **kw:dict(original=123),inspect=check)
            self.assertEqual(report['inspection']['terminal_rows'][0]['status'],'VALIDATION_FAILURE')
            self.assertIn(b'"original":123',(folder/'journal.jsonl').read_bytes())
    def test_raw_write_failure_never_calls_twice(self):
        original=w.Journal.append;calls=[]
        def broken(self,position,stage,payload):
            if stage=='RAW_RETURNED':
                self.stream.write(b'{"partial_raw":');self.stream.flush();raise OSError('synthetic disk full')
            return original(self,position,stage,payload)
        with tempfile.TemporaryDirectory() as tmp,patch.object(w.Journal,'append',broken):
            folder=Path(tmp)/'segment'
            def evaluate(**args):calls.append(args);return dict(saved=123)
            _,report=self.run_one(folder,evaluate=evaluate,inspect=lambda *a:dict(outcome='FEASIBLE'))
            self.assertEqual(len(calls),1);self.assertEqual(report['inspection']['active']['status'],'UNRESOLVED_DISPATCH');self.assertIsNotNone(report['inspection']['tail']);self.assertEqual(report['inspection']['undispatched_task_ids'],[])
            self.assertTrue((folder/'journal.jsonl').read_bytes().endswith(b'{"partial_raw":'))
    def test_complete_original_position_and_create_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'segment';calls=[]
            _,report=self.run_one(folder,evaluate=lambda **kw:dict(ok=1),inspect=lambda *a:dict(outcome='INFEASIBLE'))
            self.assertTrue(report['inspection']['complete']);self.assertEqual(report['inspection']['terminal_rows'][0]['original_task_position'],163)
            with self.assertRaises(ValueError):self.run_one(folder,evaluate=lambda **kw:calls.append(kw),inspect=lambda *a:dict(outcome='FEASIBLE'))
            self.assertEqual(calls,[])
    def test_synthetic_real_evaluator_return_matches_independent_oracle(self):
        from test_ndx_cash_topup_neighbor_shard_independent_readback_20261003 import shard_fixture
        from scripts import ndx_cash_topup_neighbor_single_evaluation_20261003 as adapter
        from scripts import ndx_cash_topup_neighbor_shard_independent_readback_20261003 as independent
        prepared,tasks,descriptor,started,records,external,oracle=shard_fixture()
        segment=dict(original_task_start=0,original_task_stop=2,task_ids=[t['task_id'] for t in tasks],original_descriptor=descriptor)
        with tempfile.TemporaryDirectory() as tmp,patch.object(w,'resource_gate',lambda *a:None):
            folder=Path(tmp)/'segment'
            _,report=w.process_segment(folder=folder,segment=segment,tasks=tasks,prepared=prepared,registration_sha='c'*64,pure=pure,adapter=adapter,evaluate=adapter.fresh_evaluator(),verify=lambda:None,input_bytes=100)
            self.assertTrue(report['inspection']['complete'])
            rows=[w.decode(line) for line in (folder/'journal.jsonl').read_bytes().splitlines()]
            for position,task in enumerate(tasks):
                expected=oracle(independent.task_arguments(prepared,task,position))
                self.assertEqual(rows[3*position+1]['payload']['result'],expected)
                self.assertEqual(rows[3*position+2]['payload'],independent.expected_detail(prepared,expected))

    def test_request_partition_keeps_unknown_separate_from_undispatched(self):
        segment,tasks=self.fixture()
        report=dict(segment=segment,inspection=dict(terminal_rows=[],active=dict(task_id='a'*64,status='RAW_SAVED_POSTCHECK_MISSING'),undispatched_task_ids=[],complete=False))
        next_segment=dict(task_ids=['d'*64])
        result=w.request_partition(dict(segments=[segment,next_segment]),[report])
        self.assertEqual(result['counts']['RAW_SAVED_POSTCHECK_MISSING'],1)
        self.assertEqual(result['task_ids_by_status']['UNDISPATCHED'],['d'*64])
        report['inspection']['undispatched_task_ids']=['a'*64]
        with self.assertRaises(ValueError):w.request_partition(dict(segments=[segment,next_segment]),[report])

    def test_conflicting_source_bindings_never_overwritten(self):
        self.assertEqual(w.merge_bindings({'source':'a'*64},{'source':'a'*64}),{'source':'a'*64})
        with self.assertRaises(ValueError):w.merge_bindings({'source':'a'*64},{'source':'b'*64})
        with self.assertRaises(ValueError):w.merge_bindings({'source':None})

    def test_runtime_identity_is_observation_not_binary_authentication(self):
        identity=w.runtime_identity()
        self.assertIs(identity['runtime_binary_closure_verified'],False)
        self.assertTrue(identity['python_version'])
        self.assertTrue(identity['platform'])
        self.assertTrue(Path(identity['executable']).is_absolute())

    def test_unbound_pure_stops_before_source_io(self):
        with patch.object(w,'PURE_SHA',None),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):w.run(execute=True)
            read.assert_not_called()

if __name__=='__main__':unittest.main()
