import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_ndx_historical_cross_k_candidate_accounts_20260923 as owner
from scripts import ndx_historical_cross_k_candidate_accounts_20260923 as m


class CandidateRunnerReview(unittest.TestCase):
    def fixture(self,skip=False):
        helper=owner.Tests();self.addCleanup(helper.doCleanups);return helper.setup_state(skip)

    def test_resigned_index_flags_and_remote_orphan_refuse_without_reexecution(self):
        folder,auth,prepared,engine=self.fixture()
        saved=m.run(folder=folder,max_new=1)['index_reference']
        baseline=json.loads(Path(saved['path']).read_bytes())
        for key,val in [('finalized_after_full_source_verification',1),('external_account_imported',True),('completed_account_task_count',True)]:
            bad=copy.deepcopy(baseline);bad[key]=val;path=folder/'index_forged.json';path.write_bytes(m.pack(bad))
            with self.subTest(key=key),self.assertRaises(ValueError):m.run(folder=folder,max_new=0,index_path=str(path),index_sha256=m.sha(path))
        (folder/'remote_attempt').mkdir()
        with self.assertRaisesRegex(ValueError,'Unindexed'):m.run(folder=folder,max_new=1,index_path=saved['path'],index_sha256=saved['sha256'])
        self.assertEqual(engine.call_count,1)

    def test_engine_changes_prepared_state_preserves_raw_and_never_finalizes(self):
        folder,auth,prepared,engine=self.fixture()
        def mutate(**kwargs):prepared['account']['contract']['transaction_cost_bps']=0;return {'original':'raw'}
        engine.side_effect=mutate
        with patch.object(m.single.control,'simulate_dynamic_frozen_incumbent_control',side_effect=AssertionError('control forbidden')) as control:
            with self.assertRaisesRegex(ValueError,'RAM'):m.run(folder=folder,max_new=1)
            control.assert_not_called()
        self.assertEqual(json.loads((folder/'job/raw.json').read_bytes())['execution'],{'original':'raw'})
        self.assertFalse((folder/'job/result.json').exists());self.assertEqual(list(folder.glob('index_*.json')),[])
        with self.assertRaisesRegex(ValueError,'Unindexed'):m.run(folder=folder,max_new=1)
        self.assertEqual(engine.call_count,1)

    def test_skipped_risk_resume_never_creates_raw_or_runs_account(self):
        folder,auth,prepared,engine=self.fixture(True)
        first=m.run(folder=folder,max_new=1)
        saved=json.loads((folder/'job/result.json').read_bytes())
        self.assertEqual(saved['status'],'SKIPPED_RISK');self.assertIs(saved['execution_performed'],False)
        self.assertIsNone(saved['raw_reference']);self.assertIsNone(saved['execution'])
        resumed=m.run(folder=folder,max_new=0,index_path=first['index_reference']['path'],index_sha256=first['index_reference']['sha256'])
        self.assertEqual(resumed['completed'],1);engine.assert_not_called()


if __name__=='__main__':unittest.main()
