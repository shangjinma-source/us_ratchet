import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import ndx_historical_cross_k_candidate_accounts_delta_20260923 as m
import test_ndx_historical_cross_k_candidate_accounts_delta_20260923 as owner


class DeltaIndependentReview(unittest.TestCase):
    def fixture(self):
        helper=owner.DeltaRunnerTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        helper.stack()
        return helper

    def test_full_ten_budget_only_global_ordinals_121_through_130(self):
        helper=self.fixture()
        result=m.execute_delta(helper.auth,helper.folder,10)
        self.assertEqual(helper.engine_calls,[str(i) for i in range(121,131)])
        index=json.loads(Path(result['index_reference']['path']).read_bytes())
        self.assertEqual([entry['global_task_ordinal_zero_based'] for entry in index['entries']],list(range(121,131)))
        self.assertFalse(index['independent_delta_audit_completed'])
        self.assertEqual(index['seed_account_audit_reference'],helper.auth['seed_audit_reference'])
        for entry in index['entries']:
            for key in ('started_reference','raw_reference','result_reference'):
                ref=entry[key];wrapped=json.loads(Path(ref['path']).read_bytes())
                self.assertEqual(wrapped['payload_sha256'],m.legacy.digest(wrapped['payload']))
                self.assertEqual(wrapped['producer_reference'],helper.auth['producer_reference'])
                self.assertEqual(index['historical_expected_source_hashes'][ref['path']],ref['sha256'])

    def test_numerical_audit_failure_keeps_raw_and_blocks_replay(self):
        helper=self.fixture()
        with patch.object(m.legacy,'result_value',side_effect=ValueError('independent audit fixture failure')):
            with self.assertRaises(ValueError):m.execute_delta(helper.auth,helper.folder,2)
        self.assertEqual(helper.engine_calls,['121'])
        self.assertTrue((helper.folder/'121/raw.json').exists())
        self.assertTrue((helper.folder/'121/failure.json').exists())
        self.assertFalse((helper.folder/'121/result.json').exists())
        self.assertFalse(list(helper.folder.glob('index_*.json')))
        with self.assertRaises(ValueError):m.execute_delta(helper.auth,helper.folder,2)
        self.assertEqual(helper.engine_calls,['121'])

    def test_runtime_change_after_engine_preserves_raw_but_no_index(self):
        helper=self.fixture()
        runtime=dict(helper.auth['runtime'])
        def engine(task_id):
            helper.engine_calls.append(task_id)
            runtime['changed_after_engine']=True
            return dict(result=task_id)
        with patch.object(m.legacy.single.candidate,'simulate_dynamic_frozen_execution_research',side_effect=engine),patch.object(m.legacy.prefix,'runtime',side_effect=lambda:runtime):
            with self.assertRaisesRegex(ValueError,'runtime'):m.execute_delta(helper.auth,helper.folder,2)
        self.assertEqual(helper.engine_calls,['121'])
        self.assertTrue((helper.folder/'121/raw.json').exists())
        self.assertTrue((helper.folder/'121/failure.json').exists())
        self.assertFalse(list(helper.folder.glob('index_*.json')))


if __name__=='__main__':unittest.main()
