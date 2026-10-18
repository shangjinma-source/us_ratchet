import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_cutoff_lane_dependency_research as core
import test_ndx_cutoff_lane_dependency_research as owner
from scripts import ndx_cutoff_lane_dependency_prepare_20260923 as cli


class LaneIndependentReview(unittest.TestCase):
    def resave(self,helper,folder,queue,frontier,complete):
        frontier['complete_date_artifact']=helper.save(folder,'complete.json',complete)
        diff=json.loads(Path(frontier['independent_full_diff_artifact']['path']).read_bytes())
        diff['output_sha256']=frontier['complete_date_artifact']['sha256']
        frontier['independent_full_diff_artifact']=helper.save(folder,'diff.json',diff)
        queue['frontier']=helper.save(folder,'frontier.json',frontier)
        return helper.save(folder,'queue.json',queue)

    def test_resigned_inner_window_metadata_must_match_context(self):
        helper=owner.LaneTests()
        for field,value in [('rolling_fit_window_count',999),('rolling_fit_window_count',True),
                            ('fit_strictly_before_evaluation',False),('fit_strictly_before_evaluation',1),
                            ('last_fit_evaluation_boundary','2023-04-04<2023-04-05')]:
            with self.subTest(field=field,value=value),tempfile.TemporaryDirectory() as folder:
                queue,_,frontier,complete=helper.fixture(folder)
                complete['records'][0]['result'][field]=value
                reference=self.resave(helper,folder,queue,frontier,complete)
                with self.assertRaises(ValueError):core.prepare_lanes([reference])

    def test_bound_diff_cannot_be_reassigned_to_another_overlay(self):
        helper=owner.LaneTests()
        with tempfile.TemporaryDirectory() as folder:
            queue,_,frontier,_=helper.fixture(folder)
            diff=json.loads(Path(frontier['independent_full_diff_artifact']['path']).read_bytes())
            diff['output_path']=str(Path(folder)/'other.json')
            frontier['independent_full_diff_artifact']=helper.save(folder,'diff.json',diff)
            queue['frontier']=helper.save(folder,'frontier.json',frontier)
            with self.assertRaises(ValueError):core.prepare_lanes([helper.save(folder,'queue.json',queue)])

    def test_nonfinite_or_bool_rank_metric_rejected(self):
        helper=owner.LaneTests()
        for value in (True,float('nan'),float('inf')):
            with self.subTest(value=value),tempfile.TemporaryDirectory() as folder:
                queue,_,frontier,complete=helper.fixture(folder)
                complete['records'][0]['result']['target_012922_distance']=value
                with self.assertRaises(ValueError):core.prepare_lanes([self.resave(helper,folder,queue,frontier,complete)])

    def test_non_equal_exact_window_metadata_and_corruption(self):
        helper=owner.LaneTests()
        for altered in (False,True):
            with self.subTest(altered=altered),tempfile.TemporaryDirectory() as folder:
                queue,_,frontier,complete=helper.fixture(folder)
                row=complete['records'][0]
                for target in (row['task'],row['result'],frontier['candidate_diagnostics'][0]):
                    target['weight_spec']='constrained_fixed_shrinkage'
                row['result'].update(rolling_fit_window_count=2,fit_strictly_before_evaluation=True,
                                     last_fit_evaluation_boundary='2023-03-30<2023-03-31')
                if altered:row['result']['rolling_fit_window_count']=3
                ref=self.resave(helper,folder,queue,frontier,complete)
                if altered:
                    with self.assertRaises(ValueError):core.prepare_lanes([ref])
                else:
                    result=core.prepare_lanes([ref])
                    self.assertTrue(result['decisions'][0]['lanes']['RETURN'][0]['saved_fit_window_metadata_verified'])

    def test_loaded_source_change_blocks_cli_before_preparation(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.py';source.write_text('modified')
            with patch.object(cli,'LOADED_SOURCES',{str(source):'0'*64}),patch.object(core,'prepare_lanes') as prepare:
                with self.assertRaises(ValueError):cli.run(['unused'],['0'*64],str(Path(folder)/'out.json'))
                prepare.assert_not_called()

    def test_empty_first_lane_cannot_become_reachable_later(self):
        dates=[('2023-04-03','2023-03-31'),('2023-05-01','2023-04-28'),('2023-06-01','2023-05-31')]
        choice=dict(job_id='a',selected={'sid-a':dict(issuer_id='issuer-a')})
        decisions=[dict(execution_date=execution,cutoff=cutoff,
            lanes={role:[] if position==0 else [choice] for role in core.ORDERS})
            for position,(execution,cutoff) in enumerate(dates)]
        with patch.object(core,'prepare_decision',side_effect=decisions):
            result=core.prepare_lanes([{}, {}, {}])
        self.assertTrue(result['dependencies'])
        self.assertTrue(all(row['dependency_status'].startswith('BLOCKED') for row in result['dependencies']))


if __name__=='__main__':unittest.main()
