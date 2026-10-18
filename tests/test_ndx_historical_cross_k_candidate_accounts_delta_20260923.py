from contextlib import ExitStack
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_historical_cross_k_candidate_accounts_delta_20260923 as module


class DeltaRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name) / 'delta'
        self.auth = dict(seed_completed_count=121, sources={}, runtime=module.legacy.prefix.runtime(),
                         producer_reference={'path':'new_producer','sha256':'new'},
                         seed_audit_reference={'path':'seed','sha256':'seed'},
                         seed_index_reference={'path':'seed_index','sha256':'seed_index'},
                         audit_reference={'path':'fit','sha256':'fit'},
                         queue=[{'task_id': str(index), 'fit_checkpoint_reference': {}} for index in range(131)])
        self.bind_calls = []
        self.engine_calls = []

    def stack(self, *, fail_engine=False):
        stack = ExitStack()
        self.addCleanup(stack.close)
        def binder(auth, row):
            self.bind_calls.append(row['task_id'])
            return dict(status='READY_FOR_SOURCE_BOUND_SINGLE_ATTEMPT',
                        account={'selected': {'arguments': {'task_id': row['task_id']}}})
        def engine(task_id):
            self.engine_calls.append(task_id)
            self.assertTrue((self.folder/task_id/'started.json').exists())
            if fail_engine:
                raise RuntimeError('synthetic engine failure')
            return {'result': task_id}
        def result(auth, row, prepared, started, raw_reference, raw, sources):
            self.assertTrue(Path(raw_reference['path']).exists())
            return {'task_id':row['task_id'], 'started_reference':started, 'raw_reference':raw_reference}
        stack.enter_context(patch.object(module.legacy, 'bind_task', side_effect=binder))
        stack.enter_context(patch.object(module.legacy.single.candidate, 'simulate_dynamic_frozen_execution_research', side_effect=engine))
        stack.enter_context(patch.object(module.legacy, 'marker_value', side_effect=lambda auth,row:{'task_id':row['task_id']}))
        stack.enter_context(patch.object(module.legacy, 'raw_value', side_effect=lambda auth,row,prepared,started,raw:{'task_id':row['task_id'],'execution':raw}))
        stack.enter_context(patch.object(module.legacy, 'result_value', side_effect=result))
        stack.enter_context(patch.object(module.legacy, 'full', return_value={'fixture':True}))
        stack.enter_context(patch.object(module.legacy.prefix, 'verify', side_effect=AssertionError('old numerical fit audit')))
        stack.enter_context(patch.object(module.legacy, 'external_reference', side_effect=AssertionError('old external audit')))
        return stack

    def test_only_new_tasks_execute_raw_first_under_new_producer(self):
        self.stack()
        report = module.execute_delta(self.auth, self.folder, 2)
        self.assertEqual(self.bind_calls, ['121','122'])
        self.assertEqual(self.engine_calls, ['121','122'])
        self.assertEqual(report['combined_accounts'], 123)
        self.assertEqual(report['new_execution_count'],2)
        self.assertEqual(report['new_skipped_risk_count'],0)
        self.assertTrue(report['real_execution_performed'])
        index = json.loads(Path(report['index_reference']['path']).read_bytes())
        self.assertEqual(len(index['entries']), 2)
        self.assertFalse(index['old_accounts_copied'])
        self.assertFalse(index['independent_delta_audit_completed'])
        started = json.loads((self.folder/'121/started.json').read_bytes())
        self.assertEqual(started['schema'],'HISTORICAL_CROSS_K_DELTA_ATTEMPT_V2')
        self.assertEqual(started['producer_reference'], self.auth['producer_reference'])
        self.assertEqual(started['global_task_ordinal_zero_based'],121)
        self.assertEqual(started['payload_sha256'],module.legacy.digest(started['payload']))

    def test_existing_attempt_or_finalized_batch_never_replays(self):
        self.stack()
        module.execute_delta(self.auth, self.folder, 1)
        with self.assertRaisesRegex(ValueError,'prohibits replay'):
            module.execute_delta(self.auth, self.folder, 1)
        self.assertEqual(self.engine_calls, ['121'])

    def test_failed_engine_retains_attempt_and_refuses_retry(self):
        self.stack(fail_engine=True)
        with self.assertRaises(RuntimeError):
            module.execute_delta(self.auth, self.folder, 1)
        self.assertTrue((self.folder/'121/failure.json').exists())
        self.assertFalse(list(self.folder.glob('index_*.json')))
        with self.assertRaises(ValueError):
            module.execute_delta(self.auth, self.folder, 1)
        self.assertEqual(self.engine_calls,['121'])

    def test_zero_budget_and_hard_authority_missing_do_not_execute(self):
        self.stack()
        report = module.execute_delta(self.auth, self.folder, 0)
        self.assertEqual(report['engine_calls'],0)
        self.assertFalse(self.folder.exists())
        with patch.object(module,'SEED_AUTHORITY',None):
            self.assertIn('BLOCKED',module.run()['status'])
            with self.assertRaises(ValueError):
                module.run(max_new=1,execute=True)
        self.assertEqual(self.engine_calls,[])

    def test_budget_runtime_and_source_guards(self):
        for invalid in (True,-1,11,'1'):
            with self.assertRaises(ValueError):
                module.budget(invalid)
        fingerprint = module.legacy.digest(self.auth)
        with patch.object(module.legacy.prefix,'runtime',return_value={'changed':True}):
            with self.assertRaisesRegex(ValueError,'runtime'):
                module.guard(self.auth,fingerprint)
        self.auth['sources']={'fixture.py':'expected'}
        with patch.object(module.legacy,'sha',return_value='changed'):
            with self.assertRaisesRegex(ValueError,'source'):
                module.guard(self.auth,module.legacy.digest(self.auth))

    def test_skipped_risk_is_not_engine_execution(self):
        self.stack()
        with patch.object(module.legacy,'bind_task',return_value={'status':'NOT_EXECUTED_ORIGINAL_FIVE_RISK_FAILURE'}), \
                patch.object(module.legacy,'result_value',return_value={'status':'SKIPPED_RISK'}):
            report=module.execute_delta(self.auth,self.folder,1)
        self.assertEqual(self.engine_calls,[])
        self.assertEqual(report['engine_calls'],0)
        self.assertEqual(report['new_execution_count'],0)
        self.assertEqual(report['new_skipped_risk_count'],1)
        self.assertFalse(report['real_execution_performed'])
        index=json.loads(Path(report['index_reference']['path']).read_bytes())
        self.assertFalse(index['real_execution_performed'])
        self.assertIsNone(index['entries'][0]['raw_reference'])

    def test_execute_must_be_exact_boolean_before_authority(self):
        with patch.object(module,'authority',side_effect=AssertionError('Unexpected authority IO')):
            for value in (1,0,'true',None):
                with self.assertRaisesRegex(ValueError,'boolean'):
                    module.run(execute=value)


if __name__ == '__main__':
    unittest.main()
