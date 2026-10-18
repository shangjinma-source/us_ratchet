import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_dated_batch_20261003 as core

IDS=[format(i,'064x') for i in range(1,1633)]

class DatedBatchTests(unittest.TestCase):
    def exercise(self, outcomes, failure_at=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);base=Path(temp.name)
        calls=[]
        def run(tid):
            calls.append(tid)
            if tid==failure_at:raise ValueError('raw exists, reader/dispatch unknown')
            return {'path':'post','sha256':'a'*64}
        def read(tid,post):
            return core.save(base/(tid+'.json'),dict(schema='DATED_SINGLE_TASK_INDEPENDENT_READBACK_V1',numerical_task_id=tid,status='PASSED',attempt_outcome=outcomes[tid]))
        result=core.execute_queue(IDS[:len(outcomes)],run_task=run,read_task=read,verify_sources=lambda:None,output=base/'batch',initial_rows=[])
        return core.reference_load(result),calls,base

    def test_risk_fail_continues_numerical_stops_and_namespace_blocks(self):
        result,calls,base=self.exercise(dict(zip(IDS,['RISK_PASSED','RISK_FAILED','NUMERICAL_EXCEPTION','RISK_PASSED'])))
        self.assertEqual(calls,IDS[:3]);self.assertEqual(result['undispatched_task_ids'],IDS[3:4]);self.assertEqual(result['new_outcome_counts']['RISK_FAILED'],1)
        self.assertTrue((base/'batch/failure.json').exists())
        with self.assertRaises(ValueError):core.execute_queue([],run_task=None,read_task=None,verify_sources=lambda:None,output=base/'batch',initial_rows=[])

    def test_exception_retains_unresolved_no_retry(self):
        result,calls,_=self.exercise(dict(zip(IDS,['RISK_PASSED']*3)),IDS[1])
        self.assertEqual(calls,IDS[:2]);self.assertEqual(result['new_readback_count'],1)
        self.assertEqual(result['unresolved_dispatched_task_ids'],IDS[1:2]);self.assertEqual(result['undispatched_task_ids'],IDS[2:3])

    def test_pending_or_nonexecute_never_loads_modules(self):
        pending={role:(path,None) for role,(path,_) in core.PINS.items()}
        with patch.object(core,'PINS',pending),patch.object(core,'load_module') as load:
            with self.assertRaises(ValueError):core.run()
            with self.assertRaises(ValueError):core.run(execute=1)
            with self.assertRaises(ValueError):core.run(execute=True)
            load.assert_not_called()

    def test_initial_must_be_new_exact_prefix_with_cross_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);tid=IDS[0]
            post=core.save(base/'post.json',dict(schema='DATED_SINGLE_TASK_POSTCHECK_V1',numerical_task_id=tid,status='ORIGINAL_RISKS_FAILED_PENDING_INDEPENDENT_READBACK'))
            report=core.save(base/'read.json',dict(schema='DATED_SINGLE_TASK_INDEPENDENT_READBACK_V1',numerical_task_id=tid,status='PASSED',attempt_outcome='RISK_FAILED',postcheck_reference=post))
            initial=dict(schema='DATED_INITIAL_COMPLETED_TASKS_V1',preparation_reference=core.PREPARATION_REFERENCE,rows=[dict(numerical_task_id=tid,postcheck_reference=post,independent_readback_reference=report)])
            self.assertEqual(core.validate_initial(initial,IDS),[tid])
            initial['rows'][0]['numerical_task_id']=IDS[1]
            with self.assertRaises(ValueError):core.validate_initial(initial,IDS)

    def test_common_loaded_once_and_saved_order_only(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        runner=SimpleNamespace(load_common=Mock(return_value={'ordered_task_ids':IDS}),run=Mock())
        reader=SimpleNamespace(load_common=Mock(return_value={}),readback=Mock())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);attempts=root/'attempts';(attempts/IDS[0]).mkdir(parents=True)
            initial={'rows':[{'numerical_task_id':IDS[0]}]}
            with patch.object(core,'OUTPUT',root/'out'),patch.object(core,'ATTEMPTS',attempts),patch.object(core,'guard'),patch.object(core,'reference_load',return_value=initial),patch.object(core,'validate_initial',return_value=IDS[:1]),patch.object(core,'load_module',side_effect=[runner,reader]),patch.object(core,'execute_queue',return_value='ok') as dispatch:
                self.assertEqual(core.run(execute=True),'ok');self.assertEqual(dispatch.call_args.args[0],IDS[1:])
            runner.load_common.assert_called_once();reader.load_common.assert_called_once();runner.run.assert_not_called()

if __name__=='__main__':unittest.main()
