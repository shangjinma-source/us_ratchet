from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_delta_three_cell_paired_v2_probe_research as runner


class GapPlanTests(unittest.TestCase):
    def test_plan_cannot_upgrade_research_flags(self):
        parent=dict(dates=[])
        plan=dict(schema='ndx_delta_three_cell_paired_gap_plan_v2',parent_plan_sha256=runner.PARENT_SHA,
            parent_plan_path=str(runner.PARENT_PLAN),planned=614,dates=[],errors=runner.prior.ERRORS,
            reconstruction_scope=runner.SCOPE,original_historical_provenance_verified=False,
            point_in_time_verified=False,promotion_allowed=False,historical_training_performed=False)
        for flag in ('original_historical_provenance_verified','point_in_time_verified','promotion_allowed','historical_training_performed'):
            changed=dict(plan,**{flag:True})
            with patch.object(runner.prior.original,'read',return_value=changed),patch.object(runner.prior,'load_plan',return_value=parent):
                with self.assertRaisesRegex(ValueError,'limited numerical reconstruction'):runner.load_plan('unused','0'*64)

    def test_real_parent_614_tasks_and_67_gap_pointers_read_only(self):
        parent=runner.prior.original.read(runner.PARENT_PLAN,runner.PARENT_SHA)
        dates=runner.projected_dates(parent)
        self.assertEqual(sum(len(day['tasks']) for day in dates),614)
        refs={row['context_path']:row['context_sha256'] for day in dates for row in day['tasks']}
        self.assertEqual(len(refs),67)
        for path,sha in refs.items():
            context=runner.prior.original.read(path,sha)
            gaps=runner.adapter.validate_historical_evidence(context,parent['source_hashes'])
            self.assertEqual(len(gaps),1);self.assertEqual(gaps[0]['expected_historical_sha256'],runner.adapter.GAP_EXPECTED_SHA)
        for old,new in zip(parent['dates'],dates):
            for a,b in zip(old['tasks'],new['tasks']):
                self.assertEqual(a['task'],b['task']);self.assertNotEqual(a['new_job_id'],b['new_job_id'])

    def test_existing_probe_refuses_before_any_old_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'probe';path.write_text('already published')
            with patch.object(runner.adapter,'recover_paired_delta') as evaluator:
                with self.assertRaises(FileExistsError):runner.run_first_probe(plan_path='missing',plan_sha256='0'*64,output=path)
                evaluator.assert_not_called()

    def test_gap_observation_change_is_not_silently_resigned(self):
        parent=runner.prior.original.read(runner.PARENT_PLAN,runner.PARENT_SHA);row=parent['dates'][0]['tasks'][0]
        context=runner.prior.original.read(row['context_path'],row['context_sha256'])
        gaps=runner.adapter.validate_historical_evidence(context,parent['source_hashes']);bad=deepcopy(gaps)
        bad[0]['observed_current_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'observation changed'):
            runner.verify_observations({row['context_path']:dict(context_sha256=row['context_sha256'],gaps=bad)},parent['source_hashes'])
